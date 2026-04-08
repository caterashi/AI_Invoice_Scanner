"""
excel_export.py
===============
Excel export / import za fakture.

Funkcije:
  save_invoices()        — spremi listu InvoiceData u Excel fajl
  invoices_to_bytes()    — vrati Excel workbook kao bajte (za Streamlit download)
  load_invoices()        — učitaj postojeće fakture iz Excel fajla
  add_invoice()          — dodaj jednu fakturu u worksheet
  _create_workbook()     — kreiraj novi workbook s headerima i stilovima
  _apply_styles()        — postavi stilove na header/data redove
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
from typing import Union

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

# Uvoz modela — fallback ako ai_extractor nije instaliran
try:
    from ai_extractor import FIELDS, InvoiceData
except ImportError:
    FIELDS = [
        "BROJFAKT", "DATUMF", "DATUMPF",
        "NAZIVPP", "SJEDISTEPP",
        "IDPDVPP", "JIBPUPP",
        "IZNBEZPDV", "IZNPDV", "IZNSAPDV",
    ]
    InvoiceData = None  # type: ignore

# ─────────────────────────────────────────────────────────────────────────────
# Nazivi kolona za Excel header (isti redosljed kao FIELDS)
# ─────────────────────────────────────────────────────────────────────────────

COLUMN_HEADERS: dict[str, str] = {
    "BROJFAKT":   "Broj fakture",
    "DATUMF":     "Datum fakture",
    "DATUMPF":    "Datum prijema",
    "NAZIVPP":    "Naziv dobavljača",
    "SJEDISTEPP": "Sjedište dobavljača",
    "IDPDVPP":    "JIB / ID (13 cifara)",
    "JIBPUPP":    "PDV broj (12 cifara)",
    "IZNBEZPDV":  "Iznos bez PDV (KM)",
    "IZNPDV":     "PDV iznos (KM)",
    "IZNSAPDV":   "Ukupno s PDV (KM)",
}

# Redni brojevi stupaca (1-based, Excel)
_COL_MAP: dict[str, int] = {f: i + 2 for i, f in enumerate(FIELDS)}
# Stupac A = redni broj fakture
_COL_INDEX  = 1
_FIRST_DATA_ROW = 3   # Red 1 = naslov, Red 2 = header

# ─────────────────────────────────────────────────────────────────────────────
# Stilovi
# ─────────────────────────────────────────────────────────────────────────────

_TITLE_FONT   = Font(name="Calibri", bold=True, size=14, color="FFFFFF")
_TITLE_FILL   = PatternFill("solid", fgColor="1F3864")
_TITLE_ALIGN  = Alignment(horizontal="center", vertical="center")

_HDR_FONT     = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
_HDR_FILL     = PatternFill("solid", fgColor="2E75B6")
_HDR_ALIGN    = Alignment(horizontal="center", vertical="center", wrap_text=True)

_DATA_FONT    = Font(name="Calibri", size=10)
_DATA_ALIGN_L = Alignment(horizontal="left",  vertical="center", indent=1)
_DATA_ALIGN_R = Alignment(horizontal="right", vertical="center", indent=1)
_DATA_ALIGN_C = Alignment(horizontal="center", vertical="center")

_ALT_FILL     = PatternFill("solid", fgColor="D9E2F3")  # svaki 2. red
_BORDER_SIDE  = Side(style="thin", color="BDD7EE")
_CELL_BORDER  = Border(
    left=_BORDER_SIDE, right=_BORDER_SIDE,
    top=_BORDER_SIDE,  bottom=_BORDER_SIDE
)

_AMOUNT_FORMAT = '#,##0.00'
_DATE_FORMAT   = 'DD.MM.YYYY'

# Polja koja su iznosi (desna poravnanost + format)
_AMOUNT_FIELDS = {"IZNBEZPDV", "IZNPDV", "IZNSAPDV"}
# Polja koja su datumi
_DATE_FIELDS   = {"DATUMF", "DATUMPF"}
# Polja koji su numerički ID-evi (centrirati)
_ID_FIELDS     = {"IDPDVPP", "JIBPUPP"}


# ─────────────────────────────────────────────────────────────────────────────
# Kreiranje novog workbooka
# ─────────────────────────────────────────────────────────────────────────────

def _create_workbook() -> tuple[Workbook, Worksheet]:
    """Kreira novi workbook s naslovnim redom i headerima stupaca."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Fakture"

    total_cols = len(FIELDS) + 1   # +1 za redni broj

    # ── Red 1: Naslov ────────────────────────────────────────────────────────
    ws.row_dimensions[1].height = 28
    ws.merge_cells(
        start_row=1, start_column=1,
        end_row=1,   end_column=total_cols
    )
    title_cell = ws.cell(row=1, column=1)
    title_cell.value    = f"Evidencija faktura — generisano {datetime.now().strftime('%d.%m.%Y')}"
    title_cell.font     = _TITLE_FONT
    title_cell.fill     = _TITLE_FILL
    title_cell.alignment = _TITLE_ALIGN

    # ── Red 2: Headeri ───────────────────────────────────────────────────────
    ws.row_dimensions[2].height = 36
    ws.cell(row=2, column=_COL_INDEX).value = "#"
    ws.cell(row=2, column=_COL_INDEX).font  = _HDR_FONT
    ws.cell(row=2, column=_COL_INDEX).fill  = _HDR_FILL
    ws.cell(row=2, column=_COL_INDEX).alignment = _HDR_ALIGN

    for field, col in _COL_MAP.items():
        c = ws.cell(row=2, column=col)
        c.value     = COLUMN_HEADERS.get(field, field)
        c.font      = _HDR_FONT
        c.fill      = _HDR_FILL
        c.alignment = _HDR_ALIGN

    # ── Freeze: zaglavlje ostaje vidljivo pri scrollanju ─────────────────────
    ws.freeze_panes = f"A{_FIRST_DATA_ROW}"

    # ── Početne širine stupaca ───────────────────────────────────────────────
    ws.column_dimensions["A"].width = 5   # redni broj
    _DEFAULT_WIDTHS = {
        "BROJFAKT": 18, "DATUMF": 14, "DATUMPF": 14,
        "NAZIVPP": 35,  "SJEDISTEPP": 35,
        "IDPDVPP": 18,  "JIBPUPP": 16,
        "IZNBEZPDV": 16, "IZNPDV": 14, "IZNSAPDV": 16,
    }
    for field, col in _COL_MAP.items():
        ws.column_dimensions[get_column_letter(col)].width = _DEFAULT_WIDTHS.get(field, 14)

    return wb, ws


# ─────────────────────────────────────────────────────────────────────────────
# Dodavanje jedne fakture
# ─────────────────────────────────────────────────────────────────────────────

def add_invoice(
    ws: Worksheet,
    invoice: "InvoiceData",
    row_num: int,
) -> None:
    """
    Dodaje jednu fakturu u worksheet u zadani red.

    Parametri
    ---------
    ws       : aktivni worksheet
    invoice  : InvoiceData objekat (ili dict s istim ključevima)
    row_num  : redni broj (1-based, za prikaz u koloni A)
    """
    excel_row = _FIRST_DATA_ROW + row_num - 1
    alt       = (row_num % 2 == 0)

    # Stupac A: redni broj
    _write_cell(ws, excel_row, _COL_INDEX, row_num, alt,
                align=_DATA_ALIGN_C)

    # Ostali stupci
    data = invoice.to_dict() if hasattr(invoice, "to_dict") else dict(invoice)

    for field, col in _COL_MAP.items():
        raw_val = data.get(field, "")

        # Konvertuj iznose u float za Excel (broj format)
        if field in _AMOUNT_FIELDS and raw_val:
            try:
                value = float(raw_val)
                _write_cell(ws, excel_row, col, value, alt,
                            align=_DATA_ALIGN_R,
                            num_format=_AMOUNT_FORMAT)
                continue
            except (ValueError, TypeError):
                pass  # padni na string

        align = (
            _DATA_ALIGN_R if field in _AMOUNT_FIELDS
            else _DATA_ALIGN_C if field in _ID_FIELDS | _DATE_FIELDS
            else _DATA_ALIGN_L
        )
        _write_cell(ws, excel_row, col, raw_val, alt, align=align)


def _write_cell(
    ws: Worksheet,
    row: int, col: int,
    value,
    alt: bool,
    align: Alignment = None,
    num_format: str = None,
) -> None:
    """Upiši vrijednost u ćeliju i primijeni stilove."""
    c = ws.cell(row=row, column=col, value=value)
    c.font   = _DATA_FONT
    c.border = _CELL_BORDER
    if alt:
        c.fill = _ALT_FILL
    if align:
        c.alignment = align
    if num_format:
        c.number_format = num_format
    ws.row_dimensions[row].height = 18


# ─────────────────────────────────────────────────────────────────────────────
# Spremi listu faktura u fajl
# ─────────────────────────────────────────────────────────────────────────────

def save_invoices(
    invoices: list,
    output_path: Union[str, Path],
) -> int:
    """
    Spremi listu InvoiceData objekata u Excel fajl.

    - Ako fajl postoji, učitava ga i nastavlja od zadnjeg reda.
    - Ako fajl ne postoji, kreira novi.
    - Kreira sve potrebne direktorije automatski.

    Parametri
    ---------
    invoices    : lista InvoiceData objekata
    output_path : putanja do Excel fajla (.xlsx)

    Vraća
    -----
    Broj uspješno dodanih faktura.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Učitaj postojeći ili kreira novi workbook
    if path.exists():
        wb = load_workbook(str(path))
        ws = wb["Fakture"] if "Fakture" in wb.sheetnames else wb.active
        # Pronađi zadnji popunjeni red
        last_row = ws.max_row
        # Odredi redni broj za sljedeći unos
        next_num = max(1, last_row - _FIRST_DATA_ROW + 2)
    else:
        wb, ws = _create_workbook()
        next_num = 1

    added = 0
    for inv in invoices:
        try:
            add_invoice(ws, inv, next_num)
            next_num += 1
            added += 1
        except Exception as e:
            # Logiraj grešku ali nastavi s ostalima
            print(f"[excel_export] Greška pri dodavanju fakture: {e}")

    if added > 0:
        wb.save(str(path))

    return added, []


# ─────────────────────────────────────────────────────────────────────────────
# Vrati Excel kao bajte (za Streamlit download)
# ─────────────────────────────────────────────────────────────────────────────

def invoices_to_bytes(invoices: list) -> bytes:
    """
    Generiše Excel workbook s fakturama i vraća ga kao bajte.

    Koristi se za st.download_button() u Streamlitu — ne sprema na disk.

    Parametri
    ---------
    invoices : lista InvoiceData objekata

    Vraća
    -----
    bytes — sadržaj .xlsx fajla
    """
    wb, ws = _create_workbook()

    for i, inv in enumerate(invoices, start=1):
        try:
            add_invoice(ws, inv, i)
        except Exception as e:
            print(f"[excel_export] Greška pri generisanju bajta: {e}")

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Učitaj fakture iz postojećeg Excel fajla
# ─────────────────────────────────────────────────────────────────────────────

def load_invoices(path: Union[str, Path]) -> list[dict]:
    """
    Učitaj fakture iz postojećeg Excel fajla.

    Koristi pandas read_excel za robusno čitanje.
    Vraća praznu listu ako fajl ne postoji ili je prazan.

    Parametri
    ---------
    path : putanja do .xlsx fajla

    Vraća
    -----
    Lista dict-ova s ključevima iz COLUMN_HEADERS (reversed mapping → FIELDS ključevi).
    """
    p = Path(path)
    if not p.exists():
        return []

    try:
        df = pd.read_excel(
            str(p),
            sheet_name="Fakture",
            header=1,        # Red 2 u Excelu (0-indexed = 1)
            dtype=str,       # Sve kao string da izbjegnemo float konverzije
            skiprows=[0],    # Preskoči naslovni red (Red 1)
        )
    except Exception as e:
        print(f"[excel_export] Greška pri čitanju Excel fajla '{p}': {e}")
        return []

    if df.empty:
        return []

    # Reverse mapping: "Broj fakture" → "BROJFAKT"
    header_to_field = {v: k for k, v in COLUMN_HEADERS.items()}

    rows: list[dict] = []
    for _, row in df.iterrows():
        record: dict[str, str] = {}
        for col_header, field_key in header_to_field.items():
            val = row.get(col_header, "")
            # Pandas čita NaN — konvertuj u prazan string
            record[field_key] = "" if pd.isna(val) else str(val).strip()
        rows.append(record)

    return rows
