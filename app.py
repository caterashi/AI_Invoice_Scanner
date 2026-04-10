from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

st.set_page_config(
    page_title="FakturaAI",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_dotenv(Path(__file__).parent / ".env")

_DEFAULTS: dict = {
    "openai_api_key": (
        st.secrets.get("OPENAI_API_KEY", "")
        if hasattr(st, "secrets")
        else os.getenv("OPENAI_API_KEY", "")
    ),
    "selected_model": "gpt-4o",
    "invoices": [],
    "last_export": None,
    "active_page": "upload",
    "app_dark_mode": True,
    "authenticated": False,
    "username": "",
}

for _key, _val in _DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _val

st.session_state["app_dark_mode"] = True

from login import render_login
from sidebar import render_sidebar
from pages.upload import render_upload
from pages.dashboard import render_dashboard

PAGE_MAP = {
    "upload": render_upload,
    "pregled": render_dashboard,
}

if not st.session_state.get("authenticated", False):
    render_login()
    st.stop()

active = render_sidebar()
render_fn = PAGE_MAP.get(active, render_upload)
render_fn()
