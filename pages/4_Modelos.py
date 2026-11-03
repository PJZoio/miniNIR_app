# -*- coding: utf-8 -*-
"""Página de modelos — classificação e regressão com CV agrupada por amostra."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import config as C
import ui
import services
from storage import db
from analysis import models

ui.setup_page("Modelos", icon="🧠")
services.ensure_db()

st.title("④ Modelos")
st.caption("Validação cruzada **agrupada por amostra física (EnsaioId)** — sem fuga "
           "de informação entre réplicas (metodologia dos scripts _GROUPED).")

MODELS_DIR = C.DATA_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def _save_block(df, feat, target, task, model_name, quick):
    """Refaz o melhor modelo em todos os dados e permite guardá-lo (para inferência)."""
    with st.expander("💾 Guardar melhor modelo (base para a futura Inferência)"):
        safe = str(target).replace("/", "_").replace(" ", "_")
        st.caption(f"Ajusta **{model_name}** a todos os dados selecionados e guarda o modelo.")
        if st.button("Guardar modelo", key=f"save_{task}_{safe}"):
            try:
                est, meta = models.fit_full_model(df, feat, target, task, model_name, quick)
                path = MODELS_DIR / f"{task}_{safe}_{model_name}.joblib"
                models.save_model(est, meta, str(path))
                st.success(f"Modelo guardado: {path.name}")
                with open(path, "rb") as fh:
                    st.download_button("⬇️ Descarregar .joblib", fh.read(),
                                       file_name=path.name, key=f"dl_{task}_{safe}")
            except Exception as e:
                st.error(f"Não foi possível guardar: {e}")


cyc = db.list_cycles()
cyc = cyc[cyc["n_ensaios"] > 0]
if cyc.empty:
    st.info("Sem dados para modelar. Importe o Global.csv de exemplo na **Home** ou faça aquisições.")
    st.stop()

# --- escopo: multi-seleção de ciclos (podem ser de datas/aplicações diferentes)
sel = st.multiselect("Ciclos a usar", cyc["cycle"].tolist(),
                     default=cyc["cycle"].tolist(),
                     format_func=lambda c: f"{c} · {cyc.loc[cyc.cycle==c,'application'].iloc[0]}")
if not sel:
    st.stop()
data = db.blocos_df(cycles=sel)
if data["EnsaioId"].nunique() < 4:
    st.warning("São precisas pelo menos 4 amostras.")
    st.stop()

feat = C.LED_COLS_AVG
targets = db.candidate_targets(data)

c1, c2, c3 = st.columns(3)
task = c1.radio("Tarefa", ["Classificação", "Regressão"])
quick = c2.toggle("Modo rápido", value=True,
                  help="Rápido: grelhas pequenas. Desligado: grelhas completas (portátil/servidor).")
c3.metric("Amostras", data["EnsaioId"].nunique())

# =====================  CLASSIFICAÇÃO  =====================
if task == "Classificação":
    cat_opts = list(targets["classification"])
    extra = []
    if "estadio" in data.columns:
        extra = ["Doença (binário, a partir de estádio)"]
    choice = st.selectbox("Alvo", extra + cat_opts if cat_opts or extra else ["(sem etiqueta categórica)"])
    df = data.copy()
    if choice.startswith("Doença"):
        df["__alvo__"] = (df["estadio"].astype(str) != "Estadio 0").map({True: "Doente", False: "Controlo"})
        target = "__alvo__"
    else:
        target = choice

    if st.button("▶️ Treinar e avaliar", type="primary"):
        bar = st.progress(0.0, text="A treinar…")
        res = models.run_classification(df, feat, target, quick=quick,
                                        progress=lambda p: bar.progress(min(p, 1.0)))
        bar.empty()
        st.session_state["clf"] = {"res": res, "target": target, "df_is_bin": choice.startswith("Doença")}

    if "clf" in st.session_state:
        res = st.session_state["clf"]["res"]
        st.caption(f"{res['n_samples']} amostras · {res['folds']} folds externos agrupados")
        rows = []
        for name, r in res["results"].items():
            if "error" in r:
                rows.append({"Modelo": name, "Erro": r["error"][:60]}); continue
            rows.append({"Modelo": name,
                         "Acc treino": round(r["train_accuracy"], 3),
                         "Acc validação": round(r["accuracy"], 3),
                         "± DP (val)": round(r["accuracy_sd"], 3),
                         "F1 macro": round(r["f1_macro"], 3),
                         "AUC": None if r["auc"] != r["auc"] else round(r["auc"], 3)})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("O resultado reportado é o de **validação**; a coluna de treino "
                   "mostra o *gap* (sinal de sobreajuste).")
        valid = {k: v for k, v in res["results"].items() if "accuracy" in v}
        if valid:
            best = max(valid, key=lambda k: valid[k]["accuracy"])
            st.success(f"Melhor (validação): **{best}** — accuracy {valid[best]['accuracy']:.3f}")
            st.plotly_chart(ui.confusion_heatmap(valid[best]["cm"], valid[best]["labels"],
                                                 f"Matriz de confusão — {best}"),
                            use_container_width=True)
            _save_block(df, feat, st.session_state["clf"]["target"], "classification", best, quick)

# =====================  REGRESSÃO  =====================
else:
    num_opts = list(targets["regression"])
    if not num_opts:
        st.warning("Sem etiquetas numéricas nos ciclos selecionados.")
        st.stop()
    target = st.selectbox("Alvo (numérico)", num_opts)
    if st.button("▶️ Treinar e avaliar", type="primary"):
        bar = st.progress(0.0, text="A treinar…")
        res = models.run_regression(data, feat, target, quick=quick,
                                    progress=lambda p: bar.progress(min(p, 1.0)))
        bar.empty()
        st.session_state["reg"] = {"res": res, "target": target}

    if "reg" in st.session_state:
        res = st.session_state["reg"]["res"]; target = st.session_state["reg"]["target"]
        st.caption(f"{res['n_samples']} amostras · {res['folds']} folds agrupados · alvo: {target}")
        rows = []
        for name, r in res["results"].items():
            if "error" in r:
                rows.append({"Modelo": name, "Erro": r["error"][:60]}); continue
            rows.append({"Modelo": name, "R² treino": round(r["train_r2"], 3),
                         "R² validação": round(r["r2"], 3), "± DP (val)": round(r["r2_sd"], 3),
                         "RMSE": round(r["rmse"], 4)})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        valid = {k: v for k, v in res["results"].items() if "r2" in v}
        if valid:
            best = max(valid, key=lambda k: valid[k]["r2"])
            st.success(f"Melhor (validação): **{best}** — R² {valid[best]['r2']:.3f}")
            st.plotly_chart(ui.parity_plot(valid[best]["y_true"], valid[best]["y_pred"],
                                           f"Previsto vs Real — {best}"), use_container_width=True)
            _save_block(data, feat, target, "regression", best, quick)

st.divider()
st.caption("Para corridas pesadas (grelhas completas, procura de janelas FT-NIR), "
           "exporta o Global.csv na Home e corre os scripts _GROUPED no portátil.")
