import io
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

st.set_page_config(page_title="Debug", layout="wide")
st.title("🔧 Debug — PyMuPDF + AI Extractor")

# ─────────────────────────────────────────────────────────────────────────────
# KORAK 1 — Provjera instaliranih biblioteka
# ─────────────────────────────────────────────────────────────────────────────

st.header("1️⃣ Biblioteke")

col1, col2, col3 = st.columns(3)

with col1:
    try:
        import fitz
        st.success(f"✅ PyMuPDF\n`{fitz.__version__}`")
    except ImportError:
        st.error("❌ PyMuPDF\n`pip install PyMuPDF`")

with col2:
    try:
        import pdfplumber
        st.success(f"✅ pdfplumber\n`{pdfplumber.__version__}`")
    except ImportError:
        st.warning("⚠️ pdfplumber\n(fallback, nije kritičan)")

with col3:
    try:
        from pdf2image import convert_from_bytes
        import subprocess
        r = subprocess.run(["pdftoppm", "-v"], capture_output=True)
        st.success("✅ pdf2image + poppler")
    except ImportError:
        st.error("❌ pdf2image nije instaliran")
    except FileNotFoundError:
        st.error("❌ poppler nije instaliran")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# KORAK 2 — Upload i provjera PDF-a
# ─────────────────────────────────────────────────────────────────────────────

st.header("2️⃣ Provjera PDF-a")

uploaded = st.file_uploader("Uploaduj PDF", type=["pdf"])

if uploaded:
    pdf_bytes = uploaded.read()
    st.caption(f"Veličina fajla: {len(pdf_bytes) / 1024:.1f} KB")

    # ── A) PyMuPDF ──────────────────────────────────────────────────────────
    st.subheader("A) PyMuPDF (fitz)")
    try:
        import fitz

        parts = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            st.caption(f"Stranica(e): {doc.page_count}")
            for i, page in enumerate(doc):
                t = page.get_text("text")
                clean = t.strip() if t else ""
                if clean:
                    parts.append(clean)
                    st.success(f"Stranica {i+1}: ✅ {len(clean)} znakova")
                    with st.expander(f"Tekst stranice {i+1}"):
                        st.text(clean[:3000] + ("..." if len(clean) > 3000 else ""))
                else:
                    st.warning(f"Stranica {i+1}: ⚠️ nema teksta")

        full = "\n\n".join(parts)
        clean_len = len(re.sub(r"\s+", "", full))

        if clean_len >= 100:
            st.success(f"✅ **Tekstualni PDF** — {clean_len} znakova → TEXT mod")
        else:
            st.error(f"❌ Slikovni PDF — {clean_len} znakova → VISION mod")

    except ImportError:
        st.error("PyMuPDF nije instaliran — `pip install PyMuPDF`")
    except Exception as e:
        st.error(f"PyMuPDF greška: `{e}`")

    st.markdown("---")

    # ── B) pdfplumber ────────────────────────────────────────────────────────
    st.subheader("B) pdfplumber (fallback)")
    try:
        import pdfplumber

        parts_pl = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                t = page.extract_text(x_tolerance=2, y_tolerance=2)
                if t and t.strip():
                    parts_pl.append(t)
                    st.success(f"Stranica {i+1}: ✅ {len(t)} znakova")
                else:
                    st.warning(f"Stranica {i+1}: ⚠️ nema teksta")

        clean_pl = len(re.sub(r"\s+", "", "".join(parts_pl)))
        if clean_pl >= 100:
            st.success(f"✅ pdfplumber čita: {clean_pl} znakova")
        else:
            st.warning(f"pdfplumber: {clean_pl} znakova (ispod praga)")

    except ImportError:
        st.warning("pdfplumber nije instaliran")
    except Exception as e:
        st.error(f"pdfplumber greška: `{e}`")

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # KORAK 3 — Kompletan GPT poziv
    # ─────────────────────────────────────────────────────────────────────────

    st.header("3️⃣ GPT ekstrakcija")

    api_key = (
        st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
    ) or os.getenv("OPENAI_API_KEY", "")

    if not api_key:
        st.error("❌ API ključ nije postavljen — provjeri .env ili st.secrets")
    else:
        st.success(f"✅ API ključ: `{api_key[:8]}...{api_key[-4:]}`")

        if st.button("🚀 Pokreni ekstrakciju", type="primary"):
            from ai_extractor import (
                _extract_text, _is_text_pdf,
                _pdf_to_b64_images, _combine_images,
                _SYSTEM_PROMPT,
            )
            import json
            from openai import OpenAI

            client = OpenAI(api_key=api_key)

            # Tekst ekstrakcija
            text     = _extract_text(pdf_bytes)
            is_text  = _is_text_pdf(text)

            st.info(f"Mod: **{'TEXT' if is_text else 'VISION'}** | "
                    f"Znakova: {len(re.sub(r'\s+','',text))}")

            # Priprema poruka
            if is_text:
                messages = [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Fajl: {uploaded.name}\n\n"
                        "Pronađi i izvuci SVE dokumente iz teksta ispod.\n\n"
                        f"TEKST DOKUMENTA:\n{text}"
                    )},
                ]
            else:
                b64_pages = _pdf_to_b64_images(pdf_bytes)
                b64       = _combine_images(b64_pages) if len(b64_pages) > 1 else b64_pages[0]
                st.caption(f"Slike: {len(b64_pages)} stranica(e)")
                messages = [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high",
                        }},
                        {"type": "text", "text": (
                            f"Fajl: {uploaded.name}\n"
                            "Pronađi i izvuci SVE dokumente s ove slike."
                        )},
                    ]},
                ]

            try:
                with st.spinner("Čekam GPT odgovor..."):
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        max_tokens=4096,
                        temperature=0,
                        messages=messages,
                    )

                raw = resp.choices[0].message.content.strip()

                st.caption(
                    f"Model: `{resp.model}` | "
                    f"Prompt tokeni: `{resp.usage.prompt_tokens}` | "
                    f"Output tokeni: `{resp.usage.completion_tokens}`"
                )

                # Sirovi odgovor
                with st.expander("📨 Sirovi GPT odgovor", expanded=True):
                    st.code(raw, language="json")

                # Parsirani JSON
                try:
                    m        = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
                    json_str = m.group(1) if m else raw
                    data     = json.loads(json_str)
                    if not isinstance(data, list):
                        data = [data]
                    st.success(f"✅ Parsirano — pronađeno dokumenata: **{len(data)}**")
                    st.json(data)
                except Exception as e:
                    st.error(f"❌ JSON parse greška: {e}")

            except Exception as e:
                st.error(f"❌ GPT poziv nije uspio: `{e}`")
