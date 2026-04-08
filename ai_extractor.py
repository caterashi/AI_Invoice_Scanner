"""
ai_extractor.py
===============
AI ekstrakcija podataka s faktura koristeći OpenAI GPT-4o Vision.

Podržava:
  - Standardne račune / otpremnice (npr. HERBAVITAL format)
  - Fiskalne izvještaje / presjeке stanja (npr. EDNA-M IBFM format)
  - Više računa na jednoj stranici / u jednom PDF-u
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Polja i model
# ─────────────────────────────────────────────────────────────────────────────

FIELDS = [
    "BROJFAKT", "DATUMF", "DATUMPF",
    "NAZIVPP", "SJEDISTEPP",
    "IDPDVPP", "JIBPUPP",
    "IZNBEZPDV", "IZNPDV", "IZNSAPDV",
]


class InvoiceData(BaseModel):
    BROJFAKT:   str = Field(default="", description="Broj računa/fakture")
    DATUMF:     str = Field(default="", description="Datum izdavanja (DD.MM.GGGG)")
    DATUMPF:    str = Field(default="", description="Datum prijema (DD.MM.GGGG)")
    NAZIVPP:    str = Field(default="", description="Naziv dobavljača")
    SJEDISTEPP: str = Field(default="", description="Adresa dobavljača")
    IDPDVPP:    str = Field(default="", description="ID/JIB - 13 cifara, počinje s 4")
    JIBPUPP:    str = Field(default="", description="PDV broj - 12 cifara")
    IZNBEZPDV:  str = Field(default="", description="Iznos bez PDV-a")
    IZNPDV:     str = Field(default="", description="Iznos PDV-a")
    IZNSAPDV:   str = Field(default="", description="Ukupno s PDV-om")

    # Interni atributi (ne šalju se u Excel, ne validiraju se)
    _filename: str = ""
    _valid: bool = True
    _warnings: list = []

    @field_validator("IDPDVPP")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v:
            return v
        digits = re.sub(r"\D", "", v)
        if len(digits) == 12:
            digits = "4" + digits
        elif len(digits) == 13 and not digits.startswith("4"):
            digits = "4" + digits[1:]
        return digits if len(digits) == 13 else v

    @field_validator("JIBPUPP")
    @classmethod
    def validate_jib(cls, v: str) -> str:
        if not v:
            return v
        digits = re.sub(r"\D", "", v)
        if len(digits) == 13 and digits.startswith("4"):
            digits = digits[1:]
        return digits if len(digits) == 12 else v

    @field_validator("IZNBEZPDV", "IZNPDV", "IZNSAPDV")
    @classmethod
    def normalize_amount(cls, v: str) -> str:
        if not v:
            return v
        # Zamijeni zarez s tačkom, ukloni razmake i točke kao separatore tisuca
        v = v.strip().replace(" ", "").replace("\xa0", "")
        # Format: 1.234,56 → 1234.56
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

SYSTEM_PROMPT = """Ti si ekspert za ekstrakciju podataka s bosanskih/regionalnih faktura i fiskalnih dokumenata.

Tvoj zadatak je analizirati dokument i izvući podatke u TAČNO zadanom JSON formatu.

## PRAVILA

### Dobavljač vs Kupac
- DOBAVLJAČ (NAZIVPP, SJEDISTEPP, IDPDVPP, JIBPUPP) = firma KOJA JE IZDALA račun = firma čiji je logo/zaglavlje = firma koja ŠALJE račun
- KUPAC = firma koja PRIMA račun — NE upisuješ podatke kupca

### ID/JIB broj (IDPDVPP)
- MORA biti TAČNO 13 cifara i počinjati s cifrom 4
- Ako nađeš "ID broj PU: 4218589430000" → to je IDPDVPP
- Ako broj ima 12 cifara, dodaj 4 ispred
- Ako nema ID broja, ostavi ""

### PDV broj (JIBPUPP)
- MORA biti TAČNO 12 cifara (isti broj kao ID ali BEZ vodeće 4)
- Ako nađeš "PDV broj: 218589430000" → to je JIBPUPP
- Ako dobavljač nije u PDV sistemu, ostavi ""

### Iznosi
- Decimalni separator MORA biti tačka (.) — npr. 155.87
- Ako nađeš zarez (155,87), pretvori u tačku (155.87)
- IZNBEZPDV = iznos BEZ PDV-a
- IZNPDV = samo PDV iznos u KM (NE procenat!)
- IZNSAPDV = ukupan iznos ZA NAPLATU s PDV-om

### Datumi
- Format: DD.MM.GGGG (npr. 31.03.2026)

### Fiskalni izvještaji / PRESJEК STANJA
Ako dokument sadrži "PRESJEК STANJA" ili "IBFM" fiskalni ispis:
- BROJFAKT: Uzmi DI broj (npr. "602/2000") ili BF raspon (npr. "1924-1926")
- DATUMF: Datum i sat iz zaglavlja (npr. "03.03.2026")
- DATUMPF: ostavi ""
- NAZIVPP: Puni naziv firme iz zaglavlja
- SJEDISTEPP: Adresa iz zaglavlja
- IDPDVPP: JIB broj iz zaglavlja (počinje s 4, 13 cifara)
- JIBPUPP: PIB/PDV broj (12 cifara, bez vodeće 4)
- IZNBEZPDV: TU (Ukupni promet) minus ZU (Ukupni porez) = IZNBEZPDV
- IZNPDV: ZU vrijednost (ukupni evidentiran porez)
- IZNSAPDV: TU vrijednost (ukupni evidentiran promet)

### Više računa na jednoj stranici
Ako dokument sadrži VIŠE RAZLIČITIH računa (svaki s drugačijim brojem računa), vrati JSON array s jednim objektom po računu.
Ako je samo jedan račun, vrati JSON array s jednim elementom.

## FORMAT ODGOVORA
Uvijek vraćaj SAMO validan JSON array, bez ikakvog teksta:

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
    import streamlit as st
    from openai import OpenAI

    key = (
        st.secrets.get("OPENAI_API_KEY", "")
        if hasattr(st, "secrets") else ""
    ) or os.getenv("OPENAI_API_KEY", "")

    if not key:
        raise ValueError("OPENAI_API_KEY nije postavljen!")
    return OpenAI(api_key=key)


# ─────────────────────────────────────────────────────────────────────────────
# Ekstrakcija — jedna slika → lista InvoiceData
# ─────────────────────────────────────────────────────────────────────────────

def extract_invoices_from_image(
    b64_image: str,
    filename: str = "",
    model: str = "gpt-4o",
) -> list[InvoiceData]:
    """
    Šalje sliku GPT-4o modelu i vraća listu InvoiceData objekata.
    Jedna slika može sadržavati više računa.
    """
    import streamlit as st

    client = _get_client()
    model = st.session_state.get("selected_model", model)

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
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
                                "Analiziraj ovaj dokument i izvuci SVE račune/fakture koje sadrži. "
                                "Vrati JSON array — jedan objekt po računu. "
                                f"Naziv fajla za referencu: {filename}"
                            ),
                        },
                    ],
                },
            ],
        )

        raw = response.choices[0].message.content.strip()
        return _parse_response(raw, filename)

    except Exception as e:
        inv = InvoiceData()
        inv._valid = False
        inv._warnings = [str(e)]
        inv._filename = filename
        return [inv]


def extract_invoice(
    b64_image: str,
    filename: str = "",
    model: str = "gpt-4o",
) -> InvoiceData:
    """
    Backwards-compatible wrapper — vraća samo prvi pronađeni račun.
    Za sve račune koristi extract_invoices_from_image().
    """
    results = extract_invoices_from_image(b64_image, filename, model)
    return results[0] if results else InvoiceData()


# ─────────────────────────────────────────────────────────────────────────────
# Parsiranje JSON odgovora
# ─────────────────────────────────────────────────────────────────────────────

def _parse_response(raw: str, filename: str) -> list[InvoiceData]:
    """Parsira GPT odgovor u listu InvoiceData objekata."""
    # Izvuci JSON iz markdown code bloka ako postoji
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if match:
        raw = match.group(1)

    # Pokušaj parsirati kao array ili single object
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Pokušaj pronaći JSON u tekstu
        match = re.search(r"(\[[\s\S]+\]|\{[\s\S]+\})", raw)
        if match:
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                inv = InvoiceData()
                inv._valid = False
                inv._warnings = [f"Nije moguće parsirati JSON: {raw[:200]}"]
                inv._filename = filename
                return [inv]
        else:
            inv = InvoiceData()
            inv._valid = False
            inv._warnings = [f"Nema JSON u odgovoru: {raw[:200]}"]
            inv._filename = filename
            return [inv]

    # Normalizuj u listu
    if isinstance(data, dict):
        data = [data]
    elif not isinstance(data, list):
        data = [{}]

    results = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        try:
            inv = InvoiceData(**{k: str(v) if v is not None else "" for k, v in item.items()})
            inv._filename = f"{filename} [{i+1}]" if len(data) > 1 else filename
            inv._valid = True
            inv._warnings = _validate(inv)
            results.append(inv)
        except Exception as e:
            inv = InvoiceData()
            inv._valid = False
            inv._warnings = [str(e)]
            inv._filename = filename
            results.append(inv)

    return results if results else [InvoiceData()]


# ─────────────────────────────────────────────────────────────────────────────
# Validacija
# ─────────────────────────────────────────────────────────────────────────────

def _validate(inv: InvoiceData) -> list[str]:
    """Vraća listu upozorenja za fakturu."""
    warnings = []

    if not inv.BROJFAKT:
        warnings.append("Broj fakture nije pronađen")
    if not inv.DATUMF:
        warnings.append("Datum fakture nije pronađen")
    if not inv.NAZIVPP:
        warnings.append("Naziv dobavljača nije pronađen")
    if inv.IDPDVPP and (len(inv.IDPDVPP) != 13 or not inv.IDPDVPP.startswith("4")):
        warnings.append(f"IDPDVPP nije 13 cifara ili ne počinje s 4: '{inv.IDPDVPP}'")
    if inv.JIBPUPP and len(inv.JIBPUPP) != 12:
        warnings.append(f"JIBPUPP nije 12 cifara: '{inv.JIBPUPP}'")
    if not inv.IZNSAPDV:
        warnings.append("Ukupan iznos nije pronađen")

    # Provjeri konzistentnost iznosa
    try:
        if inv.IZNBEZPDV and inv.IZNPDV and inv.IZNSAPDV:
            bez = float(inv.IZNBEZPDV)
            pdv = float(inv.IZNPDV)
            sa  = float(inv.IZNSAPDV)
            if abs((bez + pdv) - sa) > 0.05:
                warnings.append(
                    f"Iznosi ne odgovaraju: {bez} + {pdv} ≠ {sa}"
                )
    except (ValueError, TypeError):
        pass

    return warnings
  
def get_available_models() -> list[str]:
    """Vraća listu dostupnih OpenAI modela."""
    return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
