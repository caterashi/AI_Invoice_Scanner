"""
sidebar.py
==========
Redizajnirani sidebar sa dark/light opcijom.
"""

from __future__ import annotations

import streamlit as st


_THEME_KEY = "app_dark_mode"

_PAGES = [
    {"key": "upload", "label": "📤 Učitaj račune", "desc": "Upload i ekstrakcija PDF faktura"},
    {"key": "pregled", "label": "📊 Pregled", "desc": "Pregled svih unesenih faktura"},
]


def render_sidebar() -> str:
    _init_theme_state()
    dark_mode = st.session_state[_THEME_KEY]
    _apply_sidebar_theme(dark_mode)

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

        st.markdown("<div class='sb-section'>Prikaz</div>", unsafe_allow_html=True)
        dark_mode = st.toggle("Dark mode", key=_THEME_KEY)
        st.markdown(
            f"<div class='sb-note'>Aktivni prikaz: <b>{'dark' if dark_mode else 'light'}</b> mode</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div class='sb-section'>Navigacija</div>", unsafe_allow_html=True)

        if "active_page" not in st.session_state:
            st.session_state["active_page"] = "upload"

        for page in _PAGES:
            is_active = st.session_state["active_page"] == page["key"]
            if st.button(
                page["label"],
                key=f"nav_{page['key']}",
                use_container_width=True,
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


def _init_theme_state() -> None:
    if _THEME_KEY not in st.session_state:
        st.session_state[_THEME_KEY] = True


def _apply_sidebar_theme(dark_mode: bool) -> None:
    if dark_mode:
        bg = "#0f172a"
        card = "#111827"
        border = "#334155"
        text = "#f8fafc"
        muted = "#cbd5e1"
        accent = "#38bdf8"
    else:
        bg = "#f8fafc"
        card = "#ffffff"
        border = "#dbe4f0"
        text = "#0f172a"
        muted = "#475569"
        accent = "#2563eb"

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
            text-align:center;
            padding: 0.6rem 0 1rem 0;
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
        .sb-note {{
            background: {card};
            border: 1px solid {border};
            border-radius: 12px;
            padding: 0.65rem 0.8rem;
            margin: 0.35rem 0 0.7rem 0;
            color: {text};
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
            text-align:center;
            padding-top: 0.8rem;
            border-top: 1px solid {border};
        }}
        section[data-testid="stSidebar"] .stToggle label,
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
