"""
pages/dashboard.py
==================
Pregled svih faktura dodanih u session_state["invoices"].

Funkcije:
  - Prikaz svih faktura u tabeli
  - Sumarni KPI-evi (broj faktura, ukupan iznos)
  - Brisanje pojedinačnih redova
  - Brisanje svih faktura
  - Excel download
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ai_extractor import FIELDS, InvoiceData
from excel_export import HEADERS, invoices_to_bytes


# ─────────────────────────────────────────────────────────────────────────────
# Glavna render funkcija
# ─────────────────────────────────────────────────────────────────────────────

def render_dashboard() -> None:
    st.title("📊 Pregled faktura")

    invoices: list[InvoiceData] = st.session_state.get("invoices", [])

    if not invoices:
        _render_empty_state()
        return

    # ── KPI metrike ───────────────────────────────────────────────────────
    _render_metrics(invoices)

    st.markdown("---")

    # ── Akcijska traka ─────────────────────────────────────────────────────
    col_dl, col_del = st.columns([1, 1])

    with col_dl:
        excel_bytes = invoices_to_bytes(invoices)
        st.download_button(
            label="📥 Preuzmi Excel",
            data=excel_bytes,
            file_name=_excel_filename(),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
        )

    with col_del:
        if st.button(
            "🗑️ Obriši sve fakture",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state["_confirm_clear"] = True

    # Potvrda brisanja svih
    if st.session_state.get("_confirm_clear"):
        st.warning("⚠️ Jesi li siguran/na? Ova akcija je nepovratna.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Da, obriši sve", use_container_width=True, type="primary"):
                st.session_state["invoices"]      = []
                st.session_state["_confirm_clear"] = False
                st.rerun()
        with c2:
            if st.button("❌ Odustani", use_container_width=True):
                st.session_state["_confirm_clear"] = False
                st.rerun()
        return

    st.markdown("---")

    # ── Tabela s fakturama ─────────────────────────────────────────────────
    st.subheader("📋 Lista faktura")
    _render_table(invoices)


# ─────────────────────────────────────────────────────────────────────────────
# KPI metrike
# ─────────────────────────────────────────────────────────────────────────────

def _render_metrics(invoices: list[InvoiceData]) -> None:
    """Prikazuje 4 KPI kartice na vrhu stranice."""

    total_sa_pdv  = _sum_field(invoices, "IZNSAPDV")
    total_pdv     = _sum_field(invoices, "IZNPDV")
    total_bez_pdv = _sum_field(invoices, "IZNBEZPDV")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Ukupno faktura",
            value=len(invoices),
        )
    with col2:
        st.metric(
            label="Ukupno za naplatu",
            value=f"{total_sa_pdv:,.2f} KM".replace(",", "X").replace(".", ",").replace("X", "."),
        )
    with col3:
        st.metric(
            label="Ukupno bez PDV-a",
            value=f"{total_bez_pdv:,.2f} KM".replace(",", "X").replace(".", ",").replace("X", "."),
        )
    with col4:
        st.metric(
            label="Ukupno PDV",
            value=f"{total_pdv:,.2f} KM".replace(",", "X").replace(".", ",").replace("X", "."),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tabela s brisanjem redova
# ─────────────────────────────────────────────────────────────────────────────

def _render_table(invoices: list[InvoiceData]) -> None:
    """
    Prikazuje tabelu faktura s mogućnošću brisanja pojedinih redova.
    """
    # Pripremi DataFrame
    rows = []
    for i, inv in enumerate(invoices):
        row = {"#": i + 1}
        for field in FIELDS:
            row[HEADERS[field]] = getattr(inv, field, "")
        row["⚠️"] = "⚠️" if inv._warnings else ""
        rows.append(row)

    df = pd.DataFrame(rows)

    # Prikaži tabelu
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            HEADERS["IZNBEZPDV"]: st.column_config.NumberColumn(
                HEADERS["IZNBEZPDV"], format="%.2f KM"
            ),
            HEADERS["IZNPDV"]: st.column_config.NumberColumn(
                HEADERS["IZNPDV"], format="%.2f KM"
            ),
            HEADERS["IZNSAPDV"]: st.column_config.NumberColumn(
                HEADERS["IZNSAPDV"], format="%.2f KM"
            ),
            "⚠️": st.column_config.TextColumn("⚠️", width="small"),
        },
    )

    # ── Brisanje pojedinačnog reda ─────────────────────────────────────────
    st.markdown("#### Obriši fakturu")

    col_sel, col_btn = st.columns([3, 1])

    options = [
        f"{i + 1}. {inv.BROJFAKT or '—'} | {inv.NAZIVPP or '—'} | {inv.DATUMF or '—'}"
        for i, inv in enumerate(invoices)
    ]

    with col_sel:
        selected = st.selectbox(
            "Odaberi fakturu za brisanje",
            options=options,
            index=None,
            placeholder="Odaberi...",
            label_visibility="collapsed",
        )

    with col_btn:
        if st.button("🗑️ Obriši", use_container_width=True, disabled=selected is None):
            idx = options.index(selected)
            st.session_state["invoices"].pop(idx)
            st.success(f"Faktura obrisana.")
            st.rerun()

    # ── Upozorenja validacije ─────────────────────────────────────────────
    warnings = [(inv, inv._warnings) for inv in invoices if inv._warnings]
    if warnings:
        with st.expander(f"⚠️ Upozorenja validacije ({len(warnings)} faktura)", expanded=False):
            for inv, w_list in warnings:
                label = inv.BROJFAKT or inv.NAZIVPP or inv._filename or "Nepoznato"
                st.markdown(f"**{label}**")
                for w in w_list:
                    st.markdown(f"- {w}")


# ─────────────────────────────────────────────────────────────────────────────
# Pomoćne funkcije
# ─────────────────────────────────────────────────────────────────────────────

def _sum_field(invoices: list[InvoiceData], field: str) -> float:
    """Sabira numeričke vrijednosti jednog polja svih faktura."""
    total = 0.0
    for inv in invoices:
        try:
            total += float(getattr(inv, field, "") or 0)
        except (ValueError, TypeError):
            pass
    return total


def _excel_filename() -> str:
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return f"fakture_{ts}.xlsx"


def _render_empty_state() -> None:
    st.markdown("""
    <div style="text-align:center; padding:4rem; color:#888;">
        <div style="font-size:3rem;">📭</div>
        <p style="font-size:1.1rem; margin-top:1rem;">
            Nema faktura u listi
        </p>
        <p style="font-size:0.9rem;">
            Idi na <b>Učitaj račune</b> i uploaduj PDF fakture.
        </p>
    </div>
    """, unsafe_allow_html=True)
