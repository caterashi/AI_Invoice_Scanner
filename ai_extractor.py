"""
ai_extractor.py
===============
GPT-4o Vision ekstrakcija podataka iz faktura.

Sadrži:
  - Strukturirani PROMPT za ekstrakciju
  - InvoiceData dataclass s validacijom
  - parse_response()  — JSON parser s 3 fallback strategije
  - build_invoice()   — normalizacija + auto-fix + validacija
  - extract_invoice() — poziv OpenAI API-ja s retry logikom
  - Obrada grešaka i niske pouzdanosti prepoznavanja
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APIStatusError, RateLimitError

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Konstante
# ─────────────────────────────────────────────────────────────────────────────

FIELDS: list[str] = [
    "BROJFAKT", "DATUMF", "DATUMPF",
    "NAZIVPP", "SJEDISTEPP",
    "IDPDVPP", "JIBPUPP",
    "IZNBEZPDV", "IZNPDV", "IZNSAPDV",
]

# Ako je |IZNBEZPDV + IZNPDV - IZNSAPDV| > tolerance → upozorenje
AMOUNT_TOLERANCE = 0.10  # 10 lipa/feninga

# ─────────────────────────────────────────────────────────────────────────────
# Prompti
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Ti si precizni AI asistent specijaliziran za ekstrakciju podataka iz faktura i računa.
Tvoj zadatak je da iz priložene slike fakture izvučeš tačne podatke i vratiš ih kao validan JSON.

PRAVILA:
1. Vrati ISKLJUČIVO validan JSON objekat — bez komentara, bez markdown, bez obrazloženja.
2. Sve vrijednosti moraju biti stringovi, uključujući iznose.
3. Za iznose koristi TAČKU kao decimalni separator (npr. 155.87, nikako 155,87).
4. Ako podatak ne postoji na fakturi, vrati prazan string "".
5. IDPDVPP mora imati TAČNO 13 cifara i počinjati sa 4. Ako broj ima manje od 13 cifara, dodaj vodeće nule ili 4 dok ne bude 13 cifara.
6. JIBPUPP je isti broj kao IDPDVPP ali BEZ prve cifre (dakle 12 cifara). Ako firma nije PDV obveznik, vrati "".
7. Datumi moraju biti u formatu DD.MM.GGGG.
8. NAZIVPP je firma koja JE IZDALA račun (čiji je logo/zaglavlje na vrhu dokumenta), NE firma koja ga prima.
"""

EXTRACTION_PROMPT = """{
  "BROJFAKT":   "<Broj računa/fakture — npr. 432/10, 9034508513, 600398-1-0126-1>",
  "DATUMF":     "<Datum IZDAVANJA fakture u formatu DD.MM.GGGG>",
  "DATUMPF":    "<Datum PRIJEMA ili evidentiranja fakture u formatu DD.MM.GGGG — ostavi prazan string ako ne postoji>",
  "NAZIVPP":    "<Puni naziv DOBAVLJAČA — firma koja je IZDALA račun, čiji je logo/zaglavlje>",
  "SJEDISTEPP": "<Puna adresa dobavljača s poštanskim brojem i mjestom>",
  "IDPDVPP":    "<JIB/ID broj dobavljača — TAČNO 13 cifara, počinje sa 4>",
  "JIBPUPP":    "<PDV broj dobavljača — TAČNO 12 cifara (= IDPDVPP bez prve cifre 4). Prazan string ako nije PDV obveznik>",
  "IZNBEZPDV":  "<Iznos BEZ PDV-a, decimalni separator tačka — npr. 155.87>",
  "IZNPDV":     "<Iznos PDV-a u KM — ne procenat nego KM iznos — npr. 26.50>",
  "IZNSAPDV":   "<UKUPAN iznos SA PDV-om — npr. 182.37>"
}

Analiziraj priloženu fakturu pažljivo i popuni sve ključeve. Vrati SAMO JSON objekat, ništa drugo."""


# ─────────────────────────────────────────────────────────────────────────────
# InvoiceData model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InvoiceData:
    """
    Strukturirani model fakture s automatskom validacijom.

    Polja koja idu u Excel / prikaz: sva iz FIELDS liste.
    Interni metapodaci (_filename, _valid, _warnings, _errors) NE idu u Excel.
    """

    # ── Podaci fakture ────────────────────────────────────────────────────────
    BROJFAKT:   str = ""
    DATUMF:     str = ""
    DATUMPF:    str = ""
    NAZIVPP:    str = ""
    SJEDISTEPP: str = ""
    IDPDVPP:    str = ""
    JIBPUPP:    str = ""
    IZNBEZPDV:  str = ""
    IZNPDV:     str = ""
    IZNSAPDV:   str = ""

    # ── Interni metapodaci ────────────────────────────────────────────────────
    _filename: str       = field(default="",    repr=False)
    _valid:    bool      = field(default=True,  repr=False)
    _warnings: list[str] = field(default_factory=list, repr=False)
    _errors:   list[str] = field(default_factory=list, repr=False)
    _raw_json: str       = field(default="",    repr=False)

    # ── Konverzija ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, str]:
        """Samo FIELDS ključevi — za Excel i prikaz u tablici."""
        return {k: getattr(self, k, "") for k in FIELDS}

    def to_full_dict(self) -> dict:
        """Svi atributi uključujući metapodatke — za session_state."""
        d = self.to_dict()
        d.update({
            "_filename": self._filename,
            "_valid":    self._valid,
            "_warnings": list(self._warnings),
            "_errors":   list(self._errors),
        })
        return d

    # ── Validacija ────────────────────────────────────────────────────────────

    def validate(self) -> "InvoiceData":
        """
        Validira sve ključne atribute.
        Popunjava self._warnings (upozorenja) i self._errors (greške).
        self._valid = False ako postoji barem jedna greška.
        Vraća self za chaining.
        """
        self._warnings = []
        self._errors   = []

        self._val_broj_fakture()
        self._val_datum(self.DATUMF,  "DATUMF",  required=True)
        self._val_datum(self.DATUMPF, "DATUMPF", required=False)
        self._val_naziv()
        self._val_idpdvpp()
        self._val_jibpupp()
        self._val_iznosi()
        self._cross_val_iznosi()

        self._valid = len(self._errors) == 0
        return self

    def _val_broj_fakture(self):
        if not self.BROJFAKT or not self.BROJFAKT.strip():
            self._errors.append("BROJFAKT: Broj fakture je prazan.")
            return
        if not re.match(r'^[\w\d\-\/\.\s\(\)]+$', self.BROJFAKT.strip()):
            self._warnings.append(
                f"BROJFAKT: Neočekivani znakovi → '{self.BROJFAKT}'"
            )

    def _val_datum(self, value: str, fname: str, required: bool):
        if not value:
            if required:
                self._errors.append(f"{fname}: Datum je prazan.")
            return
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', value.strip()):
            self._warnings.append(
                f"{fname}: Datum nije u formatu DD.MM.GGGG → '{value}'"
            )

    def _val_naziv(self):
        if not self.NAZIVPP or not self.NAZIVPP.strip():
            self._errors.append("NAZIVPP: Naziv dobavljača je prazan.")

    def _val_idpdvpp(self):
        if not self.IDPDVPP:
            self._warnings.append("IDPDVPP: JIB/ID broj nije pronađen na fakturi.")
            return
        clean = re.sub(r'\s', '', self.IDPDVPP)
        if not clean.isdigit():
            self._errors.append(
                f"IDPDVPP: Mora sadržavati samo cifre → '{self.IDPDVPP}'"
            )
            return
        if len(clean) != 13:
            self._errors.append(
                f"IDPDVPP: Mora imati 13 cifara, pronađeno {len(clean)} → '{self.IDPDVPP}'"
            )
        if not clean.startswith("4"):
            self._errors.append(
                f"IDPDVPP: Mora počinjati sa cifrom 4 → '{self.IDPDVPP}'"
            )

    def _val_jibpupp(self):
        if not self.JIBPUPP:
            return  # Prazan = nije PDV obveznik — OK
        clean = re.sub(r'\s', '', self.JIBPUPP)
        if not clean.isdigit():
            self._errors.append(
                f"JIBPUPP: Mora sadržavati samo cifre → '{self.JIBPUPP}'"
            )
            return
        if len(clean) != 12:
            self._errors.append(
                f"JIBPUPP: Mora imati 12 cifara, pronađeno {len(clean)} → '{self.JIBPUPP}'"
            )
        # Konzistentnost: JIBPUPP mora biti IDPDVPP[1:]
        if self.IDPDVPP:
            idp_clean = re.sub(r'\s', '', self.IDPDVPP)
            if len(idp_clean) == 13:
                expected = idp_clean[1:]
                if clean != expected:
                    self._warnings.append(
                        f"JIBPUPP '{clean}' ne odgovara IDPDVPP[1:] '{expected}' — provjeri ručno."
                    )

    def _val_iznosi(self):
        for fname in ("IZNBEZPDV", "IZNPDV", "IZNSAPDV"):
            val = getattr(self, fname, "")
            if not val:
                self._warnings.append(f"{fname}: Iznos nije pronađen.")
                continue
            try:
                fval = float(val)
                if fval < 0:
                    self._warnings.append(f"{fname}: Negativan iznos → {val}")
                if fval == 0:
                    self._warnings.append(f"{fname}: Iznos je nula — provjeri.")
            except (ValueError, TypeError):
                self._errors.append(
                    f"{fname}: Nije validan decimalni broj → '{val}'"
                )

    def _cross_val_iznosi(self):
        """Provjeri matematičku konzistentnost: IZNBEZPDV + IZNPDV ≈ IZNSAPDV."""
        try:
            bez = float(self.IZNBEZPDV or 0)
            pdv = float(self.IZNPDV    or 0)
            sa  = float(self.IZNSAPDV  or 0)
            if sa == 0:
                return
            diff = abs((bez + pdv) - sa)
            if diff > AMOUNT_TOLERANCE:
                self._warnings.append(
                    f"Iznosi se ne slažu matematički: "
                    f"{bez:.2f} + {pdv:.2f} = {bez + pdv:.2f} "
                    f"≠ IZNSAPDV {sa:.2f} (razlika: {diff:.2f} KM) — provjeri ručno."
                )
        except (ValueError, TypeError):
            pass  # Već uhvaćeno u _val_iznosi


# ─────────────────────────────────────────────────────────────────────────────
# Normalizacija i auto-fix
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_amount(value: str) -> str:
    """
    Normalizuje različite formate decimalnih brojeva na standard s tačkom.

    Primjeri:
      '1.234,56'  → '1234.56'
      '1,234.56'  → '1234.56'
      '182,37'    → '182.37'
      '182.37'    → '182.37'
      ''          → ''
    """
    if not value:
        return ""
    v = value.strip().replace(" ", "").replace("\xa0", "")

    if "," in v and "." in v:
        # Koji separator dolazi zadnji = decimalni
        if v.rfind(",") > v.rfind("."):
            v = v.replace(".", "").replace(",", ".")
        else:
            v = v.replace(",", "")
    elif "," in v:
        parts = v.split(",")
        # Ako iza zareza ima 1 ili 2 cifre — to je decimalni separator
        if len(parts) == 2 and len(parts[1]) in (1, 2) and parts[1].isdigit():
            v = v.replace(",", ".")
        else:
            v = v.replace(",", "")

    try:
        return str(round(float(v), 2))
    except (ValueError, TypeError):
        return value  # vrati original ako ne možemo parsirati


def _fix_idpdvpp(raw: str) -> str:
    """Osiguraj da IDPDVPP ima tačno 13 cifara i počinje sa 4."""
    if not raw:
        return raw
    clean = re.sub(r'\D', '', raw)  # samo cifre
    if not clean:
        return raw
    # Dodaj vodeću 4 dok nema 13 cifara
    while len(clean) < 13:
        clean = "4" + clean
    # Ako ima previše, uzmi zadnjih 13 (edge case skenera)
    if len(clean) > 13:
        clean = clean[-13:]
    return clean


def _fix_jibpupp(raw: str, idpdvpp: str) -> str:
    """
    JIBPUPP = IDPDVPP bez prve cifre (12 cifara).
    Ako raw nije popunjen ali idpdvpp jest, automatski derivira.
    """
    if not raw and idpdvpp and len(idpdvpp) == 13:
        return idpdvpp[1:]
    if not raw:
        return raw
    clean = re.sub(r'\D', '', raw)
    if len(clean) == 13 and clean.startswith("4"):
        return clean[1:]
    if len(clean) == 12:
        return clean
    return raw


# ─────────────────────────────────────────────────────────────────────────────
# JSON parser (3 strategije)
# ─────────────────────────────────────────────────────────────────────────────

def parse_response(text: str) -> dict[str, str]:
    """
    Parsira GPT odgovor u dict s tri fallback strategije:
      1. Direktan json.loads nakon uklanjanja markdown blokova
      2. Regex izvlačenje prvog {...} bloka
      3. Regex ekstrakcija ključ-vrijednost parova (zadnji resort)

    Raises ValueError ako nijedna strategija ne uspije.
    """
    # Ukloni markdown blokove
    cleaned = re.sub(r'```(?:json)?\s*', '', text).strip()
    cleaned = re.sub(r'```', '', cleaned).strip()

    # Strategija 1: direktan parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Strategija 2: izvuci prvi JSON objekat
    match = re.search(r'\{[\s\S]*\}', cleaned)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Strategija 3: ručna ekstrakcija ključ-vrijednost parova
    extracted: dict[str, str] = {}
    for key in FIELDS:
        m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
        if m:
            extracted[key] = m.group(1)

    if extracted:
        return extracted

    # Sve strategije neuspješne
    raise ValueError(
        f"Nije moguće parsirati JSON odgovor modela.\n"
        f"Prvih 500 znakova odgovora:\n{text[:500]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_invoice(raw: dict, filename: str = "") -> InvoiceData:
    """
    Kreira InvoiceData iz sirovog dict-a:
      1. Mapira sva FIELDS polja
      2. Normalizuje iznose (tačka kao decimalni separator)
      3. Auto-popravlja IDPDVPP i JIBPUPP
      4. Pokreće validaciju
    """
    inv = InvoiceData(
        _filename=filename,
        _raw_json=json.dumps(raw, ensure_ascii=False),
    )

    for f in FIELDS:
        val = str(raw.get(f, "") or "").strip()
        if f in ("IZNBEZPDV", "IZNPDV", "IZNSAPDV"):
            val = _normalize_amount(val)
        setattr(inv, f, val)

    # Auto-fix ID/PDV brojeva
    inv.IDPDVPP = _fix_idpdvpp(inv.IDPDVPP)
    inv.JIBPUPP = _fix_jibpupp(inv.JIBPUPP, inv.IDPDVPP)

    inv.validate()
    return inv


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI klijent i helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_client() -> OpenAI:
    """Kreira OpenAI klijent. API ključ čita iz .env ili Streamlit Secrets."""
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("OPENAI_API_KEY", "")
        except Exception:
            pass
    if not key:
        raise EnvironmentError(
            "OPENAI_API_KEY nije pronađen. "
            "Postavi ga u .env fajlu ili Streamlit Secrets."
        )
    return OpenAI(api_key=key)


def get_available_models() -> list[str]:
    """Lista podržanih modela."""
    return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]


# ─────────────────────────────────────────────────────────────────────────────
# Glavna ekstrakcija
# ─────────────────────────────────────────────────────────────────────────────

def extract_invoice(
    b64_image:   str,
    media_type:  str = "image/jpeg",
    filename:    str = "",
    model:       str = "gpt-4o",
    max_retries: int = 2,
) -> InvoiceData:
    """
    Šalje sliku fakture GPT-4o Vision modelu i vraća popunjen InvoiceData.

    Parametri
    ---------
    b64_image   : base64-enkodirana slika (string)
    media_type  : MIME tip ('image/jpeg', 'image/png', itd.)
    filename    : originalni naziv fajla (za prikaz)
    model       : OpenAI model
    max_retries : broj ponovnih pokušaja parsiranja ako model vrati loš JSON

    Vraća
    -----
    InvoiceData — uvijek vraća objekat, nikad ne baca exception prema UI-u.
    U slučaju greške, _errors polje će biti popunjeno.
    """
    client = get_client()
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 2):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=1200,
                temperature=0,  # deterministički izlaz za strukturirane podatke
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url":    f"data:{media_type};base64,{b64_image}",
                                    "detail": "high",
                                },
                            },
                            {
                                "type": "text",
                                "text": EXTRACTION_PROMPT,
                            },
                        ],
                    },
                ],
            )

            raw_text = response.choices[0].message.content.strip()
            raw_dict = parse_response(raw_text)
            return build_invoice(raw_dict, filename)

        except (ValueError, json.JSONDecodeError) as e:
            # Greška parsiranja — pokušaj ponovo
            last_error = e
            if attempt <= max_retries:
                continue
            # Svi pokušaji iscrpljeni
            break

        except RateLimitError as e:
            inv = InvoiceData(_filename=filename)
            inv._errors = [
                f"OpenAI Rate Limit: Previše zahtjeva. Pokušaj ponovo za nekoliko sekundi. ({e})"
            ]
            inv._valid = False
            return inv

        except APIConnectionError as e:
            inv = InvoiceData(_filename=filename)
            inv._errors = [f"Problem s konekcijom na OpenAI API: {e}"]
            inv._valid = False
            return inv

        except APIStatusError as e:
            inv = InvoiceData(_filename=filename)
            inv._errors = [
                f"OpenAI API greška (HTTP {e.status_code}): {e.message}"
            ]
            inv._valid = False
            return inv

        except EnvironmentError as e:
            inv = InvoiceData(_filename=filename)
            inv._errors = [str(e)]
            inv._valid = False
            return inv

        except Exception as e:
            inv = InvoiceData(_filename=filename)
            inv._errors = [f"Neočekivana greška ({type(e).__name__}): {e}"]
            inv._valid = False
            return inv

    # Svi pokušaji parsiranja neuspješni
    inv = InvoiceData(_filename=filename)
    inv._errors = [
        f"Nije moguće parsirati odgovor modela nakon {max_retries + 1} pokušaj(a). "
        f"Zadnja greška: {last_error}"
    ]
    inv._valid = False
    return inv