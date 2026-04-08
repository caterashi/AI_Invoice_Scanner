"""settings.py — Postavke aplikacije."""
import os
import streamlit as st
from ai_extractor import get_available_models


def render_settings():
    st.markdown("# ⚙️ Postavke")
    st.divider()

    if "settings" not in st.session_state:
        st.session_state.settings = {
            "excel_path": "output/fakture.xlsx",
            "model": "gpt-4o",
            "ocr_dpi": 200,
            "ocr_max_pages": 4,
            "ocr_max_dim": 2400,
            "ocr_quality": 92,
        }
    s = st.session_state.settings

    # Excel putanja
    st.markdown("### 📁 Excel datoteka")
    st.caption("Putanja gdje se automatski sprema Excel nakon svake ekstrakcije.")
    excel_path = st.text_input(
        "Putanja do Excel datoteke",
        value=s.get("excel_path", "output/fakture.xlsx"),
        placeholder="output/fakture.xlsx",
    )
    if excel_path != s.get("excel_path"):
        s["excel_path"] = excel_path

    # Provjeri postoji li
    if os.path.exists(excel_path):
        st.success(f"✅ Datoteka postoji: `{excel_path}`")
    else:
        st.info(f"ℹ️ Datoteka će biti kreirana pri prvom exportu: `{excel_path}`")

    st.divider()

    # AI model
    st.markdown("### 🤖 AI model")
    models = get_available_models()
    current_model = s.get("model", "gpt-4o")
    model = st.selectbox(
        "Odaberi OpenAI model",
        options=models,
        index=models.index(current_model) if current_model in models else 0,
        help="gpt-4o = najprecizniji | gpt-4o-mini = brži i jeftiniji",
    )
    s["model"] = model

    model_info = {
        "gpt-4o":       ("Visoka preciznost, sporiji, skuplji.", "🟢"),
        "gpt-4o-mini":  ("Brži i jeftiniji, nešto manja preciznost.", "🟡"),
        "gpt-4-turbo":  ("Stariji model, dobra preciznost.", "🟡"),
    }
    if model in model_info:
        desc, badge = model_info[model]
        st.markdown(f"{badge} {desc}")

    st.divider()

    # OCR postavke
    st.markdown("### 🔬 OCR / Obrada slike")
    st.caption("Postavke za pretvaranje PDF-a u sliku i skaliranje.")

    col1, col2 = st.columns(2)
    with col1:
        dpi = st.slider("PDF DPI (kvaliteta renderiranja)", 72, 300, s.get("ocr_dpi", 200), step=25,
                        help="Viši DPI = bolja kvaliteta, ali sporije i više memorije.")
        s["ocr_dpi"] = dpi
        max_pages = st.number_input("Max stranica po PDF-u", 1, 10, s.get("ocr_max_pages", 4),
                                    help="Maksimalan broj stranica koji se šalje AI-u.")
        s["ocr_max_pages"] = int(max_pages)
    with col2:
        max_dim = st.slider("Max dimenzija slike (px)", 800, 4096, s.get("ocr_max_dim", 2400), step=200,
                            help="Slike veće od ove dimenzije bit će smanjene.")
        s["ocr_max_dim"] = max_dim
        quality = st.slider("JPEG kvaliteta (%)", 60, 100, s.get("ocr_quality", 92),
                            help="Viša kvaliteta = veći fajl, bolji OCR rezultati.")
        s["ocr_quality"] = quality

    st.divider()

    # API ključ info (read-only)
    st.markdown("### 🔑 API ključ")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        st.success(f"✅ API ključ aktivan: `{api_key[:8]}...{api_key[-4:]}`")
    else:
        st.error("❌ OPENAI_API_KEY nije pronađen u .env fajlu!")
    st.caption("API ključ se postavlja isključivo u `.env` fajlu ili Streamlit Secrets. Ne može se mijenjati ovdje.")

    if st.button("💾 Spremi postavke", type="primary"):
        st.session_state.settings = s
        st.success("✅ Postavke spremljene za ovu sesiju.")
