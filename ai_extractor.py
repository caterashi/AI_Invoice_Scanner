"""
ai_extractor.py
===============
AI ekstrakcija podataka s faktura koristeći OpenAI GPT-4o.

PDF fajlovi se obrađuju na dva načina:
  1. Tekstualni PDF  (ima OCR sloj) → tekst se šalje direktno GPT-4o
  2. Slikovni PDF    (skenirana slika) → stranice → slike → GPT-4o Vision

Oba tipa podržavaju više dokumenata u jednom PDF-u.
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
from pydantic import BaseModel, Field, field_validator

load_dotenv(Path(__file__).parent / ".env")


# ─────────────────────────────────────────────────────────────────────────────
# Konstante
# ─────────────────────────────────────────────────────────────────────────────

FIELDS = [
    "BROJFAKT", "DATUMF", "DATUMPF",
    "NAZIVPP", "SJEDISTEPP",
    "IDPDVPP", "JIBPUPP",
    "IZNBEZPDV", "IZNPDV", "IZNSAPDV",
]

_MIN_TEXT_CHARS = 100
_MAX_IMG_HEIGHT = 8000
_MAX_IMG_WIDTH  = 3000
_DPI            = 200
_JPEG_QUALITY   = 92


# ─────────────────────────────────────────────────────────────────────────────
# Model podataka
# ─────────────────────────────────────────────────────────────────────────────

class InvoiceData(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    BROJFAKT:   str = Field(default="")
    DATUMF:     str = Field(default="")
    DATUMPF:    str = Field(default="")
    NAZIVPP:    str = Field(default="")
    SJEDISTEPP: str = Field(default="")
    IDPDVPP:    str = Field(default="")
    JIBPUPP:    str = Field(default="")
    IZNBEZPDV:  str = Field(default="")
    IZNPDV:     str = Field(default="")
    IZNSAPDV:   str = Field(default="")

    # Interni metapodaci — ne idu u Excel
    _filename: str  = ""
    _valid:    bool = True
    _warnings: list = []

    @field_validator("IDPDVPP")
    @classmethod
    def fix_id(cls, v: str) -> str:
        if not v:
            return v
        d = re.sub(r"\D", "", v)
        if len(d) == 12:
            d = "4" + d
        elif len(d) == 13 and not d.startswith("4"):
            d = "4" + d[1:]
        return d if len(d) == 13 else v

    @field_validator("JIBPUPP")
    @classmethod
    def fix_jib(cls, v: str) -> str:
        if not v:
            return v
        d = re.sub(r"\D", "", v)
        if len(d) == 13 and d.startswith("4"):
            d = d[1:]
        return d if len(d) == 12 else v

    @field_validator("IZNBEZPDV", "IZNPDV", "IZNSAPDV")
    @classmethod
    def fix_amount(cls, v: str) -> str:
        if not v:
            return v
        v = v.strip().replace(" ", "").replace("\xa0", "").replace("KM", "")
        if re.match(r"^\d{1,3}(\.\d{3})+(,\d{1,2})?$", v):
            v = v.replace(".", "").replace(",", ".")
        else:
            v = v.replace(",", ".")
        try:
            return str(round(float(v), 2))
        except ValueError:
            return v

    def to_dict(self) -> dict[str, str]:
        return {f: getattr(self, f, "") for f in FIELDS}

    def __iter__(self):
        return iter(self.to_dict().items())


# ─────────────────────────────────────────────────────────────────────────────
# Sistemski prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """Ti si ekspert za čitanje i ekstrakciju podataka s komercijalnih dokumenata iz Bosne i Hercegovine i regiona (fakture, računi, otpremnice, fiskalni izvještaji i sl.).

Dokumenti mogu biti bilo kojeg formata i od bilo kojeg dobavljača. Tvoj zadatak je da razumiješ dokument, bez obzira na izgled ili strukturu, i izvučeš tražene podatke.

════════════════════════════════════════
PRAVILO BR. 1 — DOBAVLJAČ vs KUPAC
════════════════════════════════════════

DOBAVLJAČ = firma koja je IZDALA dokument
  → prepoznaješ ga po: zaglavlju, logu, "Izdao:", "Prodavac:", adresa pošiljaoca
  → NJEGA unosiš u NAZIVPP, SJEDISTEPP, IDPDVPP, JIBPUPP

KUPAC = firma koja PRIMA dokument
  → prepoznaješ ga po: "Kupac:", "Primalac:", "Isporučiti:", tabela s kupcem
  → podatke kupca POTPUNO IGNORIŠEŠ

════════════════════════════════════════
POLJA KOJA TRAŽIŠ
════════════════════════════════════════

BROJFAKT
  Jedinstveni identifikator dokumenta.
  Može biti: broj fakture, broj računa, broj otpremnice, DI broj, broj presjeка, itd.
  Uzmi ono što taj dokument identifikuje — broj koji je jedinstven za taj dokument.

DATUMF
  Datum kada je dokument izdat. Format: DD.MM.GGGG
  Može se zvati: datum fakture, datum računa, datum izdavanja, datum i sat (uzmi samo datum)

DATUMPF
  Datum prijema dokumenta, AKO je eksplicitno napisan. Inače ostavi "".

NAZIVPP
  Puni naziv dobavljača — onako kako piše u zaglavlju dokumenta.
  Primjeri naziva: "d.o.o.", "D.D.", "J.U.", "j.t.p." itd. — sve što nađeš.

SJEDISTEPP
  Puna adresa dobavljača: ulica + broj, poštanski broj, grad.
  Ako su adresni elementi na više redova, spoji ih u jednu liniju.

IDPDVPP
  Identifikacijski/JIB broj dobavljača.
  Karakteristike: TAČNO 13 cifara, počinje cifrom 4.
  Labele koje ga označavaju: "ID broj PU", "JIB", "ID broj", "Identifikacijski broj"
  Ako nađeš broj s 12 cifara koji počinje s drugom cifrom → dodaj "4" ispred.
  Ako ne postoji → ostavi "".

JIBPUPP
  PDV / PIB broj dobavljača.
  Karakteristike: TAČNO 12 cifara (isti broj kao IDPDVPP ali bez vodeće "4").
  Labele: "PDV broj", "PIB", "Poreski broj", "PDV/PIB"
  Ako dobavljač nije PDV obveznik → ostavi "".

IZNBEZPDV
  Iznos bez PDV-a, decimalna tačka (npr. 149.59).
  Labele: "Ukupno bez PDV", "Osnovica", "Neto iznos", ili izračunaj: IZNSAPDV − IZNPDV.
  Za fiskalne izvještaje: ukupni promet (TU) minus ukupni porez (ZU).

IZNPDV
  Iznos PDV-a u KM, decimalna tačka (npr. 25.43).
  Labele: "PDV iznos", "Porez", "ZU", "Ukupno PDV 17%"
  NIJE procenat — tražiš KM iznos.

IZNSAPDV
  Ukupan iznos za naplatu s PDV-om, decimalna tačka (npr. 175.02).
  Labele: "Ukupno za naplatu", "Za platiti", "Ukupan iznos", "TU", "Iznos s PDV"

════════════════════════════════════════
PRAVILA ZA IZNOSE
════════════════════════════════════════

- Decimalni separator u odgovoru: UVIJEK tačka (.) — nikad zarez
- Pretvori zarez u tačku: 1.234,56 → 1234.56
- Ne upisuj valutu (KM, BAM) — samo broj
- IZNBEZPDV + IZNPDV treba biti ≈ IZNSAPDV (dozvoljeno odstupanje ±0.06 zbog zaokruživanja)
- Ako dokument prikazuje više PDV stopa, saberi sve u jedno: ukupna osnovica, ukupni PDV, ukupno za naplatu

════════════════════════════════════════
PRAVILA ZA VIŠE DOKUMENATA U PDF-u
════════════════════════════════════════

PDF može sadržavati više odvojenih dokumenata (N faktura, N fiskalnih izvještaja itd.).
Svaki dokument ima svoj jedinstven broj (BROJFAKT).

→ Za svaki pronađeni dokument napravi jedan JSON objekt.
→ Vrati JSON array s tačno onoliko objekata koliko ima dokumenata.
→ Podaci dobavljača (naziv, adresa, ID, PDV) su često isti za sve — kopiraj ih u svaki objekt.

════════════════════════════════════════
FORMAT ODGOVORA
════════════════════════════════════════

Vraćaj ISKLJUČIVO validan JSON array — bez teksta, objašnjenja ili markdown blokova:

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
    "IZNPDV": "",
    "IZNSAPDV": ""
  }
]
"""


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI klijent
# ─────────────────────────────────────────────────────────────────────────────

def _get_client():
    from openai import OpenAI
    key = (
        st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
    ) or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY nije postavljen!")
    return OpenAI(api_key=key)


def _active_model(default: str = "gpt-4o") -> str:
    return st.session_state.get("selected_model", default)


# ─────────────────────────────────────────────────────────────────────────────
# PDF → tekst
# ─────────────────────────────────────────────────────────────────────────────

def _extract_text(pdf_bytes: bytes) -> str:
    """
    Pokušava izvući tekst iz PDF-a.
    Metode (redom): PyMuPDF → pdfplumber → prazan string.
    PyMuPDF je robusniji i čita više formata fonta.
    """
    # Metoda 1: PyMuPDF (fitz) — preporučena
    text = _extract_text_pymupdf(pdf_bytes)
    if _is_text_pdf(text):
        return text

    # Metoda 2: pdfplumber — fallback
    text = _extract_text_pdfplumber(pdf_bytes)
    return text


def _extract_text_pymupdf(pdf_bytes: bytes) -> str:
    """Ekstrakcija teksta koristeći PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
        parts = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                t = page.get_text("text")
                if t and t.strip():
                    parts.append(t)
        return "\n\n--- NOVA STRANICA ---\n\n".join(parts)
    except ImportError:
        return ""
    except Exception:
        return ""


def _extract_text_pdfplumber(pdf_bytes: bytes) -> str:
    """Ekstrakcija teksta koristeći pdfplumber."""
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text(x_tolerance=2, y_tolerance=2)
                if t:
                    parts.append(t)
        return "\n\n--- NOVA STRANICA ---\n\n".join(parts)
    except Exception:
        return ""


def _is_text_pdf(text: str) -> bool:
    """Vraća True ako PDF ima dovoljno teksta za direktnu ekstrakciju."""
    return len(re.sub(r"\s+", "", text)) >= _MIN_TEXT_CHARS


# ─────────────────────────────────────────────────────────────────────────────
# PDF → slike (za slikovne PDF-ove)
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_to_b64_images(pdf_bytes: bytes) -> list[str]:
    """Konvertuje svaku stranicu PDF-a u base64 JPEG."""
    from pdf2image import convert_from_bytes
    from PIL import Image

    pages   = convert_from_bytes(pdf_bytes, dpi=_DPI)
    results = []
    for page in pages:
        w, h = page.size
        if h > _MAX_IMG_HEIGHT or w > _MAX_IMG_WIDTH:
            ratio = min(_MAX_IMG_WIDTH / w, _MAX_IMG_HEIGHT / h)
            page  = page.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        page.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY)
        results.append(base64.b64encode(buf.getvalue()).decode())
    return results


def _combine_images(b64_list: list[str]) -> str:
    """Spaja više base64 slika vertikalno u jednu."""
    from PIL import Image

    images  = [Image.open(io.BytesIO(base64.b64decode(b))) for b in b64_list]
    max_w   = max(i.width for i in images)
    total_h = sum(i.height for i in images)

    if total_h > _MAX_IMG_HEIGHT:
        ratio   = _MAX_IMG_HEIGHT / total_h
        images  = [i.resize((int(i.width * ratio), int(i.height * ratio)), Image.LANCZOS)
                   for i in images]
        max_w   = max(i.width for i in images)
        total_h = sum(i.height for i in images)

    combined = Image.new("RGB", (max_w, total_h), (255, 255, 255))
    y = 0
    for img in images:
        combined.paste(img, (0, y))
        y += img.height

    buf = io.BytesIO()
    combined.save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode()


# ─────────────────────────────────────────────────────────────────────────────
# GPT ekstrakcija — tekst mod
# ─────────────────────────────────────────────────────────────────────────────

def _extract_via_text(text: str, filename: str) -> list[InvoiceData]:
    """Šalje tekst GPT-4o i vraća listu faktura."""
    client = _get_client()
    model  = _active_model()

    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Fajl: {filename}\n\n"
                        "Pronađi i izvuci SVE dokumente iz teksta ispod. "
                        "Vrati JSON array — jedan objekt po dokumentu.\n\n"
                        f"TEKST DOKUMENTA:\n{text}"
                    ),
                },
            ],
        )
        return _parse_response(resp.choices[0].message.content.strip(), filename)
    except Exception as e:
        return [_error_invoice(filename, str(e))]


# ─────────────────────────────────────────────────────────────────────────────
# GPT ekstrakcija — vision mod
# ─────────────────────────────────────────────────────────────────────────────

def _extract_via_vision(b64_image: str, filename: str) -> list[InvoiceData]:
    """Šalje sliku GPT-4o Vision i vraća listu faktura."""
    client = _get_client()
    model  = _active_model()

    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            temperature=0,
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
                                f"Fajl: {filename}\n"
                                "Pronađi i izvuci SVE dokumente s ove slike. "
                                "Vrati JSON array — jedan objekt po dokumentu."
                            ),
                        },
                    ],
                },
            ],
        )
        return _parse_response(resp.choices[0].message.content.strip(), filename)
    except Exception as e:
        return [_error_invoice(filename, str(e))]


# ─────────────────────────────────────────────────────────────────────────────
# Glavna javna funkcija
# ─────────────────────────────────────────────────────────────────────────────

def extract_invoices_from_pdf(
    pdf_bytes: bytes,
    filename: str = "",
) -> list[InvoiceData]:
    """
    Ekstrahuje sve fakture iz PDF fajla.

    Automatski detektuje tip PDF-a:
    - Tekstualni PDF (ima OCR sloj) → tekst → GPT-4o
    - Slikovni PDF (skeniran)       → slike → GPT-4o Vision

    Parametri
    ---------
    pdf_bytes : sadržaj PDF fajla kao bytes
    filename  : naziv fajla (za logove i labele)

    Vraća
    -----
    Lista InvoiceData objekata — jedan po dokumentu pronađenom u PDF-u.
    """
    text = _extract_text(pdf_bytes)

    if _is_text_pdf(text):
        return _extract_via_text(text, filename)

    try:
        b64_pages = _pdf_to_b64_images(pdf_bytes)
    except Exception as e:
        return [_error_invoice(filename, f"Greška pri konverziji PDF→slika: {e}")]

    if not b64_pages:
        return [_error_invoice(filename, "PDF nema stranica")]

    b64 = _combine_images(b64_pages) if len(b64_pages) > 1 else b64_pages[0]
    return _extract_via_vision(b64, filename)


# ─────────────────────────────────────────────────────────────────────────────
# Parsiranje GPT odgovora
# ─────────────────────────────────────────────────────────────────────────────

def _parse_response(raw: str, filename: str) -> list[InvoiceData]:
    """Parsira GPT odgovor u listu InvoiceData objekata."""

    # Ukloni markdown code block ako postoji
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"(\[[\s\S]+?\]|\{[\s\S]+?\})", raw)
        if not m:
            return [_error_invoice(filename, f"Nije moguće parsirati odgovor: {raw[:300]}")]
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return [_error_invoice(filename, f"JSON parse greška: {raw[:300]}")]

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return [_error_invoice(filename, "Prazan ili neispravan odgovor")]

    results = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        try:
            inv = InvoiceData(**{
                k: str(v).strip() if v is not None else ""
                for k, v in item.items()
                if k in FIELDS
            })
            inv._filename = f"{filename} [{i + 1}/{len(data)}]" if len(data) > 1 else filename
            inv._valid    = True
            inv._warnings = _validate(inv)
            results.append(inv)
        except Exception as e:
            results.append(_error_invoice(filename, str(e)))

    return results or [_error_invoice(filename, "Nema rezultata")]


# ─────────────────────────────────────────────────────────────────────────────
# Validacija
# ─────────────────────────────────────────────────────────────────────────────

def _validate(inv: InvoiceData) -> list[str]:
    """Vraća listu upozorenja za fakturu."""
    w = []

    if not inv.BROJFAKT:   w.append("Broj fakture nije pronađen")
    if not inv.DATUMF:     w.append("Datum fakture nije pronađen")
    if not inv.NAZIVPP:    w.append("Naziv dobavljača nije pronađen")
    if not inv.IZNSAPDV:   w.append("Ukupan iznos nije pronađen")

    if inv.IDPDVPP and (len(inv.IDPDVPP) != 13 or not inv.IDPDVPP.startswith("4")):
        w.append(f"IDPDVPP nije validan: '{inv.IDPDVPP}'")
    if inv.JIBPUPP and len(inv.JIBPUPP) != 12:
        w.append(f"JIBPUPP nije 12 cifara: '{inv.JIBPUPP}'")

    try:
        if inv.IZNBEZPDV and inv.IZNPDV and inv.IZNSAPDV:
            bez = float(inv.IZNBEZPDV)
            pdv = float(inv.IZNPDV)
            sa  = float(inv.IZNSAPDV)
            if abs((bez + pdv) - sa) > 0.06:
                w.append(f"Iznosi ne odgovaraju: {bez} + {pdv} ≠ {sa}")
    except (ValueError, TypeError):
        pass

    return w


# ─────────────────────────────────────────────────────────────────────────────
# Pomoćne funkcije
# ─────────────────────────────────────────────────────────────────────────────

def _error_invoice(filename: str, msg: str) -> InvoiceData:
    """Kreira InvoiceData objekt koji označava grešku."""
    inv           = InvoiceData()
    inv._filename = filename
    inv._valid    = False
    inv._warnings = [msg]
    return inv


def get_available_models() -> list[str]:
    """Vraća listu dostupnih OpenAI modela."""
    return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
