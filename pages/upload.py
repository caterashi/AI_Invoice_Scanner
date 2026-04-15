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
    )    "DATUMPF": "Datum prijema",
    "NAZIVPP": "Kupac / primalac",
    "SJEDISTEPP": "Sjedište kupca",
    "IDPDVPP": "ID PDV dobavljača",
    "JIBPUPP": "JIB dobavljača",
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
        "title": "📥 KIF upload",
        "subtitle": "Knjiga izlaznih faktura.",
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
        "accent": "#22c55e",
    },
    "kuf": {
        "title": "📤 KUF upload",
        "subtitle": "Knjiga ulaznih faktura",
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
        "accent": "#f59e0b",
    },
    "promet": {
        "title": "🧾 Dnevni promet",
        "subtitle": "Dnevni izvještaji i evidencija prometa.",
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
        "accent": "#38bdf8",
    },
}


def render_upload() -> None:
    _init_state()
    dark_mode = _force_dark_mode()
    _apply_upload_theme(dark_mode)
    _render_topbar()
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

    for cfg in _KIND_CONFIG.values():
        if cfg["results_key"] not in st.session_state:
            st.session_state[cfg["results_key"]] = []
        if cfg["errors_key"] not in st.session_state:
            st.session_state[cfg["errors_key"]] = []
        if cfg["last_run_key"] not in st.session_state:
            st.session_state[cfg["last_run_key"]] = None
        if cfg["saved_key"] not in st.session_state:
            st.session_state[cfg["saved_key"]] = []


def _force_dark_mode() -> bool:
    st.session_state[_DARK_KEY] = True
    return True


def _render_topbar() -> None:
    st.markdown("<div class='section-title'>Učitavanje dokumenata po knjigovodstvenoj vrsti</div>", unsafe_allow_html=True)


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

    st.markdown(f"<div class='upload-card'><b>{cfg['title']}</b><br><span class='upload-muted'>{cfg['subtitle']}</span></div>", unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        cfg["uploader_label"],
        type=["pdf"],
        accept_multiple_files=True,
        help="Podržani su tekstualni i skenirani PDF dokumenti.",
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
            f"Pokreni ekstrakciju — {cfg['sheet_name']}",
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
    colsave, coldownload, colclear = st.columns(3)

    with colsave:
        if st.button("Sačuvaj pregledane stavke", type="primary", use_container_width=True, key=f"save_{kind}"):
            _save_records(kind, prepared)
            st.success(f"Sačuvano stavki: {len(prepared)}")

    with coldownload:
        st.download_button(
            "Preuzmi Excel",
            data=_records_to_excel_bytes(kind, prepared),
            file_name=_excel_filename(cfg["excel_prefix"]),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"download_{kind}",
        )

    with colclear:
        if st.button("Očisti trenutni rezultat", use_container_width=True, key=f"clear_{kind}"):
            st.session_state[cfg["results_key"]] = []
            st.session_state[cfg["errors_key"]] = []
            st.session_state[cfg["last_run_key"]] = None
            st.rerun()


def _run_extraction(kind: str, uploaded_files: list) -> None:
    cfg = _KIND_CONFIG[kind]
    parser = cfg["parser"]
    all_results = []
    all_errors: list[str] = []

    progress = st.progress(0, text=f"Priprema ekstrakcije ({cfg['title']})...")

    for idx, uploaded in enumerate(uploaded_files, start=1):
        progress.progress((idx - 1) / max(len(uploaded_files), 1), text=f"Obrađujem {uploaded.name}")
        pdf_bytes = uploaded.read()
        try:
            items = parser(pdf_bytes, filename=uploaded.name)
            if not items:
                all_errors.append(f"{uploaded.name}: Nema pronađenih stavki.")
                continue

            for record in items:
                _set_record_filename(record, uploaded.name)
                warnings = _get_record_warnings(record)
                if warnings:
                    all_errors.append(f"{uploaded.name}: {', '.join(warnings)}")
                all_results.append(record)
        except Exception as e:
            all_errors.append(f"{uploaded.name}: {e}")

    progress.progress(1.0, text="Ekstrakcija završena.")
    st.session_state[cfg["results_key"]] = all_results
    st.session_state[cfg["errors_key"]] = all_errors
    st.session_state[cfg["last_run_key"]] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

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
        row = {
            "Status": "⚠️" if _get_record_warnings(record) else "",
            "Izvor": _get_record_filename(record),
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
            _set_record_filename(record, _get_record_filename(originals[idx]))
        warnings = _refresh_warnings(kind, record)
        _set_record_warnings(record, warnings)
        _set_record_valid(record, len(warnings) == 0)
        prepared.append(record)

    return prepared


def _refresh_warnings(kind: str, record: Any) -> list[str]:
    warnings: list[str] = []

    if kind == "kif":
        if not getattr(record, "BROJFAKT", ""):
            warnings.append("BROJFAKT nije pronađen")
        if not getattr(record, "DATUMF", ""):
            warnings.append("DATUMF nije pronađen")
        if not getattr(record, "NAZIVPP", ""):
            warnings.append("NAZIVPP nije pronađen")
        if not getattr(record, "IZNSAPDV", ""):
            warnings.append("IZNSAPDV nije pronađen")
        _check_amount_consistency(warnings, getattr(record, "IZNBEZPDV", ""), getattr(record, "IZNPDV", ""), getattr(record, "IZNSAPDV", ""))

    elif kind == "kuf":
        if not getattr(record, "BROJ_DOKUMENTA", ""):
            warnings.append("BROJ_DOKUMENTA nije pronađen")
        if not getattr(record, "DATUM_DOKUMENTA", ""):
            warnings.append("DATUM_DOKUMENTA nije pronađen")
        if not getattr(record, "DOBAVLJAC_NAZIV", ""):
            warnings.append("DOBAVLJAC_NAZIV nije pronađen")
        if not getattr(record, "IZNOS_SA_PDV", ""):
            warnings.append("IZNOS_SA_PDV nije pronađen")
        _check_amount_consistency(warnings, getattr(record, "IZNOS_BEZ_PDV", ""), getattr(record, "IZNOS_PDV", ""), getattr(record, "IZNOS_SA_PDV", ""))

    elif kind == "promet":
        if not getattr(record, "DATUM_PROMETA", ""):
            warnings.append("DATUM_PROMETA nije pronađen")
        if not getattr(record, "BROJ_DNEVNOG_IZVJESTAJA", ""):
            warnings.append("BROJ_DNEVNOG_IZVJESTAJA nije pronađen")
        if not getattr(record, "UKUPAN_DNEVNI_PROMET", ""):
            warnings.append("UKUPAN_DNEVNI_PROMET nije pronađen")

    return warnings


def _check_amount_consistency(warnings: list[str], without_vat: str, vat: str, total: str) -> None:
    a = _safe_float(without_vat)
    b = _safe_float(vat)
    c = _safe_float(total)
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


def _records_to_excel_bytes(kind: str, records: list[Any]) -> bytes:
    cfg = _KIND_CONFIG[kind]
    fields = cfg["fields"]
    headers = cfg["headers"]

    rows = []
    for record in records:
        row = {headers[field]: getattr(record, field, "") for field in fields}
        row["Status"] = "⚠️" if _get_record_warnings(record) else ""
        row["Izvor"] = _get_record_filename(record)
        rows.append(row)

    df = pd.DataFrame(rows)
    ordered_cols = [headers[field] for field in fields] + ["Status", "Izvor"]
    if df.empty:
        df = pd.DataFrame(columns=ordered_cols)
    else:
        df = df[ordered_cols]

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=cfg["sheet_name"])
        ws = writer.book[cfg["sheet_name"]]
        ws.freeze_panes = "A2"
        for col_cells in ws.columns:
            length = max(len(str(cell.value or "")) for cell in col_cells)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max(length + 2, 12), 38)
    buffer.seek(0)
    return buffer.getvalue()


def _excel_filename(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"


def _get_record_filename(record: Any) -> str:
    return getattr(record, "filename", "") or getattr(record, "_filename", "") or ""


def _set_record_filename(record: Any, value: str) -> None:
    try:
        record.filename = value
    except Exception:
        try:
            record._filename = value
        except Exception:
            pass


def _get_record_warnings(record: Any) -> list[str]:
    return list(getattr(record, "warnings", []) or getattr(record, "_warnings", []) or [])


def _set_record_warnings(record: Any, warnings: list[str]) -> None:
    try:
        record.warnings = warnings
    except Exception:
        try:
            record._warnings = warnings
        except Exception:
            pass


def _set_record_valid(record: Any, value: bool) -> None:
    try:
        record.valid = value
    except Exception:
        try:
            record._valid = value
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
        .hero-wrap {{
            background: linear-gradient(135deg, {card} 0%, {bg} 100%);
            border: 1px solid {border};
            border-radius: 18px;
            padding: 1.2rem;
            margin-bottom: 1rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.10);
        }}
        .hero-title {{ font-size: 1.55rem; font-weight: 700; margin-bottom: 0.35rem; }}
        .hero-subtitle {{ color: {muted}; font-size: 0.98rem; margin-bottom: 0.75rem; }}
        .hero-badge {{
            display: inline-block; padding: 0.35rem 0.7rem; border-radius: 999px;
            background: {accent}22; border: 1px solid {accent}55; color: {text};
            font-size: 0.86rem; font-weight: 600;
        }}
        .upload-card {{
            background: {card}; color: {text}; border: 1px solid {border};
            border-radius: 14px; padding: 0.9rem 1rem; margin: 0.25rem 0 0.75rem 0;
        }}
        .upload-muted {{ color: {muted}; font-size: 0.9rem; }}
        .section-title {{ margin-top: 1rem; margin-bottom: 0.5rem; font-size: 1.05rem; font-weight: 700; }}
        [data-testid="stFileUploader"] div {{ background: {card}; border: 1px solid {border}; border-radius: 16px; padding: 0.35rem; }}
        [data-testid="stFileUploader"] small,
        [data-testid="stFileUploader"] label,
        [data-testid="stFileUploader"] span {{ color: {text} !important; }}
        [data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
            border-radius: 16px; overflow: hidden; border: 1px solid {border}; background: {card};
        }}
        [data-testid="stDataFrame"] *, [data-testid="stDataEditor"] * {{ color: {text} !important; }}
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        .stTextInput > div > div,
        .stDateInput > div > div,
        .stNumberInput > div > div {{
            background: {input_bg} !important; color: {text} !important; border-color: {border} !important;
        }}
        .stAlert {{ border-radius: 14px; }}
        [data-testid="stExpander"] {{ border: 1px solid {border}; border-radius: 14px; background: {card}; }}
        [data-baseweb="tab-list"] {{ gap: 0.35rem; }}
        [data-baseweb="tab"] {{ background: {card}; border: 1px solid {border}; border-radius: 12px; }}
        .stDownloadButton button, .stButton button {{ border-radius: 12px; font-weight: 600; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
