from __future__ import annotations

import streamlit as st

_PAGES = [
    {"key": "upload", "label": "📤 Učitaj račune", "desc": "Upload i ekstrakcija PDF faktura"},
    {"key": "pregled", "label": "📊 Pregled", "desc": "Pregled svih unesenih faktura"},
]


def render_sidebar() -> str:
    _apply_sidebar_theme()

    with st.sidebar:
        st.markdown("## 🧾 FakturaAI")
        st.caption(f"Prijavljeni korisnik: {st.session_state.get('username', '')}")

        st.markdown("---")

        current_page = st.session_state.get("active_page", "upload")

        for page in _PAGES:
            if st.button(
                page["label"],
                use_container_width=True,
                type="primary" if current_page == page["key"] else "secondary",
                key=f"nav_{page['key']}",
            ):
                st.session_state["active_page"] = page["key"]
                current_page = page["key"]

            st.caption(page["desc"])

        st.markdown("---")

        if st.button("🚪 Odjava", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state["username"] = ""
            st.session_state["active_page"] = "upload"
            st.rerun()

    return st.session_state.get("active_page", "upload")


def _apply_sidebar_theme() -> None:
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        }
        section[data-testid="stSidebar"] * {
            color: white !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
