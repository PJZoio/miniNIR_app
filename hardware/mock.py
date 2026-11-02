# -*- coding: utf-8 -*-
"""Backend simulado — permite correr toda a aplicação sem o Raspberry Pi.

Sintetiza sinais realistas, reproduzindo o comportamento observado nos dados
2025.02.12:
  - canais 1300/1600/1900 nm saturados num tecto ~2.667 V (planos, sem resposta)
  - canais 1400/1700/2100 nm com resposta dependente da amostra
Assim as páginas de QC e visualização mostram a história real da saturação.

O nível de saturação é controlável por `gains`, para que a app possa também
ilustrar o *antes/depois* do ajuste de ganhos descrito no procedimento.
"""
import time
import numpy as np
from config import REF, FULL_SCALE

# Nível-base por canal (V) com os ganhos atuais (3 canais no tecto)
_BASE = {1: 2.661, 2: 0.381, 3: 2.657, 4: 0.804, 5: 2.666, 6: 1.652}
# Sensibilidade do canal à concentração (V por unidade de conc normalizada)
_SENS = {1: 0.9, 2: 0.03, 3: 0.9, 4: -0.06, 5: 0.9, 6: -0.35}
# Ruído intra-aquisição por canal (desvio em V)
_NOISE = {1: 0.0006, 2: 0.0001, 3: 0.0008, 4: 0.0004, 5: 0.0006, 6: 0.0030}


class MockADC:
    """Gera aquisições em função da amostra atual e dos ganhos por canal."""

    def __init__(self):
        self._conc = 0.0
        self._gains = {c: 1.0 for c in range(1, 7)}  # 1.0 = configuração atual

    def set_sample(self, conc):
        self._conc = float(conc) if conc is not None else 0.0

    def set_gains(self, gains):
        """gains[c] < 1 reduz o ganho do canal c (tira-o do tecto)."""
        self._gains.update({int(k): float(v) for k, v in gains.items()})

    def open(self):
        return 0

    def read_raw(self, num_samples, num_channels, progress=None):
        rng = np.random.default_rng()
        vals = np.zeros((num_samples, num_channels + 1))
        cn = (self._conc - 2.5) / 2.5  # ~[-1,1] para conc em [0,5]
        for c in range(1, num_channels + 1):
            g = self._gains.get(c, 1.0)
            ideal = (_BASE[c] + _SENS[c] * cn) * g
            noise = rng.normal(0, _NOISE[c], num_samples)
            signal = ideal + noise
            # ceifamento físico no fundo de escala
            signal = np.clip(signal, 0.0, FULL_SCALE)
            vals[:, c] = signal
        dt = 1.0 / 7200.0
        vals[:, 0] = np.arange(num_samples) * dt
        if progress:
            # simula progresso sem bloquear
            for p in (0.25, 0.5, 0.75, 1.0):
                progress(p)
                time.sleep(0.03)
        return vals

    def close(self):
        pass


class MockMotion:
    def __init__(self):
        self.position = {1: 0, 2: 0, 3: 0}

    def open(self):
        pass

    def move_to(self, motor, position):
        time.sleep(0.05)
        self.position[int(motor)] = int(position)

    def close(self):
        pass
