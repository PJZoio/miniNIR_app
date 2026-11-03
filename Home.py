# -*- coding: utf-8 -*-
"""miniNIR — visão geral, dados, qualidade e export (Home + Dataset fundidos).

Correr a partir desta pasta:  streamlit run Home.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import io
import datetime as dt
import streamlit as st
import config as C
import ui
import services
from storage import db
from analysis import qc

ui.setup_page("Início", icon="🔬")
services.ensure_db()

st.title("miniNIR · plataforma de ensaios")
st.caption("Visão geral · dados · qualidade — dispositivo NIR portátil (6 LED, 1300–2100 nm)")
st.markdown(f"**Estado do hardware:** {services.mode_badge()}")
if C.MOCK_HARDWARE:
    st.info("Modo **simulado** — a app funciona sem o Raspberry Pi. No Pi: `MININIR_MOCK=0`.")

if db.count_ensaios() == 0:
    st.warning("Sem dados ainda. Comece pela página **Aquisição**.")
    st.stop()

# --- Filtros ----------------------------------------------------------------
st.subheader("Filtros")
f1, f2, f3, f4 = st.columns([1, 2, 2, 1])
apps = ["(todas)"] + db.list_applications()
fapp = f1.selectbox("Aplicação", apps)
cyc_df = db.list_cycles()
if fapp != "(todas)":
    cyc_df = cyc_df[cyc_df["application"] == fapp]
cyc_opts = cyc_df["cycle"].tolist()
fcycles = f2.multiselect("Ciclos", cyc_opts, default=cyc_opts)
drange = f3.date_input("Intervalo de datas", value=(), help="Vazio = todas as datas")
incl_blanks = f4.toggle("Incluir brancos", value=True)

date_from = date_to = None
if isinstance(drange, (tuple, list)) and len(drange) == 2:
    date_from, date_to = drange[0].isoformat(), drange[1].isoformat()

application = None if fapp == "(todas)" else fapp
blocos = db.blocos_df(cycles=fcycles or None, application=application,
                      date_from=date_from, date_to=date_to, include_blanks=incl_blanks)
ensaios = db.ensaios_df(cycles=fcycles or None, application=application,
                        date_from=date_from, date_to=date_to, include_blanks=incl_blanks)

if blocos.empty:
    st.info("Nenhum dado para estes filtros.")
    st.stop()

# --- KPIs -------------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Amostras (ensaios)", ensaios["EnsaioId"].nunique())
k2.metric("Réplicas (blocos)", len(blocos))
k3.metric("Ciclos", blocos["cycle"].nunique())
k4.metric("Variáveis (canais)", C.NUM_CHANNELS)

st.divider()

# --- Qualidade dos canais ---------------------------------------------------
st.subheader("Qualidade dos canais")
scope = st.radio("Âmbito", ["Conjunto filtrado", "Um ensaio"], horizontal=True)
if scope == "Conjunto filtrado":
    qc_df = qc.dataset_qc(blocos)
    sat = [r for r in qc_df["Estado"] if r == "SATURADO"]
    if sat:
        st.markdown(f"⚠️ **{len(sat)} canal(is) saturado(s)** — ver procedimento de ajuste de ganhos.")
    st.dataframe(ui.style_qc_table(qc_df), use_container_width=True, hide_index=True)
    st.caption("Saturação = sinal no tecto do fundo de escala **e** sem resposta entre amostras.")
else:
    ids = ensaios["EnsaioId"].tolist()
    eid = st.selectbox("Ensaio", ids,
                       format_func=lambda i: f"#{i} · {ensaios.loc[ensaios.EnsaioId==i,'sample_name'].iloc[0]}")
    row = ensaios[ensaios["EnsaioId"] == eid].iloc[0]
    avg = [row[c] for c in C.LED_COLS_AVG]
    std = [row.get(c) for c in C.LED_COLS_STD]
    st.dataframe(ui.style_qc_table(qc.ensaio_qc(avg, std)),
                 use_container_width=True, hide_index=True)
    st.plotly_chart(ui.bar_channels(avg, f"Ensaio #{eid} — sinal por canal"),
                    use_container_width=True)

st.divider()

# --- Resposta dos canais ----------------------------------------------------
st.subheader("Resposta dos canais")
targets = db.candidate_targets(blocos)
xopts = targets["regression"] + targets["classification"] + ["sample_no"]
xsel = st.selectbox("Eixo X (etiqueta)", xopts)
st.plotly_chart(ui.line_channels_vs_sample(blocos, x=xsel, x_title=xsel),
                use_container_width=True)

# --- Tabela + export --------------------------------------------------------
st.subheader("Dados (nível de bloco)")
labels = db.label_columns(blocos)
cols = ["EnsaioId", "cycle", "sample_no", "line"] + labels + C.LED_COLS_AVG
st.dataframe(blocos[cols], use_container_width=True, hide_index=True, height=300)

buf = io.StringIO()
blocos[["EnsaioId", "line"] + labels + C.LED_COLS_AVG].to_csv(
    buf, sep=C.CSV_SEP, decimal=C.CSV_DECIMAL, index=False)
st.download_button("⬇️ Exportar Global.csv (formato dos modelos)", buf.getvalue(),
                   file_name="miniNIR_Global.csv", mime="text/csv", type="primary")

st.divider()
with st.expander("Importar CSV (formato Global)"):
    up = st.file_uploader("Ficheiro .csv (sep ';', decimais ',')", type=["csv"])
    iapp = st.selectbox("Aplicação para estes dados", db.list_applications())
    if up is not None and st.button("Importar"):
        tmp = C.DATA_DIR / "_upload.csv"
        tmp.write_bytes(up.getvalue())
        try:
            n, cyc = db.import_global_csv(tmp, application=iapp)
            st.success(f"{n} ensaios importados para o ciclo '{cyc}'."); st.rerun()
        except Exception as e:
            st.error(f"Erro ao importar: {e}")

with st.expander("Apagar um ensaio"):
    if not ensaios.empty:
        eid = st.number_input("ID do ensaio", min_value=int(ensaios["EnsaioId"].min()),
                              max_value=int(ensaios["EnsaioId"].max()), step=1)
        if st.button("Apagar", type="secondary"):
            db.delete_ensaio(int(eid)); st.success(f"Ensaio #{eid} apagado."); st.rerun()
