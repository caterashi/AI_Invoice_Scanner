"""upload.py — Učitavanje faktura i AI ekstrakcija."""
import io
import base64
import time
from datetime import date

import streamlit as st
from PIL import Image

from ai_extractor import extract_invoices_from_image, FIELDS, InvoiceData
from excel_export import save_invoices, invoices_to_bytes


# ─────────────────────────────────────────────────────────────────────────────
# Konverzija fajla u base64
# ─────────────────────────────────────────────────────────────────────────────

def _file_to_base64(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    uploaded_file.seek(0)

    if name.endswith(".pdf"):
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(data, dpi=200)
        # Spoji sve stranice vertikalno
        max_w = max(p.width for p in pages)
        total_h = sum(p.height for p in pages)
        combined = Image.new("RGB", (max_w, total_h), (255, 255, 255))
        y = 0
        for p in pages:
            combined.paste(p, (0, y))
            y += p.height
        # Resize ako je prevelika
        if max(combined.size) > 3000:
            combined.thumbnail((3000, 3000), Image.LANCZOS)
        buf = io.BytesIO()
        combined.save(buf, format="JPEG", quality=92)
    else:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        if max(img.size) > 2800:
            img.thumbnail((2800, 2800), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)

    return base64.b64encode(buf.getvalue()).decode()


# ─────────────────────────────────────────────────────────────────────────────
# Pregled dokumenta
# ─────────────────────────────────────────────────────────────────────────────

def _preview_file(uploaded_file):
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if name.endswith(".pdf"):
        try:
            from pdf2image import convert_from_bytes
            pages = convert_from_bytes(
                uploaded_file.read(), dpi=120, first_page=1, last_page=1
            )
            if pages:
                st.image(pages[0], caption="Pregled (str. 1)", use_container_width=True)
        except Exception:
            st.info("PDF pregled nije dostupan.")
    else:
        uploaded_file.seek(0)
        st.image(uploaded_file, caption="Pregled", use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Glavni renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_upload():
    st.markdown("# 📤 Učitaj račun")
    st.markdown("Dodaj jednu ili više faktura — AI će automatski izvući podatke.")
    st.divider()

    model = st.session_state.get("selected_model", "gpt-4o")

    uploaded_files = st.file_uploader(
        "Prevuci fakture ili klikni za odabir",
        type=["pdf", "jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )

    if not uploaded_files:
        return

    # ── Pregled ──────────────────────────────────────────────────────────────
    st.markdown(f"**{len(uploaded_files)} fajl(ova) odabrano**")
    if len(uploaded_files) == 1:
        with st.expander("👁️ Pregled dokumenta", expanded=True):
            _preview_file(uploaded_files[0])
    else:
        cols = st.columns(min(len(uploaded_files), 3))
        for i, f in enumerate(uploaded_files):
            with cols[i % 3]:
                ext = f.name.rsplit(".", 1)[-1].upper()
                st.markdown(f"**{ext}** — `{f.name[:30]}`")

    st.markdown("")
    col_btn, _ = st.columns([2, 5])
    with col_btn:
        run = st.button(
            "🔍 Pokreni AI ekstrakciju",
            type="primary",
            use_container_width=True,
        )

    if not run:
        return

    # ── Ekstrakcija ──────────────────────────────────────────────────────────
    bar  = st.progress(0, text="Pripremam…")
    area = st.empty()
    new_invoices: list[InvoiceData] = []
    errors = 0

    for idx, uf in enumerate(uploaded_files):
        pct = int(idx / len(uploaded_files) * 100)
        bar.progress(pct, text=f"Obrađujem {idx+1}/{len(uploaded_files)}: {uf.name}")

        with area.container():
            st.info(f"⏳ AI skenira: **{uf.name}**")
            with st.spinner("Čekam odgovor od GPT-4o…"):
                try:
                    b64 = _file_to_base64(uf)
                    # Vraća LISTU — jedan fajl može imati više računa
                    found = extract_invoices_from_image(
                        b64, filename=uf.name, model=model
                    )
                    for inv in found:
                        new_invoices.append(inv)
                        if inv._warnings:
                            st.warning(
                                f"⚠️ {inv._filename}: " + "; ".join(inv._warnings)
                            )
                    if len(found) > 1:
                        st.info(f"📄 {uf.name}: pronađeno **{len(found)} računa**")

                except Exception as e:
                    st.error(f"❌ Greška za {uf.name}: {e}")
                    errors += 1
                    time.sleep(0.5)

    bar.progress(100, text="Završeno!")
    area.empty()

    # ── Spremi u session_state ───────────────────────────────────────────────
    if "invoices" not in st.session_state:
        st.session_state["invoices"] = []
    st.session_state["invoices"].extend(new_invoices)

    # ── Rezultati ────────────────────────────────────────────────────────────
    n_ok   = sum(1 for inv in new_invoices if inv._valid)
    n_warn = sum(1 for inv in new_invoices if inv._warnings and inv._valid)
    n_err  = sum(1 for inv in new_invoices if not inv._valid)

    c1, c2, c3 = st.columns(3)
    c1.metric("✅ Obrađeno", n_ok)
    c2.metric("⚠️ Upozorenja", n_warn)
    c3.metric("❌ Greške", n_err + errors)

    if not new_invoices:
        st.warning("Nijedan račun nije uspješno obrađen.")
        return

    # ── Tabela ekstraktovanih podataka ───────────────────────────────────────
    st.divider()
    st.markdown("### 📋 Ekstraktovani podaci")

    import pandas as pd
    rows = []
    for inv in new_invoices:
        row = inv.to_dict()
        row["Fajl"] = getattr(inv, "_filename", "")
        rows.append(row)

    df = pd.DataFrame(rows)[["Fajl"] + FIELDS]
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Excel download ───────────────────────────────────────────────────────
    xlsx = invoices_to_bytes(new_invoices)
    st.download_button(
        "⬇️ Preuzmi Excel (.xlsx)",
        data=xlsx,
        file_name=f"fakture_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # ── Spremi na disk ───────────────────────────────────────────────────────
    settings   = st.session_state.get("settings", {})
    excel_path = settings.get("excel_path", "")
    if excel_path:
        added, errs_list = save_invoices(new_invoices, excel_path)
        if added:
            st.success(f"💾 Dodano {added} faktura u: `{excel_path}`")
        for e in errs_list:
            st.error(e)
