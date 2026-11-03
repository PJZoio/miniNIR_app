# -*- coding: utf-8 -*-
"""
Configuração central da aplicação miniNIR.

Tudo o que é específico do equipamento ou do ambiente vive aqui, para que
a mesma aplicação corra:
  - no Raspberry Pi, ligada ao hardware real  (MOCK_HARDWARE = False)
  - em qualquer computador, em modo simulado   (MOCK_HARDWARE = True)

As variáveis podem ser sobrepostas por ambiente, p. ex.:
    MININIR_MOCK=0  streamlit run app/Home.py      # força hardware real
    MININIR_DB=/caminho/para/mininir.db
"""
import os
from pathlib import Path

# ----------------------------------------------------------------------------
# Modo de hardware
# ----------------------------------------------------------------------------
# Por defeito simula o hardware. No Raspberry Pi, definir MININIR_MOCK=0.
MOCK_HARDWARE = os.environ.get("MININIR_MOCK", "1") not in ("0", "false", "False")

# ----------------------------------------------------------------------------
# Aquisição
# ----------------------------------------------------------------------------
REF = 5.22              # Tensão de referência do ADC (igual ao código original)
NUM_SAMPLES = 6000      # Amostras por aquisição
NUM_CHANNELS = 6        # Canais LED usados
BLOCK_SIZE = 600        # Amostras por bloco -> NUM_SAMPLES/BLOCK_SIZE blocos ("linhas")
ADC_RATE = "ADS1263_7200SPS"

# Porta série do RP2040 (motores)
SERIAL_PORT = os.environ.get("MININIR_SERIAL", "/dev/ttyACM0")
BAUD_RATE = 230400

# ----------------------------------------------------------------------------
# Metadados dos canais LED  (nominal; pico real por datasheet entre parênteses)
# ----------------------------------------------------------------------------
LED_CHANNELS = [
    {"idx": 1, "nominal": 1300, "chip": "Lms13LED", "peak_um": 1.34, "fwhm": 90},
    {"idx": 2, "nominal": 1400, "chip": "Lms14LED", "peak_um": 1.44, "fwhm": 105},
    {"idx": 3, "nominal": 1600, "chip": "Lms16LED", "peak_um": 1.67, "fwhm": 140},
    {"idx": 4, "nominal": 1700, "chip": "Lms17LED", "peak_um": 1.75, "fwhm": 170},
    {"idx": 5, "nominal": 1900, "chip": "Lms19LED", "peak_um": 1.95, "fwhm": 145},
    {"idx": 6, "nominal": 2100, "chip": "Lms21LED", "peak_um": 2.13, "fwhm": 240},
]
LED_COLS_AVG = [f"LED{c['idx']}_avg" for c in LED_CHANNELS]
LED_COLS_STD = [f"LED{c['idx']}_std" for c in LED_CHANNELS]
LED_LABELS = [f"{c['nominal']} nm" for c in LED_CHANNELS]

# ----------------------------------------------------------------------------
# Controlo de qualidade / saturação
# ----------------------------------------------------------------------------
FULL_SCALE = 2.667          # Tecto observado nos dados 2025.02.12 (V)
SAT_FRACTION = 0.90         # >= 90% do fundo de escala => suspeita de saturação
TARGET_HIGH = 0.85          # alvo: picos abaixo de 85% do fundo de escala
RESPONSE_MIN_PCT = 0.5      # resposta entre amostras < 0.5% da média => "sem resposta"

# ----------------------------------------------------------------------------
# Estádios KDIGO (ordem canónica)
# ----------------------------------------------------------------------------
ESTADIOS = ["Estadio -1", "Estadio 0", "Estadio 1", "Estadio 2",
            "Estadio 3", "Estadio 4", "Estadio 5"]

# ----------------------------------------------------------------------------
# Aplicações e etiquetas (metadados configuráveis por tipo de ensaio)
# ----------------------------------------------------------------------------
# Cada aplicação define as ETIQUETAS que o formulário de Aquisição mostra.
# Campos de etiqueta: key, label, type ('numeric'|'categorical'),
# unit, role ('regression'|'classification'|'descriptive'), options (categóricas).
# Intervalos/unidades da DRC confirmados na folha 'Análise estatistica' do xlsx.
APPLICATIONS = {
    "DRC": [
        {"key": "creatinina", "label": "Creatinina", "type": "numeric",
         "unit": "mg/dL", "role": "regression", "min": 0.7, "max": 7.1},
        {"key": "ureia", "label": "Ureia", "type": "numeric",
         "unit": "mg/dL", "role": "regression", "min": 17.0, "max": 255.3},
        {"key": "albumina", "label": "Albumina", "type": "numeric",
         "unit": "g/dL", "role": "regression", "min": 2.5, "max": 4.8},
        {"key": "estadio", "label": "Estádio KDIGO", "type": "categorical",
         "unit": "", "role": "classification", "options": ESTADIOS},
    ],
    "Biodiesel": [
        {"key": "teor_ester", "label": "Teor de éster (FAME)", "type": "numeric",
         "unit": "%", "role": "regression"},
        {"key": "origem", "label": "Origem/tipo", "type": "categorical",
         "unit": "", "role": "classification", "options": []},
    ],
    "Genérica": [
        {"key": "concentracao", "label": "Concentração", "type": "numeric",
         "unit": "", "role": "regression"},
    ],
}
DEFAULT_APPLICATION = "DRC"

# ----------------------------------------------------------------------------
# Armazenamento
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent


def _resolve_data_dir():
    """Pasta de dados gravável. Usa 'data/' na app (Pi/local); se for só de
    leitura (ex.: Streamlit Cloud), cai para uma pasta temporária gravável."""
    env = os.environ.get("MININIR_DATA")
    if env:
        return Path(env)
    candidate = BASE_DIR / "data"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        t = candidate / ".writetest"
        t.write_text("x"); t.unlink()
        return candidate
    except Exception:
        import tempfile
        return Path(tempfile.gettempdir()) / "mininir_data"


DATA_DIR = _resolve_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("MININIR_DB", DATA_DIR / "mininir.db"))

SAMPLE_CSV = BASE_DIR / "sample_data" / "2025.02.12-miniNir_solucoes_compostas-Global.csv"

# Formato do CSV compatível com os teus scripts de modelação
CSV_SEP = ";"
CSV_DECIMAL = ","

# ----------------------------------------------------------------------------
# Aspeto
# ----------------------------------------------------------------------------
PALETTE = {
    "1300 nm": "#4C72B0", "1400 nm": "#55A868", "1600 nm": "#C44E52",
    "1700 nm": "#8172B3", "1900 nm": "#CCB974", "2100 nm": "#64B5CD",
}
ACCENT = "#1F3A5F"

# ----------------------------------------------------------------------------
# Bootstrap de paths (para reaproveitar ADS1263/MiniNirAdc/rp2040Serial e
# para que as páginas Streamlit encontrem os módulos do projeto)
# ----------------------------------------------------------------------------
import sys as _sys
for _p in (str(BASE_DIR), str(BASE_DIR / "hardware")):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)
