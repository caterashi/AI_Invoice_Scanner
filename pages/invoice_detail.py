"""invoice_detail.py — Detaljan prikaz i uređivanje jedne fakture."""
import streamlit as st
from helpers import format_amount, validate_jib, validate_invoice_number, validate_pdv_number
from ai_extractor import FIELDS
from pdf_generator import invoice_to_pdf


FIELD_LABELS = {
    "BROJFAKT":   "Broj fakture",
    "DATUMF":     "Datum izdavanja (DD.MM.GGGG)",
    "DATUMPF":    "Datum prijema (DD.MM.GGGG)",
    "NAZIVPP":    "Naziv dobavljača",
    "SJEDISTEPP": "Adresa dobavljača",
    "IDPDVPP":    "JIB/ID broj (13 cifara)",
    "JIBPUPP":    "PDV broj (12 cifara)",
    "IZNBEZPDV":  "Iznos bez PDV (KM)",
    "IZNPDV":     "Iznos PDV (KM)",
    "IZNSAPDV":   "Ukupno s PDV (KM)",
}


def render_invoice_detail():
    st.markdown("# 🔍 Detalji računa")
    results = st.session_state.get("results", [])

    if not results:
        st.info("Nema učitanih faktura. Idi na **Učitaj račun**.")
        return

    # Odabir fakture
    idx = st.session_state.get("selected_invoice_idx", 0)
    options = [f"{i+1}. {r.get('_filename','—')} | {r.get('NAZIVPP','—')} | {r.get('DATUMF','—')}"
               for i, r in enumerate(results)]
    selected = st.selectbox("Odaberi fakturu", options, index=min(idx, len(options)-1))
    idx = options.index(selected)
    st.session_state.selected_invoice_idx = idx
    invoice = results[idx]

    st.divider()

    col_form, col_preview = st.columns([1, 1], gap="large")

    with col_form:
        st.markdown("### ✏️ Uređivanje podataka")
        warnings = invoice.get("_warnings", [])
        if warnings:
            for w in warnings:
                st.warning(f"⚠️ {w}")

        updated = {}
        # Grupiranje polja
        st.markdown("**Identifikacija**")
        updated["BROJFAKT"] = st.text_input(FIELD_LABELS["BROJFAKT"], value=invoice.get("BROJFAKT",""))
        c1, c2 = st.columns(2)
        with c1:
            updated["DATUMF"] = st.text_input(FIELD_LABELS["DATUMF"], value=invoice.get("DATUMF",""))
        with c2:
            updated["DATUMPF"] = st.text_input(FIELD_LABELS["DATUMPF"], value=invoice.get("DATUMPF",""))

        st.markdown("**Dobavljač**")
        updated["NAZIVPP"]    = st.text_input(FIELD_LABELS["NAZIVPP"],    value=invoice.get("NAZIVPP",""))
        updated["SJEDISTEPP"] = st.text_input(FIELD_LABELS["SJEDISTEPP"], value=invoice.get("SJEDISTEPP",""))
        c3, c4 = st.columns(2)
        with c3:
            updated["IDPDVPP"] = st.text_input(FIELD_LABELS["IDPDVPP"], value=invoice.get("IDPDVPP",""))
        with c4:
            updated["JIBPUPP"] = st.text_input(FIELD_LABELS["JIBPUPP"], value=invoice.get("JIBPUPP",""))

        st.markdown("**Iznosi**")
        a1, a2, a3 = st.columns(3)
        with a1:
            updated["IZNBEZPDV"] = st.text_input(FIELD_LABELS["IZNBEZPDV"], value=invoice.get("IZNBEZPDV",""))
        with a2:
            updated["IZNPDV"]    = st.text_input(FIELD_LABELS["IZNPDV"],    value=invoice.get("IZNPDV",""))
        with a3:
            updated["IZNSAPDV"]  = st.text_input(FIELD_LABELS["IZNSAPDV"],  value=invoice.get("IZNSAPDV",""))

        # Validacija
        valid_errors = []
        ok, msg = validate_invoice_number(updated["BROJFAKT"])
        if not ok: valid_errors.append(f"BROJFAKT: {msg}")
        if updated["IDPDVPP"]:
            ok, msg = validate_jib(updated["IDPDVPP"])
            if not ok: valid_errors.append(f"IDPDVPP: {msg}")
        if updated["JIBPUPP"]:
            ok, msg = validate_pdv_number(updated["JIBPUPP"])
            if not ok: valid_errors.append(f"JIBPUPP: {msg}")

        if valid_errors:
            for e in valid_errors:
                st.error(f"❌ {e}")

        if st.button("💾 Spremi izmjene", type="primary", use_container_width=True):
            results[idx].update(updated)
            results[idx]["_warnings"] = valid_errors
            st.session_state.results = results
            st.success("✅ Izmjene spremljene.")

    with col_preview:
        st.markdown("### 📄 Pregled dokumenta")
        # Prikaz sažetka
        try:
            iznos = float(updated.get("IZNSAPDV","") or invoice.get("IZNSAPDV","") or 0)
            st.markdown(f"""
            <div style="background:#f9f8f5;border:1px solid #dcd9d5;border-radius:12px;padding:1.25rem;margin-bottom:1rem">
              <div style="font-size:.7rem;color:#7a7974;text-transform:uppercase;letter-spacing:.05em">Ukupno za uplatu</div>
              <div style="font-size:2rem;font-weight:800;color:#01696f">{format_amount(iznos)}</div>
              <div style="font-size:.85rem;color:#7a7974;margin-top:.25rem">{invoice.get('NAZIVPP','—')}</div>
            </div>""", unsafe_allow_html=True)
        except Exception:
            pass

        # Generiraj PDF/HTML
        try:
            data, mime, ext = pdf_mime_type(invoice)
            label = "⬇️ Preuzmi PDF" if ext == ".pdf" else "⬇️ Preuzmi HTML"
            fname = f"faktura_{invoice.get('BROJFAKT','racun').replace('/','_')}{ext}"
            st.download_button(label, data=data, file_name=fname, mime=mime, use_container_width=True)
        except Exception as e:
            st.error(f"PDF greška: {e}")

        # Prikaz svih polja kao read-only tabela
        st.markdown("**Svi prepoznati podaci:**")
        for key in FIELDS:
            val = invoice.get(key, "") or "—"
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;padding:.3rem 0;
                        border-bottom:1px solid #f3f0ec;font-size:.82rem">
              <span style="color:#7a7974;font-weight:600">{key}</span>
              <span style="color:#28251d;text-align:right;max-width:60%;word-break:break-all">{val}</span>
            </div>""", unsafe_allow_html=True)
