"""
ai_extractor.py
===============
Ekstrakcija podataka iz PDF faktura pomoću GPT modela.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from PIL import Image
from pdf2image import convert_from_bytes

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    import pdfplumber
except Exception:
    pdfplumber = None

load_dotenv(Path(__file__).parent / ".env")

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

    @field_validator("BROJFAKT")
    @classmethod
    def normalize_bill_number(cls, v: str) -> str:
        s = re.sub(r"\s+", " ", str(v or "")).strip()
        if not s:
            return ""
        digits = re.sub(r"\D", "", s)
        if re.fullmatch(r"\d{8}", digits) and digits[-4:].startswith("20"):
            return f"{digits[:-4]}/{digits[-4:]}"
        m = re.search(r"(\d{3,6})\s*/\s*(20\d{2})", s)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        return s

    @field_validator("DATUMF", "DATUMPF")
    @classmethod
    def normalize_date(cls, v: str) -> str:
        s = re.sub(r"\s+", " ", str(v or "")).strip()
        if not s:
            return ""
        s = s.replace("/", ".").replace("-", ".")
        m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
        if not m:
            return s
        d, mo, y = m.groups()
        return f"{int(d):02d}.{int(mo):02d}.{y}"

    @field_validator("NAZIVPP", "SJEDISTEPP")
    @classmethod
    def clean_text(cls, v: str) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()

    @field_validator("IDPDVPP")
    @classmethod
    def normalize_idpdvpp(cls, v: str) -> str:
        s = str(v or "").strip()
        if not s:
            return ""
        d = re.sub(r"\D", "", s)
        if len(d) == 12:
            d = "4" + d
        elif len(d) == 13 and not d.startswith("4"):
            d = "4" + d[1:]
        return d if len(d) == 13 and d.startswith("4") else s

    @field_validator("JIBPUPP")
    @classmethod
    def normalize_jibpupp(cls, v: str) -> str:
        s = str(v or "").strip()
        if not s:
            return ""
        d = re.sub(r"\D", "", s)
        if len(d) == 13 and d.startswith("4"):
            d = d[1:]
        return d if len(d) == 12 else s

    @field_validator("IZNBEZPDV", "IZNSAPDV", "IZNPDV")
    @classmethod
    def normalize_amount(cls, v: str) -> str:
        s = str(v or "").strip()
        if not s:
            return ""
        s = s.replace("\xa0", " ").replace("KM", "").replace("BAM", "").replace(" ", "")
        if re.match(r"^\d{1,3}(\.\d{3})+(,\d{1,2})?$", s):
            s = s.replace(".", "").replace(",", ".")
        elif re.match(r"^\d{1,3}(,\d{3})+(\.\d{1,2})?$", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
        try:
            return f"{float(s):.2f}"
        except Exception:
            return str(v or "").strip()

    def to_dict(self) -> dict[str, str]:
        return {f: getattr(self, f, "") for f in FIELDS}


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
- Ako postoji više iznosa ili više stopa PDV-a, vrati ukupni zbir za taj račun.
- Iznose vrati samo kao broj, bez valute, sa decimalnom tačkom.
- DATUMF i DATUMPF vrati u formatu DD.MM.GGGG ako su vidljivi.
- DOBAVLJAČ je izdavalac računa; kupca, primaoca, mjesto isporuke i adresu kupca ignoriši.
- NAZIVPP, SJEDISTEPP, IDPDVPP i JIBPUPP uzimaj ISKLJUČIVO iz zaglavlja izdavaoca, pored loga/naziva firme i registracionih podataka.
- Nikada ne uzimaj naziv, adresu, ID ili PDV broj kupca za polja dobavljača.
- Ako je prisutan samo jedan identifikacioni broj dobavljača, popuni IDPDVPP po pravilu 13 cifara; JIBPUPP popuni samo ako je na dokumentu jasno naveden PDV/PIB broj ili se pouzdano može dobiti skidanjem vodeće cifre 4 iz istog ID broja dobavljača.
- Za DATUMF koristi samo datum označen kao Datum računa / Datum fakture / Datum izdavanja. Ne koristi datum isporuke kao DATUMF.
- Za DATUMPF koristi samo poseban datum prijema/evidentiranja ako je jasno odvojen od DATUMF; inače vrati "".

Logika po dokumentu:
1. Prvo pronađi BROJFAKT.
2. Zatim sve ostale podatke traži samo unutar istog bloka tog računa.
3. IZNBEZPDV, IZNPDV i IZNSAPDV uzimaj isključivo iz završnog total bloka tog istog računa: "Ukupno bez PDV-a", "Ukupno PDV", "UKUPAN IZNOS ZA NAPLATU".
4. Ako nova strana počne sa drugim "RAČUN - OTPREMNICA broj" ili drugim brojem računa, to je novi račun i totals se ne smiju miješati.
5. Ako se isti BROJFAKT pojavljuje na više strana, to je JEDAN račun. Spoji te strane u jedan rezultat i uzmi završne totale sa zadnje strane istog računa.
6. Ako isti dobavljač očigledno izdaje sve račune u PDF-u, polja NAZIVPP, SJEDISTEPP, IDPDVPP i JIBPUPP moraju ostati dosljedna kroz sve rezultate.

Kontrolne provjere:
- Ako više različitih računa imaju identične iznose, provjeri da li si slučajno preuzeo totals sa susjednog računa.
- Ako se NAZIVPP ponavlja, a SJEDISTEPP ili identifikacioni brojevi se mijenjaju između računa u istom PDF-u, vjerovatno si uzeo podatke kupca umjesto dobavljača.
- Ako IZNBEZPDV + IZNPDV nije približno jednako IZNSAPDV, potraži drugi total blok za isti račun.
"""


def _active_model(default: str = "gpt-4o") -> str:
    return st.session_state.get("selected_model", default)


def _get_api_key() -> str:
    key = st.session_state.get("openai_api_key", "")
    if key:
        return key
    try:
        if hasattr(st, "secrets"):
            return st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY", "")


def _get_client() -> OpenAI:
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY nije postavljen")
    return OpenAI(api_key=api_key)


def _extract_text_pymupdf(pdf_bytes: bytes) -> str:
    if fitz is None:
        return ""
    try:
        out: list[str] = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            out.append(page.get_text("text") or "")
        return "\n".join(out)
    except Exception:
        return ""


def _extract_text_pdfplumber(pdf_bytes: bytes) -> str:
    if pdfplumber is None:
        return ""
    try:
        out: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                out.append(page.extract_text() or "")
        return "\n".join(out)
    except Exception:
        return ""


def _extract_text(pdf_bytes: bytes) -> str:
    t1 = _extract_text_pymupdf(pdf_bytes)
    t2 = _extract_text_pdfplumber(pdf_bytes)
    text = t1 if len(re.sub(r"\s+", "", t1)) >= len(re.sub(r"\s+", "", t2)) else t2
    return re.sub(r"\s+", " ", text).strip()


def _is_text_pdf(text: str) -> bool:
    return len(re.sub(r"\s+", "", text or "")) >= _MIN_TEXT_CHARS


def _pdf_to_b64_images(pdf_bytes: bytes) -> list[str]:
    pages = convert_from_bytes(pdf_bytes, dpi=_DPI, fmt="jpeg")
    result: list[str] = []
    for img in pages:
        img = img.convert("RGB")
        w, h = img.size
        ratio = min(_MAX_IMG_WIDTH / max(w, 1), _MAX_IMG_HEIGHT / max(h, 1), 1.0)
        if ratio < 1.0:
            img = img.resize((int(w * ratio), int(h * ratio)))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
        result.append(base64.b64encode(buf.getvalue()).decode())
    return result


def _combine_images(b64_pages: list[str]) -> str:
    images = [Image.open(io.BytesIO(base64.b64decode(x))).convert("RGB") for x in b64_pages]
    width = max(img.width for img in images)
    height = sum(img.height for img in images)
    canvas = Image.new("RGB", (width, height), color=(255, 255, 255))
    y = 0
    for img in images:
        canvas.paste(img, (0, y))
        y += img.height
    if canvas.height > _MAX_IMG_HEIGHT:
        ratio = _MAX_IMG_HEIGHT / canvas.height
        canvas = canvas.resize((int(canvas.width * ratio), _MAX_IMG_HEIGHT))
    if canvas.width > _MAX_IMG_WIDTH:
        ratio = _MAX_IMG_WIDTH / canvas.width
        canvas = canvas.resize((_MAX_IMG_WIDTH, int(canvas.height * ratio)))
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode()


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
                        "Dobavljač se uzima samo iz zaglavlja izdavaoca; kupca ignoriši. "
                        "Totals veži samo za isti broj računa, a isti broj računa na više strana spoji u jedan rezultat. "
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
                            "type": "text",
                            "text": (
                                f"Fajl: {filename}\n\n"
                                "Prouči sliku dokumenta i vrati JSON array za sve pronađene dokumente. "
                                "Koristi ISKLJUČIVO ono što se vidi na slici. "
                                "Dobavljač se uzima samo iz zaglavlja izdavaoca; kupca ignoriši. "
                                "Totals veži samo za isti broj računa, a isti broj računa na više strana spoji u jedan rezultat. "
                                "NE koristi naziv fajla kao izvor podataka."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
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
    merged = _merge_duplicate_invoices(all_items)
    return merged or [_error_invoice(filename, "Nema rezultata")]


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


def _merge_duplicate_invoices(items: list[InvoiceData]) -> list[InvoiceData]:
    merged_by_number: dict[str, InvoiceData] = {}
    remainder: list[InvoiceData] = []
    for inv in items:
        broj = (inv.BROJFAKT or "").strip()
        if not broj:
            remainder.append(inv)
            continue
        if broj not in merged_by_number:
            merged_by_number[broj] = inv
            continue
        merged_by_number[broj] = _merge_invoice_pair(merged_by_number[broj], inv)
    ordered = list(merged_by_number.values())
    ordered.extend(remainder)
    return _harmonize_supplier_fields(ordered)


def _merge_invoice_pair(a: InvoiceData, b: InvoiceData) -> InvoiceData:
    merged = InvoiceData()
    text_fields = ["BROJFAKT", "DATUMF", "DATUMPF", "NAZIVPP", "SJEDISTEPP", "IDPDVPP", "JIBPUPP"]
    amount_fields = ["IZNBEZPDV", "IZNSAPDV", "IZNPDV"]

    for field in text_fields:
        setattr(merged, field, _prefer_text_value(getattr(a, field, "") or "", getattr(b, field, "") or ""))
    for field in amount_fields:
        setattr(merged, field, _prefer_amount_value(getattr(a, field, "") or "", getattr(b, field, "") or ""))

    merged._filename = a._filename or b._filename
    merged._warnings = list(dict.fromkeys((a._warnings or []) + (b._warnings or [])))
    merged._warnings = list(dict.fromkeys(merged._warnings + _validate(merged)))
    merged._valid = len(merged._warnings) == 0
    return merged


def _prefer_text_value(a: str, b: str) -> str:
    a = (a or "").strip()
    b = (b or "").strip()
    if a and not b:
        return a
    if b and not a:
        return b
    if not a and not b:
        return ""
    a_digits = len(re.sub(r"\D", "", a))
    b_digits = len(re.sub(r"\D", "", b))
    if a_digits != b_digits and max(a_digits, b_digits) >= 8:
        return a if a_digits > b_digits else b
    return a if len(a) >= len(b) else b


def _prefer_amount_value(a: str, b: str) -> str:
    a = (a or "").strip()
    b = (b or "").strip()
    if a and not b:
        return a
    if b and not a:
        return b
    if not a and not b:
        return ""
    try:
        return f"{max(float(a), float(b)):.2f}"
    except Exception:
        return a if len(a) >= len(b) else b


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

    results = _harmonize_supplier_fields(results)
    return results or [_error_invoice(filename, "Nema rezultata")]


def _harmonize_supplier_fields(items: list[InvoiceData]) -> list[InvoiceData]:
    if len(items) < 2:
        return items

    valid = [x for x in items if any([x.NAZIVPP, x.SJEDISTEPP, x.IDPDVPP, x.JIBPUPP])]
    if len(valid) < 2:
        return items

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip().lower()

    supplier_name_counts: dict[str, int] = {}
    for inv in valid:
        name = norm(inv.NAZIVPP)
        if name:
            supplier_name_counts[name] = supplier_name_counts.get(name, 0) + 1

    if not supplier_name_counts:
        return items

    top_name, top_name_count = max(supplier_name_counts.items(), key=lambda kv: kv[1])
    if top_name_count < max(2, int(len(valid) * 0.6)):
        return items

    same_name = [x for x in valid if norm(x.NAZIVPP) == top_name or not norm(x.NAZIVPP)]

    def most_common(values: list[str]) -> str:
        counts: dict[str, int] = {}
        original: dict[str, str] = {}
        for v in values:
            vv = (v or "").strip()
            if not vv:
                continue
            k = norm(vv)
            counts[k] = counts.get(k, 0) + 1
            original.setdefault(k, vv)
        if not counts:
            return ""
        k = max(counts.items(), key=lambda kv: kv[1])[0]
        return original[k]

    canonical_name = most_common([x.NAZIVPP for x in same_name])
    canonical_addr = most_common([x.SJEDISTEPP for x in same_name])
    canonical_id = most_common([x.IDPDVPP for x in same_name])
    canonical_pdv = most_common([x.JIBPUPP for x in same_name])

    for inv in items:
        if norm(inv.NAZIVPP) == top_name or not norm(inv.NAZIVPP):
            if canonical_name:
                inv.NAZIVPP = canonical_name
            if canonical_addr:
                inv.SJEDISTEPP = canonical_addr
            if canonical_id:
                inv.IDPDVPP = canonical_id
            if canonical_pdv:
                inv.JIBPUPP = canonical_pdv
            inv._warnings = _validate(inv)
            inv._valid = len(inv._warnings) == 0
    return items


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


def _error_invoice(filename: str, msg: str) -> InvoiceData:
    inv = InvoiceData()
    inv._filename = filename
    inv._valid = False
    inv._warnings = [msg]
    return inv


def get_available_models() -> list[str]:
    return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
