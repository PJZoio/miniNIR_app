# -*- coding: utf-8 -*-
"""Armazenamento em SQLite com modelo de APLICAÇÕES + ETIQUETAS.

Hierarquia:
  aplicação (DRC, Biodiesel, ...) -> define as etiquetas do formulário
    └─ ciclo (ronda de ensaios, p. ex. DRC-1)
         └─ ensaio (uma leitura de uma amostra; tem valores de etiqueta)
              └─ blocos (as réplicas = sub-blocos da aquisição)

As etiquetas são guardadas como JSON por ensaio (labels_json), por isso
aplicações diferentes podem ter campos diferentes sem mudar o esquema.

Export para CSV compatível com os modelos: EnsaioId;line;<etiquetas>;LEDk_avg.
"""
import sqlite3
import json
from datetime import datetime
import numpy as np
import pandas as pd
import config as C

# Colunas estruturais (tudo o resto, em blocos_df/ensaios_df, são etiquetas)
STRUCT_COLS = {"EnsaioId", "id", "ensaio_id", "line", "init_time", "created_at",
               "cycle", "application", "sample_no", "sample_name", "is_blank",
               "num_samples", "block_size", "raw_path"} \
              | set(C.LED_COLS_AVG) | set(C.LED_COLS_STD)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    name       TEXT PRIMARY KEY,
    labels_json TEXT NOT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS cycles (
    name        TEXT PRIMARY KEY,
    application TEXT NOT NULL,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS ensaios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    cycle       TEXT,
    sample_no   INTEGER,
    sample_name TEXT,
    is_blank    INTEGER DEFAULT 0,
    labels_json TEXT,
    num_samples INTEGER,
    block_size  INTEGER,
    raw_path    TEXT,
    led_avg     TEXT,
    led_std     TEXT,
    saturated   TEXT
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
CREATE INDEX IF NOT EXISTS idx_ensaios_cycle ON ensaios(cycle);
"""


def connect():
    conn = sqlite3.connect(str(C.DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Colunas/tabelas exigidas pelo código atual. Se faltar alguma numa BD já
# existente (p. ex. uma BD antiga que ficou no Streamlit Cloud), a BD é
# incompatível e é recriada do zero (os dados de exemplo são re-semeados).
_REQUIRED_ENSAIO_COLS = {"sample_no", "sample_name", "is_blank", "labels_json"}
_REQUIRED_TABLES = {"applications", "cycles", "ensaios", "blocos"}


def _schema_compatible():
    """True se a BD existente já tem o esquema novo. Não cria ficheiro novo."""
    if not C.DB_PATH.exists():
        return True  # não existe -> será criada de raiz, compatível
    try:
        conn = connect()
        tbls = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        cols = {r[1] for r in conn.execute("PRAGMA table_info(ensaios)")}
        conn.close()
        return _REQUIRED_TABLES.issubset(tbls) and _REQUIRED_ENSAIO_COLS.issubset(cols)
    except Exception:
        return False


def init_db():
    # Reconstrução robusta: se o esquema for incompatível, apaga o ficheiro e
    # recria (mais fiável do que DROP/PRAGMA face à semântica de transações do
    # sqlite3 em versões recentes do Python).
    if not _schema_compatible():
        try:
            C.DB_PATH.unlink()
        except Exception:
            # fallback: tentar largar as tabelas antigas
            try:
                conn = connect()
                for t in ("blocos", "ensaios", "cycles", "applications"):
                    conn.execute(f"DROP TABLE IF EXISTS {t}")
                conn.commit(); conn.close()
            except Exception:
                pass
    conn = connect()
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    # garantir aplicações pré-definidas
    for name, labels in C.APPLICATIONS.items():
        ensure_application(name, labels)


# ---------------------------------------------------------------------------
# Aplicações
# ---------------------------------------------------------------------------
def ensure_application(name, labels):
    conn = connect()
    row = conn.execute("SELECT name FROM applications WHERE name=?", (name,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO applications (name, labels_json, created_at) VALUES (?,?,?)",
                     (name, json.dumps(labels), datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    conn.close()


def save_application(name, labels):
    conn = connect()
    conn.execute(
        "INSERT INTO applications (name, labels_json, created_at) VALUES (?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET labels_json=excluded.labels_json",
        (name, json.dumps(labels), datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def list_applications():
    conn = connect()
    rows = conn.execute("SELECT name FROM applications ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


def get_application_labels(name):
    conn = connect()
    row = conn.execute("SELECT labels_json FROM applications WHERE name=?", (name,)).fetchone()
    conn.close()
    if row:
        return json.loads(row["labels_json"])
    return C.APPLICATIONS.get(name, [])


# ---------------------------------------------------------------------------
# Ciclos
# ---------------------------------------------------------------------------
def create_cycle(application, name=None):
    conn = connect()
    if not name:
        n = conn.execute("SELECT COUNT(*) FROM cycles WHERE application=?",
                         (application,)).fetchone()[0]
        # nome automático: <APP>-<n+1>, evitando colisões
        k = n + 1
        while conn.execute("SELECT 1 FROM cycles WHERE name=?",
                           (f"{application}-{k}",)).fetchone():
            k += 1
        name = f"{application}-{k}"
    conn.execute("INSERT OR IGNORE INTO cycles (name, application, created_at) VALUES (?,?,?)",
                 (name, application, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()
    return name


def cycle_application(cycle):
    conn = connect()
    row = conn.execute("SELECT application FROM cycles WHERE name=?", (cycle,)).fetchone()
    conn.close()
    return row["application"] if row else C.DEFAULT_APPLICATION


def list_cycles():
    conn = connect()
    df = pd.read_sql_query(
        """SELECT c.name AS cycle, c.application, c.created_at,
                  (SELECT COUNT(*) FROM ensaios e WHERE e.cycle=c.name) AS n_ensaios
           FROM cycles c ORDER BY c.created_at DESC, c.name""", conn)
    conn.close()
    return df


def next_sample_no(cycle):
    conn = connect()
    n = conn.execute("SELECT COALESCE(MAX(sample_no),0) FROM ensaios WHERE cycle=?",
                     (cycle,)).fetchone()[0]
    conn.close()
    return int(n) + 1


# ---------------------------------------------------------------------------
# Ensaios
# ---------------------------------------------------------------------------
def save_ensaio(cycle, labels, acq, is_blank=False, sample_name=None, saturated=None):
    conn = connect()
    cur = conn.cursor()
    sample_no = next_sample_no(cycle)
    raw_path = None
    if acq.get("raw") is not None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        raw_path = str(C.RAW_DIR / f"{cycle}_{sample_no}_{ts}.csv")
        try:
            np.savetxt(raw_path, acq["raw"], fmt="%.5f", delimiter=",")
        except Exception:
            raw_path = None
    cur.execute(
        """INSERT INTO ensaios (created_at, cycle, sample_no, sample_name, is_blank,
           labels_json, num_samples, block_size, raw_path, led_avg, led_std, saturated)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now().isoformat(timespec="seconds"), cycle, sample_no,
         sample_name or (f"branco-{sample_no}" if is_blank else f"amostra-{sample_no}"),
         1 if is_blank else 0, json.dumps(labels or {}),
         acq.get("num_samples"), acq.get("block_size"), raw_path,
         json.dumps([None if x is None or x != x else float(x) for x in acq["summary"]["avg"]]),
         json.dumps([None if x is None or x != x else float(x) for x in acq["summary"]["std"]]),
         json.dumps(saturated if saturated is not None else [None] * 6)))
    ensaio_id = cur.lastrowid
    for b in acq["blocks"]:
        cur.execute(
            "INSERT INTO blocos (ensaio_id, line, init_time, led_avg, led_std) VALUES (?,?,?,?,?)",
            (ensaio_id, b["line"], b["init_time"], json.dumps(b["avg"]), json.dumps(b["std"])))
    conn.commit()
    conn.close()
    return ensaio_id, sample_no


def delete_ensaio(ensaio_id):
    conn = connect()
    conn.execute("DELETE FROM ensaios WHERE id = ?", (ensaio_id,))
    conn.commit()
    conn.close()


def count_ensaios():
    conn = connect()
    n = conn.execute("SELECT COUNT(*) FROM ensaios").fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------------------
# Leitura (com expansão de LED e etiquetas em colunas)
# ---------------------------------------------------------------------------
def _expand_leds(df):
    for pref, src in (("LED_avg", "led_avg"), ("LED_std", "led_std")):
        if src not in df.columns:
            continue
        arr = df[src].apply(lambda s: json.loads(s) if s else [None] * 6)
        for i in range(6):
            df[f"{pref}{i+1}"] = arr.apply(lambda v: v[i] if v and i < len(v) else None)
        df = df.drop(columns=[src])
    df.rename(columns={f"LED_avg{i}": f"LED{i}_avg" for i in range(1, 7)}, inplace=True)
    df.rename(columns={f"LED_std{i}": f"LED{i}_std" for i in range(1, 7)}, inplace=True)
    return df


def _expand_labels(df):
    if "labels_json" not in df.columns:
        return df
    parsed = df["labels_json"].apply(lambda s: json.loads(s) if s else {})
    keys = set()
    for d in parsed:
        keys.update(d.keys())
    for k in sorted(keys):
        df[k] = parsed.apply(lambda d: d.get(k))
    return df.drop(columns=["labels_json"])


def _cycle_filter(cycles):
    if not cycles:
        return "", []
    if isinstance(cycles, str):
        cycles = [cycles]
    return " IN (%s)" % ",".join("?" * len(cycles)), list(cycles)


def ensaios_df(cycles=None, application=None, date_from=None, date_to=None,
               include_blanks=True):
    conn = connect()
    q = """SELECT e.*, c.application
           FROM ensaios e LEFT JOIN cycles c ON c.name = e.cycle WHERE 1=1"""
    params = []
    cf, cp = _cycle_filter(cycles)
    if cf:
        q += " AND e.cycle" + cf; params += cp
    if application:
        q += " AND c.application = ?"; params.append(application)
    if date_from:
        q += " AND e.created_at >= ?"; params.append(str(date_from))
    if date_to:
        q += " AND e.created_at <= ?"; params.append(str(date_to) + "T23:59:59")
    if not include_blanks:
        q += " AND e.is_blank = 0"
    q += " ORDER BY e.cycle, e.sample_no"
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    if df.empty:
        return df
    df = _expand_leds(df)
    df = _expand_labels(df)
    df.rename(columns={"id": "EnsaioId"}, inplace=True)
    return df


def blocos_df(cycles=None, application=None, date_from=None, date_to=None,
              include_blanks=True, ensaio_ids=None):
    conn = connect()
    q = """SELECT b.ensaio_id AS EnsaioId, b.line, b.init_time, b.led_avg, b.led_std,
                  e.cycle, e.sample_no, e.sample_name, e.is_blank, e.labels_json,
                  c.application
           FROM blocos b JOIN ensaios e ON e.id=b.ensaio_id
           LEFT JOIN cycles c ON c.name=e.cycle WHERE 1=1"""
    params = []
    cf, cp = _cycle_filter(cycles)
    if cf:
        q += " AND e.cycle" + cf; params += cp
    if application:
        q += " AND c.application = ?"; params.append(application)
    if date_from:
        q += " AND e.created_at >= ?"; params.append(str(date_from))
    if date_to:
        q += " AND e.created_at <= ?"; params.append(str(date_to) + "T23:59:59")
    if not include_blanks:
        q += " AND e.is_blank = 0"
    if ensaio_ids:
        q += " AND b.ensaio_id IN (%s)" % ",".join("?" * len(ensaio_ids))
        params += list(ensaio_ids)
    q += " ORDER BY b.ensaio_id, b.line"
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    if df.empty:
        return df
    df = _expand_leds(df)
    df = _expand_labels(df)
    return df


def label_columns(df):
    """Devolve as colunas de etiqueta presentes (não estruturais, não LED)."""
    return [c for c in df.columns if c not in STRUCT_COLS]


def candidate_targets(df):
    """Separa as etiquetas em candidatas a regressão (numéricas) e classificação."""
    num, cat = [], []
    for c in label_columns(df):
        s = df[c].dropna()
        if s.empty:
            continue
        if pd.to_numeric(s, errors="coerce").notna().all():
            num.append(c)
        else:
            cat.append(c)
    return {"regression": num, "classification": cat}


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------
def export_global_csv(path, cycles=None):
    df = blocos_df(cycles=cycles)
    if df.empty:
        raise ValueError("Sem dados para exportar.")
    labels = label_columns(df)
    cols = ["EnsaioId", "line"] + labels + C.LED_COLS_AVG
    df[cols].to_csv(path, sep=C.CSV_SEP, decimal=C.CSV_DECIMAL, index=False)
    return path


def import_global_csv(path, application="DRC", cycle=None):
    """Importa um CSV ao nível de bloco. Colunas não-estruturais viram etiquetas.
    Compatível com o Global.csv antigo (Conc, Estadio)."""
    df = pd.read_csv(path, sep=C.CSV_SEP, decimal=C.CSV_DECIMAL)
    df.columns = [c.strip() for c in df.columns]
    ensure_application(application, C.APPLICATIONS.get(application, C.APPLICATIONS["Genérica"]))
    cycle = create_cycle(application, name=cycle)

    led_avg_cols = [c for c in C.LED_COLS_AVG if c in df.columns]
    led_std_cols = [c for c in C.LED_COLS_STD if c in df.columns]
    label_cols = [c for c in df.columns
                  if c not in (set(led_avg_cols) | set(led_std_cols) | {"EnsaioId", "line"})]

    conn = connect()
    cur = conn.cursor()
    created = 0
    for eid, grp in df.groupby("EnsaioId"):
        g = grp.reset_index(drop=True)
        sample_label = str(g.iloc[0]["line"]) if "line" in g.columns else f"amostra-{eid}"
        is_blank = 1 if str(sample_label).strip().lower() in ("water", "água", "agua", "branco") else 0
        # etiquetas (valor da 1ª linha de cada ensaio)
        labels = {}
        for lc in label_cols:
            v = g.iloc[0][lc]
            if pd.isna(v):
                continue
            labels[lc.lower()] = (float(v) if pd.to_numeric(pd.Series([v]), errors="coerce").notna().all()
                                  else str(v))
        avg = g[led_avg_cols].mean().tolist() if led_avg_cols else [None] * 6
        std = g[led_std_cols].mean().tolist() if led_std_cols else [None] * 6
        cur.execute(
            """INSERT INTO ensaios (created_at, cycle, sample_no, sample_name, is_blank,
               labels_json, num_samples, block_size, raw_path, led_avg, led_std, saturated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(timespec="seconds"), cycle, created + 1,
             sample_label, is_blank, json.dumps(labels), None, None, None,
             json.dumps([None if x is None or x != x else float(x) for x in avg]),
             json.dumps([None if x is None or x != x else float(x) for x in std]),
             json.dumps([None] * 6)))
        new_id = cur.lastrowid
        for bidx, (_, row) in enumerate(g.iterrows()):
            avgb = [float(row[c]) for c in led_avg_cols] if led_avg_cols else [None] * 6
            stdb = [float(row[c]) for c in led_std_cols] if led_std_cols else [None] * 6
            cur.execute(
                "INSERT INTO blocos (ensaio_id, line, init_time, led_avg, led_std) VALUES (?,?,?,?,?)",
                (new_id, bidx, 0.0,
                 json.dumps([None if x is None or x != x else float(x) for x in avgb]),
                 json.dumps([None if x is None or x != x else float(x) for x in stdb])))
        created += 1
    conn.commit()
    conn.close()
    return created, cycle
