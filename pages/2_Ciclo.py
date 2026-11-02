# -*- coding: utf-8 -*-
"""Página de ciclo — acompanhar o conjunto de amostras de um ciclo."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import config as C
import ui
import services
from storage import db
from analysis import qc

ui.setup_page("Ciclo", icon="🔁")
services.ensure_db()

st.title("② Ciclo")

cyc = db.cycles()
if cyc.empty:
    st.info("Ainda não há ciclos. Faça aquisições na página **Aquisição**.")
    st.stop()

options = cyc["cycle"].tolist()
default = st.session_state.get("cycle", options[0])
idx = options.index(default) if default in options else 0
cycle = st.selectbox("Ciclo", options, index=idx)

ens = db.ensaios_df(cycle=cycle)
blocos = db.blocos_df(cycle=cycle)

c1, c2, c3 = st.columns(3)
c1.metric("Amostras (ensaios)", len(ens))
c2.metric("Réplicas (blocos)", len(blocos))
c3.metric("Estádios distintos", ens["estadio"].nunique() if not ens.empty else 0)

st.divider()
st.subheader("Resposta dos canais")
xaxis = st.radio("Eixo", ["Conc", "Estadio"], horizontal=True)
if not blocos.empty:
    st.plotly_chart(ui.line_channels_vs_sample(blocos, x=xaxis), use_container_width=True)

st.subheader("Controlo de qualidade / saturação (ao nível do ciclo)")
qc_df = qc.dataset_qc(blocos)
st.dataframe(ui.style_qc_table(qc_df), use_container_width=True, hide_index=True)
st.caption("O critério de saturação é a ausência de resposta entre amostras "
           "(não o %RSD, que num canal ceifado é enganadoramente baixo).")

st.divider()
st.subheader("Ensaios do ciclo")
show = ens[["id", "created_at", "series", "conc", "estadio", "descricao"]].copy()
show.columns = ["#", "Data/hora", "Série", "Conc", "Estádio", "Descrição"]
st.dataframe(show, use_container_width=True, hide_index=True)
