# -*- coding: utf-8 -*-
"""Página de dataset — navegar, filtrar, importar e exportar."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
import streamlit as st
import pandas as pd
import config as C
import ui
import services
from storage import db
from analysis import qc

ui.setup_page("Dataset", icon="🗃️")
services.ensure_db()

st.title("③ Dataset")

blocos = db.blocos_df()
ens = db.ensaios_df()

if blocos.empty:
    st.info("Sem dados. Faça aquisições ou importe um CSV abaixo.")
else:
    # filtros
    f1, f2 = st.columns(2)
    cyc_opts = ["(todos)"] + sorted(blocos["cycle"].dropna().unique().tolist())
    est_opts = ["(todos)"] + [e for e in C.ESTADIOS if e in blocos["Estadio"].unique().tolist()]
    fc = f1.selectbox("Ciclo", cyc_opts)
    fe = f2.selectbox("Estádio", est_opts)
    view = blocos.copy()
    if fc != "(todos)":
        view = view[view["cycle"] == fc]
    if fe != "(todos)":
        view = view[view["Estadio"] == fe]

    m1, m2, m3 = st.columns(3)
    m1.metric("Amostras", view["EnsaioId"].nunique())
    m2.metric("Linhas (blocos)", len(view))
    m3.metric("Canais", C.NUM_CHANNELS)

    st.plotly_chart(ui.line_channels_vs_sample(view, x="Conc"), use_container_width=True)

    with st.expander("QC do subconjunto filtrado"):
        st.dataframe(ui.style_qc_table(qc.dataset_qc(view)),
                     use_container_width=True, hide_index=True)

    st.subheader("Tabela (nível de bloco)")
    cols = ["EnsaioId", "line", "Conc", "Estadio"] + C.LED_COLS_AVG
    st.dataframe(view[cols], use_container_width=True, hide_index=True, height=320)

    # export
    buf = io.StringIO()
    view[cols].to_csv(buf, sep=C.CSV_SEP, decimal=C.CSV_DECIMAL, index=False)
    st.download_button("⬇️ Exportar Global.csv (formato dos modelos)",
                       buf.getvalue(), file_name="miniNIR_Global.csv",
                       mime="text/csv", type="primary")

st.divider()
st.subheader("Importar CSV (formato Global)")
up = st.file_uploader("Ficheiro .csv (sep ';', decimais ',')", type=["csv"])
if up is not None:
    tmp = C.DATA_DIR / "_upload.csv"
    tmp.write_bytes(up.getvalue())
    cyname = st.text_input("Nome do ciclo para estes dados", value="importado")
    if st.button("Importar"):
        try:
            n = db.import_global_csv(tmp, cycle=cyname)
            st.success(f"{n} ensaios importados para o ciclo '{cyname}'.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao importar: {e}")

# gestão
if not ens.empty:
    with st.expander("Apagar um ensaio"):
        eid = st.number_input("ID do ensaio", min_value=int(ens["id"].min()),
                              max_value=int(ens["id"].max()), step=1)
        if st.button("Apagar", type="secondary"):
            db.delete_ensaio(int(eid)); st.success(f"Ensaio #{eid} apagado."); st.rerun()
