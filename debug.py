import io
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

st.set_page_config(page_title="Debug", layout="wide")
st.title("🔧 Debug — AI Extractor")

# ─────────────────────────────────────────────────────────────────────────────
# KORAK 1 — Provjera API ključa
# ─────────────────────────────────────────────────────────────────────────────

st.header("1️⃣ API ključ")

api_key = (
    st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
) or os.getenv("OPENAI_API_KEY", "")

if api_key:
    masked = api_key[:8] + "..." + api_key[-4:]
    st.success(f"✅ API ključ pronađen: `{masked}`")
else:
    st.error("❌ API ključ NIJE pronađen — provjeri .env ili st.secrets")
    st.stop()

if st.button("🔌 Testiraj API konekciju"):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp   = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=10,
            messages=[{"role": "user", "content": "Reci samo: OK"}],
        )
        st.success(f"✅ API radi! Odgovor: `{resp.choices[0].message.content}`")
        st.caption(f"Model: {resp.model} | Tokeni: {resp.usage.total_tokens}")
    except Exception as e:
        st.error(f"❌ API greška: {e}")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# KORAK 2 — Provjera pdfplumber i pdf2image / poppler
# ─────────────────────────────────────────────────────────────────────────────

st.header("2️⃣ PDF biblioteke")

col1, col2 = st.columns(2)

with col1:
    st.subheader("pdfplumber")
    try:
        import pdfplumber
        st.success(f"✅ pdfplumber instaliran: `{pdfplumber.__version__}`")
    except ImportError:
        st.error("❌ pdfplumber nije instaliran — dodaj u requirements.txt")

with col2:
    st.subheader("pdf2image + poppler")
    try:
        from pdf2image import convert_from_bytes
        st.success("✅ pdf2image instaliran")

        # Provjeri poppler direktno
        import subprocess
        result = subprocess.run(["pdftoppm", "-v"], capture_output=True, text=True)
        if result.returncode == 0 or "pdftoppm" in result.stderr.lower():
            st.success("✅ poppler instaliran")
        else:
            st.error("❌ poppler NIJE instaliran — dodaj u packages.txt: `poppler-utils`")
    except ImportError:
        st.error("❌ pdf2image nije instaliran — dodaj u requirements.txt")
    except FileNotFoundError:
        st.error(
            "❌ **poppler nije instaliran na sistemu!**\n\n"
            "- Lokalno (Ubuntu/Debian): `sudo apt-get install poppler-utils`\n"
            "- Lokalno (Mac): `brew install poppler`\n"
            "- Lokalno (Windows): preuzmi s https://github.com/oschwartz10612/poppler-windows/releases\n"
            "- Streamlit Cloud: dodaj `poppler-utils` u `packages.txt`"
        )

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# KORAK 3 — Test konverzije PDF → slika
# ─────────────────────────────────────────────────────────────────────────────

st.header("3️⃣ Test: PDF → slika (Vision mod)")

uploaded = st.file_uploader("Uploaduj slikovni PDF za test", type=["pdf"])

if uploaded:
    pdf_bytes = uploaded.read()

    # A) pdfplumber
    st.subheader("A) pdfplumber čitanje")
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            st.caption(f"Stranica(e): {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages):
                t = page.extract_text(x_tolerance=2, y_tolerance=2)
                if t:
                    parts.append(t)
                    st.success(f"Stranica {i+1}: ✅ {len(t)} znakova")
                else:
                    st.warning(f"Stranica {i+1}: ⚠️ nema teksta — slikovni PDF")
        if not parts:
            st.info("➡️ Nema teksta → prelazi na Vision mod (pdf2image)")
    except Exception as e:
        st.error(f"pdfplumber greška: {e}")

    # B) pdf2image konverzija
    st.subheader("B) pdf2image konverzija u slike")
    try:
        from pdf2image import convert_from_bytes
        from PIL import Image

        with st.spinner("Konvertujem PDF u slike..."):
            pages = convert_from_bytes(pdf_bytes, dpi=150)

        st.success(f"✅ Konverzija uspješna — {len(pages)} slika")

        for i, page in enumerate(pages[:3]):  # prikaži max 3 stranice
            st.caption(f"Stranica {i+1}: {page.width}x{page.height}px")
            st.image(page, width=400)

        if len(pages) > 3:
            st.caption(f"... i još {len(pages)-3} stranica")

    except FileNotFoundError:
        st.error(
            "❌ **poppler nije instaliran!** pdf2image ne može raditi bez njega.\n\n"
            "**Rješenje:**\n"
            "- Mac: `brew install poppler`\n"
            "- Ubuntu: `sudo apt-get install poppler-utils`\n"
            "- Windows: preuzmi poppler i dodaj u PATH\n"
            "- Streamlit Cloud: dodaj `poppler-utils` u `packages.txt`"
        )
        st.stop()
    except Exception as e:
        st.error(f"❌ pdf2image greška: {e}")
        st.stop()

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# KORAK 4 — Kompletan GPT poziv s punim logom
# ─────────────────────────────────────────────────────────────────────────────

st.header("4️⃣ Kompletan GPT poziv — puni log")

uploaded2 = st.file_uploader(
    "Uploaduj PDF za ekstrakciju",
    type=["pdf"],
    key="full_test",
)

if uploaded2:
    pdf_bytes2 = uploaded2.read()

    if st.button("🚀 Pokreni ekstrakciju s logom"):
        from ai_extractor import (
            _extract_text, _is_text_pdf,
            _pdf_to_b64_images, _combine_images,
            _SYSTEM_PROMPT,
        )
        import json
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        # A) pdfplumber
        text      = _extract_text(pdf_bytes2)
        clean_len = len(re.sub(r"\s+", "", text))
        is_text   = _is_text_pdf(text)

        st.subheader("📄 A) Tekst iz PDF-a")
        st.caption(f"{clean_len} znakova | Mod: **{'TEXT' if is_text else 'VISION'}**")
        if text:
            with st.expander("Prikaži tekst"):
                st.text(text[:5000] + ("..." if len(text) > 5000 else ""))
        else:
            st.info("Nema teksta → Vision mod")

        # B) Priprema poruka za GPT
        if is_text:
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Fajl: {uploaded2.name}\n\n"
                    "Pronađi i izvuci SVE dokumente iz teksta ispod.\n\n"
                    f"TEKST DOKUMENTA:\n{text}"
                )},
            ]
            st.caption("GPT mod: TEXT")
        else:
            b64_pages = _pdf_to_b64_images(pdf_bytes2)
            b64       = _combine_images(b64_pages) if len(b64_pages) > 1 else b64_pages[0]
            st.caption(f"GPT mod: VISION | {len(b64_pages)} stranica(e)")
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "high",
                    }},
                    {"type": "text", "text": (
                        f"Fajl: {uploaded2.name}\n"
                        "Pronađi i izvuci SVE dokumente s ove slike."
                    )},
                ]},
            ]

        # C) GPT poziv
        try:
            with st.spinner("Čekam GPT..."):
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    max_tokens=4096,
                    temperature=0,
                    messages=messages,
                )
            raw = resp.choices[0].message.content.strip()

            st.subheader("📨 B) Sirovi GPT odgovor")
            st.caption(
                f"Model: {resp.model} | "
                f"Prompt tokeni: {resp.usage.prompt_tokens} | "
                f"Output tokeni: {resp.usage.completion_tokens}"
            )
            st.code(raw, language="json")

            # D) Parsiranje
            try:
                m        = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
                json_str = m.group(1) if m else raw
                data     = json.loads(json_str)
                st.subheader("✅ C) Parsirani JSON")
                st.json(data)
                st.success(f"Pronađeno dokumenata: **{len(data) if isinstance(data, list) else 1}**")
            except Exception as e:
                st.error(f"❌ JSON parse greška: {e}")

        except Exception as e:
            st.error(f"❌ GPT poziv nije uspio: {e}")
