"""
debug.py  —  streamlit run debug.py
"""

import io, os, re, base64
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
        import fitz; st.success(f"✅ PyMuPDF `{fitz.__version__}`")
    except ImportError:
        st.error("❌ PyMuPDF  →  `pip install PyMuPDF`")
with c2:
    try:
        import pdfplumber; st.success(f"✅ pdfplumber `{pdfplumber.__version__}`")
    except ImportError:
        st.warning("⚠️ pdfplumber nije instaliran")
with c3:
    try:
        from pdf2image import convert_from_bytes
        import subprocess
        subprocess.run(["pdftoppm", "-v"], capture_output=True, check=False)
        st.success("✅ pdf2image + poppler")
    except ImportError:
        st.error("❌ pdf2image")
    except FileNotFoundError:
        st.error("❌ poppler nije instaliran")

# ─────────────────────────────────────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
uploaded = st.file_uploader("Uploaduj PDF", type=["pdf"])
if not uploaded:
    st.stop()

pdf_bytes = uploaded.read()
st.caption(f"`{uploaded.name}` | `{len(pdf_bytes)/1024:.1f} KB`")

api_key = (
    st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
) or os.getenv("OPENAI_API_KEY", "")

if not api_key:
    st.error("❌ OPENAI_API_KEY nije postavljen")
    st.stop()

st.success(f"✅ API ključ: `{api_key[:8]}...{api_key[-4:]}`")

# ─────────────────────────────────────────────────────────────────────────────
# 2 — Prikaži sliku koja se šalje GPT-u
# ─────────────────────────────────────────────────────────────────────────────
st.header("2️⃣ Slika koja se šalje GPT-u (batch 1)")

try:
    from pdf2image import convert_from_bytes
    from PIL import Image
    from ai_extractor import _combine_images, _pdf_to_b64_images

    with st.spinner("Konvertujem PDF..."):
        b64_pages = _pdf_to_b64_images(pdf_bytes)

    st.caption(f"Ukupno stranica: {len(b64_pages)} | Batch veličina: 4")

    # Prikaži batch 1 (stranice 1–4)
    batch = b64_pages[:4]
    b64   = _combine_images(batch) if len(batch) > 1 else batch[0]

    img      = Image.open(io.BytesIO(base64.b64decode(b64)))
    img_kb   = len(base64.b64decode(b64)) / 1024
    st.caption(f"Kombinovana slika: **{img.width}x{img.height}px** | **{img_kb:.0f} KB**")

    # Prikaži preview
    col_img, col_info = st.columns([2, 1])
    with col_img:
        st.image(img, caption="Batch 1 — ovo vidi GPT Vision", use_container_width=True)
    with col_info:
        per_page_h = img.height // len(batch)
        st.metric("Visina po stranici", f"{per_page_h}px")
        st.metric("DPI konverzije", "200")
        st.metric("Stranica u batchu", len(batch))
        if per_page_h < 800:
            st.error("⚠️ Premali! GPT ne može čitati tekst")
        elif per_page_h < 1200:
            st.warning("⚠️ Granično — tekst može biti nejasan")
        else:
            st.success("✅ Dovoljna visina za čitanje")

except Exception as e:
    st.error(f"Greška: `{e}`")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# 3 — GPT opis slike (dijagnostika)
# ─────────────────────────────────────────────────────────────────────────────
st.header("3️⃣ Dijagnostika — šta GPT stvarno vidi")
st.caption("Pitamo GPT da OPIŠE sliku slobodnim tekstom — bez JSON strukture. "
           "Ako opiše pravo, slika je čitljiva. Ako halucinira, slika je loša.")

if st.button("👁️ Pitaj GPT da opiše sliku", type="secondary"):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    with st.spinner("GPT analizira sliku..."):
        resp = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=600,
            temperature=0,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "high",
                    }},
                    {"type": "text", "text":
                        "Opiši tačno šta vidiš na ovoj slici. "
                        "Navedi: naziv firme, adresu, broj fakture/računa, iznose, datume. "
                        "Ako ne možeš jasno pročitati nešto, reci to eksplicitno."
                    },
                ],
            }],
        )
    opis = resp.choices[0].message.content
    st.subheader("GPT odgovor:")
    st.write(opis)

    if any(x in opis.upper() for x in ["HERBAVITAL", "EDNA", "DENT K", "OXASIL", "XANTOPREN"]):
        st.success("✅ GPT čita pravu firmu — slika je čitljiva")
    elif "ne mogu" in opis.lower() or "nejasno" in opis.lower() or "ne vidim" in opis.lower():
        st.error("❌ GPT ne može pročitati sliku — rezolucija je preniska")
    else:
        st.warning("⚠️ Provjeri ručno da li opis odgovara PDF-u")

# ─────────────────────────────────────────────────────────────────────────────
# 4 — Puna ekstrakcija
# ─────────────────────────────────────────────────────────────────────────────
st.header("4️⃣ Puna ekstrakcija (svi batch-evi)")

if st.button("🚀 Pokreni ekstrakciju", type="primary"):
    from ai_extractor import extract_invoices_from_pdf
    import json

    with st.spinner(f"Obrađujem {len(b64_pages)} stranica u batch-evima po 4..."):
        results = extract_invoices_from_pdf(pdf_bytes, filename=uploaded.name)

    st.success(f"Pronađeno dokumenata: **{len(results)}**")

    for i, inv in enumerate(results):
        status = "✅" if not inv._warnings else "⚠️"
        with st.expander(f"{status} Dokument {i+1}: {inv.BROJFAKT or '(bez broja)'}"):
            st.json(inv.to_dict())
            if inv._warnings:
                for w in inv._warnings:
                    st.warning(w)
