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

db.init_db()
n, cyc = db.import_global_csv(C.SAMPLE_CSV, application="DRC", cycle="DRC-exemplo")
print(f"[seed] {n} ensaios -> {cyc}; apps={db.list_applications()}")

inst = Instrument(mock=True); inst.connect()
newc = db.create_cycle("DRC")
for conc in (0.0, 2.5, 5.0):
    acq = inst.acquire_sample(conc=conc, num_samples=1200)
    sat = qc.flag_saturation(acq["summary"]["avg"])
    eid, sno = db.save_ensaio(newc, {"creatinina": conc, "estadio": "Estadio 2"},
                              acq, saturated=sat)
    print(f"[acq] conc={conc} -> ensaio {eid} amostra {sno}")
inst.close()

blocos = db.blocos_df(cycles=["DRC-exemplo"])
print("\n[QC]\n" + qc.dataset_qc(blocos).to_string(index=False))

blocos["__alvo__"] = (blocos["estadio"].astype(str) != "Estadio 0").map({True: "Doente", False: "Controlo"})
rc = models.run_classification(blocos, C.LED_COLS_AVG, "__alvo__", quick=True)
for k, v in rc["results"].items():
    print("  clf", k, ("acc=%.3f treino=%.3f" % (v["accuracy"], v["train_accuracy"])) if "accuracy" in v else v.get("error"))
rr = models.run_regression(blocos, C.LED_COLS_AVG, "conc", quick=True)
for k, v in rr["results"].items():
    print("  reg", k, ("R2=%.3f treino=%.3f" % (v["r2"], v["train_r2"])) if "r2" in v else v.get("error"))

shutil.rmtree(tmp, ignore_errors=True)
print("\nOK — teste ponta-a-ponta concluído.")
