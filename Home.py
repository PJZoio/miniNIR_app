# -*- coding: utf-8 -*-
"""miniNIR — aplicação integrada de aquisição, visualização e modelação.

Entrada da app Streamlit.  Correr a partir desta pasta:
    streamlit run Home.py
"""
import streamlit as st
import config as C
import ui
import services
from storage import db
from analysis import qc

ui.setup_page("Início", icon="🔬")
services.ensure_db()

st.title("miniNIR · plataforma de ensaios")
st.caption("Aquisição · Visualização · Modelação — dispositivo portátil de "
           "espetroscopia NIR (6 LED, 1300–2100 nm) para rastreio de DRC")

st.markdown(f"**Estado do hardware:** {services.mode_badge()}")
if C.MOCK_HARDWARE:
    st.info("Está em **modo simulado** — toda a app funciona sem o Raspberry Pi "
            "(ideal para demonstração). No Pi, arranque com `MININIR_MOCK=0`.")

# KPIs -----------------------------------------------------------------------
n_ensaios = db.count_ensaios()
cyc = db.cycles()
c1, c2, c3 = st.columns(3)
c1.metric("Ensaios na base", n_ensaios)
c2.metric("Ciclos", len(cyc))
c3.metric("Canais LED", C.NUM_CHANNELS)

st.divider()

# Navegação ------------------------------------------------------------------
st.subheader("Fluxo de trabalho")
cols = st.columns(4)
cards = [
    ("① Aquisição", "Ler amostras, posicionar motores, QC de saturação em tempo real.", "Aquisicao"),
    ("② Ciclo", "Acompanhar o ciclo atual: amostras, gráficos e repetibilidade.", "Ciclo"),
    ("③ Dataset", "Navegar, filtrar, importar/exportar no formato dos modelos.", "Dataset"),
    ("④ Modelos", "Classificação e regressão com validação cruzada agrupada.", "Modelos"),
]
for col, (t, d, page) in zip(cols, cards):
    with col:
        st.markdown(f"**{t}**")
        st.markdown(f'<span class="small">{d}</span>', unsafe_allow_html=True)

st.divider()

# QC rápido do conjunto ------------------------------------------------------
st.subheader("Qualidade do conjunto (resumo)")
blocos = db.blocos_df()
if blocos.empty:
    st.write("Sem dados ainda. Comece pela página **Aquisição**.")
else:
    qc_df = qc.dataset_qc(blocos)
    sat = [r for r in qc_df["Estado"] if r == "SATURADO"]
    if sat:
        st.markdown(
            f"⚠️ **{len(sat)} canal(is) saturado(s)** detetado(s) no conjunto — "
            "ver procedimento de ajuste de ganhos.")
    st.dataframe(ui.style_qc_table(qc_df), use_container_width=True, hide_index=True)
