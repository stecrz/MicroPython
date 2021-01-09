# Example for reading Heart Rate Sensor MAX30100 in MicroPython / ESP8266

import machine
import maxim
import time

i2c = machine.I2C(-1, scl=machine.Pin(5), sda=machine.Pin(4))


def example_max30100():
    hr = maxim.MAX30100(i2c)
    hr.reset()  # set to default state in case sensor already started
    hr.setup(mode="SPO2", led_cc=11.0, sample_rate=100, pulse_width=1600)
    # additional/optional settings (see sensors.py and datasheet) examples:
    #hr.interrupt_enable("A_FULL")
    #hr.shutdown = 1

    # Example 1: IR and RED led value only
    while True:
        buf = hr.values(n=16)
        for i in range(0, len(buf), 2):
            print("%02d  |  IR: %05d  |  RED: %05d" % (i // 2, buf[i], buf[i+1]), end="\r")
            time.sleep_ms(100)

    # Example 2: ID led + RED led + temperature
    #while True:
    #    ir, red = hr.values()
    #    hr.update_temperature()
    #    print(" IR: %05d   RED: %05d   Temp.: %05.1f \xB0C" % (ir, red, hr.temperature), end="\r")


def example_max30205():
    temp = maxim.MAX30205(i2c)
    # additional/optional settings (documented in sensors.py and MAX30205 datasheet):
    #temp.os_mode_intr = False
    #temp.os_active_high = False
    #temp.os_temp_os = 38.0
    #temp.os_temp_hyst = 36.0
    #temp.os_delay = 1
    #temp.ext_data_format_enabled = False
    #temp.timeout_enabled = True
    #temp.shutdown = False

    while True:
        print(" Temp.: %05.1f \xB0C" % temp.temperature, end="\r")


if __name__ == "__main__":
    example_max30100()
