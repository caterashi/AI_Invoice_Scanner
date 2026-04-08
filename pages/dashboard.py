"""dashboard.py — Pregled metrike i liste faktura."""
import streamlit as st
from helpers import format_amount


def render_dashboard():
    st.markdown("# 📊 Pregled")
    st.markdown("Sumarni prikaz obrađenih faktura u ovoj sesiji.")
    st.divider()

    results = st.session_state.get("results", [])

    if not results:
        st.markdown("""
        <div style="text-align:center;padding:4rem 2rem;color:#7a7974">
          <div style="font-size:3rem">📂</div>
          <h3 style="color:#28251d;margin:.75rem 0 .4rem">Nema faktura</h3>
          <p>Idi na <strong>Učitaj račun</strong> i dodaj prve fakture.</p>
        </div>""", unsafe_allow_html=True)
        return

    # Izračun metrike
    amounts_sa = []
    amounts_bez = []
    amounts_pdv = []
    for r in results:
        for lst, key in [(amounts_sa, "IZNSAPDV"), (amounts_bez, "IZNBEZPDV"), (amounts_pdv, "IZNPDV")]:
            try:
                v = r.get(key, "") or ""
                if v:
                    lst.append(float(v))
            except Exception:
                pass

    total    = len(results)
    log      = st.session_state.get("log", [])
    done     = sum(1 for _, s, _ in log if s == "done")
    errors   = sum(1 for _, s, _ in log if s == "error")

    # Metrika kartice
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        (c1, "📄", "Ukupno faktura", str(total)),
        (c2, "💰", "Ukupno s PDV", format_amount(sum(amounts_sa))),
        (c3, "✅", "Obrađeno", str(done)),
        (c4, "❌", "Greške", str(errors)),
    ]
    for col, icon, label, val in cards:
        with col:
            st.markdown(f"""
            <div style="background:#f9f8f5;border:1px solid #dcd9d5;border-radius:12px;
                        padding:1rem 1.25rem;text-align:center">
              <div style="font-size:1.5rem">{icon}</div>
              <div style="font-size:1.6rem;font-weight:800;color:#01696f;line-height:1.2">{val}</div>
              <div style="font-size:.72rem;color:#7a7974;text-transform:uppercase;
                          letter-spacing:.05em;margin-top:.25rem">{label}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")

    # Iznosi breakdown
    if amounts_sa:
        b1, b2, b3 = st.columns(3)
        with b1:
            st.metric("Ukupno bez PDV", format_amount(sum(amounts_bez)))
        with b2:
            st.metric("Ukupno PDV", format_amount(sum(amounts_pdv)))
        with b3:
            avg = sum(amounts_sa) / len(amounts_sa)
            st.metric("Prosječna faktura", format_amount(avg))

    st.divider()
    st.markdown("### 📋 Lista faktura")

    import pandas as pd
    from ai_extractor import FIELDS
    df = pd.DataFrame(results)
    for c in FIELDS:
        if c not in df.columns:
            df[c] = ""
    show_cols = ["_filename", "BROJFAKT", "DATUMF", "NAZIVPP", "IZNBEZPDV", "IZNPDV", "IZNSAPDV"]
    for c in show_cols:
        if c not in df.columns:
            df[c] = ""
    df_show = df[show_cols].rename(columns={"_filename": "Fajl"})

    # Klik za detalje
    event = st.dataframe(
        df_show, use_container_width=True, hide_index=False,
        on_select="rerun", selection_mode="single-row",
    )
    if event and event.selection and event.selection.rows:
        idx = event.selection.rows[0]
        st.session_state.selected_invoice_idx = idx
        st.session_state.active_page = "invoice_detail"
        st.rerun()
