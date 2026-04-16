"""app.py
FakturaAI - glavna Streamlit aplikacija.
"""

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

from pages.dashboard import render_dashboard  # noqa: E402
from pages.upload import render_upload  # noqa: E402

PAGE_MAP = {
    "upload": render_upload,
    "pregled": render_dashboard,
}


def _expected_username() -> str:
    if hasattr(st, "secrets") and "APP_USERNAME" in st.secrets:
        return str(st.secrets["APP_USERNAME"])
    return str(os.getenv("APP_USERNAME", "")).strip()


def _expected_password() -> str:
    if hasattr(st, "secrets") and "APP_PASSWORD" in st.secrets:
        return str(st.secrets["APP_PASSWORD"])
    return str(os.getenv("APP_PASSWORD", "")).strip()


def _check_login(username: str, password: str) -> tuple[bool, str]:
    expected_user = _expected_username()
    expected_password = _expected_password()

    if expected_user and expected_password:
        ok = username == expected_user and password == expected_password
        return ok, "Pogrešno korisničko ime ili lozinka."

    ok = bool(username.strip()) and bool(password.strip())
    return ok, "Unesi korisničko ime i lozinku."


def _render_login() -> None:
    _apply_login_theme()

    left, center, right = st.columns([1.2, 1, 1.2])
    with center:
        st.markdown(
            """
            <div class="login-card">
                <div class="login-title">FakturaAI</div>
                <div class="login-subtitle">Prijavi se za pristup KIF, KUF i dnevnom prometu.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Korisničko ime", placeholder="Unesi korisničko ime")
            password = st.text_input("Lozinka", type="password", placeholder="Unesi lozinku")
            submitted = st.form_submit_button("Prijava", use_container_width=True, type="primary")

        if submitted:
            ok, error_message = _check_login(username, password)
            if ok:
                st.session_state["authenticated"] = True
                st.session_state["username"] = username.strip()
                st.session_state["active_page"] = "upload"
                st.rerun()
            else:
                st.error(error_message)

        if not (_expected_username() and _expected_password()):
            st.info("APP_USERNAME i APP_PASSWORD nisu postavljeni, pa je uključen fallback login sa bilo kojim ne-praznim unosom.")


def _apply_login_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #111827 50%, #0b1220 100%);
            color: #f8fafc;
        }
        .block-container {
            padding-top: 8vh;
            padding-bottom: 4vh;
        }
        .login-card {
            background: rgba(17, 24, 39, 0.92);
            border: 1px solid #334155;
            border-radius: 20px;
            padding: 1.4rem 1.2rem 1rem 1.2rem;
            margin-bottom: 1rem;
            box-shadow: 0 20px 60px rgba(0,0,0,0.25);
            text-align: center;
        }
        .login-title {
            font-size: 2rem;
            font-weight: 800;
            color: #f8fafc;
            margin-bottom: 0.35rem;
        }
        .login-subtitle {
            color: #cbd5e1;
            font-size: 0.98rem;
        }
        div[data-baseweb="input"] > div,
        .stTextInput > div > div {
            background: #0b1220 !important;
            color: #f8fafc !important;
            border-color: #334155 !important;
        }
        .stTextInput label,
        .stMarkdown,
        .stAlert,
        p,
        span,
        div {
            color: #f8fafc;
        }
        .stButton > button,
        .stForm button {
            border-radius: 12px;
            font-weight: 700;
        }
        section[data-testid="stSidebar"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    if not st.session_state.get("authenticated", False):
        _render_login()
        return

    active = render_sidebar()
    render_fn = PAGE_MAP.get(active, render_upload)
    render_fn()


if __name__ == "__main__":
    main()
