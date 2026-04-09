"""
ai_extractor.py
===============
Ekstrakcija podataka s PDF faktura pomoću OpenAI GPT-4o.

Podržava:
- tekstualne PDF-ove (PyMuPDF / pdfplumber)
- skenirane PDF-ove (pdf2image + GPT Vision)
- više dokumenata u jednom PDF-u
"""

from __future__ import annotations

import base64
import html
import io
import json
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv(Path(__file__).parent / ".env")


# ─────────────────────────────────────────────────────────────────────────────
# Konstante
# ─────────────────────────────────────────────────────────────────────────────

FIELDS = [
    "BROJFAKT",
    "DATUMF",
    "DATUMPF",
    "NAZIVPP",
    "SJEDISTEPP",
    "IDPDVPP",
    "JIBPUPP",
    "IZNBEZPDV",
    "IZNSAPDV",
    "IZNPDV",
]

_MIN_TEXT_CHARS = 100
_DPI = 200
_JPEG_QUALITY = 92
_MAX_IMG_HEIGHT = 8000
_MAX_IMG_WIDTH = 3000
_VISION_BATCH = 4


# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────

class InvoiceData(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    BROJFAKT: str = Field(default="")
    DATUMF: str = Field(default="")
    DATUMPF: str = Field(default="")
    NAZIVPP: str = Field(default="")
    SJEDISTEPP: str = Field(default="")
    IDPDVPP: str = Field(default="")
    JIBPUPP: str = Field(default="")
    IZNBEZPDV: str = Field(default="")
    IZNSAPDV: str = Field(default="")
    IZNPDV: str = Field(default="")

    _filename: str = ""
    _valid: bool = True
    _warnings: list[str] = []

    @field_validator("BROJFAKT", "DATUMF", "DATUMPF", "NAZIVPP", "SJEDISTEPP")
    @classmethod
    def clean_text(cls, v: str) -> str:
        if not v:
            return ""
        return re.sub(r"\s+", " ", str(v)).strip()

    @field_validator("IDPDVPP")
    @classmethod
    def normalize_idpdvpp(cls, v: str) -> str:
        if not v:
            return ""
        d = re.sub(r"\D", "", str(v))
        if len(d) == 12:
            d = "4" + d
        elif len(d) == 13 and not d.startswith("4"):
            d = "4" + d[1:]
        return d if len(d) == 13 and d.startswith("4") else str(v).strip()

    @field_validator("JIBPUPP")
    @classmethod
    def normalize_jibpupp(cls, v: str) -> str:
        if not v:
            return ""
        d = re.sub(r"\D", "", str(v))
        if len(d) == 13 and d.startswith("4"):
            d = d[1:]
        return d if len(d) == 12 else str(v).strip()

    @field_validator("IZNBEZPDV", "IZNSAPDV", "IZNPDV")
    @classmethod
    def normalize_amount(cls, v: str) -> str:
        if v in (None, ""):
            return ""
        s = str(v).strip()
        s = s.replace("\xa0", " ").replace("KM", "").replace("BAM", "")
        s = s.replace(" ", "")
        if re.match(r"^\d{1,3}(\.\d{3})+(,\d{1,2})?$", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            return f"{float(s):.2f}"
        except Exception:
            return str(v).strip()

    def to_dict(self) -> dict[str, str]:
        return {f: getattr(self, f, "") for f in FIELDS}


# ─────────────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """
Ti si ekspert za ekstrakciju podataka sa faktura i računa iz Bosne i Hercegovine i regiona.

Tvoj zadatak je da iz dokumenta izvučeš podatke i vratiš ISKLJUČIVO validan JSON array.
Ne piši objašnjenja, uvod, napomene ni markdown osim čistog JSON-a.

PDF može sadržavati jedan ili više dokumenata. Za SVAKI dokument vrati jedan JSON objekt.
Ako neko polje ne postoji ili nije jasno vidljivo, upiši prazan string "".

Ključevi MORAJU biti TAČNO ovi:

{
  "BROJFAKT": "Broj računa/fakture (npr. 432/10, 9034508513, 600398-1-0126-1)",
  "DATUMF": "Datum izdavanja fakture (format DD.MM.GGGG)",
  "DATUMPF": "Datum prijema fakture — ako postoji poseban datum prijema/evidentiranja, upiši ga (format DD.MM.GGGG). Ako ne postoji, ostavi prazan string",
  "NAZIVPP": "Puni naziv DOBAVLJAČA — firma KOJA JE IZDALA račun (čiji je logo/zaglavlje). To je firma koja ŠALJE račun, NE firma koja ga prima!",
  "SJEDISTEPP": "Puna adresa dobavljača sa poštanskim brojem i mjestom",
  "IDPDVPP": "ID broj (JIB) dobavljača - MORA biti TAČNO 13 cifara i počinjati sa 4. Ako na računu vidiš broj koji nema 13 cifara ili ne počinje sa 4, dodaj vodeću 4 da bude 13 cifara",
  "JIBPUPP": "PDV broj dobavljača - MORA biti TAČNO 12 cifara. To je isti broj kao ID/JIB ali BEZ vodeće cifre 4. Ako dobavljač NIJE u PDV sistemu (nema PDV broj na računu), ostavi prazan string",
  "IZNBEZPDV": "Iznos BEZ PDV-a (decimalni separator tačka, npr. 155.87)",
  "IZNSAPDV": "UKUPAN iznos za uplatu SA PDV-om (npr. 182.37)",
  "IZNPDV": "Iznos PDV-a u KM (NE procenat, nego koliko PDV iznosi u novcu, npr. 26.50)"
}

Pravila:
- Čitaj ISKLJUČIVO ono što je eksplicitno vidljivo u dokumentu ili tekstu.
- NE izmišljaj podatke.
- NE koristi naziv fajla kao izvor podataka.
- Ako postoji više iznosa ili više stopa PDV-a, vrati ukupni zbir za dokument.
- Iznose vrati samo kao broj, bez valute, sa decimalnom tačkom.
- DATUMF i DATUMPF vrati u formatu DD.MM.GGGG ako su vidljivi.
- DOBAVLJAČ je izdavalac računa; kupca ignoriši.
- Ako je prisutan samo jedan identifikacioni broj dobavljača, popuni IDPDVPP po pravilu 13 cifara; JIBPUPP popuni samo ako je na dokumentu jasno naveden PDV/PIB broj ili se pouzdano može dobiti skidanjem vodeće 4 iz istog broja.

Vrati isključivo JSON array, npr.:
[
  {
    "BROJFAKT": "",
    "DATUMF": "",
    "DATUMPF": "",
    "NAZIVPP": "",
    "SJEDISTEPP": "",
    "IDPDVPP": "",
    "JIBPUPP": "",
    "IZNBEZPDV": "",
    "IZNSAPDV": "",
    "IZNPDV": ""
  }
]
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI
# ─────────────────────────────────────────────────────────────────────────────

def _get_client():
    from openai import OpenAI

    key = (
        st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
    ) or os.getenv("OPENAI_API_KEY", "")

    if not key:
        raise ValueError("OPENAI_API_KEY nije postavljen")

    return OpenAI(api_key=key)


def _active_model(default: str = "gpt-4o") -> str:
    return st.session_state.get("selected_model", default)


# ─────────────────────────────────────────────────────────────────────────────
# Ekstrakcija teksta
# ─────────────────────────────────────────────────────────────────────────────

def _extract_text(pdf_bytes: bytes) -> str:
    text = _extract_text_pymupdf(pdf_bytes)
    if _is_text_pdf(text):
        return text

    text = _extract_text_pdfplumber(pdf_bytes)
    if _is_text_pdf(text):
        return text

    return ""


def _extract_text_pymupdf(pdf_bytes: bytes) -> str:
    try:
        import fitz

        parts = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text = page.get_text("text") or ""
                if len(re.sub(r"\s+", "", text)) > 10:
                    parts.append(text.strip())
                    continue

                html_text = page.get_text("html") or ""
                if html_text:
                    html_text = re.sub(r"<img[^>]*>", " ", html_text, flags=re.IGNORECASE)
                    html_text = re.sub(r"<[^>]+>", " ", html_text)
                    html_text = html.unescape(html_text)
                    html_text = re.sub(r"\s+", " ", html_text).strip()
                    if len(re.sub(r"\s+", "", html_text)) > 10:
                        parts.append(html_text)

        return "\n\n--- NOVA STRANICA ---\n\n".join(parts)
    except Exception:
        return ""


def _extract_text_pdfplumber(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber

        parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if text and text.strip():
                    parts.append(text.strip())

        return "\n\n--- NOVA STRANICA ---\n\n".join(parts)
    except Exception:
        return ""


def _is_text_pdf(text: str) -> bool:
    return len(re.sub(r"\s+", "", text or "")) >= _MIN_TEXT_CHARS


# ─────────────────────────────────────────────────────────────────────────────
# PDF → slike
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_to_b64_images(pdf_bytes: bytes) -> list[str]:
    from pdf2image import convert_from_bytes
    from PIL import Image

    pages = convert_from_bytes(pdf_bytes, dpi=_DPI)
    results = []

    for page in pages:
        w, h = page.size
        if h > _MAX_IMG_HEIGHT or w > _MAX_IMG_WIDTH:
            ratio = min(_MAX_IMG_WIDTH / w, _MAX_IMG_HEIGHT / h)
            page = page.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        page.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY)
        results.append(base64.b64encode(buf.getvalue()).decode())

    return results


def _combine_images(b64_list: list[str]) -> str:
    from PIL import Image

    images = [Image.open(io.BytesIO(base64.b64decode(b))) for b in b64_list]
    max_w = max(img.width for img in images)
    total_h = sum(img.height for img in images)

    if total_h > _MAX_IMG_HEIGHT:
        ratio = _MAX_IMG_HEIGHT / total_h
        images = [
            img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            for img in images
        ]
        max_w = max(img.width for img in images)
        total_h = sum(img.height for img in images)

    combined = Image.new("RGB", (max_w, total_h), (255, 255, 255))
    y = 0
    for img in images:
        combined.paste(img, (0, y))
        y += img.height

    buf = io.BytesIO()
    combined.save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode()


# ─────────────────────────────────────────────────────────────────────────────
# GPT pozivi
# ─────────────────────────────────────────────────────────────────────────────

def _extract_via_text(text: str, filename: str) -> list[InvoiceData]:
    client = _get_client()
    model = _active_model()

    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Fajl: {filename}\n\n"
                        "Ispod je tekst iz PDF dokumenta. Koristi ISKLJUČIVO podatke koji se vide u tekstu. "
                        "NE izmišljaj i NE koristi naziv fajla kao izvor podataka. "
                        "Vrati JSON array za sve pronađene dokumente.\n\n"
                        f"TEKST DOKUMENTA:\n{text}"
                    ),
                },
            ],
        )
        return _parse_response(resp.choices[0].message.content.strip(), filename)
    except Exception as e:
        return [_error_invoice(filename, str(e))]


def _extract_via_vision(b64_image: str, filename: str) -> list[InvoiceData]:
    client = _get_client()
    model = _active_model()

    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Fajl: {filename}\n\n"
                                "Ovo je skenirana slika dokumenta. Čitaj ISKLJUČIVO ono što je fizički vidljivo na slici. "
                                "NE izmišljaj, NE pretpostavljaj i NE koristi naziv fajla kao izvor podataka. "
                                "Ako neko polje nije jasno vidljivo, ostavi prazan string. "
                                "Vrati JSON array za sve dokumente koji se vide na slici."
                            ),
                        },
                    ],
                },
            ],
        )
        return _parse_response(resp.choices[0].message.content.strip(), filename)
    except Exception as e:
        return [_error_invoice(filename, str(e))]


def _extract_via_vision_batched(b64_pages: list[str], filename: str) -> list[InvoiceData]:
    all_items: list[InvoiceData] = []
    total = len(b64_pages)

    for start in range(0, total, _VISION_BATCH):
        batch = b64_pages[start:start + _VISION_BATCH]
        end = min(start + _VISION_BATCH, total)
        label = f"{filename} [str.{start + 1}-{end}/{total}]"
        image = _combine_images(batch) if len(batch) > 1 else batch[0]
        all_items.extend(_extract_via_vision(image, label))

    unique: list[InvoiceData] = []
    seen: set[tuple[str, str, str]] = set()
    for inv in all_items:
        key = (
            inv.BROJFAKT.strip(),
            inv.DATUMF.strip(),
            inv.IZNSAPDV.strip(),
        )
        if any(key) and key in seen:
            continue
        if any(key):
            seen.add(key)
        unique.append(inv)

    return unique or [_error_invoice(filename, "Nema rezultata")]


# ─────────────────────────────────────────────────────────────────────────────
# Javna funkcija
# ─────────────────────────────────────────────────────────────────────────────

def extract_invoices_from_pdf(pdf_bytes: bytes, filename: str = "") -> list[InvoiceData]:
    text = _extract_text(pdf_bytes)
    if _is_text_pdf(text):
        return _extract_via_text(text, filename)

    try:
        pages = _pdf_to_b64_images(pdf_bytes)
    except Exception as e:
        return [_error_invoice(filename, f"Greška pri konverziji PDF→slika: {e}")]

    if not pages:
        return [_error_invoice(filename, "PDF nema stranica")]

    if len(pages) == 1:
        return _extract_via_vision(pages[0], filename)

    return _extract_via_vision_batched(pages, filename)


# ─────────────────────────────────────────────────────────────────────────────
# Parsiranje
# ─────────────────────────────────────────────────────────────────────────────

def _parse_response(raw: str, filename: str) -> list[InvoiceData]:
    if not raw:
        return [_error_invoice(filename, "Prazan odgovor modela")]

    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()

    if raw.startswith("Na osnovu") or raw.startswith("Evo"):
        m2 = re.search(r"(\[[\s\S]+\]|\{[\s\S]+\})", raw)
        if m2:
            raw = m2.group(1).strip()

    try:
        data = json.loads(raw)
    except Exception:
        m3 = re.search(r"(\[[\s\S]+\]|\{[\s\S]+\})", raw)
        if not m3:
            return [_error_invoice(filename, f"JSON parse greška: {raw[:300]}")]
        try:
            data = json.loads(m3.group(1))
        except Exception:
            return [_error_invoice(filename, f"JSON parse greška: {raw[:300]}")]

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list) or not data:
        return [_error_invoice(filename, "Model nije vratio validan JSON array")]

    results: list[InvoiceData] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue

        payload = {field: str(item.get(field, "") or "").strip() for field in FIELDS}

        try:
            inv = InvoiceData(**payload)
            inv._filename = f"{filename} [{i}/{len(data)}]" if len(data) > 1 else filename
            inv._warnings = _validate(inv)
            inv._valid = len(inv._warnings) == 0
            results.append(inv)
        except Exception as e:
            results.append(_error_invoice(filename, str(e)))

    return results or [_error_invoice(filename, "Nema rezultata")]


# ─────────────────────────────────────────────────────────────────────────────
# Validacija
# ─────────────────────────────────────────────────────────────────────────────

def _validate(inv: InvoiceData) -> list[str]:
    warnings: list[str] = []

    if not inv.BROJFAKT:
        warnings.append("BROJFAKT nije pronađen")
    if not inv.DATUMF:
        warnings.append("DATUMF nije pronađen")
    if not inv.NAZIVPP:
        warnings.append("NAZIVPP nije pronađen")
    if not inv.IZNSAPDV:
        warnings.append("IZNSAPDV nije pronađen")

    if inv.IDPDVPP:
        digits = re.sub(r"\D", "", inv.IDPDVPP)
        if len(digits) != 13 or not digits.startswith("4"):
            warnings.append(f"IDPDVPP nije validan: {inv.IDPDVPP}")

    if inv.JIBPUPP:
        digits = re.sub(r"\D", "", inv.JIBPUPP)
        if len(digits) != 12:
            warnings.append(f"JIBPUPP nije validan: {inv.JIBPUPP}")

    try:
        if inv.IDPDVPP and inv.JIBPUPP:
            id_d = re.sub(r"\D", "", inv.IDPDVPP)
            pdv_d = re.sub(r"\D", "", inv.JIBPUPP)
            if len(id_d) == 13 and len(pdv_d) == 12 and id_d[1:] != pdv_d:
                warnings.append("IDPDVPP i JIBPUPP nisu međusobno usklađeni")
    except Exception:
        pass

    try:
        if inv.IZNBEZPDV and inv.IZNPDV and inv.IZNSAPDV:
            bez = float(inv.IZNBEZPDV)
            pdv = float(inv.IZNPDV)
            sa = float(inv.IZNSAPDV)
            if abs((bez + pdv) - sa) > 0.06:
                warnings.append(f"Iznosi nisu usklađeni: {bez:.2f} + {pdv:.2f} != {sa:.2f}")
    except Exception:
        warnings.append("Jedan ili više iznosa nisu numerički")

    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# Pomoćne
# ─────────────────────────────────────────────────────────────────────────────

def _error_invoice(filename: str, msg: str) -> InvoiceData:
    inv = InvoiceData()
    inv._filename = filename
    inv._valid = False
    inv._warnings = [msg]
    return inv


def get_available_models() -> list[str]:
    return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
