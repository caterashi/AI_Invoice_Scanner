"""
ai_extractor.py
===============
AI ekstrakcija podataka s faktura koristeći OpenAI GPT-4o.

PDF fajlovi se obrađuju na dva načina:
  1. Tekstualni PDF  (ima OCR sloj) → tekst se šalje direktno GPT-4o
  2. Slikovni PDF    (skenirana slika) → stranice → slike → GPT-4o Vision

Oba tipa podržavaju više računa/presječa u jednom PDF-u.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Any

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

_MIN_TEXT_CHARS = 100   # min. znakova da se PDF smatra tekstualnim
_MAX_IMG_HEIGHT = 8000  # max. visina kombinirane slike u pikselima
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
        # 1.234,56 → 1234.56
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

_SYSTEM_PROMPT = """Ti si ekspert za ekstrakciju podataka s bosanskih/regionalnih faktura i fiskalnih dokumenata.

## OSNOVNA PRAVILA

**DOBAVLJAČ** = firma KOJA JE IZDALA račun (zaglavlje, logo, šalje račun) → nju unosiš
**KUPAC**     = firma koja PRIMA račun → podatke kupca POTPUNO IGNORIŠEŠ

---

## POLJA

| Polje | Opis i primjeri |
|-------|-----------------|
| BROJFAKT | Broj računa/fakture (npr. 0494/2026, 432/10) |
| DATUMF | Datum izdavanja računa: DD.MM.GGGG |
| DATUMPF | Datum prijema ako eksplicitno piše, inače "" |
| NAZIVPP | Puni naziv DOBAVLJAČA (iz zaglavlja) |
| SJEDISTEPP | Puna adresa dobavljača (ulica, poštanski broj, grad) |
| IDPDVPP | ID/JIB broja DOBAVLJAČA — TAČNO 13 cifara, počinje s 4 |
| JIBPUPP | PDV/PIB broj DOBAVLJAČA — TAČNO 12 cifara (= IDPDVPP bez vodeće 4); "" ako nije PDV obveznik |
| IZNBEZPDV | Iznos bez PDV-a (decimalna tačka, npr. 149.59) |
| IZNPDV | Iznos PDV-a u KM (decimalna tačka, npr. 25.43) |
| IZNSAPDV | Ukupan iznos ZA NAPLATU s PDV-om (npr. 175.02) |

---

## IDPDVPP — DETALJNA PRAVILA

- Labele: "ID broj PU:", "JIB:" — oba se odnose na isti broj
- Mora biti TAČNO 13 cifara i počinjati s 4
- Primjer: "JIB: 4218144580028" → IDPDVPP = "4218144580028"
- Primjer: "ID broj PU: 4218589430000" → IDPDVPP = "4218589430000"
- Ako ima 12 cifara → dodaj 4 ispred. Ako nema → ostavi ""

## JIBPUPP — DETALJNA PRAVILA

- Labele: "PDV broj:", "PIB:" — oba se odnose na isti broj
- Mora biti TAČNO 12 cifara (isti broj kao IDPDVPP, ali BEZ vodeće 4)
- Primjer: "PIB: 218144580001" → JIBPUPP = "218144580001"
- Primjer: "PDV broj: 218589430000" → JIBPUPP = "218589430000"
- Ako dobavljač nije u PDV sistemu → ostavi ""

## IZNOSI — PRAVILA

- Decimalni separator: UVIJEK tačka (.)
- Uzimaj iz redova: "Ukupno bez PDV-a", "Ukupno PDV", "UKUPAN IZNOS ZA NAPLATU"
- IZNBEZPDV + IZNPDV mora biti = IZNSAPDV (provjeri!)

---

## TIP 1: STANDARDNI RAČUN / OTPREMNICA (HERBAVITAL format)

Zaglavlje sadrži naziv i adresu dobavljača, PDV broj i ID broj PU.
Svaki račun ima header: "RAČUN - OTPREMNICA broj: XXXX/GGGG"
- BROJFAKT = broj iz tog headera (npr. "0494/2026")
- DATUMF   = "Datum računa:" iz zaglavlja tog računa (DD.MM.GGGG)
- DATUMPF  = "" (nema posebnog datuma prijema)
- Iznosi iz tabele na dnu svakog računa

---

## TIP 2: FISKALNI IZVJEŠTAJ (EDNA-M / IBFM — PRESJEК STANJA)

Struktura svakog presjeк stanja:
```
JIB: 4218144580028        ← IDPDVPP
PIB: 218144580001         ← JIBPUPP
IBFM: BR036670
PRESJEК STANJA
03.03.2026. 17:55         ← DATUMF
BF: 1924 - 1926           ← BF raspon
DI: 602 / 2000            ← DI broj
TU: 5.868,00              ← ukupni promet = IZNSAPDV
ZU: 852,62                ← ukupni porez = IZNPDV
```

Mapiranje:
- BROJFAKT  = DI broj (npr. "602/2000")
- DATUMF    = datum iz zaglavlja presjeк stanja (npr. "03.03.2026")
- DATUMPF   = ""
- NAZIVPP   = naziv firme iz zaglavlja
- SJEDISTEPP = adresa firme iz zaglavlja
- IDPDVPP   = JIB iz zaglavlja (počinje s 4, 13 cifara)
- JIBPUPP   = PIB iz zaglavlja (12 cifara)
- IZNBEZPDV = TU minus ZU (izračunaj! npr. 5868.00 - 852.62 = 5015.38)
- IZNPDV    = ZU vrijednost
- IZNSAPDV  = TU vrijednost

---

## VIŠE DOKUMENATA U JEDNOM PDF-u

Ako PDF sadrži N različitih računa ili N različitih presjeк stanja:
→ vrati JSON array s TAČNO N objekata — po jedan za svaki dokument

Primjer za HERBAVITAL PDF s 10 računa:
→ vrati array od 10 objekata, svaki s drugačijim BROJFAKT

Primjer za EDNA-M PDF s 5 presjeк stanja (DI: 602, 603, 604, 605, 606):
→ vrati array od 5 objekata, svaki s drugačijim BROJFAKT (DI brojem)

---

## FORMAT ODGOVORA

Vraćaj ISKLJUČIVO validan JSON array, bez ikakvog teksta ili objašnjenja:

[{"BROJFAKT":"","DATUMF":"","DATUMPF":"","NAZIVPP":"","SJEDISTEPP":"","IDPDVPP":"","JIBPUPP":"","IZNBEZPDV":"","IZNPDV":"","IZNSAPDV":""}]
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
    Pokušava izvući tekst iz PDF-a koristeći pdfplumber.
    Vraća prazan string ako PDF nema tekstualnog sloja.
    """
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text(x_tolerance=2, y_tolerance=2)
                if t:
                    text_parts.append(t)
        return "\n\n--- NOVA STRANICA ---\n\n".join(text_parts)
    except Exception:
        return ""


def _is_text_pdf(text: str) -> bool:
    """Vraća True ako PDF ima dovoljno teksta za direktnu ekstrakciju."""
    clean = re.sub(r"\s+", "", text)
    return len(clean) >= _MIN_TEXT_CHARS


# ─────────────────────────────────────────────────────────────────────────────
# PDF → slike (za slikovne PDF-ove)
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_to_b64_images(pdf_bytes: bytes) -> list[str]:
    """
    Konvertuje svaku stranicu PDF-a u base64 JPEG.
    Vraća listu base64 stringova — jedan po stranici.
    """
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
    """
    Spaja više base64 slika vertikalno u jednu.
    Korisno kad su sve stranice dio istog dokumenta.
    """
    from PIL import Image

    images = []
    for b64 in b64_list:
        img_data = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_data))
        images.append(img)

    max_w   = max(i.width for i in images)
    total_h = sum(i.height for i in images)

    if total_h > _MAX_IMG_HEIGHT:
        ratio   = _MAX_IMG_HEIGHT / total_h
        images  = [
            i.resize((int(i.width * ratio), int(i.height * ratio)), Image.LANCZOS)
            for i in images
        ]
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
                        "Izvuci SVE fakture iz teksta ispod. "
                        "Vrati JSON array — jedan objekt po fakturi.\n\n"
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
                                "Izvuci SVE fakture s ove slike. "
                                "Vrati JSON array — jedan objekt po fakturi."
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
    - Tekstualni PDF (ima OCR sloj) → tekst → GPT-4o (brže, jeftinije)
    - Slikovni PDF (skeniran)       → slike → GPT-4o Vision

    Parametri
    ---------
    pdf_bytes : sadržaj PDF fajla kao bytes
    filename  : naziv fajla (za logove i labele)

    Vraća
    -----
    Lista InvoiceData objekata — jedan po fakturi u dokumentu.
    """
    # 1. Pokušaj tekstualnu ekstrakciju
    text = _extract_text(pdf_bytes)

    if _is_text_pdf(text):
        return _extract_via_text(text, filename)

    # 2. Fallback: konvertuj u slike i pošalji Vision modelu
    try:
        b64_pages = _pdf_to_b64_images(pdf_bytes)
    except Exception as e:
        return [_error_invoice(filename, f"Greška pri konverziji PDF→slika: {e}")]

    if not b64_pages:
        return [_error_invoice(filename, "PDF nema stranica")]

    b64_combined = _combine_images(b64_pages) if len(b64_pages) > 1 else b64_pages[0]
    return _extract_via_vision(b64_combined, filename)



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
        # Pokušaj pronaći JSON unutar teksta
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

    if not inv.BROJFAKT:
        w.append("Broj fakture nije pronađen")
    if not inv.DATUMF:
        w.append("Datum fakture nije pronađen")
    if not inv.NAZIVPP:
        w.append("Naziv dobavljača nije pronađen")
    if not inv.IZNSAPDV:
        w.append("Ukupan iznos nije pronađen")

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
    """Kreira InvoiceData objekt s greškom."""
    inv           = InvoiceData()
    inv._filename = filename
    inv._valid    = False
    inv._warnings = [msg]
    return inv


def get_available_models() -> list[str]:
    """Vraća listu dostupnih OpenAI modela."""
    return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
