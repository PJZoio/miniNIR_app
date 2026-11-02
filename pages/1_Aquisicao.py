# -*- coding: utf-8 -*-
"""Página de aquisição — ler amostras e verificar saturação em tempo real."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import config as C
import ui
import services
from storage import db
from analysis import qc

ui.setup_page("Aquisição", icon="📥")
services.ensure_db()
inst = services.get_instrument()

st.title("① Aquisição")
st.caption(services.mode_badge())

# --- ligação ----------------------------------------------------------------
cc1, cc2 = st.columns([1, 3])
with cc1:
    if not inst.is_open:
        if st.button("🔌 Ligar instrumento", type="primary", use_container_width=True):
            try:
                inst.connect()
                st.rerun()
            except Exception as e:
                st.error(f"Falha a ligar: {e}")
    else:
        if st.button("⏹️ Desligar", use_container_width=True):
            inst.close(); st.rerun()
with cc2:
    st.markdown("Estado: " + ("**ligado** ✅" if inst.is_open else "**desligado**"))

st.divider()
left, right = st.columns([1, 1])

# --- metadados + motores ----------------------------------------------------
with left:
    st.subheader("Amostra")
    cycle = st.text_input("Ciclo", value=st.session_state.get("cycle", "ciclo-1"))
    st.session_state["cycle"] = cycle
    series = st.text_input("Série", value="S")
    conc = st.number_input("Concentração", min_value=0.0, value=2.5, step=0.1,
                           help="Valor da amostra composta (usado como alvo de regressão).")
    estadio = st.selectbox("Estádio KDIGO", C.ESTADIOS, index=2)
    descricao = st.text_input("Descrição", value="")

    with st.expander("Motores (posicionamento)"):
        for m, name in [(1, "X"), (2, "Y"), (3, "Z")]:
            mc1, mc2 = st.columns([2, 1])
            pos = mc1.number_input(f"Motor {name} (passos)", value=0, step=100, key=f"pos{m}")
            if mc2.button(f"Mover {name}", key=f"mv{m}", use_container_width=True):
                if inst.is_open:
                    try:
                        inst.move_to(m, pos); st.toast(f"Motor {name} → {pos}")
                    except Exception as e:
                        st.error(e)
                else:
                    st.warning("Ligue o instrumento primeiro.")

    if C.MOCK_HARDWARE:
        with st.expander("🧪 Simular ajuste de ganhos (demonstração)"):
            st.caption("Reduzir o ganho dos canais saturados (1300/1600/1900 nm) "
                       "mostra-os a sair do tecto — ilustra o procedimento.")
            g1 = st.slider("Ganho 1300 nm", 0.3, 1.0, 1.0, 0.05)
            g3 = st.slider("Ganho 1600 nm", 0.3, 1.0, 1.0, 0.05)
            g5 = st.slider("Ganho 1900 nm", 0.3, 1.0, 1.0, 0.05)
            inst.set_mock_gains({1: g1, 3: g3, 5: g5})

# --- aquisição --------------------------------------------------------------
with right:
    st.subheader("Aquisição")
    ns = st.select_slider("Nº de amostras", options=[600, 1200, 3000, 6000],
                          value=C.NUM_SAMPLES)
    st.caption(f"Divide em blocos de {C.BLOCK_SIZE} → {ns // C.BLOCK_SIZE} réplicas por ensaio.")

    if st.button("▶️ Adquirir amostra", type="primary", use_container_width=True,
                 disabled=not inst.is_open):
        bar = st.progress(0.0, text="A adquirir…")
        acq = inst.acquire_sample(conc=conc, num_samples=ns,
                                  progress=lambda p: bar.progress(min(p, 1.0),
                                                                  text=f"A adquirir… {int(p*100)}%"))
        bar.empty()
        sat = qc.flag_saturation(acq["summary"]["avg"])
        meta = dict(cycle=cycle, series=series, conc=conc,
                    estadio=estadio, descricao=descricao)
        eid = db.save_ensaio(meta, acq, saturated=sat)
        st.session_state["last_acq"] = {"acq": acq, "sat": sat, "eid": eid}
        st.success(f"Ensaio #{eid} guardado ({ns // C.BLOCK_SIZE} réplicas).")

    if "last_acq" in st.session_state:
        la = st.session_state["last_acq"]
        st.plotly_chart(ui.bar_channels(la["acq"]["summary"]["avg"],
                                        f"Ensaio #{la['eid']} — sinal por canal"),
                        use_container_width=True)
        qdf = qc.ensaio_qc(la["acq"]["summary"]["avg"], la["acq"]["summary"]["std"])
        if any(s == "SATURADO" for s in qdf["Estado"]):
            st.warning("Canais saturados nesta leitura — considere reduzir o ganho "
                       "(ver procedimento).")
        st.dataframe(ui.style_qc_table(qdf), use_container_width=True, hide_index=True)
