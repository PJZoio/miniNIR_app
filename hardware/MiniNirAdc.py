#!/usr/bin/python3
# -*- coding:utf-8 -*-
"""
A library to interface RPI to the High-Precision-AD-HAT
https://www.waveshare.com/18983.htm

"""

from ADS1263 import ADS1263
import time
import numpy as np

REF = 5.22          # Modify according to actual voltage
class MiniNirAdc():
    """
    Models an ADC HAT  connection
    """

    def __init__(self, num_samples=6000, num_channels=6):
        """
        Initializes the connection to the High-Precision-AD-HAT
        """
        self.adc = ADS1263()

    def open(self):
        """
        """
        if (self.adc.ADS1263_init_ADC1('ADS1263_7200SPS') == -1):
            return -1
       # exit()
        self.adc.ADS1263_SetMode(0)
        
        return 0

    def read(self, num_samples=6000, num_channels=6):
        if (num_samples < 1):
            num_samples = 1
        if (num_channels < 1):
            num_channels = 1
        elif (num_channels > 10):
            num_channels = 10
        adcValues = np.zeros((num_samples, num_channels + 1))

        time_start = time.time()
        for i in range(num_samples):
            for c in range(num_channels):
                raw = self.adc.ADS1263_GetChannalValue(c)
                if(raw>>31 ==1):
                    adcval = REF*2 - raw * REF / 0x80000000
                else:
                    adcval = raw * REF / 0x7fffffff   # 32bit
                adcValues[i, c + 1] = adcval

            adcValues[i, 0] = time.time() - time_start

        time_end = time.time()
        freq = num_samples / (time_end - time_start)
        print(f'frequency = {freq}')

        return adcValues

        
    def close(self):
        """
        To ensure we are properly closing our connection to the
        High-Precision-AD-HAT
        """
        self.adc.ADS1263_Exit()
        #self.ser.close()
 

if __name__ == '__main__':

    ad = MiniNirAdc()
    if (ad.open() == -1):
        print('Open Error')

    vals = ad.read(num_samples=60, num_channels=6)
