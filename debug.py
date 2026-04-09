"""
debug.py  —  streamlit run debug.py
"""

import io, os, re
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
        r = subprocess.run(["pdftoppm", "-v"], capture_output=True)
        st.success("✅ pdf2image + poppler")
        _poppler_ok = True
    except ImportError:
        st.error("❌ pdf2image  →  `pip install pdf2image`")
        _poppler_ok = False
    except FileNotFoundError:
        st.error(
            "❌ **poppler nije instaliran**\n\n"
            "Mac: `brew install poppler`\n"
            "Ubuntu: `sudo apt-get install poppler-utils`\n"
            "Streamlit Cloud: `poppler-utils` u `packages.txt`"
        )
        _poppler_ok = False

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# 2 — Upload
# ─────────────────────────────────────────────────────────────────────────────
st.header("2️⃣ Analiza PDF-a")
uploaded = st.file_uploader("Uploaduj PDF", type=["pdf"])
if not uploaded:
    st.stop()

pdf_bytes = uploaded.read()
st.caption(f"`{uploaded.name}` | `{len(pdf_bytes)/1024:.1f} KB`")

# ── A) PyMuPDF plain text ────────────────────────────────────────────────────
st.subheader("A) PyMuPDF — text mod")
try:
    import fitz
    text_chars = 0
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        st.caption(f"Stranica(e): {doc.page_count}")
        for page in doc:
            t = page.get_text("text") or ""
            text_chars += len(re.sub(r"\s+", "", t))
    icon = "✅" if text_chars >= 100 else "❌"
    st.write(f"{icon} text mod: **{text_chars}** znakova bez razmaka")
except Exception as e:
    st.error(f"PyMuPDF greška: `{e}`")

# ── B) PyMuPDF HTML — s i bez stripovanja ───────────────────────────────────
st.subheader("B) PyMuPDF — html mod (s uklanjanjem img tagova)")
try:
    import fitz
    raw_html_chars    = 0
    stripped_chars    = 0
    stripped_parts    = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            html = page.get_text("html") or ""
            raw_html_chars += len(re.sub(r"\s+", "", html))

            # Strip img tagova i HTML tagova
            clean = re.sub(r"<img[^>]*>", "", html, flags=re.IGNORECASE)
            clean = re.sub(r"<[^>]+>", " ", clean)
            clean = (clean
                     .replace("&amp;", "&").replace("&lt;", "<")
                     .replace("&gt;", ">").replace("&nbsp;", " ")
                     .replace("&#39;", "'").replace("&quot;", '"'))
            clean = re.sub(r"\s+", " ", clean).strip()
            stripped_chars += len(re.sub(r"\s+", "", clean))
            if clean:
                stripped_parts.append(clean)

    st.write(f"📦 Sirovi HTML:               **{raw_html_chars:,}** znakova (img base64 uključen)")
    icon = "✅" if stripped_chars >= 100 else "❌"
    st.write(f"{icon}  Nakon uklanjanja img: **{stripped_chars:,}** znakova")

    if stripped_chars >= 100:
        st.success("➡️ TEXT mod će biti korišten (html→strip)")
        with st.expander("Prikaži čisti tekst (prva 3000 znaka)"):
            preview = " ".join(stripped_parts)[:3000]
            st.text(preview)
    else:
        st.warning(
            "➡️ Nakon uklanjanja img tagova nema teksta — "
            "PDF je **čisto slikovni** (scanned). "
            "Koristit će se **VISION mod**."
        )
except Exception as e:
    st.error(f"HTML strip greška: `{e}`")

# ── C) Finalni zaključak kroz ai_extractor ───────────────────────────────────
st.subheader("C) Finalni zaključak — ai_extractor._extract_text()")
try:
    from ai_extractor import _extract_text, _is_text_pdf
    extracted = _extract_text(pdf_bytes)
    clean_len = len(re.sub(r"\s+", "", extracted))

    if clean_len >= 100:
        st.success(f"✅ **TEXT mod** — {clean_len:,} znakova → šalje se GPT-4o")
        with st.expander("Prikaži tekst"):
            st.text(extracted[:5000] + ("..." if len(extracted) > 5000 else ""))
    else:
        st.warning(f"⚠️ **VISION mod** — samo {clean_len} znakova teksta")
except Exception as e:
    st.error(f"ai_extractor greška: `{e}`")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# 3 — Vision test (pdf2image)
# ─────────────────────────────────────────────────────────────────────────────
st.header("3️⃣ Vision mod — pdf2image test")
try:
    from pdf2image import convert_from_bytes
    with st.spinner("Konvertujem PDF u slike..."):
        pages = convert_from_bytes(pdf_bytes, dpi=150)
    st.success(f"✅ Konverzija uspješna — {len(pages)} slika")
    st.image(pages[0], caption="Stranica 1 (preview, 150 DPI)", width=380)
    if len(pages) > 1:
        st.caption(f"... i još {len(pages)-1} stranica")
except FileNotFoundError:
    st.error(
        "❌ **poppler nije instaliran** — Vision mod ne može raditi!\n\n"
        "**Mac:** `brew install poppler`\n"
        "**Ubuntu:** `sudo apt-get install poppler-utils`\n"
        "**Windows:** https://github.com/oschwartz10612/poppler-windows/releases → dodaj u PATH\n"
        "**Streamlit Cloud:** dodaj `poppler-utils` u `packages.txt`"
    )
    st.stop()
except Exception as e:
    st.error(f"pdf2image greška: `{e}`")
    st.stop()

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# 4 — GPT ekstrakcija
# ─────────────────────────────────────────────────────────────────────────────
st.header("4️⃣ GPT ekstrakcija")

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
                "Pronađi i izvuci SVE dokumente.\n\n"
                f"TEKST:\n{text}"
            )},
        ]
    else:
        try:
            b64_pages = _pdf_to_b64_images(pdf_bytes)
            b64       = _combine_images(b64_pages) if len(b64_pages) > 1 else b64_pages[0]
            st.caption(f"Konvertovane stranice: {len(b64_pages)}")
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
                model="gpt-4o", max_tokens=4096, temperature=0,
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
            m    = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
            data = json.loads(m.group(1) if m else raw)
            if not isinstance(data, list):
                data = [data]
            st.success(f"✅ Pronađeno dokumenata: **{len(data)}**")
            st.json(data)
        except Exception as e:
            st.error(f"❌ JSON parse greška: {e}")

    except Exception as e:
        st.error(f"❌ GPT greška: `{e}`")
