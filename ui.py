# -*- coding: utf-8 -*-
"""Elementos de interface partilhados: tema, cabeçalho, gráficos (Plotly)."""
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import config as C

_CSS = """
<style>
.block-container {padding-top: 2.2rem; max-width: 1200px;}
h1, h2, h3 {color: #1F3A5F;}
div[data-testid="stMetric"] {background: #f6f8fb; border: 1px solid #e7ecf3;
    border-radius: 10px; padding: 12px 14px;}
.badge {display:inline-block; padding:2px 10px; border-radius:12px;
    font-size:0.8rem; font-weight:600;}
.badge-sat {background:#fce8e6; color:#b03020;}
.badge-ok {background:#e7f4ea; color:#2e7d32;}
.badge-warn {background:#fff4e5; color:#b26a00;}
.small {color:#667; font-size:0.85rem;}
</style>
"""


def setup_page(title, icon="🔬"):
    st.set_page_config(page_title=f"miniNIR · {title}", page_icon=icon,
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(_CSS, unsafe_allow_html=True)


def status_badge(status):
    cls = {"SATURADO": "badge-sat", "OK": "badge-ok"}.get(status, "badge-warn")
    return f'<span class="badge {cls}">{status}</span>'


def style_qc_table(df):
    def _color(val):
        if val == "SATURADO":
            return "background-color:#fce8e6; color:#b03020; font-weight:600;"
        if val == "OK":
            return "background-color:#e7f4ea; color:#2e7d32;"
        if val == "Perto do tecto":
            return "background-color:#fff4e5; color:#b26a00;"
        return ""
    if "Estado" in df.columns:
        return df.style.map(_color, subset=["Estado"])
    return df


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def bar_channels(avg_list, title="Sinal por canal"):
    """Barras dos 6 canais com linha de fundo de escala."""
    colors = [C.PALETTE[l] for l in C.LED_LABELS]
    fig = go.Figure(go.Bar(x=C.LED_LABELS, y=avg_list, marker_color=colors,
                           text=[f"{v:.3f}" for v in avg_list], textposition="outside"))
    fig.add_hline(y=C.FULL_SCALE, line_dash="dash", line_color="#b03020",
                  annotation_text="fundo de escala", annotation_position="top right")
    fig.add_hline(y=C.TARGET_HIGH * C.FULL_SCALE, line_dash="dot", line_color="#b26a00",
                  annotation_text="alvo 85%", annotation_position="bottom right")
    fig.update_layout(title=title, yaxis_title="Sinal (V)", height=360,
                      margin=dict(t=48, b=20, l=10, r=10), showlegend=False,
                      yaxis_range=[0, C.FULL_SCALE * 1.12])
    return fig


def line_channels_vs_sample(blocos, x="Conc"):
    """Média por amostra de cada canal vs concentração/estádio."""
    per = blocos.groupby(["EnsaioId", x] if x in blocos.columns else ["EnsaioId"])
    fig = go.Figure()
    for ch in C.LED_CHANNELS:
        col = f"LED{ch['idx']}_avg"
        g = blocos.groupby(x)[col].mean().reset_index() if x in blocos.columns else None
        if g is None:
            continue
        fig.add_trace(go.Scatter(x=g[x], y=g[col], mode="lines+markers",
                                 name=f"{ch['nominal']} nm",
                                 line=dict(color=C.PALETTE[f"{ch['nominal']} nm"])))
    fig.update_layout(title=f"Resposta dos canais vs {x}", xaxis_title=x,
                      yaxis_title="Sinal (V)", height=420,
                      margin=dict(t=48, b=20, l=10, r=10),
                      legend=dict(orientation="h", y=-0.2))
    return fig


def confusion_heatmap(cm, labels, title="Matriz de confusão"):
    z = np.array(cm)
    fig = px.imshow(z, x=labels, y=labels, color_continuous_scale="Blues",
                    text_auto=True, aspect="auto",
                    labels=dict(x="Previsto", y="Real", color="n"))
    fig.update_layout(title=title, height=420, margin=dict(t=48, b=20, l=10, r=10))
    return fig


def parity_plot(y_true, y_pred, title="Previsto vs Real"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=y_true, y=y_pred, mode="markers",
                             marker=dict(color=C.ACCENT, opacity=0.6)))
    lo, hi = min(min(y_true), min(y_pred)), max(max(y_true), max(y_pred))
    fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines",
                             line=dict(dash="dash", color="#b03020"), showlegend=False))
    fig.update_layout(title=title, xaxis_title="Real", yaxis_title="Previsto",
                      height=420, margin=dict(t=48, b=20, l=10, r=10), showlegend=False)
    return fig
