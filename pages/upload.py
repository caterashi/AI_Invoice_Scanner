"""
pages/upload.py
===============
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from ai_extractor import FIELDS, InvoiceData, extract_invoices_from_pdf
from excel_export import HEADERS, invoices_to_bytes

_EDITOR_KEY = "upload_editor"
_RESULTS_KEY = "upload_results"
_ERRORS_KEY = "upload_errors"
_LAST_RUN_KEY = "upload_last_run"
_DARK_KEY = "app_dark_mode"


# ─────────────────────────────────────────────────────────────────────────────
# Glavna stranica
# ─────────────────────────────────────────────────────────────────────────────
def render_upload() -> None:
    _init_state()
    dark_mode = _force_dark_mode()
    _apply_upload_theme(dark_mode)
    _render_topbar()
    _render_hero()

    uploaded_files = st.file_uploader(
        "Odaberi PDF fajlove",
        type=["pdf"],
        accept_multiple_files=True,
        help="Podržani su tekstualni i skenirani PDF dokumenti.",
    )

    if not uploaded_files:
        _render_empty_state(dark_mode)
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(
            f'<div class="upload-card"><b>Odabrano dokumenata:</b> {len(uploaded_files)}</div>',
            unsafe_allow_html=True,
        )

    with col2:
        run = st.button("Ekstrahuj podatke", type="primary", use_container_width=True)

    if run:
        _run_extraction(uploaded_files)

    results: list[InvoiceData] = st.session_state.get(_RESULTS_KEY, [])
    errors: list[str] = st.session_state.get(_ERRORS_KEY, [])

    if errors:
        with st.expander(f"Greške i upozorenja ({len(errors)})", expanded=True):
            for err in errors:
                st.error(err)

    if not results:
        return

    st.markdown('<div class="section-title">Pregled ekstrahiranih podataka</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="upload-card">Provjeri rezultat, ispravi po potrebi i zatim preuzmi Excel ili očisti rezultat.</div>',
        unsafe_allow_html=True,
    )

    edited_rows = _render_editor(results)
    prepared = _rows_to_invoices(edited_rows, results)

    st.markdown('<div class="section-title">Akcije</div>', unsafe_allow_html=True)
    col_download, col_clear = st.columns(2)

    with col_download:
        st.download_button(
            "Preuzmi Excel",
            data=invoices_to_bytes(prepared),
            file_name=_excel_filename(),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with col_clear:
        if st.button("Očisti rezultat", use_container_width=True):
            st.session_state[_RESULTS_KEY] = []
            st.session_state[_ERRORS_KEY] = []
            st.session_state[_LAST_RUN_KEY] = None
            st.session_state.pop(_EDITOR_KEY, None)
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────
def _init_state() -> None:
    if _RESULTS_KEY not in st.session_state:
        st.session_state[_RESULTS_KEY] = []
    if _ERRORS_KEY not in st.session_state:
        st.session_state[_ERRORS_KEY] = []
    if _LAST_RUN_KEY not in st.session_state:
        st.session_state[_LAST_RUN_KEY] = None
    if _DARK_KEY not in st.session_state:
        st.session_state[_DARK_KEY] = True

    st.session_state.pop("invoices", None)
    st.session_state.pop("last_export", None)


def _force_dark_mode() -> bool:
    st.session_state[_DARK_KEY] = True
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Top bar / odjava
# ─────────────────────────────────────────────────────────────────────────────
def _logout_user() -> None:
    st.session_state["authenticated"] = False
    st.session_state["username"] = ""
    st.session_state[_RESULTS_KEY] = []
    st.session_state[_ERRORS_KEY] = []
    st.session_state[_LAST_RUN_KEY] = None
    st.session_state.pop(_EDITOR_KEY, None)
    st.session_state.pop("invoices", None)
    st.session_state.pop("last_export", None)
    st.rerun()


def _render_topbar() -> None:
    left, mid, right = st.columns([5, 2, 1])

    with left:
        st.markdown("### Učitavanje faktura")

    with mid:
        username = str(st.session_state.get("username", "") or "").strip()
        if username:
            st.caption(f"Prijavljen: {username}")

    with right:
        if st.button("Odjava", use_container_width=True):
            _logout_user()


def _render_hero() -> None:
    st.markdown(
        """
        <div class="hero-wrap">
            <div class="hero-title">PDF ekstrakcija računa</div>
            <div class="hero-subtitle">
                Uploaduj jedan ili više PDF dokumenata, pregledaj rezultat i preuzmi finalni Excel.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tema
# ─────────────────────────────────────────────────────────────────────────────
def _apply_upload_theme(dark_mode: bool) -> None:
    if dark_mode:
        bg = "#0f172a"
        card = "#111827"
        border = "#334155"
        text = "#f8fafc"
        muted = "#cbd5e1"
        inputbg = "#0b1220"
    else:
        bg = "#f8fafc"
        card = "#ffffff"
        border = "#dbe4f0"
        text = "#0f172a"
        muted = "#475569"
        inputbg = "#ffffff"

    st.markdown(
        f"""
        <style>
            .stApp {{
                background: {bg};
                color: {text};
            }}

            .block-container {{
                padding-top: 1.2rem;
                padding-bottom: 2rem;
            }}

            h1, h2, h3, h4, h5, h6, p, label, span, div {{
                color: {text};
            }}

            section[data-testid="stSidebar"] {{
                display: none !important;
            }}

            button[kind="header"] {{
                display: none !important;
            }}

            .hero-wrap {{
                background: linear-gradient(135deg, {card} 0%, {bg} 100%);
                border: 1px solid {border};
                border-radius: 18px;
                padding: 1.2rem 1.2rem 1rem 1.2rem;
                margin-bottom: 1rem;
                box-shadow: 0 10px 30px rgba(0,0,0,0.10);
            }}

            .hero-title {{
                font-size: 1.55rem;
                font-weight: 700;
                color: {text};
                margin-bottom: 0.35rem;
            }}

            .hero-subtitle {{
                color: {muted};
                font-size: 0.98rem;
                margin-bottom: 0;
            }}

            .upload-card {{
                background: {card};
                color: {text};
                border: 1px solid {border};
                border-radius: 14px;
                padding: 0.9rem 1rem;
                margin: 0.25rem 0 0.75rem 0;
            }}

            .upload-muted {{
                color: {muted};
                font-size: 0.9rem;
            }}

            .section-title {{
                margin-top: 1rem;
                margin-bottom: 0.5rem;
                font-size: 1.05rem;
                font-weight: 700;
                color: {text};
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

            [data-testid="stDataFrame"],
            [data-testid="stDataEditor"] {{
                border-radius: 16px;
                overflow: hidden;
                border: 1px solid {border};
                background: {card};
            }}

            [data-testid="stDataFrame"],
            [data-testid="stDataEditor"] * {{
                color: {text} !important;
            }}

            div[data-baseweb="select"] > div,
            div[data-baseweb="input"] > div,
            .stTextInput > div > div,
            .stDateInput > div > div,
            .stNumberInput > div > div {{
                background: {inputbg} !important;
                color: {text} !important;
                border-color: {border} !important;
            }}

            .stAlert {{
                border-radius: 14px;
            }}

            [data-testid="stExpander"] {{
                border: 1px solid {border};
                border-radius: 14px;
                background: {card};
            }}

            [data-testid="stMarkdownContainer"] p {{
                color: {text};
            }}

            .stDownloadButton > button,
            .stButton > button {{
                border-radius: 12px;
                font-weight: 600;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Ekstrakcija
# ─────────────────────────────────────────────────────────────────────────────
def _run_extraction(uploaded_files) -> None:
    all_results: list[InvoiceData] = []
    all_errors: list[str] = []

    progress = st.progress(0, text="Priprema ekstrakcije...")

    for idx, uploaded in enumerate(uploaded_files, start=1):
        progress.progress((idx - 1) / len(uploaded_files), text=f"Obrađujem {uploaded.name}...")
        pdf_bytes = uploaded.read()

        try:
            items = extract_invoices_from_pdf(pdf_bytes, filename=uploaded.name)

            if not items:
                all_errors.append(f"{uploaded.name}: Nema pronađenih dokumenata.")
                continue

            valid_in_file = 0

            for inv in items:
                inv.filename = inv.filename or uploaded.name
                all_results.append(inv)
                valid_in_file += 1

                if inv.warnings:
                    all_errors.append(f"{inv.filename}: {', '.join(inv.warnings)}")

            if valid_in_file == 0:
                all_errors.append(f"{uploaded.name}: Ekstrakcija nije vratila nijedan rezultat.")

        except Exception as e:
            all_errors.append(f"{uploaded.name}: {e}")

    progress.progress(1.0, text="Ekstrakcija završena.")

    st.session_state[_RESULTS_KEY] = all_results
    st.session_state[_ERRORS_KEY] = all_errors
    st.session_state[_LAST_RUN_KEY] = datetime.now().isoformat()
    st.session_state.pop(_EDITOR_KEY, None)

    if all_results:
        st.success(f"Pronađeno dokumenata: {len(all_results)}")
    else:
        st.warning("Nijedan dokument nije ekstrahovan.")


# ─────────────────────────────────────────────────────────────────────────────
# Editor
# ─────────────────────────────────────────────────────────────────────────────
def _render_editor(invoices: list[InvoiceData]) -> list[dict]:
    df = _to_editor_df(invoices)

    edited_df = st.data_editor(
        df,
        key=_EDITOR_KEY,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "Status": st.column_config.TextColumn("Status", width="small", disabled=True),
            "Izvor": st.column_config.TextColumn("Izvor", width="medium", disabled=True),
            HEADERS["BROJFAKT"]: st.column_config.TextColumn(HEADERS["BROJFAKT"], width="medium"),
            HEADERS["DATUMF"]: st.column_config.TextColumn(HEADERS["DATUMF"], width="small"),
            HEADERS["DATUMPF"]: st.column_config.TextColumn(HEADERS["DATUMPF"], width="small"),
            HEADERS["NAZIVPP"]: st.column_config.TextColumn(HEADERS["NAZIVPP"], width="large"),
            HEADERS["SJEDISTEPP"]: st.column_config.TextColumn(HEADERS["SJEDISTEPP"], width="large"),
            HEADERS["IDPDVPP"]: st.column_config.TextColumn(HEADERS["IDPDVPP"], width="medium"),
            HEADERS["JIBPUPP"]: st.column_config.TextColumn(HEADERS["JIBPUPP"], width="medium"),
            HEADERS["IZNBEZPDV"]: st.column_config.TextColumn(HEADERS["IZNBEZPDV"], width="small"),
            HEADERS["IZNSAPDV"]: st.column_config.TextColumn(HEADERS["IZNSAPDV"], width="small"),
            HEADERS["IZNPDV"]: st.column_config.TextColumn(HEADERS["IZNPDV"], width="small"),
        },
    )

    return [
        {field: str(row.get(HEADERS[field], "") or "").strip() for field in FIELDS}
        for _, row in edited_df.iterrows()
    ]


def _to_editor_df(invoices: list[InvoiceData]) -> pd.DataFrame:
    rows = []

    for inv in invoices:
        row = {
            "Status": "⚠️" if inv.warnings else "",
            "Izvor": inv.filename or "",
        }
        for field in FIELDS:
            row[HEADERS[field]] = getattr(inv, field, "")
        rows.append(row)

    return pd.DataFrame(rows)


def _rows_to_invoices(rows: list[dict], originals: list[InvoiceData]) -> list[InvoiceData]:
    results: list[InvoiceData] = []

    for idx, row in enumerate(rows):
        inv = InvoiceData(**{field: row.get(field, "") for field in FIELDS})

        if idx < len(originals):
            inv.filename = originals[idx].filename

        inv.warnings = _refresh_warnings(inv)
        inv.valid = len(inv.warnings) == 0
        results.append(inv)

    return results


def _refresh_warnings(inv: InvoiceData) -> list[str]:
    warnings: list[str] = []

    if not inv.BROJFAKT:
        warnings.append("BROJFAKT nije pronađen")
    if not inv.DATUMF:
        warnings.append("DATUMF nije pronađen")
    if not inv.NAZIVPP:
        warnings.append("NAZIVPP nije pronađen")
    if not inv.IZNSAPDV:
        warnings.append("IZNSAPDV nije pronađen")

    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# Pomoćne
# ─────────────────────────────────────────────────────────────────────────────
def _excel_filename() -> str:
    return f"fakture_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"


def _render_empty_state(dark_mode: bool) -> None:
    mode_text = "dark" if dark_mode else "light"
    st.markdown(
        f"""
        <div class="upload-card" style="text-align:center; padding:2rem 1rem;">
            <div style="font-size:3rem; margin-bottom:0.5rem;">🧾</div>
            <div style="font-size:1.15rem; font-weight:700; margin-bottom:0.4rem;">
                Uploaduj PDF račune za ekstrakciju
            </div>
            <div class="upload-muted">
                Aktivni prikaz: {mode_text} mode. Podržani su standardni i skenirani PDF dokumenti.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
