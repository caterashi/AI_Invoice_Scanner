
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
from pydantic import BaseModel, Field, PrivateAttr, field_validator
from pdf2image import convert_from_bytes

try:
    import fitz
except Exception:
    fitz = None

try:
    import pdfplumber
except Exception:
    pdfplumber = None

load_dotenv(Path(__file__).parent / ".env")

FIELDS = [
    "BROJ_DOKUMENTA",
    "DATUM_DOKUMENTA",
    "DATUM_PRIJEMA",
    "DOBAVLJAC_NAZIV",
    "DOBAVLJAC_SJEDISTE",
    "DOBAVLJAC_IDPDV",
    "DOBAVLJAC_JIB",
    "IZNOS_BEZ_PDV",
    "IZNOS_PDV",
    "IZNOS_SA_PDV",
    "VRSTA_DOKUMENTA",
]

_MIN_TEXT_CHARS = 100
_DPI = 200
_JPEG_QUALITY = 92
_MAX_IMG_HEIGHT = 8000
_MAX_IMG_WIDTH = 3000


class KUFData(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    BROJ_DOKUMENTA: str = Field(default="")
    DATUM_DOKUMENTA: str = Field(default="")
    DATUM_PRIJEMA: str = Field(default="")
    DOBAVLJAC_NAZIV: str = Field(default="")
    DOBAVLJAC_SJEDISTE: str = Field(default="")
    DOBAVLJAC_IDPDV: str = Field(default="")
    DOBAVLJAC_JIB: str = Field(default="")
    IZNOS_BEZ_PDV: str = Field(default="")
    IZNOS_PDV: str = Field(default="")
    IZNOS_SA_PDV: str = Field(default="")
    VRSTA_DOKUMENTA: str = Field(default="")

    _filename: str = PrivateAttr(default="")
    _valid: bool = PrivateAttr(default=True)
    _warnings: list[str] = PrivateAttr(default_factory=list)

    @property
    def filename(self) -> str:
        return self._filename

    @filename.setter
    def filename(self, value: str) -> None:
        self._filename = str(value or "")

    @property
    def warnings(self) -> list[str]:
        return self._warnings

    @warnings.setter
    def warnings(self, value: list[str]) -> None:
        self._warnings = list(value or [])

    @property
    def valid(self) -> bool:
        return self._valid

    @valid.setter
    def valid(self, value: bool) -> None:
        self._valid = bool(value)

    @field_validator("DATUM_DOKUMENTA", "DATUM_PRIJEMA")
    @classmethod
    def normalize_date(cls, v: str) -> str:
        s = re.sub(r"\s+", " ", str(v or "")).strip()
        if not s:
            return ""
        s = s.replace("/", ".").replace("-", ".")
        s = re.sub(r"\s*\.\s*", ".", s)
        m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
        if not m:
            return s
        d, mo, y = m.groups()
        return f"{int(d):02d}.{int(mo):02d}.{y}"

    @field_validator("DOBAVLJAC_NAZIV", "DOBAVLJAC_SJEDISTE", "VRSTA_DOKUMENTA", "BROJ_DOKUMENTA")
    @classmethod
    def clean_text(cls, v: str) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()

    @field_validator("DOBAVLJAC_IDPDV")
    @classmethod
    def normalize_idpdv(cls, v: str) -> str:
        s = str(v or "").strip()
        if not s:
            return ""
        d = re.sub(r"\D", "", s)
        if len(d) == 12:
            d = "4" + d
        return d if len(d) == 13 and d.startswith("4") else s

    @field_validator("DOBAVLJAC_JIB")
    @classmethod
    def normalize_jib(cls, v: str) -> str:
        s = str(v or "").strip()
        if not s:
            return ""
        d = re.sub(r"\D", "", s)
        if len(d) == 13 and d.startswith("4"):
            d = d[1:]
        return d if len(d) == 12 else s

    @field_validator("IZNOS_BEZ_PDV", "IZNOS_PDV", "IZNOS_SA_PDV")
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
Ti si ekspert za ekstrakciju knjigovodstvenih podataka iz KUF dokumentacije u Bosni i Hercegovini.

Zadatak: iz PDF dokumenta vrati ISKLJUČIVO validan JSON array, bez objašnjenja.
Dokument može biti ulazna faktura, račun dobavljača, KUF izvještaj ili kombinacija više ulaznih dokumenata.
Za svaki dokument ili prepoznatljivu stavku vrati jedan JSON objekt.
Ako polje nije jasno vidljivo, vrati prazan string.

Vrati tačno ove ključeve:
{
  "BROJ_DOKUMENTA": "Broj ulazne fakture ili računa dobavljača",
  "DATUM_DOKUMENTA": "Datum dokumenta / datum izdavanja računa u formatu DD.MM.GGGG",
  "DATUM_PRIJEMA": "Datum prijema ako je eksplicitno naveden, inače prazan string",
  "DOBAVLJAC_NAZIV": "Naziv dobavljača",
  "DOBAVLJAC_SJEDISTE": "Adresa ili sjedište dobavljača",
  "DOBAVLJAC_IDPDV": "ID/PDV broj dobavljača, 13 cifara i počinje sa 4 ako je vidljiv",
  "DOBAVLJAC_JIB": "JIB/PDV bez vodeće 4, 12 cifara ako je vidljiv",
  "IZNOS_BEZ_PDV": "Iznos bez PDV-a",
  "IZNOS_PDV": "Iznos PDV-a",
  "IZNOS_SA_PDV": "Ukupan iznos sa PDV-om",
  "VRSTA_DOKUMENTA": "račun, faktura, avans, uvoz ili ostalo"
}

Pravila:
- Fokus je na poljima korisnim za knjigu ulaznih faktura i PDV obradu.
- Ako vidiš račun dobavljača, obavezno preferiraj dobavljača kao glavni subjekt.
- DATUM_DOKUMENTA je datum izdavanja računa, ne datum valute ili plaćanja.
- DATUM_PRIJEMA popuni samo ako je eksplicitno naveden.
- IZNOS_BEZ_PDV, IZNOS_PDV i IZNOS_SA_PDV uzimaj iz total bloka istog dokumenta.
- VRSTA_DOKUMENTA procijeni samo ako je jasno iz sadržaja; inače "račun" ili prazan string.
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


def _extract_text_pages(pdf_bytes: bytes) -> list[str]:
    pages_a, pages_b = [], []
    if fitz is not None:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages_a = [(page.get_text("text") or "").strip() for page in doc]
        except Exception:
            pages_a = []
    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages_b = [(page.extract_text() or "").strip() for page in pdf.pages]
        except Exception:
            pages_b = []
    score_a = sum(len(re.sub(r"\s+", "", x)) for x in pages_a)
    score_b = sum(len(re.sub(r"\s+", "", x)) for x in pages_b)
    pages = pages_a if score_a >= score_b else pages_b
    return [re.sub(r"\s+", " ", p).strip() for p in pages]


def _is_text_pdf(text: str) -> bool:
    return len(re.sub(r"\s+", "", text or "")) >= _MIN_TEXT_CHARS


def _pdf_to_b64_images(pdf_bytes: bytes) -> list[str]:
    pages = convert_from_bytes(pdf_bytes, dpi=_DPI, fmt="jpeg")
    out = []
    for img in pages:
        img = img.convert("RGB")
        w, h = img.size
        ratio = min(_MAX_IMG_WIDTH / max(w, 1), _MAX_IMG_HEIGHT / max(h, 1), 1.0)
        if ratio < 1.0:
            img = img.resize((int(w * ratio), int(h * ratio)))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
        out.append(base64.b64encode(buf.getvalue()).decode())
    return out


def _parse_response(raw: str, filename: str) -> list[KUFData]:
    if not raw:
        return [_error_record(filename, "Prazan odgovor modela")]
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()
    try:
        data = json.loads(raw)
    except Exception:
        m2 = re.search(r"(\[[\s\S]+\]|\{[\s\S]+\})", raw)
        if not m2:
            return [_error_record(filename, f"JSON parse greška: {raw[:300]}")]
        try:
            data = json.loads(m2.group(1))
        except Exception:
            return [_error_record(filename, f"JSON parse greška: {raw[:300]}")]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return [_error_record(filename, "Model nije vratio validan JSON array")]

    items = []
    for item in data:
        if not isinstance(item, dict):
            continue
        payload = {field: str(item.get(field, "") or "").strip() for field in FIELDS}
        rec = KUFData(**payload)
        rec.filename = filename
        rec.warnings = _validate(rec)
        rec.valid = len(rec.warnings) == 0
        items.append(rec)
    return items or [_error_record(filename, "Nema rezultata")]


def _extract_via_text(text: str, filename: str) -> list[KUFData]:
    client = _get_client()
    resp = client.chat.completions.create(
        model=_active_model(),
        temperature=0,
        max_tokens=2200,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Fajl: {filename}\n\nTEKST DOKUMENTA:\n{text}"},
        ],
    )
    return _parse_response(resp.choices[0].message.content.strip(), filename)


def _extract_via_vision(images: list[str], filename: str) -> list[KUFData]:
    client = _get_client()
    content = [{"type": "text", "text": f"Fajl: {filename}. Vrati KUF podatke kao JSON array."}]
    for img in images[:8]:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}})
    resp = client.chat.completions.create(
        model=_active_model(),
        temperature=0,
        max_tokens=2200,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    )
    return _parse_response(resp.choices[0].message.content.strip(), filename)


def _validate(rec: KUFData) -> list[str]:
    warnings = []
    if not rec.BROJ_DOKUMENTA:
        warnings.append("BROJ_DOKUMENTA nije pronađen")
    if not rec.DATUM_DOKUMENTA:
        warnings.append("DATUM_DOKUMENTA nije pronađen")
    if not rec.DOBAVLJAC_NAZIV:
        warnings.append("DOBAVLJAC_NAZIV nije pronađen")
    if not rec.IZNOS_SA_PDV:
        warnings.append("IZNOS_SA_PDV nije pronađen")
    try:
        if rec.IZNOS_BEZ_PDV and rec.IZNOS_PDV and rec.IZNOS_SA_PDV:
            if abs((float(rec.IZNOS_BEZ_PDV) + float(rec.IZNOS_PDV)) - float(rec.IZNOS_SA_PDV)) > 0.06:
                warnings.append("Iznosi nisu usklađeni")
    except Exception:
        warnings.append("Jedan ili više iznosa nisu numerički")
    return warnings


def _error_record(filename: str, msg: str) -> KUFData:
    rec = KUFData()
    rec.filename = filename
    rec.valid = False
    rec.warnings = [msg]
    return rec


def extract_invoices_from_pdf(pdf_bytes: bytes, filename: str = "") -> list[KUFData]:
    text_pages = _extract_text_pages(pdf_bytes)
    full_text = "\n".join(text_pages).strip()
    if _is_text_pdf(full_text):
        return _extract_via_text(full_text, filename)
    return _extract_via_vision(_pdf_to_b64_images(pdf_bytes), filename)


def extract_kuf_from_pdf(pdf_bytes: bytes, filename: str = "") -> list[KUFData]:
    return extract_invoices_from_pdf(pdf_bytes, filename)
