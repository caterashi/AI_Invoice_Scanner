"""
pages/upload.py
===============
Upload stranica sa tri odvojene sekcije/parsers:
- KIF  -> ai_extractor
- KUF  -> kuf_extractor (fallback na ai_extractor ako modul ne postoji)
- Dnevni promet -> dnevni_promet_extractor (fallback na ai_extractor ako modul ne postoji)
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd
import streamlit as st

from ai_extractor import FIELDS, InvoiceData, extract_invoices_from_pdf as extract_kif_from_pdf
from excel_export import HEADERS, invoices_to_bytes

try:
    from kuf_extractor import extract_invoices_from_pdf as extract_kuf_from_pdf
except Exception:
    try:
        from kuf_extractor import extract_kuf_from_pdf  # type: ignore
    except Exception:
        extract_kuf_from_pdf = extract_kif_from_pdf

try:
    from dnevni_promet_extractor import extract_invoices_from_pdf as extract_promet_from_pdf
except Exception:
    try:
        from dnevni_promet_extractor import extract_dnevni_promet_from_pdf  # type: ignore
    except Exception:
        extract_promet_from_pdf = extract_kif_from_pdf

_DARK_KEY = "app_dark_mode"

_KIND_CONFIG = {
    "kif": {
        "title": "📥 KIF upload",
        "subtitle": "Knjiga ulaznih faktura. PDF-ovi iz ove sekcije šalju se na ai_extractor.",
        "uploader_label": "Odaberi KIF PDF fajlove",
        "results_key": "upload_results_kif",
        "errors_key": "upload_errors_kif",
        "last_run_key": "upload_last_run_kif",
        "editor_key": "upload_editor_kif",
        "parser": extract_kif_from_pdf,
        "excel_prefix": "kif",
        "accent": "#22c55e",
    },
    "kuf": {
        "title": "📤 KUF upload",
        "subtitle": "Knjiga izlaznih faktura. PDF-ovi iz ove sekcije šalju se na kuf_extractor.",
        "uploader_label": "Odaberi KUF PDF fajlove",
        "results_key": "upload_results_kuf",
        "errors_key": "upload_errors_kuf",
        "last_run_key": "upload_last_run_kuf",
        "editor_key": "upload_editor_kuf",
        "parser": extract_kuf_from_pdf,
        "excel_prefix": "kuf",
        "accent": "#f59e0b",
    },
    "promet": {
        "title": "🧾 Dnevni promet upload",
        "subtitle": "PDF-ovi iz ove sekcije šalju se na dnevni_promet_extractor.",
        "uploader_label": "Odaberi PDF fajlove dnevnog prometa",
        "results_key": "upload_results_promet",
        "errors_key": "upload_errors_promet",
        "last_run_key": "upload_last_run_promet",
        "editor_key": "upload_editor_promet",
        "parser": extract_promet_from_pdf,
        "excel_prefix": "dnevni_promet",
        "accent": "#38bdf8",
    },
}


def render_upload() -> None:
    _init_state()
    dark_mode = _force_dark_mode()
    _apply_upload_theme(dark_mode)
    _render_topbar()
    _render_hero(dark_mode)

    tab1, tab2, tab3 = st.tabs(["KIF", "KUF", "Dnevni promet"])

    with tab1:
        _render_kind_upload("kif")
    with tab2:
        _render_kind_upload("kuf")
    with tab3:
        _render_kind_upload("promet")


def _init_state() -> None:
    if "invoices" not in st.session_state:
        st.session_state["invoices"] = []
    if _DARK_KEY not in st.session_state:
        st.session_state[_DARK_KEY] = True

    for cfg in _KIND_CONFIG.values():
        if cfg["results_key"] not in st.session_state:
            st.session_state[cfg["results_key"]] = []
        if cfg["errors_key"] not in st.session_state:
            st.session_state[cfg["errors_key"]] = []
        if cfg["last_run_key"] not in st.session_state:
            st.session_state[cfg["last_run_key"]] = None


def _force_dark_mode() -> bool:
    st.session_state[_DARK_KEY] = True
    return True


def _render_topbar() -> None:
    st.markdown("<div class='section-title'>Učitavanje dokumenata po tipu</div>", unsafe_allow_html=True)


def _render_hero(dark_mode: bool) -> None:
    mode_label = "Dark mode uključen" if dark_mode else "Light mode uključen"
    st.markdown(
        f"""
        <div class="hero-wrap">
            <div class="hero-title">PDF ekstrakcija: KIF / KUF / Dnevni promet</div>
            <div class="hero-subtitle">Svaka sekcija koristi svoj parser. Uploaduj PDF-ove, pregledaj rezultat, ispravi po potrebi i potvrdi unos.</div>
            <div class="hero-badge">{mode_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_kind_upload(kind: str) -> None:
    cfg = _KIND_CONFIG[kind]
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
            f"Pokreni ekstrakciju — {kind.upper() if kind != 'promet' else 'DNEVNI PROMET'}",
            type="primary",
            use_container_width=True,
            key=f"run_{kind}",
        )

    if run:
        _run_extraction(kind, uploaded_files)

    results: list[InvoiceData] = st.session_state.get(cfg["results_key"], [])
    errors: list[str] = st.session_state.get(cfg["errors_key"], [])

    if errors:
        with st.expander(f"⚠️ Greške i upozorenja ({len(errors)})", expanded=True):
            for err in errors:
                st.error(err)

    if not results:
        return

    st.markdown("<div class='section-title'>Pregled ekstrahiranih podataka</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='upload-card'>Parser za ovu sekciju: <b>{cfg['parser'].__module__}</b>. Provjeri rezultat, ispravi po potrebi i zatim potvrdi unos ili preuzmi Excel.</div>",
        unsafe_allow_html=True,
    )

    edited_rows = _render_editor(kind, results)
    prepared = _rows_to_invoices(edited_rows, results)

    st.markdown("<div class='section-title'>Akcije</div>", unsafe_allow_html=True)
    colsave, coldownload, colclear = st.columns(3)

    with colsave:
        if st.button("Dodaj u listu", type="primary", use_container_width=True, key=f"save_{kind}"):
            st.session_state["invoices"].extend(prepared)
            st.success(f"Dodano faktura: {len(prepared)}")

    with coldownload:
        st.download_button(
            "Preuzmi Excel",
            data=invoices_to_bytes(prepared),
            file_name=_excel_filename(cfg["excel_prefix"]),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"download_{kind}",
        )

    with colclear:
        if st.button("Očisti rezultat", use_container_width=True, key=f"clear_{kind}"):
            st.session_state[cfg["results_key"]] = []
            st.session_state[cfg["errors_key"]] = []
            st.session_state[cfg["last_run_key"]] = None
            st.rerun()


def _run_extraction(kind: str, uploaded_files: list) -> None:
    cfg = _KIND_CONFIG[kind]
    parser: Callable[[bytes, str], list[InvoiceData]] = cfg["parser"]
    all_results: list[InvoiceData] = []
    all_errors: list[str] = []

    progress = st.progress(0, text=f"Priprema ekstrakcije ({cfg['title']})...")

    for idx, uploaded in enumerate(uploaded_files, start=1):
        progress.progress((idx - 1) / len(uploaded_files), text=f"Obrađujem {uploaded.name}")
        pdf_bytes = uploaded.read()
        try:
            items = parser(pdf_bytes, filename=uploaded.name)
            if not items:
                all_errors.append(f"{uploaded.name}: Nema pronađenih dokumenata.")
                continue

            valid_in_file = 0
            for inv in items:
                try:
                    inv.filename = inv.filename or uploaded.name
                except Exception:
                    pass
                all_results.append(inv)
                valid_in_file += 1
                warnings = getattr(inv, "warnings", []) or getattr(inv, "_warnings", [])
                if warnings:
                    all_errors.append(f"{uploaded.name}: {', '.join(warnings)}")

            if valid_in_file == 0:
                all_errors.append(f"{uploaded.name}: Ekstrakcija nije vratila nijedan rezultat.")
        except Exception as e:
            all_errors.append(f"{uploaded.name}: {e}")

    progress.progress(1.0, text="Ekstrakcija završena.")
    st.session_state[cfg["results_key"]] = all_results
    st.session_state[cfg["errors_key"]] = all_errors
    st.session_state[cfg["last_run_key"]] = datetime.now().isoformat()

    if all_results:
        st.success(f"Pronađeno dokumenata: {len(all_results)}")
    else:
        st.warning("Nijedan dokument nije ekstrahovan.")


def _render_editor(kind: str, invoices: list[InvoiceData]) -> list[dict]:
    cfg = _KIND_CONFIG[kind]
    df = _to_editor_df(invoices)
    edited_df = st.data_editor(
        df,
        key=cfg["editor_key"],
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
        warnings = getattr(inv, "warnings", []) or getattr(inv, "_warnings", [])
        filename = getattr(inv, "filename", "") or getattr(inv, "_filename", "") or ""
        row = {"Status": "⚠️" if warnings else "", "Izvor": filename}
        for field in FIELDS:
            row[HEADERS[field]] = getattr(inv, field, "")
        rows.append(row)
    return pd.DataFrame(rows)


def _rows_to_invoices(rows: list[dict], originals: list[InvoiceData]) -> list[InvoiceData]:
    results = []
    for idx, row in enumerate(rows):
        inv = InvoiceData(**{field: row.get(field, "") for field in FIELDS})
        if idx < len(originals):
            try:
                inv.filename = getattr(originals[idx], "filename", "") or getattr(originals[idx], "_filename", "")
            except Exception:
                pass
        try:
            inv.warnings = _refresh_warnings(inv)
            inv.valid = len(inv.warnings) == 0
        except Exception:
            pass
        results.append(inv)
    return results


def _refresh_warnings(inv: InvoiceData) -> list[str]:
    warnings = []
    if not inv.BROJFAKT:
        warnings.append("BROJFAKT nije pronađen")
    if not inv.DATUMF:
        warnings.append("DATUMF nije pronađen")
    if not inv.NAZIVPP:
        warnings.append("NAZIVPP nije pronađen")
    if not inv.IZNSAPDV:
        warnings.append("IZNSAPDV nije pronađen")
    return warnings


def _excel_filename(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"


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
            margin-bottom: 0.75rem;
        }}
        .hero-badge {{
            display: inline-block;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: {accent}22;
            border: 1px solid {accent}55;
            color: {text};
            font-size: 0.86rem;
            font-weight: 600;
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
        [data-testid="stFileUploader"] div {{
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
        .stAlert {{
            border-radius: 14px;
        }}
        [data-testid="stExpander"] {{
            border: 1px solid {border};
            border-radius: 14px;
            background: {card};
        }}
        [data-baseweb="tab-list"] {{
            gap: 0.35rem;
        }}
        [data-baseweb="tab"] {{
            background: {card};
            border: 1px solid {border};
            border-radius: 12px;
        }}
        .stDownloadButton button, .stButton button {{
            border-radius: 12px;
            font-weight: 600;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    if not uploaded_files:
        _render_empty_state()
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(
            f"""
            <div class="upload-card">
                <b>Odabrano fajlova:</b> {len(uploaded_files)}
            </div>
            """,
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

    st.markdown(
        '<div class="section-title">Pregled ekstrahiranih podataka</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="upload-card">
            Provjeri rezultat, ispravi po potrebi i zatim potvrdi unos ili preuzmi Excel.
        </div>
        """,
        unsafe_allow_html=True,
    )

    edited_rows = _render_editor(results)
    prepared = _rows_to_invoices(edited_rows, results)

    st.markdown('<div class="section-title">Akcije</div>', unsafe_allow_html=True)
    col_save, col_download, col_clear = st.columns(3)

    with col_save:
        if st.button("Dodaj u listu", type="primary", use_container_width=True):
            st.session_state["invoices"].extend(prepared)
            st.success(f"Dodano faktura: {len(prepared)}")

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
            st.rerun()


def _init_state() -> None:
    if "invoices" not in st.session_state:
        st.session_state["invoices"] = []

    if _RESULTS_KEY not in st.session_state:
        st.session_state[_RESULTS_KEY] = []

    if _ERRORS_KEY not in st.session_state:
        st.session_state[_ERRORS_KEY] = []

    if _DARK_KEY not in st.session_state:
        st.session_state[_DARK_KEY] = True


def _force_dark_mode() -> None:
    st.session_state[_DARK_KEY] = True


def _render_topbar() -> None:
    st.markdown("### Učitavanje faktura")


def _render_hero() -> None:
    st.markdown(
        """
        <div class="hero-wrap">
            <div class="hero-title">PDF ekstrakcija računa</div>
            <div class="hero-subtitle">
                Uploaduj jedan ili više PDF fajlova, pregledaj rezultat i potvrdi samo ispravne stavke.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _apply_upload_theme() -> None:
    bg = "#0f172a"
    card = "#111827"
    border = "#334155"
    text = "#f8fafc"
    muted = "#cbd5e1"
    input_bg = "#0b1220"
    accent = "#38bdf8"
    row = "#111827"

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

        .hero-wrap {{
            background: linear-gradient(135deg, {card} 0%, {bg} 100%);
            border: 1px solid {border};
            border-radius: 18px;
            padding: 1.2rem 1.2rem 1rem 1.2rem;
            margin-bottom: 1rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.10);
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
            margin-bottom: 0.2rem;
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

        [data-testid="stDataFrame"] *,
        [data-testid="stDataEditor"] * {{
            color: {text} !important;
        }}

        [data-testid="stDataEditor"] [role="gridcell"] {{
            background: {row} !important;
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

        .stDownloadButton button,
        .stButton button {{
            border-radius: 12px;
            font-weight: 600;
        }}

        .stButton button[kind="primary"] {{
            background: {accent} !important;
            color: #001018 !important;
            border: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _run_extraction(uploaded_files) -> None:
    all_results: list[InvoiceData] = []
    all_errors: list[str] = []

    progress = st.progress(0, text="Priprema ekstrakcije...")

    for idx, uploaded in enumerate(uploaded_files, start=1):
        progress.progress(
            (idx - 1) / len(uploaded_files),
            text=f"Obrađujem: {uploaded.name}",
        )

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

    if all_results:
        st.success(f"Pronađeno dokumenata: {len(all_results)}")
    else:
        st.warning("Nijedan dokument nije ekstrahovan.")


def _render_editor(invoices: list[InvoiceData]) -> list[dict]:
    df = _to_editor_df(invoices)

    column_config = {
        "Status": st.column_config.TextColumn("Status", width="small", disabled=True),
        "Izvor": st.column_config.TextColumn("Izvor", width="medium", disabled=True),
    }

    for field in FIELDS:
        column_config[HEADERS[field]] = st.column_config.TextColumn(
            HEADERS[field],
            width="medium",
        )

    edited_df = st.data_editor(
        df,
        key=_EDITOR_KEY,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config=column_config,
    )

    return [
        {
            field: str(row.get(HEADERS[field], "") or "").strip()
            for field in FIELDS
        }
        for _, row in edited_df.iterrows()
    ]


def _to_editor_df(invoices: list[InvoiceData]) -> pd.DataFrame:
    rows = []

    for inv in invoices:
        row = {
            "Status": "⚠️" if inv.warnings else "✅",
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


def _excel_filename() -> str:
    return f"fakture_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"


def _render_empty_state() -> None:
    st.markdown(
        """
        <div class="upload-card" style="text-align:center; padding:2rem 1rem;">
            <div style="font-size:3rem; margin-bottom:0.5rem;">📄</div>
            <div style="font-size:1.15rem; font-weight:700; margin-bottom:0.4rem;">
                Uploaduj PDF račune za ekstrakciju
            </div>
            <div class="upload-muted">
                Podržani su standardni i skenirani PDF dokumenti.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
