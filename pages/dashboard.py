"""
pages/dashboard.py
==================
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from ai_extractor import FIELDS, InvoiceData
from excel_export import HEADERS, invoices_to_bytes


_THEME_KEY = "app_dark_mode"
_CONFIRM_KEY = "dashboard_confirm_clear"


def render_dashboard() -> None:
    _init_state()
    dark_mode = st.session_state[_THEME_KEY]
    _apply_dashboard_theme(dark_mode)

    st.markdown("<div class='db-title'>📊 Pregled faktura</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='db-subtitle'>Pregledaj sve potvrđene stavke, preuzmi Excel ili obriši pojedinačne unose.</div>",
        unsafe_allow_html=True,
    )

    invoices: list[InvoiceData] = st.session_state.get("invoices", [])
    if not invoices:
        _render_empty_state()
        return

    _render_metrics(invoices)
    _render_actions(invoices)
    _render_table(invoices)


def _init_state() -> None:
    if _THEME_KEY not in st.session_state:
        st.session_state[_THEME_KEY] = True
    if _CONFIRM_KEY not in st.session_state:
        st.session_state[_CONFIRM_KEY] = False
    if "invoices" not in st.session_state:
        st.session_state["invoices"] = []


def _render_metrics(invoices: list[InvoiceData]) -> None:
    ukupno = len(invoices)
    suma_sa = _sum_field(invoices, "IZNSAPDV")
    suma_bez = _sum_field(invoices, "IZNBEZPDV")
    suma_pdv = _sum_field(invoices, "IZNPDV")

    st.markdown("<div class='db-section'>Sažetak</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _metric_card("Ukupno faktura", str(ukupno))
    with c2:
        _metric_card("Ukupno sa PDV", _fmt_km(suma_sa))
    with c3:
        _metric_card("Ukupno bez PDV", _fmt_km(suma_bez))
    with c4:
        _metric_card("Ukupno PDV", _fmt_km(suma_pdv))


def _render_actions(invoices: list[InvoiceData]) -> None:
    st.markdown("<div class='db-section'>Akcije</div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])

    with c1:
        st.download_button(
            "📥 Preuzmi Excel",
            data=invoices_to_bytes(invoices),
            file_name=_excel_filename(),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
        )

    with c2:
        if st.button("🗑️ Obriši sve fakture", use_container_width=True):
            st.session_state[_CONFIRM_KEY] = True

    if st.session_state[_CONFIRM_KEY]:
        st.markdown(
            "<div class='db-warning'>Brisanje je nepovratno. Potvrdi ako želiš ukloniti sve fakture iz liste.</div>",
            unsafe_allow_html=True,
        )
        a, b = st.columns(2)
        with a:
            if st.button("✅ Potvrdi brisanje", type="primary", use_container_width=True):
                st.session_state["invoices"] = []
                st.session_state[_CONFIRM_KEY] = False
                st.rerun()
        with b:
            if st.button("↩️ Odustani", use_container_width=True):
                st.session_state[_CONFIRM_KEY] = False
                st.rerun()


def _render_table(invoices: list[InvoiceData]) -> None:
    st.markdown("<div class='db-section'>Lista faktura</div>", unsafe_allow_html=True)

    df = _to_df(invoices)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            "⚠️": st.column_config.TextColumn("⚠️", width="small"),
        },
    )

    st.markdown("<div class='db-section'>Obriši jednu fakturu</div>", unsafe_allow_html=True)
    options = [
        f"{i + 1}. {inv.BROJFAKT or '—'} | {inv.NAZIVPP or '—'} | {inv.DATUMF or '—'}"
        for i, inv in enumerate(invoices)
    ]

    c1, c2 = st.columns([3, 1])
    with c1:
        selected = st.selectbox(
            "Odaberi fakturu",
            options=options,
            index=None,
            placeholder="Odaberi stavku za brisanje",
            label_visibility="collapsed",
        )
    with c2:
        if st.button("🗑️ Obriši", use_container_width=True, disabled=selected is None):
            idx = options.index(selected)
            st.session_state["invoices"].pop(idx)
            st.success("Faktura je obrisana.")
            st.rerun()

    warnings = [(inv, inv._warnings) for inv in invoices if inv._warnings]
    if warnings:
        with st.expander(f"⚠️ Upozorenja validacije ({len(warnings)})", expanded=False):
            for inv, items in warnings:
                st.markdown(f"**{inv.BROJFAKT or inv.NAZIVPP or inv._filename or 'Dokument'}**")
                for item in items:
                    st.markdown(f"- {item}")


def _metric_card(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _to_df(invoices: list[InvoiceData]) -> pd.DataFrame:
    rows = []
    for i, inv in enumerate(invoices, start=1):
        row = {"#": i, "⚠️": "⚠️" if inv._warnings else ""}
        for field in FIELDS:
            row[HEADERS[field]] = getattr(inv, field, "")
        rows.append(row)
    return pd.DataFrame(rows)


def _sum_field(invoices: list[InvoiceData], field: str) -> float:
    total = 0.0
    for inv in invoices:
        try:
            total += float(getattr(inv, field, "") or 0)
        except Exception:
            pass
    return total


def _fmt_km(value: float) -> str:
    return f"{value:,.2f} KM".replace(",", "X").replace(".", ",").replace("X", ".")


def _excel_filename() -> str:
    return f"fakture_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"


def _render_empty_state() -> None:
    st.markdown(
        """
        <div class="empty-card">
            <div class="empty-icon">📭</div>
            <div class="empty-title">Nema faktura u listi</div>
            <div class="empty-subtitle">Dodaj fakture na stranici za upload da bi se ovdje pojavile.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _apply_dashboard_theme(dark_mode: bool) -> None:
    if dark_mode:
        bg = "#0f172a"
        card = "#111827"
        border = "#334155"
        text = "#f8fafc"
        muted = "#cbd5e1"
        accent = "#38bdf8"
        input_bg = "#0b1220"
    else:
        bg = "#f8fafc"
        card = "#ffffff"
        border = "#dbe4f0"
        text = "#0f172a"
        muted = "#475569"
        accent = "#2563eb"
        input_bg = "#ffffff"

    st.markdown(
        f"""
        <style>
        .stApp {{
            background: {bg};
            color: {text};
        }}
        .db-title {{
            font-size: 1.8rem;
            font-weight: 800;
            color: {text};
            margin-bottom: 0.25rem;
        }}
        .db-subtitle {{
            color: {muted};
            margin-bottom: 1rem;
        }}
        .db-section {{
            margin-top: 1rem;
            margin-bottom: 0.55rem;
            font-size: 1rem;
            font-weight: 800;
            color: {text};
        }}
        .metric-card {{
            background: linear-gradient(135deg, {card} 0%, {bg} 100%);
            border: 1px solid {border};
            border-radius: 16px;
            padding: 1rem;
            min-height: 108px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.08);
            margin-bottom: 0.5rem;
        }}
        .metric-label {{
            color: {muted};
            font-size: 0.9rem;
            margin-bottom: 0.35rem;
        }}
        .metric-value {{
            color: {accent};
            font-size: 1.45rem;
            font-weight: 800;
            line-height: 1.2;
        }}
        .db-warning {{
            background: {card};
            border: 1px solid {border};
            border-left: 5px solid #f59e0b;
            border-radius: 14px;
            padding: 0.95rem 1rem;
            color: {text};
            margin: 0.5rem 0 0.8rem 0;
        }}
        .empty-card {{
            text-align: center;
            background: {card};
            border: 1px solid {border};
            border-radius: 18px;
            padding: 2.2rem 1rem;
            margin-top: 1rem;
        }}
        .empty-icon {{
            font-size: 3rem;
            margin-bottom: 0.5rem;
        }}
        .empty-title {{
            color: {text};
            font-size: 1.2rem;
            font-weight: 800;
            margin-bottom: 0.3rem;
        }}
        .empty-subtitle {{
            color: {muted};
            font-size: 0.95rem;
        }}
        [data-testid="stDataFrame"] , [data-testid="stDataEditor"] {{
            border: 1px solid {border};
            border-radius: 16px;
            overflow: hidden;
            background: {card};
        }}
        [data-testid="stDataFrame"] * , [data-testid="stDataEditor"] * {{
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
        .stButton button, .stDownloadButton button {{
            border-radius: 12px;
            font-weight: 700;
        }}
        [data-testid="stExpander"] {{
            border: 1px solid {border};
            border-radius: 14px;
            background: {card};
        }}
        h1, h2, h3, h4, h5, h6, p, label, span, div {{
            color: {text};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
