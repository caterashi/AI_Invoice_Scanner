import io
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

st.set_page_config(page_title="Debug", layout="wide")
st.title("🔧 Debug — PDF čitanje + GPT")

# ─────────────────────────────────────────────────────────────────────────────
# 1 — Biblioteke
# ─────────────────────────────────────────────────────────────────────────────

st.header("1️⃣ Biblioteke")

c1, c2, c3 = st.columns(3)
with c1:
    try:
        import fitz
        st.success(f"✅ PyMuPDF `{fitz.__version__}`")
    except ImportError:
        st.error("❌ PyMuPDF  →  `pip install PyMuPDF`")

with c2:
    try:
        import pdfplumber
        st.success(f"✅ pdfplumber `{pdfplumber.__version__}`")
    except ImportError:
        st.warning("⚠️ pdfplumber nije instaliran")

with c3:
    try:
        from pdf2image import convert_from_bytes
        import subprocess
        subprocess.run(["pdftoppm", "-v"], capture_output=True, check=True)
        st.success("✅ pdf2image + poppler")
    except ImportError:
        st.error("❌ pdf2image  →  `pip install pdf2image`")
    except (FileNotFoundError, subprocess.CalledProcessError):
        st.error(
            "❌ **poppler nije instaliran**\n\n"
            "Mac: `brew install poppler`\n"
            "Ubuntu: `sudo apt-get install poppler-utils`\n"
            "Streamlit Cloud: dodaj `poppler-utils` u `packages.txt`"
        )

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# 2 — PDF analiza
# ─────────────────────────────────────────────────────────────────────────────

st.header("2️⃣ PDF analiza")

uploaded = st.file_uploader("Uploaduj PDF", type=["pdf"])

if not uploaded:
    st.stop()

pdf_bytes = uploaded.read()
st.caption(f"Fajl: `{uploaded.name}` | Veličina: `{len(pdf_bytes)/1024:.1f} KB`")

# ── PyMuPDF — svi modovi ─────────────────────────────────────────────────────
st.subheader("PyMuPDF — svi modovi ekstrakcije")

try:
    import fitz

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        st.caption(f"Broj stranica: {doc.page_count}")

        for mode in ("text", "blocks", "html", "rawdict"):
            total_chars = 0
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc2:
                for page in doc2:
                    raw = page.get_text(mode)
                    if isinstance(raw, list):
                        raw = " ".join(
                            b[4] for b in raw
                            if isinstance(b, tuple) and len(b) > 4
                        )
                    elif isinstance(raw, dict):
                        raw = str(raw)
                    total_chars += len(re.sub(r"\s+", "", raw or ""))

            icon = "✅" if total_chars >= 100 else "❌"
            st.write(f"{icon} Mod `{mode}`: **{total_chars}** znakova bez razmaka")

except ImportError:
    st.error("PyMuPDF nije instaliran")
except Exception as e:
    st.error(f"PyMuPDF greška: `{e}`")

# ── pdfplumber ────────────────────────────────────────────────────────────────
st.subheader("pdfplumber")
try:
    import pdfplumber
    total_pl = 0
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            total_pl += len(re.sub(r"\s+", "", t))
    icon = "✅" if total_pl >= 100 else "❌"
    st.write(f"{icon} pdfplumber: **{total_pl}** znakova bez razmaka")
except ImportError:
    st.warning("pdfplumber nije instaliran")
except Exception as e:
    st.error(f"pdfplumber greška: `{e}`")

# ── Zaključak ─────────────────────────────────────────────────────────────────
st.subheader("Zaključak — koji mod će se koristiti")

from ai_extractor import _extract_text, _is_text_pdf
extracted = _extract_text(pdf_bytes)
clean_len = len(re.sub(r"\s+", "", extracted))

if clean_len >= 100:
    st.success(
        f"✅ **TEXT mod** — {clean_len} znakova izvučeno\n\n"
        "Tekst se šalje direktno GPT-4o."
    )
    with st.expander("Prikaži izvučeni tekst"):
        st.text(extracted[:5000] + ("..." if len(extracted) > 5000 else ""))
else:
    st.warning(
        f"⚠️ **VISION mod** — tekstualna ekstrakcija dala je samo {clean_len} znakova\n\n"
        "PDF će se konvertovati u slike i poslati GPT-4o Vision."
    )

    # Proba konverziju u sliku
    st.subheader("Test pdf2image konverzije")
    try:
        from pdf2image import convert_from_bytes
        with st.spinner("Konvertujem..."):
            pages = convert_from_bytes(pdf_bytes, dpi=150)
        st.success(f"✅ Konverzija uspješna — {len(pages)} slika")
        st.image(pages[0], caption="Stranica 1 (preview)", width=400)
    except FileNotFoundError:
        st.error(
            "❌ **poppler nije instaliran** — Vision mod ne može raditi!\n\n"
            "Mac: `brew install poppler`\n"
            "Ubuntu: `sudo apt-get install poppler-utils`\n"
            "Streamlit Cloud: `poppler-utils` u `packages.txt`"
        )
    except Exception as e:
        st.error(f"pdf2image greška: `{e}`")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# 3 — GPT ekstrakcija
# ─────────────────────────────────────────────────────────────────────────────

st.header("3️⃣ GPT ekstrakcija")

api_key = (
    st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
) or os.getenv("OPENAI_API_KEY", "")

if not api_key:
    st.error("❌ OPENAI_API_KEY nije postavljen")
    st.stop()

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

    text    = _extract_text(pdf_bytes)
    is_text = _is_text_pdf(text)
    st.info(f"Mod: **{'TEXT' if is_text else 'VISION'}**")

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
        try:
            b64_pages = _pdf_to_b64_images(pdf_bytes)
            b64       = _combine_images(b64_pages) if len(b64_pages) > 1 else b64_pages[0]
            st.caption(f"Stranica(e) konvertovano: {len(b64_pages)}")
        except Exception as e:
            st.error(f"❌ Konverzija u sliku nije uspjela: `{e}`")
            st.stop()
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
        with st.spinner("Čekam GPT..."):
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

        with st.expander("📨 Sirovi GPT odgovor", expanded=True):
            st.code(raw, language="json")

        try:
            m        = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
            json_str = m.group(1) if m else raw
            data     = json.loads(json_str)
            if not isinstance(data, list):
                data = [data]
            st.success(f"✅ Pronađeno dokumenata: **{len(data)}**")
            st.json(data)
        except Exception as e:
            st.error(f"❌ JSON parse greška: {e}")

    except Exception as e:
        st.error(f"❌ GPT greška: `{e}`")
