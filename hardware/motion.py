# -*- coding: utf-8 -*-
"""Backend de movimento real (RP2040 / 3 motores de passo via série).

Reaproveita rp2040Serial.py. O firmware aceita `M1/M2/M3 <posição>` e
devolve OK/NOK. Import de `serial` é lazy.
"""
from config import SERIAL_PORT, BAUD_RATE

MOTOR_NAMES = {1: "X", 2: "Y", 3: "Z"}


class RealMotion:
    def __init__(self):
        self._rp = None

    def open(self):
        from rp2040Serial import rp2040  # lazy: precisa de pyserial + porta
        self._rp = rp2040(serial_port=SERIAL_PORT, baud_rate=BAUD_RATE)

    def move_to(self, motor, position):
        """motor em {1,2,3} (X,Y,Z); position em passos (micropassos)."""
        if self._rp is None:
            raise RuntimeError("Ligação ao RP2040 não aberta")
        self._rp.moveTo(motor, int(position))

    def close(self):
        if self._rp is not None:
            self._rp.close()
            self._rp = None
