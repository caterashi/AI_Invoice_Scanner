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

# Provjeri da li ključ zapravo radi
if st.button("🔌 Testiraj API konekciju"):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
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
# KORAK 2 — Provjera pdfplumber čitanja
# ─────────────────────────────────────────────────────────────────────────────

st.header("2️⃣ pdfplumber — čitanje teksta iz PDF-a")

uploaded = st.file_uploader("Uploaduj PDF za test", type=["pdf"])

if uploaded:
    pdf_bytes = uploaded.read()

    try:
        import pdfplumber

        parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            st.info(f"📄 Broj stranica: {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages):
                t = page.extract_text(x_tolerance=2, y_tolerance=2)
                if t:
                    parts.append(t)
                    with st.expander(f"Stranica {i + 1} — {len(t)} znakova"):
                        st.text(t)
                else:
                    st.warning(f"⚠️ Stranica {i + 1}: nema teksta (slikovni PDF)")

        full_text = "\n\n--- NOVA STRANICA ---\n\n".join(parts)
        clean_len = len(re.sub(r"\s+", "", full_text))

        if clean_len >= 100:
            st.success(f"✅ Tekstualni PDF — {clean_len} znakova bez razmaka → ide na GPT tekst mod")
        else:
            st.warning(f"⚠️ Slikovni PDF — samo {clean_len} znakova → ide na GPT Vision mod")

    except Exception as e:
        st.error(f"❌ pdfplumber greška: {e}")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# KORAK 3 — Kompletan GPT poziv s punim logom
# ─────────────────────────────────────────────────────────────────────────────

st.header("3️⃣ Kompletan GPT poziv — puni log")

uploaded2 = st.file_uploader(
    "Uploaduj PDF za ekstrakciju (s punim logom)",
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
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        # Korak A: pdfplumber
        text = _extract_text(pdf_bytes2)
        clean_len = len(re.sub(r"\s+", "", text))
        is_text = _is_text_pdf(text)

        st.subheader("📄 A) Izvučeni tekst")
        st.caption(f"Dužina: {clean_len} znakova | Mod: {'TEXT' if is_text else 'VISION'}")
        if text:
            with st.expander("Prikaži izvučeni tekst"):
                st.text(text[:5000] + ("..." if len(text) > 5000 else ""))

        # Korak B: GPT poziv
        st.subheader("🤖 B) GPT poziv")

        if is_text:
            user_msg = (
                f"Fajl: {uploaded2.name}\n\n"
                "Pronađi i izvuci SVE dokumente iz teksta ispod. "
                "Vrati JSON array — jedan objekt po dokumentu.\n\n"
                f"TEKST DOKUMENTA:\n{text}"
            )
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ]
            st.caption("Mod: TEXT")
        else:
            b64_pages = _pdf_to_b64_images(pdf_bytes2)
            b64       = _combine_images(b64_pages) if len(b64_pages) > 1 else b64_pages[0]
            st.caption(f"Mod: VISION | Stranica(e): {len(b64_pages)}")
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high",
                        }},
                        {"type": "text", "text": (
                            f"Fajl: {uploaded2.name}\n"
                            "Pronađi i izvuci SVE dokumente s ove slike. "
                            "Vrati JSON array — jedan objekt po dokumentu."
                        )},
                    ],
                },
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

            st.success("✅ GPT odgovorio")
            st.caption(
                f"Model: {resp.model} | "
                f"Prompt tokeni: {resp.usage.prompt_tokens} | "
                f"Output tokeni: {resp.usage.completion_tokens}"
            )

            st.subheader("📨 C) Sirovi GPT odgovor")
            st.code(raw, language="json")

            # Parsiranje
            import json
            try:
                m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
                json_str = m.group(1) if m else raw
                data = json.loads(json_str)
                st.subheader("✅ D) Parsirani JSON")
                st.json(data)
                st.success(f"Pronađeno dokumenata: **{len(data)}**")
            except Exception as e:
                st.error(f"❌ JSON parse greška: {e}")

        except Exception as e:
            st.error(f"❌ GPT poziv nije uspio: {e}")

