# -*- coding: utf-8 -*-
"""Orquestrador do instrumento miniNIR.

Expõe uma interface única à aplicação, escolhendo o backend real ou simulado
conforme `config.MOCK_HARDWARE`. Uma só instância deve ser partilhada na app
(ver app/services.py, via st.cache_resource).

Fluxo de um ensaio:
    posicionar (opcional) -> adquirir N amostras x 6 canais
    -> média/desvio por canal (resumo)
    -> dividir em blocos de BLOCK_SIZE (as "linhas"/réplicas)
"""
import numpy as np
import config as C


class Instrument:
    def __init__(self, mock=None):
        self.mock = C.MOCK_HARDWARE if mock is None else mock
        if self.mock:
            from hardware.mock import MockADC, MockMotion
            self.adc = MockADC()
            self.motion = MockMotion()
        else:
            from hardware.adc import RealADC
            from hardware.motion import RealMotion
            self.adc = RealADC()
            self.motion = RealMotion()
        self._open = False

    # ---- ligação -----------------------------------------------------------
    def connect(self):
        self.adc.open()
        try:
            self.motion.open()
        except Exception as e:  # motores são opcionais para adquirir
            self.motion_error = str(e)
        self._open = True

    def close(self):
        try:
            self.adc.close()
        finally:
            try:
                self.motion.close()
            except Exception:
                pass
        self._open = False

    @property
    def is_open(self):
        return self._open

    # ---- movimento ---------------------------------------------------------
    def move_to(self, motor, position):
        self.motion.move_to(motor, position)

    # ---- simulação (sem efeito no hardware real) ---------------------------
    def set_mock_sample(self, conc):
        if self.mock:
            self.adc.set_sample(conc)

    def set_mock_gains(self, gains):
        if self.mock:
            self.adc.set_gains(gains)

    # ---- aquisição ---------------------------------------------------------
    def acquire_raw(self, num_samples=None, num_channels=None, progress=None):
        ns = num_samples or C.NUM_SAMPLES
        nc = num_channels or C.NUM_CHANNELS
        return self.adc.read_raw(ns, nc, progress=progress)

    def acquire_sample(self, conc=None, num_samples=None, num_channels=None,
                       block_size=None, progress=None):
        """Aquisição completa + resumo + blocos. Devolve dict pronto a gravar."""
        ns = num_samples or C.NUM_SAMPLES
        nc = num_channels or C.NUM_CHANNELS
        bs = block_size or C.BLOCK_SIZE
        if self.mock and conc is not None:
            self.adc.set_sample(conc)

        raw = self.acquire_raw(ns, nc, progress=progress)   # (ns, nc+1)

        avg = np.mean(raw, axis=0)      # [t, ch1..chN]
        std = np.std(raw, axis=0)
        summary = {
            "avg": [float(avg[c + 1]) for c in range(nc)],
            "std": [float(std[c + 1]) for c in range(nc)],
        }

        blocks = []
        line = 0
        for i in range(0, raw.shape[0], bs):
            seg = raw[i:i + bs, :]
            a = np.mean(seg, axis=0)
            s = np.std(seg, axis=0)
            blocks.append({
                "line": line,
                "init_time": float(seg[0, 0]),
                "avg": [float(a[c + 1]) for c in range(nc)],
                "std": [float(s[c + 1]) for c in range(nc)],
            })
            line += 1

        return {"raw": raw, "summary": summary, "blocks": blocks,
                "num_samples": ns, "num_channels": nc, "block_size": bs}
