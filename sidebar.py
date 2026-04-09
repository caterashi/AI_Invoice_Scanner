"""
sidebar.py
==========
Sidebar navigacija — renderuje meni i vraća naziv aktivne stranice.
"""

from __future__ import annotations

import streamlit as st


_PAGES = [
    {"key": "upload",  "label": "📤 Učitaj račune", "desc": "Upload i ekstrakcija PDF faktura"},
    {"key": "pregled", "label": "📊 Pregled",        "desc": "Pregled svih unesenih faktura"},
]


def render_sidebar() -> str:
    """
    Renderuje sidebar i vraća key aktivne stranice.
    Vraća: "upload" ili "pregled".
    """
    with st.sidebar:

        # ── Logo / naslov ─────────────────────────────────────────────────
        st.markdown(
            """
            <div style="text-align:center; padding: 1.2rem 0 0.8rem 0;">
                <span style="font-size:2.6rem;">🧾</span>
                <h2 style="margin:0.3rem 0 0 0; font-size:1.5rem; font-weight:700;">
                    FakturaAI
                </h2>
                <p style="margin:0.2rem 0 0 0; font-size:0.75rem; color:#888;">
                    Ekstrakcija podataka s faktura
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()

        # ── Navigacija ────────────────────────────────────────────────────
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

        st.divider()

        # ── Brojač faktura ─────────────────────────────────────────────────
        invoice_count = len(st.session_state.get("invoices", []))
        if invoice_count > 0:
            st.metric(label="Faktura u listi", value=invoice_count)
        else:
            st.caption("📭 Lista faktura je prazna")

        # ── Footer ─────────────────────────────────────────────────────────
        st.markdown(
            """
            <div style="position:fixed; bottom:1rem; font-size:0.7rem; color:#bbb;">
                FakturaAI &nbsp;·&nbsp; powered by GPT-4o
            </div>
            """,
            unsafe_allow_html=True,
        )

    return st.session_state["active_page"]


