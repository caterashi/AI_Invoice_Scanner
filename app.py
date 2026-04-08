"""app.py — Glavna Streamlit aplikacija s login sistemom i navigacijom."""
import hashlib
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Skener Faktura AI",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300..700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #f7f6f2; }
.main .block-container { padding-top: 1.5rem; max-width: 1200px; }
div[data-testid="stSidebarContent"] {
    background: #f9f8f5 !important;
    border-right: 1px solid #dcd9d5;
}
/* Login */
.login-center {
    max-width: 380px; margin: 4rem auto;
    background: #f9f8f5; border: 1px solid #dcd9d5;
    border-radius: 16px; padding: 2.5rem 2rem;
    box-shadow: 0 4px 24px rgba(0,0,0,.08);
}
button[kind="primary"] { background-color: #01696f !important; }
</style>
""", unsafe_allow_html=True)

# ── Auth ─────────────────────────────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def get_credentials() -> tuple[str, str]:
    username = os.getenv("APP_USERNAME", "")
    pw_hash  = os.getenv("APP_PASSWORD_HASH", "")
    try:
        username = username or st.secrets.get("APP_USERNAME", "")
        pw_hash  = pw_hash  or st.secrets.get("APP_PASSWORD_HASH", "")
    except Exception:
        pass
    return username.strip(), pw_hash.strip()

def check_login(username_input: str, password_input: str) -> bool:
    stored_user, stored_hash = get_credentials()
    if not stored_user or not stored_hash:
        return False
    return (
        username_input.strip() == stored_user
        and hash_pw(password_input) == stored_hash
    )

# ── Session init ─────────────────────────────────────────────────────────────
for key, default in [
    ("authenticated", False),
    ("results", []),
    ("log", []),
    ("active_page", "dashboard"),
    ("settings", {
        "excel_path": "output/fakture.xlsx",
        "model": "gpt-4o",
        "ocr_dpi": 200,
        "ocr_max_pages": 4,
        "ocr_max_dim": 2400,
        "ocr_quality": 92,
    }),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── LOGIN ────────────────────────────────────────────────────────────────────
if not st.session_state.authenticated:
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        st.markdown("""
        <div style="text-align:center;margin-bottom:1.5rem">
          <div style="font-size:2.5rem">🧾</div>
          <h2 style="font-weight:800;color:#28251d;margin:.25rem 0">Skener Faktura AI</h2>
          <p style="color:#7a7974;font-size:.9rem">Prijavite se za nastavak</p>
        </div>
        """, unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Korisničko ime", placeholder="username")
            password = st.text_input("Lozinka", type="password", placeholder="••••••••")
            submitted = st.form_submit_button(
                "Prijavi se", use_container_width=True, type="primary"
            )
        if submitted:
            if check_login(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("❌ Pogrešno korisničko ime ili lozinka.")
    st.stop()

# ── MAIN APP ─────────────────────────────────────────────────────────────────
from sidebar import render_sidebar
from pages.dashboard import render_dashboard
from pages.upload import render_upload
from pages.invoice_detail import render_invoice_detail
from pages.settings import render_settings

active = render_sidebar()

PAGE_MAP = {
    "dashboard":      render_dashboard,
    "upload":         render_upload,
    "invoice_detail": render_invoice_detail,
    "settings":       render_settings,
}

render_fn = PAGE_MAP.get(active, render_dashboard)
render_fn()
