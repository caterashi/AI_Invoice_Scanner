"""
pages/upload.py
===============
Stranica za upload i ekstrakciju podataka s PDF faktura.

Tok:
  1. Korisnik uploaduje jedan ili više PDF fajlova
  2. Svaki PDF se obrađuje kroz ai_extractor.extract_invoices_from_pdf()
  3. Rezultati se prikazuju u editabilnoj tabeli
  4. Potvrđeni zapisi se dodaju u session_state["invoices"]
  5. Excel download je dostupan odmah
"""

from __future__ import annotations

import streamlit as st

from ai_extractor import InvoiceData, FIELDS, extract_invoices_from_pdf
from excel_export import invoices_to_bytes, HEADERS


# ─────────────────────────────────────────────────────────────────────────────
# Konstante
# ─────────────────────────────────────────────────────────────────────────────

_FIELD_LABELS = list(HEADERS.values())   # display nazivi kolona


# ─────────────────────────────────────────────────────────────────────────────
# Glavna render funkcija
# ─────────────────────────────────────────────────────────────────────────────

def render_upload() -> None:
    st.title("📤 Učitaj račune")

    # Provjera API ključa
    if not st.session_state.get("openai_api_key"):
        st.warning("⚠️ OpenAI API ključ nije postavljen. Idi na **Postavke** i unesi ključ.")
        return

    # ── Upload zona ──────────────────────────────────────────────────────────
    uploaded_files = st.file_uploader(
        "Prevuci PDF fajlove ovdje ili klikni za odabir",
        type=["pdf"],
        accept_multiple_files=True,
        help="Podržani su tekstualni PDF-ovi (s OCR slojem) i skenirani PDF-ovi.",
    )

    if not uploaded_files:
        _render_empty_state()
        return

    # ── Dugme za pokretanje ekstrakcije ──────────────────────────────────────
    col1, col2 = st.columns([2, 1])
    with col1:
        st.caption(f"Odabrano fajlova: **{len(uploaded_files)}**")
    with col2:
        extract_btn = st.button(
            "🔍 Ekstrahuj podatke",
            type="primary",
            use_container_width=True,
        )

    if not extract_btn:
        return

    # ── Ekstrakcija ───────────────────────────────────────────────────────────
    all_extracted: list[InvoiceData] = []
    errors: list[str] = []

    progress = st.progress(0, text="Priprema...")

    for idx, uf in enumerate(uploaded_files):
        filename = uf.name
        progress.progress(
            (idx) / len(uploaded_files),
            text=f"Obrađujem {filename}...",
        )

        pdf_bytes = uf.read()

        with st.spinner(f"⏳ {filename}"):
            try:
                results = extract_invoices_from_pdf(pdf_bytes, filename=filename)
                for inv in results:
                    if inv._valid:
                        all_extracted.append(inv)
                    else:
                        errors.append(f"**{filename}**: {'; '.join(inv._warnings)}")
            except Exception as e:
                errors.append(f"**{filename}**: {e}")

    progress.progress(1.0, text="Gotovo!")

    # ── Greške ────────────────────────────────────────────────────────────────
    if errors:
        with st.expander(f"⚠️ Greške ({len(errors)})", expanded=True):
            for err in errors:
                st.error(err, icon="⚠️")

    if not all_extracted:
        st.error("Nije pronađena nijedna faktura.")
        return

    st.success(f"✅ Pronađeno faktura: **{len(all_extracted)}**")

    # ── Prikaz i uređivanje rezultata ─────────────────────────────────────────
    st.markdown("---")
    st.subheader("📋 Pregled ekstrahiranih podataka")
    st.caption("Provjeri i po potrebi ispravi podatke prije potvrde.")

    edited = _render_editor(all_extracted)

    # ── Upozorenja ────────────────────────────────────────────────────────────
    warnings_count = sum(len(inv._warnings) for inv in all_extracted if inv._warnings)
    if warnings_count:
        with st.expander(f"⚠️ Upozorenja validacije ({warnings_count})", expanded=False):
            for inv in all_extracted:
                if inv._warnings:
                    st.markdown(f"**{inv._filename or inv.BROJFAKT}**")
                    for w in inv._warnings:
                        st.markdown(f"- {w}")

    # ── Akcije ────────────────────────────────────────────────────────────────
    st.markdown("---")
    col_save, col_dl, col_clear = st.columns(3)

    with col_save:
        if st.button("💾 Dodaj u listu", type="primary", use_container_width=True):
            invoices = _rows_to_invoices(edited, all_extracted)
            st.session_state["invoices"].extend(invoices)
            st.success(f"Dodano {len(invoices)} faktura u listu.")
            st.rerun()

    with col_dl:
        all_invoices = _rows_to_invoices(edited, all_extracted)
        excel_bytes  = invoices_to_bytes(all_invoices)
        st.download_button(
            label="📥 Preuzmi Excel",
            data=excel_bytes,
            file_name=_excel_filename(all_invoices),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with col_clear:
        if st.button("🗑️ Poništi", use_container_width=True):
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Editabilna tabela
# ─────────────────────────────────────────────────────────────────────────────

def _render_editor(invoices: list[InvoiceData]) -> list[dict]:
    """
    Prikazuje st.data_editor s ekstrahiranim podacima.
    Vraća listu redova (dict) nakon eventualnog uređivanja.
    """
    import pandas as pd

    rows = []
    for inv in invoices:
        row = {HEADERS[f]: getattr(inv, f, "") for f in FIELDS}
        # Dodaj indikator valjanosti
        row["Status"] = "✅" if not inv._warnings else "⚠️"
        rows.append(row)

    df = pd.DataFrame(rows)

    edited_df = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn("Status", width="small", disabled=True),
            HEADERS["IZNBEZPDV"]: st.column_config.TextColumn(HEADERS["IZNBEZPDV"], width="medium"),
            HEADERS["IZNPDV"]:    st.column_config.TextColumn(HEADERS["IZNPDV"],    width="medium"),
            HEADERS["IZNSAPDV"]:  st.column_config.TextColumn(HEADERS["IZNSAPDV"],  width="medium"),
            HEADERS["NAZIVPP"]:   st.column_config.TextColumn(HEADERS["NAZIVPP"],   width="large"),
            HEADERS["SJEDISTEPP"]:st.column_config.TextColumn(HEADERS["SJEDISTEPP"],width="large"),
        },
        num_rows="fixed",
    )

    # Vrati samo FIELDS kolone (bez Status)
    return [
        {f: row.get(HEADERS[f], "") for f in FIELDS}
        for _, row in edited_df.iterrows()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Pomoćne funkcije
# ─────────────────────────────────────────────────────────────────────────────

def _rows_to_invoices(
    rows: list[dict],
    originals: list[InvoiceData],
) -> list[InvoiceData]:
    """Konvertuje uredene redove nazad u InvoiceData objekte."""
    result = []
    for i, row in enumerate(rows):
        inv = InvoiceData(**{f: str(row.get(f, "")) for f in FIELDS})
        # Prenesi metapodatke iz originala ako postoji
        if i < len(originals):
            inv._filename = originals[i]._filename
            inv._valid    = originals[i]._valid
            inv._warnings = originals[i]._warnings
        result.append(inv)
    return result


def _excel_filename(invoices: list[InvoiceData]) -> str:
    """Generiše naziv Excel fajla."""
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return f"fakture_{ts}.xlsx"


def _render_empty_state() -> None:
    """Prikazuje info poruku kad nema uploadovanih fajlova."""
    st.markdown("""
    <div style="text-align:center; padding:3rem; color:#888;">
        <div style="font-size:3rem;">📄</div>
        <p style="font-size:1.1rem; margin-top:1rem;">
            Uploaduj PDF fakture da započneš ekstrakciju
        </p>
        <p style="font-size:0.9rem;">
            Podržani formati: standardni računi (HERBAVITAL tip),
            fiskalni izvještaji (EDNA-M/IBFM tip)
        </p>
    </div>
    """, unsafe_allow_html=True)
