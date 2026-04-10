from __future__ import annotations

import os

import bcrypt
import streamlit as st


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def render_login() -> None:
    st.markdown("## Prijava")
    st.caption("Prijavite se za pristup aplikaciji FakturaAI.")

    expected_username = os.getenv("APP_USERNAME", "")
    expected_password_hash = os.getenv("APP_PASSWORD_HASH", "")

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Korisničko ime")
        password = st.text_input("Lozinka", type="password")
        submitted = st.form_submit_button("Prijavi se", use_container_width=True)

    if submitted:
        if not expected_username or not expected_password_hash:
            st.error("Login nije konfigurisan. Nedostaju APP_USERNAME ili APP_PASSWORD_HASH.")
            return

        if username == expected_username and verify_password(password, expected_password_hash):
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.success("Uspješna prijava.")
            st.rerun()

        st.session_state["authenticated"] = False
        st.session_state["username"] = ""
        st.error("Pogrešno korisničko ime ili lozinka.")
