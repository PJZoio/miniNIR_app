# -*- coding: utf-8 -*-
"""Página de aquisição — novos ensaios com etiquetas configuráveis por aplicação."""
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
                inst.connect(); st.rerun()
            except Exception as e:
                st.error(f"Falha a ligar: {e}")
    else:
        if st.button("⏹️ Desligar", use_container_width=True):
            inst.close(); st.rerun()
with cc2:
    st.markdown("Estado: " + ("**ligado** ✅" if inst.is_open else "**desligado** — pode preparar o ensaio; ligue antes de adquirir."))

st.divider()
left, right = st.columns([1, 1])

# --- aplicação, ciclo e etiquetas ------------------------------------------
with left:
    st.subheader("Aplicação e ciclo")
    apps = db.list_applications()
    app = st.selectbox("Aplicação", apps,
                       index=apps.index(C.DEFAULT_APPLICATION) if C.DEFAULT_APPLICATION in apps else 0)

    cyc_df = db.list_cycles()
    app_cycles = cyc_df[cyc_df["application"] == app]["cycle"].tolist()
    colc1, colc2 = st.columns([3, 1])
    cycle = colc1.selectbox("Ciclo", app_cycles or ["(nenhum — crie um)"],
                            index=0, key="aq_cycle")
    if colc2.button("➕ Novo", use_container_width=True, help="Cria um ciclo novo (nome automático)"):
        new = db.create_cycle(app)
        st.session_state["aq_cycle"] = new
        st.rerun()
    if cycle == "(nenhum — crie um)":
        st.info("Crie um ciclo para começar (botão ➕ Novo).")
        cycle = None

    st.subheader("Amostra")
    is_blank = st.toggle("É um branco (referência)", value=False,
                         help="Preenche automaticamente as etiquetas numéricas a 0.")
    next_no = db.next_sample_no(cycle) if cycle else 1
    st.caption(f"Nº da amostra (automático): **{next_no}**")
    sample_name = st.text_input("Nome/rótulo da amostra (opcional)",
                                value="" if not is_blank else "branco")

    # Campos de etiqueta, dinâmicos conforme a aplicação
    labels = {}
    for ld in db.get_application_labels(app):
        key, lab, unit = ld["key"], ld["label"], ld.get("unit", "")
        disp = f"{lab}" + (f" ({unit})" if unit else "")
        if ld["type"] == "numeric":
            if is_blank:
                labels[key] = 0.0
                st.number_input(disp, value=0.0, disabled=True, key=f"lab_{key}")
            else:
                labels[key] = st.number_input(
                    disp, value=float(ld.get("min", 0.0)),
                    min_value=(float(ld["min"]) if "min" in ld else None),
                    max_value=(float(ld["max"]) if "max" in ld else None),
                    key=f"lab_{key}")
        else:  # categorical
            opts = ld.get("options") or []
            if opts:
                labels[key] = st.selectbox(disp, opts, key=f"lab_{key}")
            else:
                labels[key] = st.text_input(disp, key=f"lab_{key}")

# --- aquisição --------------------------------------------------------------
with right:
    st.subheader("Aquisição")
    nrep = st.slider("Nº de réplicas", min_value=1, max_value=10, value=10,
                     help="Sub-blocos de 600 amostras por leitura (pseudo-réplicas). "
                          "Réplica verdadeira = repetir toda a leitura da mesma amostra.")
    ns = nrep * C.BLOCK_SIZE
    st.caption(f"= {ns} amostras ADC, divididas em {nrep} bloco(s) de {C.BLOCK_SIZE}.")

    # valor para variar o sinal simulado: 1ª etiqueta numérica (ou 0 se branco)
    mock_conc = 0.0
    if not is_blank:
        for ld in db.get_application_labels(app):
            if ld["type"] == "numeric" and labels.get(ld["key"]) is not None:
                mock_conc = float(labels[ld["key"]]); break

    can_acq = inst.is_open and cycle is not None
    if st.button("▶️ Adquirir amostra", type="primary", use_container_width=True,
                 disabled=not can_acq):
        bar = st.progress(0.0, text="A adquirir…")
        acq = inst.acquire_sample(conc=mock_conc, num_samples=ns,
                                  progress=lambda p: bar.progress(min(p, 1.0),
                                                                  text=f"A adquirir… {int(p*100)}%"))
        bar.empty()
        sat = qc.flag_saturation(acq["summary"]["avg"])
        eid, sno = db.save_ensaio(cycle, labels, acq, is_blank=is_blank,
                                  sample_name=sample_name or None, saturated=sat)
        st.session_state["last_acq"] = {"acq": acq, "sat": sat, "eid": eid, "sno": sno}
        st.success(f"Ensaio #{eid} (amostra {sno} do ciclo {cycle}) guardado — {nrep} réplica(s).")
    if not can_acq:
        st.caption("Para adquirir: ligar o instrumento e selecionar/criar um ciclo.")

    if "last_acq" in st.session_state:
        la = st.session_state["last_acq"]
        st.plotly_chart(ui.bar_channels(la["acq"]["summary"]["avg"],
                                        f"Ensaio #{la['eid']} — sinal por canal"),
                        use_container_width=True)
        qdf = qc.ensaio_qc(la["acq"]["summary"]["avg"], la["acq"]["summary"]["std"])
        if any(s == "SATURADO" for s in qdf["Estado"]):
            st.warning("Canais saturados nesta leitura — considere reduzir o ganho (ver procedimento).")
        st.dataframe(ui.style_qc_table(qdf), use_container_width=True, hide_index=True)

st.divider()

# --- diálogo de composição automática (seringas) — pré-visualização --------
def _syringes_body():
    st.caption("Pré-visualização do módulo de **análise contínua e automática** "
               "(ainda inativo — depende do hardware dos motores/seringas).")
    st.write("Para uma solução-alvo, cada seringa (solução-base) teria a sua "
             "concentração; o volume correspondente converte-se em passos do motor, "
             "misturando à entrada da cuvette.")
    bases = st.number_input("Nº de seringas (soluções-base)", 2, 8, 3)
    for i in range(int(bases)):
        c1, c2 = st.columns([2, 1])
        c1.slider(f"Seringa {i+1} — concentração da base", 0.0, 100.0, 0.0, key=f"syr{i}")
        c2.text_input("Solução-base", value=["Ureia", "Creatinina", "Albumina",
                                             "SFB", "Água"][i] if i < 5 else "", key=f"syrn{i}")
    st.info("Mapeamento concentração→volume→passos a definir com os dados de "
            "calibração e a folha 'Análise estatística'.")

if st.button("🧪 Composição automática (seringas) — pré-visualização"):
    if hasattr(st, "dialog"):
        st.dialog("Composição automática por seringas")(_syringes_body)()
    else:
        with st.expander("Composição automática por seringas", expanded=True):
            _syringes_body()

if C.MOCK_HARDWARE:
    with st.expander("🧪 Simular ajuste de ganhos (demonstração)"):
        st.caption("Reduzir o ganho dos canais saturados (1300/1600/1900 nm) mostra-os a sair do tecto.")
        g1 = st.slider("Ganho 1300 nm", 0.3, 1.0, 1.0, 0.05)
        g3 = st.slider("Ganho 1600 nm", 0.3, 1.0, 1.0, 0.05)
        g5 = st.slider("Ganho 1900 nm", 0.3, 1.0, 1.0, 0.05)
        inst.set_mock_gains({1: g1, 3: g3, 5: g5})
