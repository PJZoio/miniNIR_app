# -*- coding: utf-8 -*-
"""Página de modelos — classificação e regressão com CV agrupada por amostra."""
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
st.caption("Validação cruzada **agrupada por amostra física (EnsaioId)** — sem "
           "fuga de informação entre réplicas, como nos teus scripts _GROUPED.")

blocos = db.blocos_df()
if blocos.empty or blocos["EnsaioId"].nunique() < 4:
    st.info("São precisas várias amostras para modelar. Importe o Global.csv de "
            "exemplo na página **Dataset** ou faça aquisições.")
    st.stop()

# escopo
cyc_opts = ["(todos os ciclos)"] + sorted(blocos["cycle"].dropna().unique().tolist())
scope = st.selectbox("Conjunto", cyc_opts)
data = blocos if scope == "(todos os ciclos)" else blocos[blocos["cycle"] == scope]

feat = C.LED_COLS_AVG
c1, c2, c3 = st.columns(3)
task = c1.radio("Tarefa", ["Classificação", "Regressão"])
quick = c2.toggle("Modo rápido", value=True,
                  help="Rápido: grelhas pequenas (ok no Pi). Desligado: grelhas "
                       "completas (correr no portátil/servidor).")
c3.metric("Amostras", data["EnsaioId"].nunique())

if task == "Classificação":
    target_choice = st.selectbox("Alvo", ["Estádio (6 classes)", "Doença (binário)"])
    df = data.copy()
    if target_choice.startswith("Doença"):
        ctrl = "Estadio 0"
        df["alvo"] = (df["Estadio"] != ctrl).map({True: "Doente", False: "Controlo"})
    else:
        df["alvo"] = df["Estadio"]
    if st.button("▶️ Treinar e avaliar", type="primary"):
        bar = st.progress(0.0, text="A treinar modelos…")
        res = models.run_classification(df, feat, "alvo", quick=quick,
                                        progress=lambda p: bar.progress(min(p, 1.0)))
        bar.empty()
        st.session_state["clf_res"] = res
    if "clf_res" in st.session_state:
        res = st.session_state["clf_res"]
        st.caption(f"{res['n_samples']} amostras · {res['folds']} folds externos agrupados")
        rows = []
        for name, r in res["results"].items():
            if "error" in r:
                rows.append({"Modelo": name, "Erro": r["error"]}); continue
            rows.append({"Modelo": name, "Accuracy": round(r["accuracy"], 3),
                         "± DP": round(r["accuracy_sd"], 3),
                         "F1 macro": round(r["f1_macro"], 3),
                         "AUC": None if r["auc"] != r["auc"] else round(r["auc"], 3)})
        tab = pd.DataFrame(rows)
        st.dataframe(tab, use_container_width=True, hide_index=True)
        valid = {k: v for k, v in res["results"].items() if "accuracy" in v}
        if valid:
            best = max(valid, key=lambda k: valid[k]["accuracy"])
            st.success(f"Melhor modelo: **{best}** "
                       f"(accuracy {valid[best]['accuracy']:.3f})")
            st.plotly_chart(ui.confusion_heatmap(valid[best]["cm"], valid[best]["labels"],
                                                 f"Matriz de confusão — {best}"),
                            use_container_width=True)

else:  # Regressão
    num_targets = ["Conc"] + [c for c in data.columns
                              if c not in (C.LED_COLS_AVG + C.LED_COLS_STD +
                                           ["EnsaioId", "line", "init_time", "Estadio",
                                            "series", "cycle", "Conc"])
                              and pd.to_numeric(data[c], errors="coerce").notna().any()]
    target = st.selectbox("Alvo (numérico)", num_targets,
                          help="Conc por defeito. Importe um CSV com colunas de "
                               "creatinina/ureia/albumina para as modelar.")
    if st.button("▶️ Treinar e avaliar", type="primary"):
        bar = st.progress(0.0, text="A treinar modelos…")
        res = models.run_regression(data, feat, target, quick=quick,
                                    progress=lambda p: bar.progress(min(p, 1.0)))
        bar.empty()
        st.session_state["reg_res"] = res
        st.session_state["reg_target"] = target
    if "reg_res" in st.session_state:
        res = st.session_state["reg_res"]
        st.caption(f"{res['n_samples']} amostras · {res['folds']} folds agrupados · "
                   f"alvo: {st.session_state.get('reg_target')}")
        rows = []
        for name, r in res["results"].items():
            if "error" in r:
                rows.append({"Modelo": name, "Erro": r["error"]}); continue
            rows.append({"Modelo": name, "R²": round(r["r2"], 3),
                         "± DP": round(r["r2_sd"], 3), "RMSE": round(r["rmse"], 4)})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        valid = {k: v for k, v in res["results"].items() if "r2" in v}
        if valid:
            best = max(valid, key=lambda k: valid[k]["r2"])
            st.success(f"Melhor modelo: **{best}** (R² {valid[best]['r2']:.3f})")
            st.plotly_chart(ui.parity_plot(valid[best]["y_true"], valid[best]["y_pred"],
                                           f"Previsto vs Real — {best}"),
                            use_container_width=True)

st.divider()
st.caption("Nota: para corridas pesadas (grelhas completas, procura de janelas "
           "FT-NIR), exporte o Global.csv na página Dataset e use os scripts "
           "_GROUPED no portátil/servidor — o Pi é lento para nested-CV.")
