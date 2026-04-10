"""
ai_extractor.py
===============
V2
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
    import fitz
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
        s = s.replace(" ", "") if len(s) <= 24 else s
        digits = re.sub(r"\D", "", s)
        m = re.search(r"(\d{3,6})[\/-](20\d{2})", s)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        if re.fullmatch(r"\d{7,10}", digits) and len(digits) >= 8 and digits[-4:].startswith("20"):
            return f"{digits[:-4]}/{digits[-4:]}"
        return re.sub(r"\s+", "", s)

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

Dokument može sadržavati jedan račun, više različitih računa, više dobavljača, račune različite strukture i višestrane račune.
Za SVAKI račun vrati jedan JSON objekt.
Ako neko polje ne postoji ili nije jasno vidljivo, upiši prazan string "".

Ključevi MORAJU biti TAČNO ovi:
{
  "BROJFAKT": "Broj računa/fakture",
  "DATUMF": "Datum izdavanja fakture (format DD.MM.GGGG)",
  "DATUMPF": "Datum prijema fakture ili prazan string",
  "NAZIVPP": "Puni naziv dobavljača / izdavaoca računa",
  "SJEDISTEPP": "Puna adresa dobavljača sa poštanskim brojem i mjestom",
  "IDPDVPP": "ID/JIB dobavljača, 13 cifara i počinje sa 4",
  "JIBPUPP": "PDV broj dobavljača, 12 cifara, bez vodeće 4",
  "IZNBEZPDV": "Iznos bez PDV-a, decimalna tačka",
  "IZNSAPDV": "Ukupan iznos sa PDV-om, decimalna tačka",
  "IZNPDV": "Iznos PDV-a u novcu, decimalna tačka"
}

Pravila:
- Čitaj samo ono što je vidljivo u dokumentu.
- Ne koristi naziv fajla kao izvor podataka.
- Dobavljač je izdavalac računa, ne kupac.
- Ne pretpostavljaj da svi računi u PDF-u imaju istog dobavljača.
- Za svaki račun posebno odredi dobavljača iz njegovog zaglavlja ili bloka izdavaoca.
- DATUMF uzmi samo sa oznaka kao što su Datum računa, Datum fakture, Datum izdavanja.
- DATUMPF upiši samo ako postoji poseban datum prijema/evidentiranja; inače "".
- IZNBEZPDV, IZNPDV i IZNSAPDV uzimaj iz total bloka istog računa.
- Ako je ovo nastavak prethodne strane istog računa, koristi isti BROJFAKT samo ako je to jasno vidljivo ili jasno proizlazi iz kontinuiteta istog računa.
- Ako nisi siguran da li podatak pripada dobavljaču ili kupcu, ostavi polje prazno.
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



def _extract_text_pages_pymupdf(pdf_bytes: bytes) -> list[str]:
    if fitz is None:
        return []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        return [(page.get_text("text") or "").strip() for page in doc]
    except Exception:
        return []



def _extract_text_pages_pdfplumber(pdf_bytes: bytes) -> list[str]:
    if pdfplumber is None:
        return []
    try:
        out: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                out.append((page.extract_text() or "").strip())
        return out
    except Exception:
        return []



def _extract_text_pages(pdf_bytes: bytes) -> list[str]:
    a = _extract_text_pages_pymupdf(pdf_bytes)
    b = _extract_text_pages_pdfplumber(pdf_bytes)
    score_a = sum(len(re.sub(r"\s+", "", x)) for x in a)
    score_b = sum(len(re.sub(r"\s+", "", x)) for x in b)
    pages = a if score_a >= score_b else b
    return [re.sub(r"\s+", " ", p).strip() for p in pages]



def _extract_text(pdf_bytes: bytes) -> str:
    return "\n".join(_extract_text_pages(pdf_bytes)).strip()



def _is_text_pdf(text: str) -> bool:
    return len(re.sub(r"\s+", "", text or "")) >= _MIN_TEXT_CHARS



def _find_invoice_number(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "")
    patterns = [
        r"(?:RAČUN|RACUN|FAKTURA|OTPREMNICA|RAČUN\s*-\s*OTPREMNICA|RACUN\s*-\s*OTPREMNICA)[^\d]{0,35}(?:broj|br\.?|no\.?|#)?[^\d]{0,10}(\d{3,6}[\/-]20\d{2})",
        r"(?:broj|br\.?|no\.?|#)[^\d]{0,10}(\d{3,6}[\/-]20\d{2})",
        r"(?:RAČUN|RACUN|FAKTURA|OTPREMNICA)[^\d]{0,35}(\d{7,10})",
        r"(?:broj|br\.?|no\.?|#)[^\d]{0,10}(\d{7,10})",
    ]
    for pat in patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            return InvoiceData.normalize_bill_number(m.group(1))
    return ""



def _looks_like_continuation_without_number(text: str) -> bool:
    t = (text or "").lower()
    continuation_markers = [
        "ukupno bez pdv",
        "ukupno pdv",
        "ukupan iznos za naplatu",
        "slovima",
        "rok pla",
        "broj otpremnice",
        "strana 2",
        "strana 3",
        "red. broj",
        "iznos bez pdv",
    ]
    score = sum(1 for m in continuation_markers if m in t)
    return score >= 2



def _has_new_invoice_signal(text: str) -> bool:
    t = re.sub(r"\s+", " ", text or "")
    if _find_invoice_number(t):
        return True
    signals = [
        r"(?:ra[čc]un|faktura|otpremnica)\s*[-–]?\s*(?:otpremnica)?",
        r"(?:datum\s+ra[čc]una|datum\s+fakture|datum\s+izdavanja)",
    ]
    return any(re.search(p, t, flags=re.IGNORECASE) for p in signals)



def _segment_text_pages(page_texts: list[str]) -> list[dict]:
    segments: list[dict] = []
    current_pages: list[str] = []
    current_numbers: list[str] = []
    current_page_ids: list[int] = []

    for idx, page in enumerate(page_texts, start=1):
        number = _find_invoice_number(page)
        is_cont = _looks_like_continuation_without_number(page)
        has_new = _has_new_invoice_signal(page)

        if not current_pages:
            current_pages = [page]
            current_page_ids = [idx]
            if number:
                current_numbers = [number]
            continue

        active_number = current_numbers[-1] if current_numbers else ""

        should_split = False
        if number and active_number and number != active_number:
            should_split = True
        elif number and not active_number and not is_cont:
            should_split = True
        elif has_new and not is_cont and active_number and number and number != active_number:
            should_split = True

        if should_split:
            segments.append({
                "number": active_number,
                "text": "\n\n".join(current_pages).strip(),
                "pages": current_page_ids[:],
            })
            current_pages = [page]
            current_page_ids = [idx]
            current_numbers = [number] if number else []
        else:
            current_pages.append(page)
            current_page_ids.append(idx)
            if number:
                current_numbers.append(number)

    if current_pages:
        segments.append({
            "number": current_numbers[-1] if current_numbers else "",
            "text": "\n\n".join(current_pages).strip(),
            "pages": current_page_ids[:],
        })
    return segments



def _pdf_to_b64_images(pdf_bytes: bytes) -> list[str]:
    pages = convert_from_bytes(pdf_bytes, dpi=_DPI, fmt="jpeg")
    out: list[str] = []
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



def _extract_via_text_segment(text: str, filename: str, label: str = "") -> list[InvoiceData]:
    client = _get_client()
    model = _active_model()
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=2200,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Fajl: {filename}\n"
                        f"Segment: {label or 'tekst'}\n\n"
                        "Ovo je jedan segment PDF-a. "
                        "Vrati samo račune vidljive u ovom segmentu. "
                        "Ako segment izgleda kao nastavak istog računa na narednoj strani, zadrži isti BROJFAKT samo ako je broj vidljiv ili je kontinuitet total bloka očigledan. "
                        "Ne pretpostavljaj da drugi segmenti imaju istog dobavljača.\n\n"
                        f"TEKST DOKUMENTA:\n{text}"
                    ),
                },
            ],
        )
        return _parse_response(resp.choices[0].message.content.strip(), f"{filename}{' ' + label if label else ''}")
    except Exception as e:
        return [_error_invoice(filename, str(e))]



def _extract_via_vision_segment(b64_image: str, filename: str, label: str = "") -> list[InvoiceData]:
    client = _get_client()
    model = _active_model()
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=2200,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Fajl: {filename}\n"
                                f"Segment: {label or 'slika'}\n\n"
                                "Ovo je jedna stranica ili mali segment PDF-a. "
                                "Vrati samo račune vidljive u ovom segmentu. "
                                "Ako se vidi samo nastavak total bloka bez novog broja računa, tretiraj ga kao mogući nastavak prethodnog računa i vrati samo jasno vidljive podatke. "
                                "Ne pretpostavljaj istog dobavljača za druge segmente."
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
        return _parse_response(resp.choices[0].message.content.strip(), f"{filename}{' ' + label if label else ''}")
    except Exception as e:
        return [_error_invoice(filename, str(e))]



def extract_invoices_from_pdf(pdf_bytes: bytes, filename: str = "") -> list[InvoiceData]:
    page_texts = _extract_text_pages(pdf_bytes)
    full_text = "\n".join(page_texts).strip()

    if _is_text_pdf(full_text):
        segments = _segment_text_pages(page_texts) if page_texts else []
        if not segments:
            return _extract_via_text_segment(full_text, filename)
        items: list[InvoiceData] = []
        for seg in segments:
            label = f"[str.{seg['pages'][0]}-{seg['pages'][-1]}]"
            items.extend(_extract_via_text_segment(seg["text"], filename, label))
        return _merge_duplicate_invoices(items)

    pages = _pdf_to_b64_images(pdf_bytes)
    if not pages:
        return [_error_invoice(filename, "PDF nema stranica")]

    items: list[InvoiceData] = []
    for i, page in enumerate(pages, start=1):
        items.extend(_extract_via_vision_segment(page, filename, f"[str.{i}]"))
    return _merge_duplicate_invoices(items)



def _supplier_key(inv: InvoiceData) -> str:
    parts = []
    if inv.NAZIVPP:
        parts.append(re.sub(r"\s+", " ", inv.NAZIVPP).strip().lower())
    if inv.IDPDVPP:
        parts.append(re.sub(r"\D", "", inv.IDPDVPP))
    if inv.JIBPUPP:
        parts.append(re.sub(r"\D", "", inv.JIBPUPP))
    return "|".join([p for p in parts if p])



def _invoice_strength(inv: InvoiceData) -> int:
    score = 0
    for f in FIELDS:
        if getattr(inv, f, ""):
            score += 1
    if inv.BROJFAKT:
        score += 3
    if inv.IZNSAPDV:
        score += 2
    if inv.NAZIVPP:
        score += 2
    return score



def _is_probable_continuation(a: InvoiceData, b: InvoiceData) -> bool:
    if a.BROJFAKT and not b.BROJFAKT and b.IZNSAPDV:
        if a.NAZIVPP and b.NAZIVPP and a.NAZIVPP != b.NAZIVPP:
            return False
        if a.DATUMF and b.DATUMF and a.DATUMF != b.DATUMF:
            return False
        return True
    if b.BROJFAKT and not a.BROJFAKT and a.IZNSAPDV:
        if a.NAZIVPP and b.NAZIVPP and a.NAZIVPP != b.NAZIVPP:
            return False
        if a.DATUMF and b.DATUMF and a.DATUMF != b.DATUMF:
            return False
        return True
    return False



def _compatible_for_merge(a: InvoiceData, b: InvoiceData) -> bool:
    if _is_probable_continuation(a, b):
        return True

    a_num = (a.BROJFAKT or "").strip()
    b_num = (b.BROJFAKT or "").strip()
    if a_num and b_num and a_num != b_num:
        return False

    a_sup = _supplier_key(a)
    b_sup = _supplier_key(b)
    if a_sup and b_sup and a_sup != b_sup:
        return False

    if a.DATUMF and b.DATUMF and a.DATUMF != b.DATUMF:
        return False

    if a.IZNSAPDV and b.IZNSAPDV:
        try:
            diff = abs(float(a.IZNSAPDV) - float(b.IZNSAPDV))
            if diff > 0.06:
                if a_num and b_num and a_num == b_num:
                    return False
                if a.IZNBEZPDV and b.IZNBEZPDV:
                    if abs(float(a.IZNBEZPDV) - float(b.IZNBEZPDV)) > 0.06:
                        return False
        except Exception:
            pass

    if a_num and b_num and a_num == b_num:
        return True

    overlap = 0
    if a.NAZIVPP and b.NAZIVPP and a.NAZIVPP == b.NAZIVPP:
        overlap += 1
    if a.DATUMF and b.DATUMF and a.DATUMF == b.DATUMF:
        overlap += 1
    if a.IDPDVPP and b.IDPDVPP and a.IDPDVPP == b.IDPDVPP:
        overlap += 1
    if a.JIBPUPP and b.JIBPUPP and a.JIBPUPP == b.JIBPUPP:
        overlap += 1
    return overlap >= 3



def _merge_duplicate_invoices(items: list[InvoiceData]) -> list[InvoiceData]:
    clean = [x for x in items if any(getattr(x, f, "") for f in FIELDS) or x._warnings]
    groups: list[list[InvoiceData]] = []

    for inv in clean:
        placed = False
        candidate_idx = None
        candidate_score = -1
        for idx, group in enumerate(groups):
            if _compatible_for_merge(group[0], inv):
                score = _invoice_strength(group[0])
                if score > candidate_score:
                    candidate_score = score
                    candidate_idx = idx
        if candidate_idx is not None:
            groups[candidate_idx].append(inv)
            placed = True
        if not placed:
            groups.append([inv])

    merged = [_merge_invoice_group(g) for g in groups]
    merged = _inherit_missing_invoice_numbers(merged)
    merged.sort(key=lambda x: ((x.DATUMF or "9999.99.99"), (x.BROJFAKT or "ZZZZ")))
    return merged or [_error_invoice("", "Nema rezultata")]



def _inherit_missing_invoice_numbers(items: list[InvoiceData]) -> list[InvoiceData]:
    if len(items) < 2:
        return items
    for i in range(1, len(items)):
        prev = items[i - 1]
        cur = items[i]
        if not cur.BROJFAKT and prev.BROJFAKT and cur.IZNSAPDV:
            if _is_probable_continuation(prev, cur):
                cur.BROJFAKT = prev.BROJFAKT
                cur._warnings = _validate(cur)
                cur._valid = len(cur._warnings) == 0
    return items



def _merge_invoice_group(group: list[InvoiceData]) -> InvoiceData:
    if len(group) == 1:
        inv = group[0]
        inv._warnings = _validate(inv)
        inv._valid = len(inv._warnings) == 0
        return inv

    merged = InvoiceData()
    text_fields = ["BROJFAKT", "DATUMF", "DATUMPF", "NAZIVPP", "SJEDISTEPP", "IDPDVPP", "JIBPUPP"]
    amount_fields = ["IZNBEZPDV", "IZNSAPDV", "IZNPDV"]

    for field in text_fields:
        values = [getattr(x, field, "") or "" for x in group]
        setattr(merged, field, _best_text(values))
    for field in amount_fields:
        values = [getattr(x, field, "") or "" for x in group]
        setattr(merged, field, _best_amount(values))

    merged._filename = group[0]._filename
    merged._warnings = []
    for x in group:
        merged._warnings.extend(x._warnings or [])
    merged._warnings = list(dict.fromkeys(merged._warnings + _validate(merged)))
    merged._valid = len(merged._warnings) == 0
    return merged



def _best_text(values: list[str]) -> str:
    vals = [re.sub(r"\s+", " ", v).strip() for v in values if str(v or "").strip()]
    if not vals:
        return ""
    counts: dict[str, int] = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    best_count = max(counts.values())
    candidates = [v for v, c in counts.items() if c == best_count]
    if len(candidates) == 1:
        return candidates[0]
    candidates.sort(key=lambda x: (len(re.sub(r"\D", "", x)), len(x)), reverse=True)
    return candidates[0]



def _best_amount(values: list[str]) -> str:
    vals = [str(v or "").strip() for v in values if str(v or "").strip()]
    if not vals:
        return ""
    numeric: dict[str, int] = {}
    parsed: dict[str, float] = {}
    for v in vals:
        try:
            vv = f"{float(v):.2f}"
            numeric[vv] = numeric.get(vv, 0) + 1
            parsed[vv] = float(vv)
        except Exception:
            pass
    if numeric:
        best_count = max(numeric.values())
        candidates = [k for k, c in numeric.items() if c == best_count]
        candidates.sort(key=lambda x: parsed[x], reverse=True)
        return candidates[0]
    vals.sort(key=len, reverse=True)
    return vals[0]



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

