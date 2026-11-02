# -*- coding: utf-8 -*-
"""Backend de ADC real (Raspberry Pi + HAT Waveshare ADS1263).

Reaproveita MiniNirAdc.py do repositório original. Os imports do hardware
são feitos dentro dos métodos (lazy), para que o módulo possa ser importado
em qualquer máquina sem o HAT instalado.
"""
import time
import numpy as np
from config import REF, ADC_RATE


class RealADC:
    def __init__(self):
        self._adc = None

    def open(self):
        from ADS1263 import ADS1263  # lazy: só existe no Pi
        self._adc = ADS1263()
        if self._adc.ADS1263_init_ADC1(ADC_RATE) == -1:
            raise RuntimeError("Falha a inicializar o ADS1263")
        self._adc.ADS1263_SetMode(0)

    def read_raw(self, num_samples, num_channels, progress=None):
        """Devolve ndarray (num_samples, num_channels+1): [t, ch0..chN]."""
        vals = np.zeros((num_samples, num_channels + 1))
        t0 = time.time()
        for i in range(num_samples):
            for c in range(num_channels):
                raw = self._adc.ADS1263_GetChannalValue(c)
                if raw >> 31 == 1:
                    adcval = REF * 2 - raw * REF / 0x80000000
                else:
                    adcval = raw * REF / 0x7FFFFFFF
                vals[i, c + 1] = adcval
            vals[i, 0] = time.time() - t0
            if progress and (i % 200 == 0):
                progress(i / num_samples)
        if progress:
            progress(1.0)
        return vals

    def close(self):
        if self._adc is not None:
            self._adc.ADS1263_Exit()
            self._adc = None
