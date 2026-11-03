# miniNIR — plataforma integrada

Aplicação única (Streamlit) para **adquirir**, **visualizar** e **modelar** os
ensaios do dispositivo miniNIR (6 LED, 1300–2100 nm) para rastreio de DRC.
Integra e reorganiza os scripts existentes do repositório `MiniNIR` num fluxo
articulado, com controlo de qualidade de saturação incorporado.

## O que faz

| Área | Descrição |
|---|---|
| **Home** | Visão geral + dados (Dataset fundido aqui): **filtros** por aplicação / ciclo / data / etiqueta, KPIs, **QC de saturação** (conjunto ou por ensaio), gráfico de resposta, tabela e **export/import `Global.csv`**. |
| **① Aquisição** | Novos ensaios: escolhe **aplicação** e **ciclo** (botão «novo», numeração automática), preenche as **etiquetas configuráveis** da aplicação (p. ex. creatinina/ureia/albumina/estádio na DRC), toggle de **branco**, slider de **réplicas**, e vê o sinal por canal **com QC de saturação em tempo real**. Pré-visualização do módulo de **seringas** (análise automática). |
| **② Ciclo** | Acompanha a ronda: **última leitura**, **comparação** de leituras, métricas (amostras / réplicas / observações / variáveis), resposta dos canais por etiqueta e QC. |
| **④ Modelos** | Classificação e regressão com **CV agrupada por amostra** (sem data leakage), **multi-seleção de ciclos**, alvos a partir das **etiquetas**, **treino + validação** lado a lado e **guardar o melhor modelo** (base para a futura Inferência). |

### Modelo de dados: aplicações + etiquetas
Cada **aplicação** (DRC, Biodiesel, Genérica…) define as **etiquetas** do formulário
(nome, tipo numérico/categórico, unidade, papel regressão/classificação). Um **ciclo**
é uma ronda de ensaios de uma aplicação; cada **ensaio** guarda os valores das
etiquetas. Assim a mesma app serve soro/DRC, biodiesel, *flow* industrial, etc., sem
mudar o esquema. As etiquetas da DRC usam os intervalos da folha 'Análise estatística'.

## Modo simulado vs hardware real

- **Simulado (por defeito):** corre em qualquer computador, sem o Pi. Sintetiza
  sinais realistas (três canais saturados — 1300/1600/1900 nm — como nos dados
  reais). Ideal para demonstração.
- **Hardware real (no Raspberry Pi):** arrancar com `MININIR_MOCK=0`.

## Como correr

```bash
pip install -r requirements.txt
streamlit run Home.py
```

No Raspberry Pi, ligado ao equipamento:

```bash
# instalar também: pip install pyserial
MININIR_MOCK=0 streamlit run Home.py
# aceder de outro PC na rede: http://<ip-do-pi>:8501
```

Na primeira execução, a base de dados (SQLite) é semeada com os dados de
exemplo em `sample_data/` para a app ficar logo navegável.

## Variáveis de ambiente

| Variável | Omissão | Efeito |
|---|---|---|
| `MININIR_MOCK` | `1` | `0` usa o hardware real (ADC + motores). |
| `MININIR_DB` | `data/mininir.db` | Caminho da base SQLite. |
| `MININIR_DATA` | `data/` | Pasta de dados (BD + CSV brutos). |
| `MININIR_SERIAL` | `/dev/ttyACM0` | Porta série do RP2040. |

## Estrutura

```
Home.py                 # entrada Streamlit (visão geral + dados + export/import)
pages/                  # 1 Aquisição · 2 Ciclo · 4 Modelos
config.py               # equipamento, canais LED, QC, caminhos, tema
services.py             # instrumento + BD partilhados (cache)
ui.py                   # tema e gráficos (Plotly)
hardware/               # camada de hardware (isolada e testável)
  ADS1263.py, MiniNirAdc.py, rp2040Serial.py   # reaproveitados do repo
  adc.py, motion.py     # wrappers do hardware real
  mock.py               # backend simulado
  instrument.py         # orquestrador (escolhe real/mock)
storage/db.py           # SQLite (aplicações/ciclos/ensaios+etiquetas/blocos) + export/import
analysis/qc.py          # saturação / repetibilidade / resposta
analysis/models.py      # classificação + regressão (CV agrupada)
sample_data/            # Global.csv de exemplo (2025.02.12)
```

## Armazenamento

Fonte de verdade local em **SQLite** (um ficheiro, portátil, descarregável).
Export para `Global.csv` a qualquer momento. Se quiseres sincronizar com o
servidor MySQL da faculdade, é um passo adicional fácil de acrescentar
(mantém-se o mesmo esquema `ensaios`/`blocos` ↔ `tabelaEnsaios`/`dadosPLS`).

## Notas

- As "réplicas" por ensaio são os blocos de 600 amostras (6000/600 = 10),
  como no teu `splitDadosSQL.py`. Se quiseres réplicas como **novas pipetagens**,
  basta fazer várias aquisições da mesma amostra — o modelo agrupa na mesma.
- Para corridas pesadas de modelação (grelhas completas, procura de janelas
  FT-NIR), exporta o `Global.csv` e corre os scripts `_GROUPED` no portátil.

---

## Execução no Raspberry Pi (hardware real) — passo a passo

**1. Pré-requisitos do sistema (uma vez):**
```bash
sudo raspi-config        # Interface Options -> SPI -> Enable (necessário para o ADC)
sudo reboot
```
O utilizador deve pertencer aos grupos `spi` e `dialout` (acesso ao ADC e à porta série):
```bash
sudo usermod -aG spi,gpio,dialout $USER   # terminar sessão e voltar a entrar
```

**2. Dependências:**
```bash
pip install -r requirements.txt -r requirements-pi.txt
```
(Instala, além da app, `pyserial`, `spidev` e `RPi.GPIO`.)

**3. Ligações físicas:**
- HAT Waveshare ADS1263 encaixado no Pi (SPI0).
- RP2040 (motores) ligado por USB — confirmar a porta com `ls /dev/ttyACM*`
  (por omissão `/dev/ttyACM0`; mudar com `MININIR_SERIAL=/dev/ttyACM1`).

**4. Arrancar em modo real:**
```bash
MININIR_MOCK=0 streamlit run Home.py
```
Aceder de outro computador na rede: `http://<ip-do-pi>:8501`.

> Nota: o driver `ADS1263.py` usa a configuração de hardware `config_adc_hat.py`
> (Waveshare). Isto já está tratado — o `import` foi corrigido para não colidir
> com o `config.py` da aplicação.

**Resolução de problemas:**
- `No module named 'spidev'/'RPi.GPIO'` → falta `requirements-pi.txt`.
- `SPI not enabled` / erro de `/dev/spidev0.0` → SPI não ativo no `raspi-config`.
- Motores não respondem → porta série errada (`MININIR_SERIAL`) ou utilizador fora do grupo `dialout`.

## Ligação ao MySQL da faculdade (2ª etapa)

O SQLite local continua a ser a fonte de verdade; o MySQL seria um destino de
**sincronização** (envio dos ensaios/blocos). Para o ligar será preciso:

1. **Credenciais:** copiar `sql_config.py.example` para `sql_config.py` e preencher
   `host`, `user`, `passwd`, `db` (o ficheiro está no `.gitignore`).
2. **Cliente MySQL:** `pip install PyMySQL` (ou `mysqlclient`, que precisa de
   `sudo apt install default-libmysqlclient-dev`).
3. **Acesso de rede:** o Pi/portátil tem de alcançar o servidor (rede da
   faculdade ou VPN); confirmar host/porta (3306) e firewall.
4. **Tabelas no servidor:** `tabelaEnsaios` e `dadosPLS` (as mesmas dos scripts
   originais) — mapeiam diretamente para os `ensaios`/`blocos` da app.
5. **Módulo de sincronização:** a acrescentar (`storage/mysql_sync.py`) com uma
   função "enviar ensaio -> MySQL", chamada opcionalmente após cada aquisição ou
   em lote. Fica para quando confirmares o esquema e as credenciais com o teu
   professor.
