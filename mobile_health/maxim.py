# MicroPython library for different MAXIM health sensors.
# Author: github.com/stecrz
# Date: Jan 2021

import struct


class Sensor:
    def __init__(self, i2c, i2c_addr):
        if i2c_addr not in i2c.scan():
            raise OSError(19)
        self._i2c = i2c
        self._addr = i2c_addr

    def _read(self, reg, n=1) -> bytes:
        # Reads the value from the register <reg> (0-3), length <n> bytes.
        return self._i2c.readfrom_mem(self._addr, reg, n)

    def _write(self, reg, val: bytes):
        # Writes the given value <val> into register <reg> (0-3).
        self._i2c.writeto_mem(self._addr, reg, val)

    def _read_bit(self, reg, idx, n=1):
        # Returns one (<n>=1) specific bit <idx> (0 = LSB) from the register <reg>.
        return (int.from_bytes(self._read(reg, 1 + (idx+n-1)//8), 'big') >> idx) & ((1 << n) - 1)

    def _write_bit(self, reg, idx, bit, n=1):
        # Changes one (<n>=1) specific bit <idx> (0 = LSB) in the register <reg>.
        buf = bytearray(1 + (idx + n - 1) // 8)
        self._i2c.readfrom_mem_into(self._addr, reg, buf)
        for i in range(idx, idx+n):
            buf[i // 8] &= ~(1 << i % 8)
            buf[i // 8] |= ((bit & 1) << i % 8)
            bit >>= 1
        self._write(reg, buf)


class MAX30205(Sensor):
    # MAX30205 - Human Body Temperature Sensor
    NUM_FAULTS = (1, 2, 4, 6)

    def __init__(self, i2c, addr=0x48):
        super().__init__(i2c, addr)

    def _read_temp(self, reg) -> float:
        # Reads the value from register <reg>, parsed as a temperature (2 byte, two's complement).
        return struct.unpack('>h', self._read(reg, 2))[0] / 2**8 + self.ext_data_format_enabled * 64

    def _write_temp(self, reg, val: float):
        # Writes the given temperature <val> into register <reg> (0-3).
        self._write(reg, struct.pack('>h', round(val * 2**8)))

    @property
    def temperature(self):
        # Reads the temperature from the register. In case shutdown == True,
        # update_once() should be called previously in order to do a new reading.
        return self._read_temp(0x00)

    # Overtemperature Shutdown (OS) temperature settings:

    @property
    def os_temp_hyst(self):
        return self._read_temp(0x02)

    @os_temp_hyst.setter
    def os_temp_hyst(self, t):
        self._write_temp(0x02, t)

    @property
    def os_temp_os(self):
        return self._read_temp(0x03)

    @os_temp_os.setter
    def os_temp_os(self, t):
        self._write_temp(0x03, t)

    # Configuration register (mainly for OS):

    def _read_config_bit(self, idx, **kw):
        # Reads one specific bit D0-D7 <idx> (0 = LSB) from the configuration register.
        return self._read_bit(0x01, idx, **kw)

    def _write_config_bit(self, idx, val, **kw):
        # Write one specific bit D0-D7 <idx> (0 = LSB) in the configuration register.
        self._write_bit(0x01, idx, val, **kw)

    @property
    def shutdown(self):
        return self._read_config_bit(0)

    @shutdown.setter
    def shutdown(self, v):
        # Puts the device in shutdown modeto reduce supply current to 3.5μA or less.
        # I²C remains active and master is still able to read registers (old values).
        # update_once() can be called to update the temperature register during sleep.
        self._write_config_bit(0, v)

    @property
    def os_mode_intr(self):
        return self._read_config_bit(1)

    @os_mode_intr.setter
    def os_mode_intr(self, v):
        # Sets the Overtemperature Shutdown output operation mode: In any case,
        # the OS is activated when temp > temp_os.
        # - True = interrupt mode = OS turned off on read operation (of any register).
        # - False = comparator/themostat mode = OS turned off when temp < temp_hyst.
        self._write_config_bit(1, v)

    @property
    def os_active_high(self):
        return self._read_config_bit(2)

    @os_active_high.setter
    def os_active_high(self, v):
        # Sets the OS output polarity (True = active high, False = active low).
        self._write_config_bit(2, v)

    @property
    def os_delay(self):
        return self.NUM_FAULTS[self._read_config_bit(3, n=2)]  # bits 3 + 4

    @os_delay.setter
    def os_delay(self, num_faults):
        # Sets the number of faults (44-50ms per conversion) required to trigger an OS condition.
        self._write_config_bit(3, self.NUM_FAULTS.index(num_faults), n=2)

    @property
    def ext_data_format_enabled(self):
        return self._read_config_bit(5)

    @ext_data_format_enabled.setter
    def ext_data_format_enabled(self, v):
        # If set to True, the extended data format is used for the temperature registers,
        # which increases the upper temperature limit by 64°C.
        self._write_config_bit(5, v)

    @property
    def timeout_enabled(self):
        return not self._read_config_bit(6)

    @timeout_enabled.setter
    def timeout_enabled(self, v):
        # If set to True, the I²C bus will be automatically reset if it is low for 50ms or more.
        self._write_config_bit(6, not v)

    def update_once(self):  # ONE-SHOT
        # This function can be called when the sensor is in shutdown mode. It will cause the
        # sensor to wake up and update the temperature register before falling back asleep.
        self._write_config_bit(7, True)

    def reset(self):
        self._write(0x01, b'\x00')
        self.os_temp_os = 80
        self.os_temp_hyst = 75


def elem2idx(e, elems, idx=True):
    # idx = If True, e is interpreted as an index if not found in elems.
    if e not in elems or e is None:
        if idx and isinstance(e, int) and 0 <= e < len(elems):
            return e  # use as index
        raise ValueError("possible params: " + str([x for x in elems if x is not None]))
    return elems.index(e)


class MAX30100(Sensor):
    # MAX30100 - Pulse Oximeter and Heart-Rate Sensor IC for Wearable Health
    INTR_ENB = (None,)*4 + ("SPO2_RDY", "HR_RDY", "TEMP_RDY", "A_FULL")
    INTR = ("PWR_RDY",) + INTR_ENB[1:]
    MODES = (None, None, "HR", "SPO2") + (None,)*4
    SAMPLE_RATES = [50, 100, 167, 200, 400, 600, 800, 1000]
    PULSE_WIDTHS = [200, 400, 800, 1600]
    LED_CURRENTS = [0.0, 4.4, 7.6, 11.0, 14.2, 17.4, 20.8, 24.0, 27.1, 30.6, 33.8, 37.0, 40.2, 43.6, 46.8, 50.0]

    def __init__(self, i2c, addr=0x57):
        super().__init__(i2c, addr)

    def setup(self, mode="SPO2", led_cc=11.0, sample_rate=100, pulse_width=1600):
        # Method for performing some basic initializations (could be done manually).
        self.mode = mode
        self.led_cc_ir = led_cc
        self.led_cc_red = led_cc
        self.spo2_sample_rate = sample_rate
        self.led_pulse_width = pulse_width

    def reset(self):
        # Clears everything to the default state.
        self._write_bit(0x06, 6, 1)

    def values(self, n=1):
        # Returns a tuple containing the measured value of (1.) the IR and (2.) the RED led.
        # Since the FIFO contains 16 readings these values will not be the current but oldest ones.
        # If <n> is greated than 1, the result will be a tuple (ir1, red1, ir2, red2, ..., irN, ledN)
        return struct.unpack('>'+'HH'*n, self._read(0x05, n=4*n))  # reg doesnt auto-inc => read(4) reads 4x

    def interrupt_enable(self, intr, enable=1):
        # Enables or disables a certain interrupt <intr> specified by its name (e.g. SPO2_RDY) or index (e.g. 4).
        self._write_bit(0x01, elem2idx(intr, self.INTR_ENB), enable)
        # return self.interrupted(intr)  # read current interrupt status (to clear status register)  # TODO req?
        # return self._read_bit(0x00, elem2idx(intr, self.INTR))

    def interrupt_disable(self, intr):
        return self.interrupt_enable(intr, 0)

    def interrupt_enabled(self, intr):
        # Returns whether a certain interrupt is currently enabled.
        return self._read_bit(0x01, elem2idx(intr, self.INTR_ENB))

    def interrupted(self):
        # Returns the current status of a all interrupts (cleared afterwards).
        status = self._read(0x00)[0]
        return {name: status >> i & 1 for i, name in enumerate(self.INTR) if name is not None}

    @property
    def ptr_write(self):
        return self._read_bit(0x02, 0, n=4)  # where next sample is stored (auto inc on w)

    @property
    def ptr_read(self):
        return self._read_bit(0x04, 0, n=4)  # where next sample is read from by I²C (auto inc on r)

    @ptr_read.setter
    def ptr_read(self, val):
        # Sets the 4-bit-pointer, where the next value should be read from. Auto-inc. on read op.
        self._write_bit(0x04, 0, val, n=4)

    def num_samples_available(self):
        # Returns the number of samples in the circular FIFO queue that have not been read.
        return (self.ptr_write + 16 - self.ptr_read) % 16

    def num_samples_lost(self):
        # Returns the FIFO overflow counter, i. e., number of samples that could not
        # be pushed no to the FIFO because it is full. Reset to 0 when FIFO is read.
        return self._read_bit(0x03, 0, n=4)

    @property
    def shutdown(self):
        return self._read_bit(0x06, 7)

    @shutdown.setter
    def shutdown(self, v):
        # Puts the device in power-save mode (1) or wakes it up (0).
        self._write_bit(0x06, 7, v)

    @property
    def mode(self):
        num = self._read_bit(0x06, 0, n=3)
        return num if self.MODES[num] is None else self.MODES[num]

    @mode.setter
    def mode(self, m):
        # Changes the device mode to "HR"(=2) only enabled or "SPO2" (=3) enabled.
        self._write_bit(0x06, 0, elem2idx(m, self.MODES), n=3)

    @property
    def spo2_high_resolution(self):
        # Returns whether high resolution is enabled (= 16-bit ADC res. with 1.6ms LED pulse width)
        return self._read_bit(0x07, 6)

    @spo2_high_resolution.setter
    def spo2_high_resolution(self, bit):
        self._write_bit(0x07, 6, bit)

    @property
    def spo2_sample_rate(self):
        return self.SAMPLE_RATES[self._read_bit(0x07, 2, n=3)]

    @spo2_sample_rate.setter
    def spo2_sample_rate(self, sr):
        # Sets the sampliung rate <sr> = samples per second (sample = 1x IR + 1x RED pulse).
        # pulse width limited by sample rate (otherwise highest sample rate is stored).
        self._write_bit(0x07, 2, elem2idx(sr, self.SAMPLE_RATES), n=3)

    @property
    def led_pulse_width(self):
        return self.PULSE_WIDTHS[self._read_bit(0x07, 0, n=2)]

    @led_pulse_width.setter
    def led_pulse_width(self, pw):
        # Sets the pulse width <pw> (in µs) for both IR and RED led.
        self._write_bit(0x07, 0, elem2idx(pw, self.PULSE_WIDTHS), n=2)

    @property
    def led_cc_red(self):
        return self.LED_CURRENTS[self._read_bit(0x09, 4, n=4)]

    @led_cc_red.setter
    def led_cc_red(self, curr):
        # Current control for the RED led, where <curr> is the typ. current in mA (or index 0 -16)
        self._write_bit(0x09, 4, elem2idx(curr, self.LED_CURRENTS, idx=False), n=4)

    @property
    def led_cc_ir(self):
        return self.LED_CURRENTS[self._read_bit(0x09, 0, n=4)]

    @led_cc_ir.setter
    def led_cc_ir(self, curr):
        # Current control for the IR led, where <curr> is the typ. current in mA (or index 0 -16)
        self._write_bit(0x09, 0, elem2idx(curr, self.LED_CURRENTS, idx=False), n=4)

    def update_temperature(self):
        self._write_bit(0x06, 3, 1)

    @property
    def temperature(self):
        temp = struct.unpack('bB', self._read(0x16, 2))
        return temp[0] + (temp[1] & 0x0f) / 16

    @property
    def part_id(self):
        # Returns a int-tuple (revision ID, part ID)
        res = self._read(0xFE, 2)
        return res[0], res[1]
