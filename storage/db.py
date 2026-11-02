# -*- coding: utf-8 -*-
"""Armazenamento em SQLite (fonte de verdade local, portátil).

Dois níveis, espelhando o teu esquema MySQL:
  - ensaios : uma linha por aquisição (resumo média/desvio por LED + metadados)
  - blocos  : os blocos de 600 amostras ("linhas"/réplicas) de cada ensaio
              -> equivalente à tabela dadosPLS que alimenta os modelos.

Export para CSV no formato exato do teu Global.csv:
  EnsaioId;line;Conc;Estadio;LED1_avg;...;LED6_avg   (sep=';', decimal=',')
"""
import sqlite3
import json
from datetime import datetime
import numpy as np
import pandas as pd
import config as C

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ensaios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    cycle       TEXT,
    series      TEXT,
    conc        REAL,
    estadio     TEXT,
    descricao   TEXT,
    num_samples INTEGER,
    block_size  INTEGER,
    raw_path    TEXT,
    led_avg     TEXT,   -- JSON [6]
    led_std     TEXT,   -- JSON [6]
    saturated   TEXT    -- JSON [6] bool
);
CREATE TABLE IF NOT EXISTS blocos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ensaio_id  INTEGER NOT NULL REFERENCES ensaios(id) ON DELETE CASCADE,
    line       INTEGER,
    init_time  REAL,
    led_avg    TEXT,
    led_std    TEXT
);
CREATE INDEX IF NOT EXISTS idx_blocos_ensaio ON blocos(ensaio_id);
"""


def connect():
    conn = sqlite3.connect(str(C.DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = connect()
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
def save_ensaio(meta, acq, saturated=None):
    """meta: dict(cycle, series, conc, estadio, descricao);
    acq: resultado de Instrument.acquire_sample; saturated: lista[6] bool."""
    conn = connect()
    cur = conn.cursor()
    raw_path = None
    if acq.get("raw") is not None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        raw_path = str(C.RAW_DIR / f"{meta.get('series','S')}_{ts}.csv")
        np.savetxt(raw_path, acq["raw"], fmt="%.5f", delimiter=",")
    cur.execute(
        """INSERT INTO ensaios (created_at, cycle, series, conc, estadio,
           descricao, num_samples, block_size, raw_path, led_avg, led_std, saturated)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now().isoformat(timespec="seconds"),
         meta.get("cycle"), meta.get("series"), meta.get("conc"),
         meta.get("estadio"), meta.get("descricao"),
         acq.get("num_samples"), acq.get("block_size"), raw_path,
         json.dumps(acq["summary"]["avg"]), json.dumps(acq["summary"]["std"]),
         json.dumps(saturated if saturated is not None else [None] * 6)))
    ensaio_id = cur.lastrowid
    for b in acq["blocks"]:
        cur.execute(
            """INSERT INTO blocos (ensaio_id, line, init_time, led_avg, led_std)
               VALUES (?,?,?,?,?)""",
            (ensaio_id, b["line"], b["init_time"],
             json.dumps(b["avg"]), json.dumps(b["std"])))
    conn.commit()
    conn.close()
    return ensaio_id


def delete_ensaio(ensaio_id):
    conn = connect()
    conn.execute("DELETE FROM ensaios WHERE id = ?", (ensaio_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _expand(df, col, prefix):
    arr = df[col].apply(lambda s: json.loads(s) if s else [None] * 6)
    for i in range(6):
        df[f"{prefix}{i+1}"] = arr.apply(lambda v: v[i] if v and i < len(v) else None)
    return df.drop(columns=[col])


def ensaios_df(cycle=None):
    conn = connect()
    q = "SELECT * FROM ensaios"
    params = ()
    if cycle:
        q += " WHERE cycle = ?"
        params = (cycle,)
    q += " ORDER BY id"
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    if df.empty:
        return df
    df = _expand(df, "led_avg", "LED_avg")
    df = _expand(df, "led_std", "LED_std")
    df.rename(columns={f"LED_avg{i}": f"LED{i}_avg" for i in range(1, 7)}, inplace=True)
    df.rename(columns={f"LED_std{i}": f"LED{i}_std" for i in range(1, 7)}, inplace=True)
    return df


def blocos_df(cycle=None, ensaio_ids=None):
    """Tabela ao nível de bloco (como dadosPLS) com Conc/Estadio juntos."""
    conn = connect()
    q = """SELECT b.ensaio_id AS EnsaioId, b.line, b.init_time, b.led_avg, b.led_std,
                  e.conc AS Conc, e.estadio AS Estadio, e.series, e.cycle
           FROM blocos b JOIN ensaios e ON e.id = b.ensaio_id"""
    conds, params = [], []
    if cycle:
        conds.append("e.cycle = ?"); params.append(cycle)
    if ensaio_ids:
        conds.append("b.ensaio_id IN (%s)" % ",".join("?" * len(ensaio_ids)))
        params.extend(ensaio_ids)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY b.ensaio_id, b.line"
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    if df.empty:
        return df
    df = _expand(df, "led_avg", "LED_avg")
    df = _expand(df, "led_std", "LED_std")
    df.rename(columns={f"LED_avg{i}": f"LED{i}_avg" for i in range(1, 7)}, inplace=True)
    df.rename(columns={f"LED_std{i}": f"LED{i}_std" for i in range(1, 7)}, inplace=True)
    return df


def cycles():
    conn = connect()
    df = pd.read_sql_query(
        "SELECT cycle, COUNT(*) n FROM ensaios WHERE cycle IS NOT NULL GROUP BY cycle ORDER BY MAX(id) DESC",
        conn)
    conn.close()
    return df


def count_ensaios():
    conn = connect()
    n = conn.execute("SELECT COUNT(*) FROM ensaios").fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------------------
# Export / Import no formato Global.csv
# ---------------------------------------------------------------------------
def export_global_csv(path, cycle=None):
    df = blocos_df(cycle=cycle)
    if df.empty:
        raise ValueError("Sem dados para exportar.")
    cols = ["EnsaioId", "line", "Conc", "Estadio"] + C.LED_COLS_AVG
    out = df[cols].copy()
    out.to_csv(path, sep=C.CSV_SEP, decimal=C.CSV_DECIMAL, index=False)
    return path


def import_global_csv(path, cycle="importado"):
    """Importa um Global.csv (nível de bloco) reconstruindo ensaios + blocos."""
    df = pd.read_csv(path, sep=C.CSV_SEP, decimal=C.CSV_DECIMAL)
    df.columns = [c.strip() for c in df.columns]
    conn = connect()
    cur = conn.cursor()
    created = 0
    for eid, grp in df.groupby("EnsaioId"):
        g = grp.reset_index(drop=True)
        sample_label = str(g.iloc[0]["line"]) if "line" in g.columns else "import"
        avg = g[C.LED_COLS_AVG].mean().tolist()
        std_cols = [c for c in C.LED_COLS_STD if c in g.columns]
        std = g[std_cols].mean().tolist() if std_cols else [None] * 6
        cur.execute(
            """INSERT INTO ensaios (created_at, cycle, series, conc, estadio,
               descricao, num_samples, block_size, raw_path, led_avg, led_std, saturated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(timespec="seconds"), cycle,
             sample_label,
             float(g.iloc[0]["Conc"]) if "Conc" in g else None,
             str(g.iloc[0].get("Estadio")) if "Estadio" in g else None,
             f"Importado (EnsaioId original {eid}, amostra '{sample_label}')",
             None, None, None,
             json.dumps([None if x is None or x != x else float(x) for x in avg]),
             json.dumps([None if x is None or x != x else float(x) for x in std]),
             json.dumps([None] * 6)))
        new_id = cur.lastrowid
        for bidx, (_, row) in enumerate(g.iterrows()):
            avgb = [float(row[c]) for c in C.LED_COLS_AVG]
            stdb = [float(row[c]) for c in std_cols] if std_cols else [None] * 6
            cur.execute(
                """INSERT INTO blocos (ensaio_id, line, init_time, led_avg, led_std)
                   VALUES (?,?,?,?,?)""",
                (new_id, bidx, 0.0,
                 json.dumps([None if x is None or x != x else float(x) for x in avgb]),
                 json.dumps([None if x is None or x != x else float(x) for x in stdb])))
        created += 1
    conn.commit()
    conn.close()
    return created
