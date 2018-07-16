# POWER SAVING METHODS
# EDIT: INTR ON ADXL362 NOT WORKING

from utime import sleep_ms


def deepsleep():  # TODO >71min sleep possible?
    # import machine
    # rtc = machine.RTC()
    # rtc.irq(trigger=rtc.ALARM0, wake=machine.DEEPSLEEP)
    # machine.deepsleep()

    # new version:
    import esp
    esp.deepsleep(500)  # possible to wake up after ... ms



def setup_motion_switch(spi, cs, freq=25, thresh_act=200, samp_act=200, thresh_inact=120, samp_inact=20, mrange=2):
    # Sets up a motion switch based on Analog Devices ADXL362 accelerometer to wake up from deepsleep.
    #
    # The ADXL362, operating at a frequency of <freq> Hz (in 12.5, 25, 50, 100, 200, 400), sets the INT2 pin
    # to HIGH if it detects a motion for at least <samp_act> samples. The motion is triggered by a
    # strength/acceleration greater than <tresh_act> mg (less = more sensitive) and is finished (no
    # motion detected anymore) when the strength falls back below <thresh_inact> mg for at least
    # <samp_inact> samples. <freq> is also known as output data rate ODR.
    #
    # Samples depend on frequency. E.g. when frequency is 100, this means there are 100 samples a second.
    # => Increasing frequency means you have to increase <samp_..> as well.
    # In wakeup mode (not used right now) frequency is always 6, meaning ~5-6 samples per second.
    #
    # Measurement range <mrange> is one of (2, 4, 8) g, where 2 ist the most sensitive (but smaller value
    # range).

    def write_reg(addr, val):  # <addr> specifies the register, <val> is the data of type int
        cs(0)
        spi.write(bytes((0x0A, addr, val)))
        cs(1)
        sleep_ms(1)  # just to be safe, not required

    # def read_reg(addr, length=1):
    #     cs(0)
    #     spi.write(bytes((0x0B, addr)))  # write_readinto instead?
    #     val = spi.read(length)  # sends 0x00 length times
    #     cs(1)
    #     return val

    write_reg(0x1F, 0x52)  # perform soft reset
    sleep_ms(1)  # ~0.5ms required after a soft reset

    write_reg(0x2C, 0b00010000 | (2, 4, 8).index(mrange) << 6 | (12.5, 25, 50, 100, 200, 400).index(freq))

    write_reg(0x20, thresh_act & 0xFF)  # TRESH_ACT_L
    write_reg(0x21, thresh_act >> 8 & 0b111)  # TRESH_ACT_H

    write_reg(0x22, samp_act)  # TIME_ACT (samples = time (s) * freq (Hz))

    write_reg(0x23, thresh_inact & 0xFF)  # TRESH_INACT_L
    write_reg(0x24, thresh_inact >> 8 & 0b111)  # TRESH_INACT_H

    write_reg(0x25, samp_inact)

    write_reg(0x27, 0b00111111)  # loop-mode motion detection, enable acst./inact. reference

    write_reg(0x2B, 0b01000000)  # default! map AWAKE bit to INT2 (gate of the switch), active=high (MSB)
    #write_reg(0x2A, 0b00010000)  # make ACITIVITY bit to INT1

    write_reg(0x2D, 0b00001010)  # def! measurement mode, wakeup mode
    #write_reg(0x2D, 0b00000110)  # measurement mode, autosleep mode (instead of wakeup mode)
    #write_reg(0x2D, 0b00101010)  # measurement, wakeup, ultra low noise


#spi = SPI(1, polarity=0, phase=0)
#cs = Pin(15, Pin.OUT)
#setup_motion_switch(spi, cs)

# from machine import Pin, I2C, SPI
# setup_motion_switch(SPI(1, polarity=0, phase=0), Pin(15, Pin.OUT),
#                     thresh_act=250, thresh_inact=150, samp_inact=30, samp_act=0, freq=100, mrange=2)
#
# # testin = Pin(12, Pin.IN)
# # testout = Pin(13, Pin.OUT)
# import display, time
# global oled
# oled = display.Display(I2C(-1, Pin(5), Pin(4)), 128, 64)
# oled.clear()
#
# # for i in range(50):
# #     testout(testin())
# #     oled.print(testin())
#
#
# inp = Pin(16, Pin.IN)
#
# v = 0
# tmr = time.ticks_ms()
# while True:
#     v_new = inp()
#     if v_new != v:
#         tmr_new = time.ticks_ms()
#         oled.println("was %d for %.1f s" % (v, round(time.ticks_diff(tmr_new, tmr) / 1000, 1)))
#         tmr = tmr_new
#         v = v_new
