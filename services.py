# -*- coding: utf-8 -*-
"""Recursos partilhados pela app (ligação ao instrumento, BD, seed)."""
import streamlit as st
import config as C
from hardware.instrument import Instrument
from storage import db


@st.cache_resource
def get_instrument():
    """Instância única do instrumento (mock ou real), persistente entre reruns."""
    return Instrument()


@st.cache_resource
def ensure_db():
    db.init_db()
    # semear com os dados reais na primeira utilização, se a BD estiver vazia
    if db.count_ensaios() == 0 and C.SAMPLE_CSV.exists():
        try:
            db.import_global_csv(C.SAMPLE_CSV, cycle="2025.02.12 (exemplo)")
        except Exception as e:
            st.warning(f"Não foi possível semear os dados de exemplo: {e}")
    return True


def mode_badge():
    if C.MOCK_HARDWARE:
        return "🟡 Modo simulado (sem hardware)"
    return "🟢 Hardware ligado"
