"""upload.py — Učitavanje faktura i AI ekstrakcija."""
import io, base64, time
import streamlit as st
from PIL import Image
from ai_extractor import extract_invoice, get_available_models, FIELDS
from excel_export import save_invoices, invoices_to_bytes


def _file_to_base64(uploaded_file) -> tuple[str, str]:
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    uploaded_file.seek(0)
    if name.endswith(".pdf"):
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(data, dpi=200, first_page=1, last_page=4)
        total_h = sum(p.height for p in pages)
        combined = Image.new("RGB", (pages[0].width, total_h), (255, 255, 255))
        y = 0
        for p in pages:
            combined.paste(p, (0, y)); y += p.height
        buf = io.BytesIO()
        combined.save(buf, format="JPEG", quality=92)
        return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"
    else:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        if max(img.size) > 2400:
            img.thumbnail((2400, 2400), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"


def _preview_file(uploaded_file):
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if name.endswith(".pdf"):
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(uploaded_file.read(), dpi=120, first_page=1, last_page=1)
        if pages:
            st.image(pages[0], caption="Pregled (str. 1)", use_container_width=True)
    else:
        uploaded_file.seek(0)
        st.image(uploaded_file, caption="Pregled", use_container_width=True)


def render_upload():
    st.markdown("# 📤 Učitaj račun")
    st.markdown("Dodaj jednu ili više faktura — AI će automatski izvući podatke.")
    st.divider()

    settings = st.session_state.get("settings", {})
    model = settings.get("model", "gpt-4o")

    uploaded_files = st.file_uploader(
        "Prevuci fakture ili klikni za odabir",
        type=["pdf", "jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )

    if not uploaded_files:
        return

    # Pregled dokumenata
    st.markdown(f"**{len(uploaded_files)} fajl(ova) odabrano**")
    if len(uploaded_files) == 1:
        with st.expander("👁️ Pregled dokumenta", expanded=True):
            _preview_file(uploaded_files[0])
    else:
        cols = st.columns(min(len(uploaded_files), 3))
        for i, f in enumerate(uploaded_files):
            with cols[i % 3]:
                ext = f.name.rsplit(".", 1)[-1].upper()
                st.markdown(f"**{ext}** — {f.name[:30]}")

    st.markdown("")
    col_btn, _ = st.columns([2, 5])
    with col_btn:
        run = st.button("🔍 Pokreni AI ekstrakciju", type="primary", use_container_width=True)

    if run:
        bar = st.progress(0, text="Pripremam…")
        area = st.empty()
        new_results, new_log = [], []

        for idx, uf in enumerate(uploaded_files):
            pct = int(idx / len(uploaded_files) * 100)
            bar.progress(pct, text=f"Obrađujem {idx+1}/{len(uploaded_files)}: {uf.name}")
            with area.container():
                st.info(f"⏳ AI skenira: **{uf.name}**")
                with st.spinner("Čekam odgovor od GPT-4o…"):
                    try:
                        b64, mtype = _file_to_base64(uf)
                        inv = extract_invoice(b64, mtype, filename=uf.name, model=model)
                        inv_dict = inv.to_dict()
                        inv_dict["_filename"] = uf.name
                        inv_dict["_warnings"] = inv._warnings
                        new_results.append(inv_dict)
                        new_log.append((uf.name, "done", "OK"))
                        if inv._warnings:
                            st.warning(f"⚠️ Upozorenja za {uf.name}: " + "; ".join(inv._warnings))
                    except Exception as e:
                        new_log.append((uf.name, "error", str(e)))
                        st.error(f"❌ Greška: {e}")
                        time.sleep(1)

        bar.progress(100, text="Završeno!")
        area.empty()

        if "results" not in st.session_state:
            st.session_state.results = []
        if "log" not in st.session_state:
            st.session_state.log = []
        st.session_state.results.extend(new_results)
        st.session_state.log.extend(new_log)

        done  = sum(1 for _, s, _ in new_log if s == "done")
        errs  = sum(1 for _, s, _ in new_log if s == "error")
        if done:
            st.success(f"✅ Obrađeno: **{done}** faktura.")
        if errs:
            st.error(f"❌ Greške: **{errs}** faktura.")

        # Prikaz ekstraktovanih podataka
        if new_results:
            st.divider()
            st.markdown("### Ekstraktovani podaci")
            import pandas as pd
            df = pd.DataFrame(new_results)
            for c in FIELDS:
                if c not in df.columns: df[c] = ""
            st.dataframe(df[["_filename"] + FIELDS].rename(columns={"_filename": "Fajl"}),
                         use_container_width=True, hide_index=True)

            # Excel download
            from ai_extractor import InvoiceData, build_invoice
            inv_objs = []
            for r in new_results:
                inv = InvoiceData(_filename=r.get("_filename",""))
                for f in FIELDS:
                    setattr(inv, f, r.get(f, ""))
                inv_objs.append(inv)

            xlsx = invoices_to_bytes(inv_objs)
            from datetime import date
            st.download_button(
                "⬇️ Preuzmi Excel (.xlsx)",
                data=xlsx,
                file_name=f"fakture_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            # Spremi na disk ako je putanja postavljena
            excel_path = settings.get("excel_path", "")
            if excel_path:
                added, errs_list = save_invoices(inv_objs, excel_path)
                if added:
                    st.success(f"💾 Dodano {added} faktura u: `{excel_path}`")
                for e in errs_list:
                    st.error(e)
