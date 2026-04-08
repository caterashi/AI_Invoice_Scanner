"""
sidebar.py
==========
Streamlit sidebar navigacija s tri stranice:
  - 📊 Pregled       — pregled svih uvezenih faktura
  - 📤 Učitaj račun  — upload i AI ekstrakcija
  - ⚙️  Postavke     — API ključ, model, putanja za export
"""

from __future__ import annotations
from pathlib import Path
import streamlit as st

PAGES = {
    "📊 Pregled":       "pregled",
    "📤 Učitaj račun":  "upload",
    "⚙️  Postavke":     "postavke",
}

_DEFAULT_PAGE = "📤 Učitaj račun"


def _init_state() -> None:
    defaults = {
        "active_page":    _DEFAULT_PAGE,
        "openai_api_key": "",
        "selected_model": "gpt-4o",
        "export_path":    str(Path(__file__).parent / "output" / "fakture.xlsx"),
        "auto_export":    True,
        "invoices":       [],
        "last_export":    None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_sidebar() -> str:
    """
    Renderuje sidebar navigaciju.
    Vraća ključ aktivne stranice: "pregled" | "upload" | "postavke"
    """
    _init_state()

    with st.sidebar:
        st.markdown(
            """
            <div style="text-align:center; padding: 10px 0 18px 0;">
              <div style="font-size:2.2rem;">🧾</div>
              <div style="font-size:1.15rem; font-weight:700;
                          color:#1F3864; line-height:1.2;">
                Faktura<span style="color:#2E75B6;">AI</span>
              </div>
              <div style="font-size:0.72rem; color:#888; margin-top:2px;">
                AI ekstrakcija podataka s računa
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()

        st.markdown(
            "<p style='font-size:0.72rem; font-weight:600; "
            "text-transform:uppercase; letter-spacing:0.07em; "
            "color:#888; margin-bottom:6px;'>Navigacija</p>",
            unsafe_allow_html=True,
        )

        for label in PAGES:
            is_active = st.session_state["active_page"] == label
            if st.button(
                label,
                key=f"nav_{label}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state["active_page"] = label
                st.rerun()

        st.divider()

        invoices = st.session_state.get("invoices", [])
        n_total  = len(invoices)
        n_valid  = sum(1 for inv in invoices if getattr(inv, "_valid", True))
        n_warn   = sum(
            1 for inv in invoices
            if getattr(inv, "_warnings", []) and getattr(inv, "_valid", True)
        )
        n_err = n_total - n_valid

        st.markdown(
            "<p style='font-size:0.72rem; font-weight:600; "
            "text-transform:uppercase; letter-spacing:0.07em; "
            "color:#888; margin-bottom:8px;'>Statistika sesije</p>",
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Ukupno", n_total)
        with col2:
            st.metric("Valjane", n_valid)

        if n_warn > 0 or n_err > 0:
            col3, col4 = st.columns(2)
            with col3:
                st.metric("⚠️ Upoz.", n_warn)
            with col4:
                st.metric("❌ Greške", n_err)

        last = st.session_state.get("last_export")
        if last:
            st.caption(f"Zadnji export: {last.strftime('%d.%m.%Y %H:%M')}")

        st.divider()

        api_key = st.session_state.get("openai_api_key", "")
        if api_key and api_key.startswith("sk-"):
            st.success("✅ API ključ postavljen")
        else:
            st.warning("⚠️ API ključ nije postavljen")
            if st.button("→ Idi na Postavke", use_container_width=True):
                st.session_state["active_page"] = "⚙️  Postavke"
                st.rerun()

        st.markdown(
            "<div style='text-align:center; font-size:0.68rem; "
            "color:#bbb; padding-top:10px;'>"
            "FakturaAI v1.0 · Powered by GPT-4o"
            "</div>",
            unsafe_allow_html=True,
        )

    if st.session_state["active_page"] not in PAGES:
        st.session_state["active_page"] = _DEFAULT_PAGE
    return PAGES[st.session_state["active_page"]]


def go_to(page_label: str) -> None:
    """Programski navigiraj na stranicu."""
    if page_label in PAGES:
        st.session_state["active_page"] = page_label
        st.rerun()
    else:
        raise ValueError(f"Nepoznata stranica: '{page_label}'. Dozvoljene: {list(PAGES.keys())}")


def current_page() -> str:
    """Vrati ključ trenutno aktivne stranice."""
    _init_state()
    return PAGES.get(st.session_state["active_page"], "upload")

