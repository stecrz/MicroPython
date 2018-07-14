# Analog Devices ADXL362 accelerometer driver

from machine import SPI, Pin
import utime as time
import ustruct as struct


class ADXL362:
    def __init__(self, spi, cs_pin):
        self._spi = spi
        self._cs = Pin(cs_pin, Pin.OUT, value=1)
        self.reset()

        self.x = 0
        self.y = 0
        self.z = 0
        self.temp = 0  # °C
        self.sensitivity = 1  # mG/LSB (for converting value (bits) to G)

    def reset(self):  # soft reset clears all register settings, mode = standby
        self.write_reg(0x1F, 0x52)

    def set_activity_mode(self):
        self.write_reg(0x27, ord(self.read_reg(0x27)) & 0b111010 | 0b1)

    def set_fifo_mode(self, mode, store_temp=False):
        # """ :param mode:    0 = FIFO disabled
        #                     1 = oldest saved mode
        #                     2 = stream mode
        #                     3 = triggered mode
        #     :param store_temp: True = temperature saved in FIFO (together with x,y,z)"""
        self.write_reg(0x28, ord(self.read_reg(0x28)) & 0b11111000 | mode | (store_temp << 2))

    def set_measurement_mode(self, measurement=True):  # measurement or standby mode?
        self.write_reg(0x2D, ord(self.read_reg(0x2D)) & 0b11111100 | (0 if not measurement else 0b10))

    def set_measurement_range(self, range=2, odr=100, half_bw=True):
        # range = 2,4,8 g (lower -> more accurate because 12 bit only)
        # odr = output data rate in hertz, possible values:
        range_bits = (2, 4, 8).index(range)
        odr_bits = (12.5, 25, 50, 100, 200, 400).index(odr)
        self.write_reg(0x2C, range_bits<<6 | half_bw<<4 | odr_bits)

    def set_intmap1(self, map_activity, active_low=False):
        self.write_reg(0x2A, active_low<<7 | map_activity<<4)

    def update(self):  # main function for reading x, y, z and temperature
        x, y, z, t = struct.unpack('<hhhh', self.read_reg(0x0E, 8))
        self.temp = t * 0.065
        self.x = x * self.sensitivity
        self.y = y * self.sensitivity
        self.z = z * self.sensitivity

    def write_reg(self, addr, *val):  # <addr> specifies the register
        self._cs(0)
        self._spi.write(bytes((0x0A, addr) + val))
        self._cs(1)
        time.sleep_ms(1)  # ~0.5ms required

    def read_reg(self, addr, length=1):
        self._cs(0)
        self._spi.write(bytes((0x0B, addr)))  # write_readinto instead?
        val = self._spi.read(length)  # sends 0x00 length times
        self._cs(1)
        return val


adxl362 = ADXL362(SPI(1, polarity=0, phase=0), 15)
adxl362.set_measurement_mode()
adxl362.update()
print(adxl362.read_reg(0x29))
print(adxl362.x, adxl362.y, adxl362.z, adxl362.temp)
