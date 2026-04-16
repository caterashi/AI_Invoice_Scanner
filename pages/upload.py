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

from ai_extractor import FIELDS as KIF_FIELDS
from ai_extractor import InvoiceData as KIFData
from ai_extractor import extract_invoices_from_pdf as extract_kif_from_pdf
from dnevni_promet_extractor import (
    DnevniPrometData,
    PROMET_FIELDS,
    extract_promet_from_pdf,
)
from kuf_extractor import KUF_FIELDS, KUFData, extract_kuf_from_pdf

_DARK_KEY = "app_dark_mode"
_SHARED_SAVE_KEY = "shared_saved_records"
_SELECTED_KIND_KEY = "selected_upload_kind"

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
        "short": "KIF",
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
        "short": "KUF",
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
        "short": "Dnevni promet",
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
    _render_kind_selector()
    _render_kind_upload(st.session_state[_SELECTED_KIND_KEY])



def _init_state() -> None:
    if _DARK_KEY not in st.session_state:
        st.session_state[_DARK_KEY] = True
    if _SHARED_SAVE_KEY not in st.session_state:
        st.session_state[_SHARED_SAVE_KEY] = {"kif": [], "kuf": [], "promet": []}
    if _SELECTED_KIND_KEY not in st.session_state:
        st.session_state[_SELECTED_KIND_KEY] = "kif"
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



def _render_kind_selector() -> None:
    st.markdown("<div class='section-title'>Odaberi tip dokumenta</div>", unsafe_allow_html=True)
    cols = st.columns(3)
    order = ["kif", "kuf", "promet"]

    for col, kind in zip(cols, order):
        cfg = _KIND_CONFIG[kind]
        active = st.session_state.get(_SELECTED_KIND_KEY) == kind
        label = f"{'● ' if active else ''}{cfg['short']}"
        with col:
            if st.button(label, key=f"select_{kind}", use_container_width=True, type="primary" if active else "secondary"):
                st.session_state[_SELECTED_KIND_KEY] = kind
                st.rerun()



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
            getattr(record, "IZNOS_BEZ_PDV", ""),
            getattr(record, "IZNOS_PDV", ""),
            getattr(record, "IZNOS_SA_PDV", ""),
        )

    elif kind == "promet":
        if not getattr(record, "DATUM_PROMETA", ""):
            w.append("DATUM_PROMETA nije pronađen")
        if not getattr(record, "BROJ_DNEVNOG_IZVJESTAJA", ""):
            w.append("BROJ_DNEVNOG_IZVJESTAJA nije pronađen")
        if not getattr(record, "UKUPAN_DNEVNI_PROMET", ""):
            w.append("UKUPAN_DNEVNI_PROMET nije pronađen")

    return w



def _check_amounts(warnings: list[str], bez_pdv: Any, pdv: Any, sa_pdv: Any) -> None:
    a = _safe_float(bez_pdv)
    b = _safe_float(pdv)
    c = _safe_float(sa_pdv)

    if a is None or b is None or c is None:
        return

    if abs((a + b) - c) > 0.06:
        warnings.append("Iznosi nisu usklađeni")



def _safe_float(value: Any) -> float | None:
    s = str(value or "").strip()
    if not s:
        return None

    s = s.replace("KM", "").replace("BAM", "").replace(" ", "")

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")

    try:
        return float(s)
    except Exception:
        return None



def _save_records(kind: str, records: list[Any]) -> None:
    cfg = _KIND_CONFIG[kind]
    st.session_state[cfg["saved_key"]] = records
    st.session_state[_SHARED_SAVE_KEY][kind] = records

    if kind == "kif":
        st.session_state["invoices"] = records

    st.session_state["last_export"] = {
        "kind": kind,
        "count": len(records),
        "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
    }



def _records_to_excel_bytes(kind: str, records: list[Any]) -> bytes:
    cfg = _KIND_CONFIG[kind]
    fields = cfg["fields"]
    headers = cfg["headers"]

    rows = []
    for record in records:
        row = {headers[field]: getattr(record, field, "") for field in fields}
        row["Status"] = "⚠️" if _get_attr(record, "warnings") else ""
        row["Izvor"] = _get_attr(record, "filename") or ""
        rows.append(row)

    ordered_cols = [headers[field] for field in fields] + ["Status", "Izvor"]
    df = pd.DataFrame(rows, columns=ordered_cols)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=cfg["sheet_name"])
        worksheet = writer.book[cfg["sheet_name"]]
        worksheet.freeze_panes = "A2"

        for col in worksheet.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            worksheet.column_dimensions[col[0].column_letter].width = min(max(max_len + 2, 12), 40)

    buffer.seek(0)
    return buffer.getvalue()



def _excel_filename(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"



def _get_attr(record: Any, name: str, default: Any = None) -> Any:
    if hasattr(record, name):
        return getattr(record, name)
    private_name = f"_{name}"
    if hasattr(record, private_name):
        return getattr(record, private_name)
    return default



def _set_attr(record: Any, name: str, value: Any) -> None:
    try:
        setattr(record, name, value)
        return
    except Exception:
        pass

    private_name = f"_{name}"
    try:
        setattr(record, private_name, value)
        return
    except Exception:
        pass

    try:
        object.__setattr__(record, name, value)
    except Exception:
        pass



def _render_empty_state(kind: str) -> None:
    title = _KIND_CONFIG[kind]["title"]
    st.markdown(
        f"""
        <div class="upload-card" style="text-align:center; padding:2rem 1rem;">
            <div style="font-size:3rem; margin-bottom:0.5rem;">📄</div>
            <div style="font-size:1.15rem; font-weight:700; margin-bottom:0.4rem;">{title}</div>
            <div class="upload-muted">Uploaduj PDF dokumente da pokreneš ekstrakciju za ovu sekciju.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )



def _apply_upload_theme(dark_mode: bool) -> None:
    if dark_mode:
        bg = "#0f172a"
        card = "#111827"
        border = "#334155"
        text = "#f8fafc"
        muted = "#cbd5e1"
        input_bg = "#0b1220"
        accent = "#38bdf8"
    else:
        bg = "#f8fafc"
        card = "#ffffff"
        border = "#dbe4f0"
        text = "#0f172a"
        muted = "#475569"
        input_bg = "#ffffff"
        accent = "#2563eb"

    st.markdown(
        f"""
        <style>
        .stApp {{ background: {bg}; color: {text}; }}
        .block-container {{ padding-top: 1.2rem; padding-bottom: 2rem; }}
        h1, h2, h3, h4, h5, h6, p, label, span, div {{ color: {text}; }}
        .upload-card {{
            background: {card};
            color: {text};
            border: 1px solid {border};
            border-radius: 14px;
            padding: 0.9rem 1rem;
            margin: 0.25rem 0 0.75rem 0;
        }}
        .upload-muted {{ color: {muted}; font-size: 0.9rem; }}
        .section-title {{
            margin-top: 1rem;
            margin-bottom: 0.5rem;
            font-size: 1.05rem;
            font-weight: 700;
        }}
        [data-testid="stFileUploader"] > div {{
            background: {card};
            border: 1px solid {border};
            border-radius: 16px;
            padding: 0.35rem;
        }}
        [data-testid="stFileUploader"] small,
        [data-testid="stFileUploader"] label,
        [data-testid="stFileUploader"] span {{
            color: {text} !important;
        }}
        [data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid {border};
            background: {card};
        }}
        [data-testid="stDataFrame"] *, [data-testid="stDataEditor"] * {{
            color: {text} !important;
        }}
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        .stTextInput > div > div,
        .stDateInput > div > div,
        .stNumberInput > div > div {{
            background: {input_bg} !important;
            color: {text} !important;
            border-color: {border} !important;
        }}
        .stAlert {{ border-radius: 14px; }}
        [data-testid="stExpander"] {{
            border: 1px solid {border};
            border-radius: 14px;
            background: {card};
        }}
        .stDownloadButton button, .stButton button {{
            border-radius: 12px;
            font-weight: 700;
            min-height: 54px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
