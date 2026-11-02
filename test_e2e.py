# -*- coding: utf-8 -*-
"""Teste ponta-a-ponta em modo simulado (sem UI, sem hardware)."""
import os, tempfile, shutil
tmp = tempfile.mkdtemp()
os.environ["MININIR_DATA"] = tmp
os.environ["MININIR_DB"] = os.path.join(tmp, "test.db")
os.environ["MININIR_MOCK"] = "1"

import config as C
from storage import db
from analysis import qc, models
from hardware.instrument import Instrument

print("MOCK:", C.MOCK_HARDWARE, "| DB:", C.DB_PATH)

# 1) init + seed
db.init_db()
n = db.import_global_csv(C.SAMPLE_CSV, cycle="2025.02.12")
print(f"[seed] {n} ensaios importados; total={db.count_ensaios()}")

# 2) mock acquisition (varia por concentração)
inst = Instrument(mock=True)
inst.connect()
for conc in (0.0, 2.5, 5.0):
    acq = inst.acquire_sample(conc=conc, num_samples=1200)
    sat = qc.flag_saturation(acq["summary"]["avg"])
    eid = db.save_ensaio(dict(cycle="teste", series="T", conc=conc,
                              estadio="Estadio 2", descricao="e2e"), acq, saturated=sat)
    print(f"[acq] conc={conc} eid={eid} avg={[round(v,3) for v in acq['summary']['avg']]} sat={sat}")
inst.close()

# 3) dataset QC (deve marcar 1300/1600/1900 como SATURADO nos dados reais)
blocos = db.blocos_df(cycle="2025.02.12")
qc_df = qc.dataset_qc(blocos)
print("\n[QC conjunto 2025.02.12]")
print(qc_df.to_string(index=False))

# 4) export
out = os.path.join(tmp, "export.csv")
db.export_global_csv(out, cycle="2025.02.12")
print("\n[export] ->", out, "linhas:", sum(1 for _ in open(out)) - 1)

# 5) classificação (estádio) e regressão (Conc) no conjunto real
data = db.blocos_df(cycle="2025.02.12")
data["alvo"] = (data["Estadio"] != "Estadio 0").map({True: "Doente", False: "Controlo"})
print("\n[classificação: Doença] a treinar…")
res = models.run_classification(data, C.LED_COLS_AVG, "alvo", quick=True)
for name, r in res["results"].items():
    print("  ", name, "acc=%.3f" % r["accuracy"] if "accuracy" in r else r.get("error"))

print("\n[regressão: Conc] a treinar…")
rr = models.run_regression(data, C.LED_COLS_AVG, "Conc", quick=True)
for name, r in rr["results"].items():
    print("  ", name, "R2=%.3f" % r["r2"] if "r2" in r else r.get("error"))

shutil.rmtree(tmp, ignore_errors=True)
print("\nOK — teste ponta-a-ponta concluído.")
