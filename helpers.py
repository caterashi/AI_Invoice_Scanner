"""
helpers.py
==========
Pomoćne funkcije:
  - format_amount()         — formatiranje iznosa s valutom
  - validate_oib()          — validacija OIB-a (ISO 7064, MOD 11,10)
  - validate_jib()          — validacija JIB/ID broja (13 cifara, počinje s 4)
  - validate_pdv_number()   — validacija PDV broja (12 cifara)
  - validate_invoice_number() — provjera broja računa (nije prazan + regex)
  - normalize_amount()      — normalizacija decimalnog separatora
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


# ─────────────────────────────────────────────────────────────────────────────
# Formatiranje iznosa
# ─────────────────────────────────────────────────────────────────────────────

def format_amount(value, currency: str = "KM") -> str:
    """
    Formatira decimalni iznos u čitljivi string s oznakom valute.

    Primjeri:
      format_amount(1234.5)       → '1.234,50 KM'
      format_amount(0)            → '0,00 KM'
      format_amount("182.37")     → '182,37 KM'
      format_amount("", "EUR")    → '— EUR'
      format_amount(None)         → '— KM'
    """
    if value is None or value == "":
        return f"— {currency}"
    try:
        d = Decimal(str(value))
        # Format s tačkom kao tisućnim i zarezom kao decimalnim (BiH standard)
        int_part, dec_part = f"{d:.2f}".split(".")
        int_formatted = ""
        for i, ch in enumerate(reversed(int_part)):
            if i > 0 and i % 3 == 0 and ch != "-":
                int_formatted = "." + int_formatted
            int_formatted = ch + int_formatted
        return f"{int_formatted},{dec_part} {currency}"
    except (InvalidOperation, TypeError, ValueError):
        return f"— {currency}"


# ─────────────────────────────────────────────────────────────────────────────
# Validacija OIB (Hrvatska, ISO 7064 MOD 11,10)
# ─────────────────────────────────────────────────────────────────────────────

def validate_oib(oib: str) -> tuple[bool, str]:
    """
    Validira hrvatski OIB prema ISO 7064, MOD 11,10 algoritmu.

    Algoritam:
      1. Počni s product = 10
      2. Za svaku od prvih 10 cifara:
           sum = (int(cifra) + product) % 10
           if sum == 0: sum = 10
           product = (sum * 2) % 11
      3. check = 11 - product
           if check == 10: check = 0
      4. check mora biti jednak 11. cifri OIB-a

    Parametri
    ---------
    oib : string koji se validira (razmaci se ignoruju)

    Vraća
    -----
    (True, "OK") ili (False, poruka_greške)
    """
    if not oib:
        return False, "OIB je prazan."

    oib_clean = re.sub(r"\s", "", oib)

    if not oib_clean.isdigit():
        return False, "OIB mora sadržavati samo znamenke."

    if len(oib_clean) != 11:
        return False, f"OIB mora imati tačno 11 znamenki (ima {len(oib_clean)})."

    # ISO 7064, MOD 11,10 provjera
    product = 10
    for digit in oib_clean[:10]:
        total = (int(digit) + product) % 10
        if total == 0:
            total = 10
        product = (total * 2) % 11

    check = 11 - product
    if check == 10:
        check = 0

    if check != int(oib_clean[10]):
        return False, (
            f"OIB kontrolna znamenka nije ispravna "
            f"(očekivano: {check}, pronađeno: {oib_clean[10]})."
        )

    return True, "OK"


# ─────────────────────────────────────────────────────────────────────────────
# Validacija JIB / ID broja (BiH dobavljači)
# ─────────────────────────────────────────────────────────────────────────────

def validate_jib(jib: str) -> tuple[bool, str]:
    """
    Validira JIB/ID broj dobavljača.

    Pravila:
      - Tačno 13 cifara
      - Mora počinjati sa cifrom 4

    Parametri
    ---------
    jib : string koji se validira (razmaci se ignoruju)

    Vraća
    -----
    (True, "OK") ili (False, poruka_greške)
    """
    if not jib:
        return False, "JIB je prazan."

    clean = re.sub(r"\s", "", jib)

    if not clean.isdigit():
        return False, f"JIB mora sadržavati samo cifre, pronađeno: '{jib}'."

    if len(clean) != 13:
        return False, (
            f"JIB mora imati tačno 13 cifara "
            f"(ima {len(clean)}: '{clean}')."
        )

    if not clean.startswith("4"):
        return False, f"JIB mora počinjati sa cifrom 4 (počinje sa '{clean[0]}')."

    return True, "OK"


# ─────────────────────────────────────────────────────────────────────────────
# Validacija PDV broja
# ─────────────────────────────────────────────────────────────────────────────

def validate_pdv_number(pdv: str) -> tuple[bool, str]:
    """
    Validira PDV broj dobavljača.

    Pravila:
      - Tačno 12 cifara
      - Prazan string je OK (firma nije PDV obveznik)

    Parametri
    ---------
    pdv : string koji se validira (razmaci se ignoruju)

    Vraća
    -----
    (True, "OK") ili (False, poruka_greške)
    """
    if not pdv:
        return True, "Prazan — firma nije u PDV sistemu (OK)."

    clean = re.sub(r"\s", "", pdv)

    if not clean.isdigit():
        return False, f"PDV broj mora sadržavati samo cifre, pronađeno: '{pdv}'."

    if len(clean) != 12:
        return False, (
            f"PDV broj mora imati tačno 12 cifara "
            f"(ima {len(clean)}: '{clean}')."
        )

    return True, "OK"


# ─────────────────────────────────────────────────────────────────────────────
# Validacija broja računa/fakture
# ─────────────────────────────────────────────────────────────────────────────

# Dozvoljeni znakovi u broju fakture: slova, cifre, crtice, kose crte, tačke, razmaci, zagrade
_INVOICE_NUMBER_PATTERN = re.compile(r"^[\w\d\-\/\.\s\(\)]+$", re.UNICODE)
# Minimalna dužina broja fakture
_INVOICE_NUMBER_MIN_LEN = 1
# Maksimalna dužina broja fakture
_INVOICE_NUMBER_MAX_LEN = 50


def validate_invoice_number(broj: str) -> tuple[bool, str]:
    """
    Validira broj računa/fakture.

    Provjere:
      1. Nije None ili prazan string
      2. Nije kraći od {_INVOICE_NUMBER_MIN_LEN} znaka
      3. Nije duži od {_INVOICE_NUMBER_MAX_LEN} znakova
      4. Sadrži samo dozvoljene znakove (regex)

    Parametri
    ---------
    broj : string s brojem fakture

    Vraća
    -----
    (True, "OK") ili (False, poruka_greške)
    """
    if not broj or not str(broj).strip():
        return False, "Broj računa ne smije biti prazan."

    stripped = str(broj).strip()

    if len(stripped) < _INVOICE_NUMBER_MIN_LEN:
        return False, f"Broj računa je prekratak (min {_INVOICE_NUMBER_MIN_LEN} znak)."

    if len(stripped) > _INVOICE_NUMBER_MAX_LEN:
        return False, (
            f"Broj računa je predugačak "
            f"(max {_INVOICE_NUMBER_MAX_LEN} znakova, ima {len(stripped)})."
        )

    if not _INVOICE_NUMBER_PATTERN.match(stripped):
        # Pronađi koji znakovi nisu dozvoljeni
        bad_chars = sorted(set(
            ch for ch in stripped
            if not re.match(r"[\w\d\-\/\.\s\(\)]", ch, re.UNICODE)
        ))
        return False, (
            f"Broj računa sadrži nedozvoljene znakove: "
            f"{', '.join(repr(c) for c in bad_chars)}"
        )

    return True, "OK"


# ─────────────────────────────────────────────────────────────────────────────
# Normalizacija decimalnog separatora
# ─────────────────────────────────────────────────────────────────────────────

def normalize_amount(value: str) -> str:
    """
    Normalizuje različite formate decimalnih iznosa u standard s tačkom.

    Podržani ulazni formati:
      '1.234,56'  → '1234.56'   (EU format: tačka=tisućni, zarez=decimalni)
      '1,234.56'  → '1234.56'   (US format: zarez=tisućni, tačka=decimalni)
      '182,37'    → '182.37'    (BiH format: samo decimalni zarez)
      '182.37'    → '182.37'    (standard, nepromijenjen)
      '0'         → '0.0'
      ''          → ''

    Parametri
    ---------
    value : string s iznosom

    Vraća
    -----
    Normalizovani string s tačkom kao decimalnim separatorom,
    ili originalni string ako parsiranje nije moguće.
    """
    if not value:
        return ""

    v = str(value).strip().replace(" ", "").replace("\xa0", "")

    if "," in v and "." in v:
        # Koji separator dolazi zadnji = decimalni separator
        if v.rfind(",") > v.rfind("."):
            # '1.234,56' → EU format
            v = v.replace(".", "").replace(",", ".")
        else:
            # '1,234.56' → US format
            v = v.replace(",", "")
    elif "," in v:
        parts = v.split(",")
        # Ako iza zareza 1 ili 2 cifre → decimalni separator
        if len(parts) == 2 and len(parts[1]) in (1, 2) and parts[1].isdigit():
            v = v.replace(",", ".")
        else:
            v = v.replace(",", "")

    try:
        return str(round(float(v), 2))
    except (ValueError, TypeError):
        return value  # vrati original ako ne možemo parsirati
