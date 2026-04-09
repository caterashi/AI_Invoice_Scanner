"""
pages/upload.py
===============
Upload i ekstrakcija podataka iz PDF faktura.
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


# ─────────────────────────────────────────────────────────────────────────────
# Glavna stranica
# ─────────────────────────────────────────────────────────────────────────────

def render_upload() -> None:
    st.title("📤 Učitaj račune")
    st.caption("Učitaj jedan ili više PDF fajlova, provjeri rezultat i dodaj potvrđene stavke u listu.")

    if "invoices" not in st.session_state:
        st.session_state["invoices"] = []
    if _RESULTS_KEY not in st.session_state:
        st.session_state[_RESULTS_KEY] = []
    if _ERRORS_KEY not in st.session_state:
        st.session_state[_ERRORS_KEY] = []

    uploaded_files = st.file_uploader(
        "Odaberi PDF fajlove",
        type=["pdf"],
        accept_multiple_files=True,
        help="Podržani su tekstualni i skenirani PDF dokumenti.",
    )

    if not uploaded_files:
        _render_empty_state()
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        st.caption(f"Odabrano fajlova: **{len(uploaded_files)}**")
    with col2:
        run = st.button("🔍 Ekstrahuj podatke", type="primary", use_container_width=True)

    if run:
        _run_extraction(uploaded_files)

    results: list[InvoiceData] = st.session_state.get(_RESULTS_KEY, [])
    errors: list[str] = st.session_state.get(_ERRORS_KEY, [])

    if errors:
        with st.expander(f"⚠️ Greške i upozorenja ({len(errors)})", expanded=True):
            for err in errors:
                st.error(err)

    if not results:
        return

    st.markdown("---")
    st.subheader("📋 Pregled ekstrahiranih podataka")
    st.caption("Po potrebi ispravi podatke prije potvrde.")

    edited_rows = _render_editor(results)

    st.markdown("---")
    col_save, col_download, col_clear = st.columns(3)

    prepared = _rows_to_invoices(edited_rows, results)

    with col_save:
        if st.button("💾 Dodaj u listu", type="primary", use_container_width=True):
            st.session_state["invoices"].extend(prepared)
            st.success(f"Dodano faktura: **{len(prepared)}**")

    with col_download:
        st.download_button(
            "📥 Preuzmi Excel",
            data=invoices_to_bytes(prepared),
            file_name=_excel_filename(),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with col_clear:
        if st.button("🗑️ Očisti rezultat", use_container_width=True):
            st.session_state[_RESULTS_KEY] = []
            st.session_state[_ERRORS_KEY] = []
            st.session_state[_LAST_RUN_KEY] = None
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Ekstrakcija
# ─────────────────────────────────────────────────────────────────────────────

def _run_extraction(uploaded_files) -> None:
    all_results: list[InvoiceData] = []
    all_errors: list[str] = []

    progress = st.progress(0, text="Priprema ekstrakcije...")

    for idx, uploaded in enumerate(uploaded_files, start=1):
        progress.progress((idx - 1) / len(uploaded_files), text=f"Obrađujem: {uploaded.name}")
        pdf_bytes = uploaded.read()

        try:
            items = extract_invoices_from_pdf(pdf_bytes, filename=uploaded.name)
            if not items:
                all_errors.append(f"{uploaded.name}: Nema pronađenih dokumenata.")
                continue

            valid_in_file = 0
            for inv in items:
                inv._filename = inv._filename or uploaded.name
                all_results.append(inv)
                valid_in_file += 1
                if inv._warnings:
                    all_errors.append(f"{inv._filename}: {'; '.join(inv._warnings)}")

            if valid_in_file == 0:
                all_errors.append(f"{uploaded.name}: Ekstrakcija nije vratila nijedan rezultat.")

        except Exception as e:
            all_errors.append(f"{uploaded.name}: {e}")

    progress.progress(1.0, text="Ekstrakcija završena")

    st.session_state[_RESULTS_KEY] = all_results
    st.session_state[_ERRORS_KEY] = all_errors
    st.session_state[_LAST_RUN_KEY] = datetime.now().isoformat()

    if all_results:
        st.success(f"Pronađeno dokumenata: **{len(all_results)}**")
    else:
        st.warning("Nijedan dokument nije ekstrahovan.")


# ─────────────────────────────────────────────────────────────────────────────
# Tabela za uređivanje
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
            "Status": "⚠️" if inv._warnings else "✅",
            "Izvor": inv._filename or "",
        }
        for field in FIELDS:
            row[HEADERS[field]] = getattr(inv, field, "")
        rows.append(row)
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Konverzije i pomoćne
# ─────────────────────────────────────────────────────────────────────────────

def _rows_to_invoices(rows: list[dict], originals: list[InvoiceData]) -> list[InvoiceData]:
    results: list[InvoiceData] = []

    for idx, row in enumerate(rows):
        inv = InvoiceData(**{field: row.get(field, "") for field in FIELDS})
        if idx < len(originals):
            inv._filename = originals[idx]._filename
            inv._warnings = _refresh_warnings(inv)
            inv._valid = len(inv._warnings) == 0
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
        <div style="text-align:center; padding:3rem; color:#888;">
            <div style="font-size:3rem;">📄</div>
            <p style="font-size:1.1rem; margin-top:1rem;">Uploaduj PDF račune za ekstrakciju.</p>
            <p style="font-size:0.9rem;">Podržani su standardni i skenirani PDF dokumenti.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
