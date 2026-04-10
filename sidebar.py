"""
sidebar.py
==========
"""

from __future__ import annotations

import streamlit as st


_PAGES = [
    {"key": "upload", "label": "📤 Učitaj račune", "desc": "Upload i ekstrakcija PDF faktura"},
    {"key": "pregled", "label": "📊 Pregled", "desc": "Pregled svih unesenih faktura"},
]


def render_sidebar() -> str:
    _apply_sidebar_theme()

    with st.sidebar:
        st.markdown(
            """
            <div class="sb-brand">
                <div class="sb-icon">🧾</div>
                <div class="sb-title">FakturaAI</div>
                <div class="sb-subtitle">Ekstrakcija podataka s faktura</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div class='sb-section'>Navigacija</div>", unsafe_allow_html=True)

        active_page = st.session_state.setdefault("active_page", "upload")

        for page in _PAGES:
            is_active = active_page == page["key"]
            if st.button(
                page["label"],
                key=f"nav_{page['key']}",
                width="stretch",
                type="primary" if is_active else "secondary",
                help=page["desc"],
            ):
                st.session_state["active_page"] = page["key"]
                st.rerun()

        st.markdown("<div class='sb-section'>Status</div>", unsafe_allow_html=True)

        invoice_count = len(st.session_state.get("invoices", []))
        st.markdown(
            f"""
            <div class="sb-card">
                <div class="sb-card-label">Faktura u listi</div>
                <div class="sb-card-value">{invoice_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="sb-footer">
                FakturaAI · uredan pregled · brža obrada
            </div>
            """,
            unsafe_allow_html=True,
        )

    return st.session_state["active_page"]


def _apply_sidebar_theme() -> None:
    bg = "#0f172a"
    card = "#111827"
    border = "#334155"
    text = "#f8fafc"
    muted = "#cbd5e1"
    accent = "#38bdf8"

    st.markdown(
        f"""
        <style>
        section[data-testid="stSidebar"] {{
            background: {bg};
            border-right: 1px solid {border};
        }}
        section[data-testid="stSidebar"] * {{
            color: {text};
        }}
        .sb-brand {{
            text-align: center;
            padding: 0.6rem 0 1rem;
            margin-bottom: 0.6rem;
            border-bottom: 1px solid {border};
        }}
        .sb-icon {{
            font-size: 2.4rem;
            margin-bottom: 0.2rem;
        }}
        .sb-title {{
            font-size: 1.35rem;
            font-weight: 800;
            color: {text};
        }}
        .sb-subtitle {{
            color: {muted};
            font-size: 0.82rem;
            margin-top: 0.1rem;
        }}
        .sb-section {{
            margin-top: 0.9rem;
            margin-bottom: 0.45rem;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: {muted};
            font-weight: 700;
        }}
        .sb-card {{
            background: linear-gradient(135deg, {card} 0%, {bg} 100%);
            border: 1px solid {border};
            border-radius: 14px;
            padding: 0.9rem 0.95rem;
            margin-top: 0.25rem;
        }}
        .sb-card-label {{
            font-size: 0.82rem;
            color: {muted};
            margin-bottom: 0.2rem;
        }}
        .sb-card-value {{
            font-size: 1.55rem;
            font-weight: 800;
            color: {accent};
        }}
        .sb-footer {{
            margin-top: 1rem;
            color: {muted};
            font-size: 0.78rem;
            text-align: center;
            padding-top: 0.8rem;
            border-top: 1px solid {border};
        }}
        section[data-testid="stSidebar"] .stButton button,
        section[data-testid="stSidebar"] .stMarkdown p,
        section[data-testid="stSidebar"] .stCaption {{
            color: {text} !important;
        }}
        section[data-testid="stSidebar"] .stButton button {{
            border-radius: 12px;
            font-weight: 700;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
