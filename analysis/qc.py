# -*- coding: utf-8 -*-
"""Controlo de qualidade — saturação, repetibilidade e resposta à amostra.

Implementa o diagnóstico do procedimento de ganhos:
  - saturação: sinal encostado ao fundo de escala (>= SAT_FRACTION * FULL_SCALE)
  - o indicador determinante de saturação é a AUSÊNCIA de resposta entre
    amostras, não o %RSD (um canal ceifado tem %RSD artificialmente baixo).
"""
import numpy as np
import pandas as pd
import config as C


def flag_saturation(avg_list):
    """Lista[6] bool: canal saturado se média >= SAT_FRACTION do fundo de escala."""
    thr = C.SAT_FRACTION * C.FULL_SCALE
    return [bool(v is not None and v >= thr) for v in avg_list]


def ensaio_qc(avg_list, std_list):
    """QC de uma única aquisição (nível de ensaio)."""
    rows = []
    thr = C.SAT_FRACTION * C.FULL_SCALE
    for ch, a, s in zip(C.LED_CHANNELS, avg_list, std_list):
        pct_fs = 100 * a / C.FULL_SCALE if a is not None else None
        rsd = 100 * s / a if (a and s is not None and a != 0) else None
        rows.append({
            "Canal": f"{ch['nominal']} nm (LED{ch['idx']})",
            "Sinal (V)": round(a, 4) if a is not None else None,
            "% F. Escala": round(pct_fs, 1) if pct_fs is not None else None,
            "%RSD intra": round(rsd, 4) if rsd is not None else None,
            "Estado": "SATURADO" if (a is not None and a >= thr) else "OK",
        })
    return pd.DataFrame(rows)


def dataset_qc(blocos):
    """QC ao nível do conjunto: usa a variação ENTRE amostras como critério.

    blocos: DataFrame de storage.blocos_df (colunas EnsaioId, LEDk_avg, LEDk_std).
    """
    if blocos is None or blocos.empty:
        return pd.DataFrame()
    rows = []
    thr = C.SAT_FRACTION * C.FULL_SCALE
    for ch in C.LED_CHANNELS:
        col = f"LED{ch['idx']}_avg"
        scol = f"LED{ch['idx']}_std"
        # média por amostra física
        per_sample = blocos.groupby("EnsaioId")[col].mean()
        mean_sig = float(per_sample.mean())
        resp_range = float(per_sample.max() - per_sample.min())
        resp_pct = 100 * resp_range / mean_sig if mean_sig else 0.0
        # %RSD intra-amostra médio
        if scol in blocos.columns and blocos[scol].notna().any():
            rsd = (blocos[scol] / blocos[col].replace(0, np.nan)).mean() * 100
        else:
            rsd = np.nan
        saturated = mean_sig >= thr
        no_response = resp_pct < C.RESPONSE_MIN_PCT
        if saturated and no_response:
            status = "SATURADO"
        elif saturated:
            status = "Perto do tecto"
        else:
            status = "OK"
        rows.append({
            "Canal": f"{ch['nominal']} nm (LED{ch['idx']})",
            "Sinal médio (V)": round(mean_sig, 4),
            "% F. Escala": round(100 * mean_sig / C.FULL_SCALE, 1),
            "Resposta entre amostras": f"{resp_pct:.2f} %",
            "%RSD intra": (round(rsd, 4) if rsd == rsd else None),
            "Estado": status,
        })
    return pd.DataFrame(rows)
