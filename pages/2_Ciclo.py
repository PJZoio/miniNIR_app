# -*- coding: utf-8 -*-
"""Página de ciclo — acompanhar a ronda de ensaios em curso."""
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

cyc = db.list_cycles()
if cyc.empty or cyc["n_ensaios"].sum() == 0:
    st.info("Ainda não há ciclos com ensaios. Comece na página **Aquisição**.")
    st.stop()

cyc = cyc[cyc["n_ensaios"] > 0]
options = cyc["cycle"].tolist()
default = st.session_state.get("aq_cycle", options[0])
idx = options.index(default) if default in options else 0
cycle = st.selectbox("Ciclo", options, index=idx,
                     format_func=lambda c: f"{c}  ·  {cyc.loc[cyc.cycle==c,'application'].iloc[0]}")

ens = db.ensaios_df(cycles=[cycle])
blocos = db.blocos_df(cycles=[cycle])
labels = db.label_columns(blocos)
nrep = (len(blocos) / max(1, ens["EnsaioId"].nunique()))

# --- métricas (terminologia correta) ---------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Amostras lidas", ens["EnsaioId"].nunique())
c2.metric("Réplicas/amostra", f"{nrep:.0f}")
c3.metric("Observações totais", len(blocos))
c4.metric("Variáveis (canais)", C.NUM_CHANNELS)
st.caption("Etiquetas ativas nesta aplicação: " + (", ".join(labels) if labels else "—"))

st.divider()

# --- última leitura ---------------------------------------------------------
st.subheader("Última leitura")
last = ens.sort_values("sample_no").iloc[-1]
lc1, lc2 = st.columns([1, 1])
with lc1:
    st.markdown(f"**#{int(last['EnsaioId'])} · {last['sample_name']}** "
                f"{'(branco)' if last['is_blank'] else ''}")
    meta = {k: last.get(k) for k in labels}
    st.write({k: v for k, v in meta.items() if v is not None} or "—")
    avg = [last[c] for c in C.LED_COLS_AVG]
    std = [last.get(c) for c in C.LED_COLS_STD]
    st.dataframe(ui.style_qc_table(qc.ensaio_qc(avg, std)),
                 use_container_width=True, hide_index=True)
with lc2:
    st.plotly_chart(ui.bar_channels([last[c] for c in C.LED_COLS_AVG],
                                    "Sinal por canal"), use_container_width=True)

# --- comparar leituras anteriores ------------------------------------------
st.subheader("Comparar leituras")
pick = st.multiselect(
    "Escolher ensaios para comparar", ens["EnsaioId"].tolist(),
    default=ens["EnsaioId"].tolist()[-min(3, len(ens)):],
    format_func=lambda i: f"#{i} · {ens.loc[ens.EnsaioId==i,'sample_name'].iloc[0]}")
if pick:
    rows = [[ens.loc[ens.EnsaioId == i, c].iloc[0] for c in C.LED_COLS_AVG] for i in pick]
    names = [f"#{i}" for i in pick]
    st.plotly_chart(ui.compare_channels(rows, names), use_container_width=True)

st.divider()

# --- resposta e QC ----------------------------------------------------------
st.subheader("Resposta dos canais")
targets = db.candidate_targets(blocos)
xopts = targets["regression"] + targets["classification"] + ["sample_no"]
xsel = st.selectbox("Eixo X", xopts)
st.plotly_chart(ui.line_channels_vs_sample(blocos, x=xsel, x_title=xsel),
                use_container_width=True)

st.subheader("Qualidade / saturação (ciclo)")
st.dataframe(ui.style_qc_table(qc.dataset_qc(blocos)),
             use_container_width=True, hide_index=True)

st.subheader("Ensaios do ciclo")
show_cols = ["EnsaioId", "sample_no", "sample_name", "is_blank"] + labels
st.dataframe(ens[show_cols].rename(columns={"EnsaioId": "#", "sample_no": "nº",
             "sample_name": "amostra", "is_blank": "branco"}),
             use_container_width=True, hide_index=True)
