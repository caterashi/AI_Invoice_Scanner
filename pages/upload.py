"""
pages/upload.py
===============
KIF  → ai_extractor.py              (extract_invoices_from_pdf, InvoiceData, FIELDS)
KUF  → kuf_extractor.py             (extract_kuf_from_pdf, KUFData, KUF_FIELDS)
Promet → dnevni_promet_extractor.py (extract_promet_from_pdf, DnevniPrometData, PROMET_FIELDS)
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st

# ── KIF ───────────────────────────────────────────────────────────────────────
from ai_extractor import FIELDS as KIF_FIELDS
from ai_extractor import InvoiceData as KIFData
from ai_extractor import extract_invoices_from_pdf as extract_kif_from_pdf

# ── KUF ───────────────────────────────────────────────────────────────────────
from kuf_extractor import KUF_FIELDS, KUFData, extract_kuf_from_pdf

# ── Dnevni promet ─────────────────────────────────────────────────────────────
from dnevni_promet_extractor import (
    PROMET_FIELDS,
    DnevniPrometData,
    extract_promet_from_pdf,
)

_DARK_KEY = "app_dark_mode"
_SHARED_SAVE_KEY = "shared_saved_records"

KIF_HEADERS = {
    "BROJFAKT": "Broj fakture",
    "DATUMF": "Datum fakture",
    "DATUMPF": "Datum prijema",
    "NAZIVPP": "Kupac / primalac",
    "SJEDISTEPP": "Sjedište kupca",
    "IDPDVPP": "ID PDV",
    "JIBPUPP": "JIB",
    "IZNBEZPDV": "Iznos bez PDV",
    "IZNSAPDV": "Iznos sa PDV",
    "IZNPDV": "Iznos PDV",
}

KUF_HEADERS = {
    "BROJ_DOKUMENTA": "Broj dokumenta",
    "DATUM_DOKUMENTA": "Datum dokumenta",
    "DATUM_PRIJEMA": "Datum prijema",
    "DOBAVLJAC_NAZIV": "Dobavljač",
    "DOBAVLJAC_SJEDISTE": "Sjedište dobavljača",
    "DOBAVLJAC_IDPDV": "ID PDV dobavljača",
    "DOBAVLJAC_JIB": "JIB dobavljača",
    "IZNOS_BEZ_PDV": "Iznos bez PDV",
    "IZNOS_PDV": "Iznos PDV",
    "IZNOS_SA_PDV": "Iznos sa PDV",
    "VRSTA_DOKUMENTA": "Vrsta dokumenta",
}

PROMET_HEADERS = {
    "DATUM_PROMETA": "Datum prometa",
    "BROJ_DNEVNOG_IZVJESTAJA": "Broj dnevnog izvještaja",
    "POSLJEDNJI_BF": "Posljednji BF",
    "POSLJEDNJI_RF": "Posljednji RF",
    "BROJ_IZDATIH_FAKTURA": "Broj izdatih faktura",
    "UKUPAN_DNEVNI_PROMET": "Ukupan dnevni promet",
    "POSLOVNA_JEDINICA": "Poslovna jedinica",
    "FISKALNI_UREDJAJ": "Fiskalni uređaj",
}

_KIND_CONFIG: dict[str, dict[str, Any]] = {
    "kif": {
        "title": "📥 KIF – Knjiga izlaznih faktura",
        "subtitle": "Izlazne fakture / KIF.",
        "uploader_label": "Odaberi KIF PDF dokumente",
        "parser": extract_kif_from_pdf,
        "model_cls": KIFData,
        "fields": KIF_FIELDS,
        "headers": KIF_HEADERS,
        "excel_prefix": "kif",
        "sheet_name": "KIF",
        "saved_label": "KIF stavke",
        "results_key": "upload_results_kif",
        "errors_key": "upload_errors_kif",
        "last_run_key": "upload_last_run_kif",
        "editor_key": "upload_editor_kif",
        "saved_key": "saved_kif_records",
    },
    "kuf": {
        "title": "📤 KUF – Knjiga ulaznih faktura",
        "subtitle": "Ulazne fakture / KUF.",
        "uploader_label": "Odaberi KUF PDF dokumente",
        "parser": extract_kuf_from_pdf,
        "model_cls": KUFData,
        "fields": KUF_FIELDS,
        "headers": KUF_HEADERS,
        "excel_prefix": "kuf",
        "sheet_name": "KUF",
        "saved_label": "KUF stavke",
        "results_key": "upload_results_kuf",
        "errors_key": "upload_errors_kuf",
        "last_run_key": "upload_last_run_kuf",
        "editor_key": "upload_editor_kuf",
        "saved_key": "saved_kuf_records",
    },
    "promet": {
        "title": "🧾 Dnevni promet",
        "subtitle": "Dnevni izvještaji i fiskalni promet.",
        "uploader_label": "Odaberi PDF dokumente dnevnog prometa",
        "parser": extract_promet_from_pdf,
        "model_cls": DnevniPrometData,
        "fields": PROMET_FIELDS,
        "headers": PROMET_HEADERS,
        "excel_prefix": "dnevni_promet",
        "sheet_name": "DNEVNI_PROMET",
        "saved_label": "Dnevni promet stavke",
        "results_key": "upload_results_promet",
        "errors_key": "upload_errors_promet",
        "last_run_key": "upload_last_run_promet",
        "editor_key": "upload_editor_promet",
        "saved_key": "saved_promet_records",
    },
}


def render_upload() -> None:
    _init_state()
    dark_mode = _force_dark_mode()
    _apply_upload_theme(dark_mode)
    _render_saved_summary()

    tab1, tab2, tab3 = st.tabs(["KIF", "KUF", "Dnevni promet"])
    with tab1:
        _render_kind_upload("kif")
    with tab2:
        _render_kind_upload("kuf")
    with tab3:
        _render_kind_upload("promet")


def _init_state() -> None:
    if _DARK_KEY not in st.session_state:
        st.session_state[_DARK_KEY] = True
    if _SHARED_SAVE_KEY not in st.session_state:
        st.session_state[_SHARED_SAVE_KEY] = {"kif": [], "kuf": [], "promet": []}
    if "invoices" not in st.session_state:
        st.session_state["invoices"] = []
    if "last_export" not in st.session_state:
        st.session_state["last_export"] = None

    for cfg in _KIND_CONFIG.values():
        for k in ("results_key", "errors_key"):
            if cfg[k] not in st.session_state:
                st.session_state[cfg[k]] = []
        if cfg["last_run_key"] not in st.session_state:
            st.session_state[cfg["last_run_key"]] = None
        if cfg["saved_key"] not in st.session_state:
            st.session_state[cfg["saved_key"]] = []


def _force_dark_mode() -> bool:
    st.session_state[_DARK_KEY] = True
    return True


def _render_saved_summary() -> None:
    st.markdown("<div class='section-title'>Sačuvane stavke</div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for col, kind in zip(cols, ["kif", "kuf", "promet"]):
        cfg = _KIND_CONFIG[kind]
        count = len(st.session_state.get(cfg["saved_key"], []))
        with col:
            st.markdown(
                f"<div class='upload-card'><b>{cfg['saved_label']}:</b> {count}</div>",
                unsafe_allow_html=True,
            )


def _render_kind_upload(kind: str) -> None:
    cfg = _KIND_CONFIG[kind]

    st.markdown(
        f"<div class='upload-card'><b>{cfg['title']}</b><br>"
        f"<span class='upload-muted'>{cfg['subtitle']}</span></div>",
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        cfg["uploader_label"],
        type=["pdf"],
        accept_multiple_files=True,
        key=f"uploader_{kind}",
    )

    if not uploaded_files:
        _render_empty_state(kind)
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(
            f"<div class='upload-card'><b>Odabrano fajlova:</b> {len(uploaded_files)}</div>",
            unsafe_allow_html=True,
        )
    with col2:
        run = st.button(
            f"Pokreni ekstrakciju – {cfg['sheet_name']}",
            type="primary",
            use_container_width=True,
            key=f"run_{kind}",
        )

    if run:
        _run_extraction(kind, uploaded_files)

    results = st.session_state.get(cfg["results_key"], [])
    errors = st.session_state.get(cfg["errors_key"], [])
    last_run = st.session_state.get(cfg["last_run_key"])

    if last_run:
        st.caption(f"Zadnje pokretanje: {last_run}")

    if errors:
        with st.expander(f"⚠️ Greške i upozorenja ({len(errors)})", expanded=True):
            for err in errors:
                st.error(err)

    if not results:
        return

    st.markdown("<div class='section-title'>Pregled ekstrahiranih podataka</div>", unsafe_allow_html=True)
    edited_rows = _render_editor(kind, results)
    prepared = _rows_to_records(kind, edited_rows, results)

    st.markdown("<div class='section-title'>Akcije</div>", unsafe_allow_html=True)
    col_save, col_download, col_clear = st.columns(3)

    with col_save:
        if st.button("Sačuvaj stavke", type="primary", use_container_width=True, key=f"save_{kind}"):
            _save_records(kind, prepared)
            st.success(f"Sačuvano stavki: {len(prepared)}")

    with col_download:
        st.download_button(
            "Preuzmi Excel",
            data=_records_to_excel_bytes(kind, prepared),
            file_name=_excel_filename(cfg["excel_prefix"]),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"download_{kind}",
        )

    with col_clear:
        if st.button("Očisti rezultat", use_container_width=True, key=f"clear_{kind}"):
            st.session_state[cfg["results_key"]] = []
            st.session_state[cfg["errors_key"]] = []
            st.session_state[cfg["last_run_key"]] = None
            st.session_state.pop(cfg["editor_key"], None)
            st.rerun()


def _run_extraction(kind: str, uploaded_files: list) -> None:
    cfg = _KIND_CONFIG[kind]
    parser = cfg["parser"]
    all_results = []
    all_errors: list[str] = []

    progress = st.progress(0, text=f"Priprema ekstrakcije ({cfg['title']})…")

    for idx, uploaded in enumerate(uploaded_files, start=1):
        progress.progress((idx - 1) / max(len(uploaded_files), 1), text=f"Obrađujem {uploaded.name}")
        pdf_bytes = uploaded.read()
        try:
            items = parser(pdf_bytes, filename=uploaded.name)
            if not items:
                all_errors.append(f"{uploaded.name}: Nema pronađenih stavki.")
                continue

            if not isinstance(items, list):
                items = [items]

            for record in items:
                _set_attr(record, "filename", uploaded.name)
                warnings = _refresh_warnings(kind, record)
                _set_attr(record, "warnings", warnings)
                _set_attr(record, "valid", len(warnings) == 0)
                if warnings:
                    all_errors.append(f"{uploaded.name}: {', '.join(warnings)}")
                all_results.append(record)
        except Exception as exc:
            all_errors.append(f"{uploaded.name}: {exc}")

    progress.progress(1.0, text="Ekstrakcija završena.")
    st.session_state[cfg["results_key"]] = all_results
    st.session_state[cfg["errors_key"]] = all_errors
    st.session_state[cfg["last_run_key"]] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    st.session_state.pop(cfg["editor_key"], None)

    if all_results:
        st.success(f"Pronađeno stavki: {len(all_results)}")
    else:
        st.warning("Nijedna stavka nije ekstrahovana.")


def _render_editor(kind: str, records: list[Any]) -> list[dict[str, str]]:
    cfg = _KIND_CONFIG[kind]
    fields = cfg["fields"]
    headers = cfg["headers"]
    df = _to_editor_df(kind, records)

    column_config: dict[str, Any] = {
        "Status": st.column_config.TextColumn("Status", width="small", disabled=True),
        "Izvor": st.column_config.TextColumn("Izvor", width="medium", disabled=True),
    }
    for field in fields:
        label = headers[field]
        width = "large" if len(label) > 15 else "medium"
        column_config[label] = st.column_config.TextColumn(label, width=width)

    edited_df = st.data_editor(
        df,
        key=cfg["editor_key"],
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config=column_config,
    )

    return [
        {field: str(row.get(headers[field], "") or "").strip() for field in fields}
        for _, row in edited_df.iterrows()
    ]


def _to_editor_df(kind: str, records: list[Any]) -> pd.DataFrame:
    cfg = _KIND_CONFIG[kind]
    fields = cfg["fields"]
    headers = cfg["headers"]
    rows = []

    for record in records:
        row: dict[str, Any] = {
            "Status": "⚠️" if _get_attr(record, "warnings") else "",
            "Izvor": _get_attr(record, "filename") or "",
        }
        for field in fields:
            row[headers[field]] = getattr(record, field, "")
        rows.append(row)

    return pd.DataFrame(rows)


def _rows_to_records(kind: str, rows: list[dict[str, str]], originals: list[Any]) -> list[Any]:
    cfg = _KIND_CONFIG[kind]
    model_cls = cfg["model_cls"]
    fields = cfg["fields"]
    prepared = []

    for idx, row in enumerate(rows):
        payload = {field: row.get(field, "") for field in fields}
        record = model_cls(**payload)
        if idx < len(originals):
            _set_attr(record, "filename", _get_attr(originals[idx], "filename") or "")
        warnings = _refresh_warnings(kind, record)
        _set_attr(record, "warnings", warnings)
        _set_attr(record, "valid", len(warnings) == 0)
        prepared.append(record)

    return prepared


def _refresh_warnings(kind: str, record: Any) -> list[str]:
    w: list[str] = []

    if kind == "kif":
        if not getattr(record, "BROJFAKT", ""):
            w.append("BROJFAKT nije pronađen")
        if not getattr(record, "DATUMF", ""):
            w.append("DATUMF nije pronađen")
        if not getattr(record, "NAZIVPP", ""):
            w.append("NAZIVPP nije pronađen")
        if not getattr(record, "IZNSAPDV", ""):
            w.append("IZNSAPDV nije pronađen")
        _check_amounts(
            w,
            getattr(record, "IZNBEZPDV", ""),
            getattr(record, "IZNPDV", ""),
            getattr(record, "IZNSAPDV", ""),
        )

    elif kind == "kuf":
        if not getattr(record, "BROJ_DOKUMENTA", ""):
            w.append("BROJ_DOKUMENTA nije pronađen")
        if not getattr(record, "DATUM_DOKUMENTA", ""):
            w.append("DATUM_DOKUMENTA nije pronađen")
        if not getattr(record, "DOBAVLJAC_NAZIV", ""):
            w.append("DOBAVLJAC_NAZIV nije pronađen")
        if not getattr(record, "IZNOS_SA_PDV", ""):
            w.append("IZNOS_SA_PDV nije pronađen")
        _check_amounts(
            w,
            
