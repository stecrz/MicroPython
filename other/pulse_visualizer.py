import ssd1306
import machine
import utime
from micropython import const

MAX_QUEUE_SIZE = const(8)  # number of last heart beats the bpm value is based on
DEFAULT_TRESHOLD = const(550)  # default treshold for the first beat


class PulseVisualizer:
    # """ displays the pulse, which is read from the ADC (sensor must be connected) on an oled oled. """

    def __init__(self, width, height, scl=5, sda=4):
        self._WIDTH = width
        self._HEIGHT = height
        self.oled = ssd1306.SSD1306_I2C(self._WIDTH, self._HEIGHT, machine.I2C(-1, machine.Pin(scl), machine.Pin(sda)))
        self.oled.fill(0)  # init (if sth drawn before)
        self.oled.show()
        self.last_y = 0  # recently drawn value (last on visible graph)

    def _append_value(self, y, dx=5):
        # """ appends the given y-value to the pulse graph on the oled oled by connecting the
        # new point to the last value with a line (dx = horizontal distance to last point). """
        self.oled.scroll(-dx, 0)  # move current graph to the left
        self.oled.framebuf.fill_rect(self._WIDTH-dx, 0, dx, self._HEIGHT, 0)  # clear last columns for connection
        self.oled.framebuf.line(self._WIDTH-dx, self.last_y, self._WIDTH-1, y, 1)  # draw connection line and new y
        self.last_y = y

    def update(self, adc_value, bpm):
        # """ updates the oled with the given value from the ADC (must be in range 0-1024!)"""
        # graph:
        y = adc_value*self._HEIGHT/1025  # transform 0-1024 to 0-height
        y = self._HEIGHT-1 - y  # invert value (because oled top is 0 (inverted y axis))
        self._append_value(y)  # takes 85ms on 128x64
        # bpm value:
        self.oled.framebuf.fill_rect(0, 0, 8*3, 9, 1)
        self.oled.text("%3d" % bpm, 0, 1, 0)
        # make changes visible:
        self.oled.show()


class PulseSensor:
    def __init__(self, max_bpm=280, min_bpm=30, min_diff=30, max_speed_change=20):
        # """ @:param max_bpm     maximum number of beats per minute (otherwise invalid detection)
        #     @:param min_bpm     minimum -"-
        #     @:param min_diff    peak and trough have to have a difference of at least _ (0-1023) per beat
        #     @:param max_speedup heart beat length can change (increase/decrease) by a maximum of _ precent (%) """

        self._MAX_IBH = 60000/min_bpm         # maximum interval between peaks/highs of two heartbeats (fixed)
        self._MIN_IBH = 60000/max_bpm         # minimum -"-
        self._MIN_DIFF = min_diff             # minimum amplitude (difference between highest and lowest)
        self._MAX_SPC = max_speed_change/100  # maximum speed change (speedup/slowdown) per beat

        self.adc = machine.ADC(0)  # analog to digital converter
        self.value = 0             # last adc value (0-1024)
        self.bpm = 0               # current heart rate

        self._treshold = None  # treshold (mean of high and low)
        self._highest = None   # adc value of last peak (maximum wave point)
        self._lowest = None    # adc value of last trough (minimum -"-)
        self._tpb = None       # start time/ticks of previous beat (when threshold is exceeded for the first time)
        self._dpb = None       # list of durations of previous beats (ms)
        self.peak = None       # pulse - set to True if treshold is currently exceeded (heart beat)
        self.reset()           # -> initialize above attributes

    def reset(self):
        self.bpm = 0
        self._treshold = DEFAULT_TRESHOLD
        self._highest = DEFAULT_TRESHOLD
        self._lowest = DEFAULT_TRESHOLD
        self._tpb = utime.ticks_ms()
        self._dpb = None
        self.peak = False

    def update(self):
        self.value = self.adc.read()

        tcb = utime.ticks_ms()                       # time/ticks of current read
        tpb_diff = utime.ticks_diff(tcb, self._tpb)  # time since last beat

        if self.value < self._lowest:
            self._lowest = self.value
        elif self.value > self._highest:
            self._highest = self.value

        if tpb_diff >= self._MAX_IBH:  # no beat detected for too long
            self.reset()
        elif self.value < self._treshold:
            if self.peak:  # pulse ends
                self.peak = False
                # calculate threshold based on latest min/max value:
                self._treshold = max((self._highest-self._lowest)/2, self._MIN_DIFF) + self._lowest
                self._highest = self._treshold  # reset
                self._lowest = self._treshold  # reset
        else:  # treshold exceeded
            if self._dpb is None:  # first beat
                self._dpb = []  # create the list
                self._tpb = tcb  # start time of beat
                self.peak = True
            # check for new heart beat (avoid recognizing too fast)
            elif not self.peak and tpb_diff >= self._MIN_IBH and (not self._dpb or
                 (1-self._MAX_SPC)*self._dpb[-1] <= tpb_diff <= (1+self._MAX_SPC)*self._dpb[-1]):  # -> new beat
                self._tpb = tcb  # start time of beat
                self.peak = True  # pulse detected

                if len(self._dpb) >= MAX_QUEUE_SIZE:
                    del self._dpb[0]
                self._dpb.append(tpb_diff)  # add duration of previous beat

                self.bpm = round(60000 / (sum(self._dpb) / len(self._dpb)))  # calculate BPM value


sensor = PulseSensor()
oled = PulseVisualizer(128, 64)
led = machine.Pin(16, machine.Pin.OUT)

while True:
    sensor.update()
    oled.update(sensor.value, sensor.bpm)
    led.value(sensor.peak)
