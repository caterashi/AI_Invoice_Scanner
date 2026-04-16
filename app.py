from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from login import render_login
from pages.upload import render_upload

st.set_page_config(
    page_title="FakturaAI",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

load_dotenv(Path(__file__).resolve().parent / ".env")

DEFAULTS = {
    "openai_api_key": st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else os.getenv("OPENAI_API_KEY", ""),
    "selected_model": "gpt-4o",
    "invoices": [],
    "last_export": None,
    "active_page": "upload",
    "app_dark_mode": True,
    "authenticated": False,
    "username": "",
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def _apply_theme() -> None:
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] {
            display: none !important;
        }

        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }

        .app-topbar {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 16px;
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
        }

        .app-title {
            font-size: 1.6rem;
            font-weight: 800;
            color: #f8fafc;
            margin: 0;
        }

        .app-subtitle {
            color: #cbd5e1;
            font-size: 0.95rem;
            margin-top: 0.2rem;
        }

        .stButton > button {
            border-radius: 12px;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _logout() -> None:
    st.session_state["authenticated"] = False
    st.session_state["username"] = ""
    st.session_state["active_page"] = "upload"
    st.rerun()


def _render_topbar() -> None:
    left, mid, right = st.columns([5, 2, 1])

    with left:
        st.markdown(
            """
            <div class="app-topbar">
                <div class="app-title">FakturaAI</div>
                <div class="app-subtitle">Upload i ekstrakcija KIF / KUF / dnevnog prometa.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with mid:
        username = str(st.session_state.get("username", "") or "").strip()
        if username:
            st.markdown("")
            st.caption(f"Prijavljen: {username}")

    with right:
        st.markdown("")
        st.markdown("")
        st.button(
            "Odjava",
            key="logout_main",
            use_container_width=True,
            on_click=_logout,
        )


def main() -> None:
    _apply_theme()

    if not st.session_state.get("authenticated", False):
        render_login()
        return

    st.session_state["active_page"] = "upload"
    _render_topbar()
    render_upload()


if __name__ == "__main__":
    main()
