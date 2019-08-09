# MODULE FOR IO
from mcp23017 import MCP23017
from ssd1306_vert import SSD1306_I2C
from machine import Pin, I2C
import utime
from uasyncio import CancelledError, sleep_ms as d
import framebuf


_SCL = 5
_SDA = 4

_ADDR_MCP = 0x24

_RLY = {'BL': 0, 'HO': 1, 'ST': 2, 'IG': 3, 'LED': 4}  # MCP output pins for relays
_LED_G = 11   # green LED output pin
_LED_B = 12   # blue LED output pin
_BUZZER = 13  # buzzer output pin
_IN_SWITCH_BLF = 8  # input pin for brake light flash switch pin on MCP
_IN_PWR = 10  # input pin for powered status of the bike
_IN_TEST = 9  # test input button on mini board, can be used instead of BLF switch on bike for testing


async def blink(outfun, d1=150, d2=0, startval=1):
    # Calls <outfun> with value 1 and rests for <d1> ms, then calls with value 0 and rests for <d2> ms
    # if <startval> is 1. Otherwise (if <startval> is 0), <outfun> will be called with param 0 first.
    try:
        outfun(startval)
        await d(d1)
        outfun(1-startval)
    except CancelledError:  # make sure this coro always ends in the same state, even if task cancelled inbetween
        outfun(1-startval)
        return
    if d2:
        await d(d2)


class OLED(SSD1306_I2C):
    # Vertical OLED with possibility to blit an image or text using PBM files (without lines 1/2).
    # Note that attribute width saves height and attribute height stores width; use attributes w and h instead!

    _CHRS = {  # special chars unsupported by OS filenames
        ':': "COL", '.': "DOT", '?': "QM", '°': "DEG", '<': "LT", '>': "GT",
        '/': "SLH", "'": "QT", '&': "AND", 'ß': "SS"
    }
    _DIR_CHRS = "img/chr/"
    _DIR_IMGS = "img/ico/"

    def __init__(self, w, h, i2c):
        super().__init__(w, h, i2c, vertical=True)
        self.w = w
        self.h = h

    def clear(self):
        self.fill(0)
        self.show()

    def _align(self, x, y, w, h, xo, yo):
        if x is None:
            x = self.w / 2 - w / 2
        if y is None:
            y = self.h / 2 - h / 2
        return int(x + xo), int(y + yo)

    # Displays an image given as PBM file without header lines (must contain data only!).
    # - fn = the image name without '.pbm' ending and without 'img/' (but incl subdir).
    # - x/y = top-left coords (not given means centered horizontally/vertically on display)
    # - w/h = image width/height (use original resolution saved in line 3 if w/h not given)
    # - hoff/voff = additional offset added to x/y coord
    # Returns the blitted area (x, y, w, h)
    def img(self, fn, x=None, y=None, w=None, h=None, hoff=0, voff=0):
        with open(OLED._DIR_IMGS + fn, 'rb') as f:
            wh = f.readline().strip().split()

            if w is None:
                w = int(wh[0])
            if h is None:
                h = int(wh[1])
            x, y = self._align(x, y, w, h, hoff, voff)

            data = bytearray(f.read())
            self.blit(framebuf.FrameBuffer(data, w, h, framebuf.MONO_HLSB), x, y)
            return x, y, w, h

    def power(self, state):  # turns the OLED on/off
        if state:
            self.poweron()
        else:
            self.poweroff()

    @staticmethod
    def load_chr(c, size):  # -> (w, h, data)
        if c == ' ':
            return 2 if size == 12 else 4, 0, b''

        fn = OLED._DIR_CHRS + str(size) + '_'
        if 'A' <= c <= 'Z':
            fn += 'U_'
        elif 'a' <= c <= 'z':
            fn += 'L_'
            c = c.upper()
        elif c in OLED._CHRS:  # there are other spec chars as well
            c = OLED._CHRS[c]
        fn += c

        try:
            with open(fn, 'rb') as f:
                wh = f.readline().strip().split()
                return int(wh[0]), int(wh[1]), bytearray(f.read())
        except OSError:  # failed to load, probably unsupported letter
            return 2 if size == 12 else 4, 0, b''  # space

    @staticmethod
    def prefetch_chrs(s, size):
        return {c: OLED.load_chr(c, size) for c in s}

    # Displays the given text on the oled using graphics from 'chr' folder at the given coords (overlay, clear before!).
    # - x/y = top-left coords (not given means centered horizontally/vertically on display)
    # - hoff/voff = additional offset added to x/y coord (if you dont want to specify x/y, but move from center instead)
    # - hspace = horizontal spacing between chars (pixels)
    # - lspace = line distance (like in Word, e.g. 1.5 = 150% = half line space)
    # - align: 'j' = justify, 'c' = center, 'l' = left
    # - size = 12 or 50, see chr folder (not the real font size!)
    # - autobreak: if set to True, a linebreak will be inserted automatically whenever a line doesn't fit on the screen
    # - scroll: scroll old content up, clear lower area, blit text -> y will be set automatically
    # - buf: Normally chars will be fetched freshly each time to use as less RAM as possible. If you have enough RAM and
    #        you will use the same chars in multiple blit calls, you can prefetch them once will prefetch_chrs method.
    # Returns the blitted area (x, y, w, h)
    def text(self, txt, x=None, y=None, hoff=0, voff=0, hspace=1, lspace=1.0, align='c', size=12, autobreak=False, scroll=False, buf=None):
        lines = [[]]
        lwidth = [0]

        for c in txt:
            cbuf = None if c == '\n' else buf[c] if buf is not None and c in buf else OLED.load_chr(c, size)
            if c == '\n' or lwidth[-1] + cbuf[0] > self.w and autobreak:
                if lwidth[-1] > 0:
                    lwidth[-1] -= hspace  # remove last hspace
                lines.append([])
                lwidth.append(0)
            if c != '\n':
                lines[-1].append(cbuf)
                lwidth[-1] += cbuf[0] + hspace
        if lwidth[-1] > 0:
            lwidth[-1] -= hspace

        lheight = round(max(max(d[1] for d in l) for l in lines) * lspace)

        W = max(lwidth)
        H = lheight * len(lines)
        x, y = self._align(x, y, W, H, hoff, voff)
        if scroll:
            hscroll = H + 1
            self.scroll(0, -hscroll)
            self.fill_rect(0, self.h-hscroll, self.w, hscroll, 0)
            y = self.h - H

        for i in range(len(lines)):
            hs = hspace
            xi = x
            if align == 'j' and len(lines[i]) > 1:  # fit by increasing hspace
                hs += (W - lwidth[i]) / (len(lines[i]) - 1)
            elif align == 'c':
                xi += (W - lwidth[i]) / 2

            for w, h, b in lines[i]:
                if h > 0:
                    self.blit(framebuf.FrameBuffer(b, w, h, framebuf.MONO_HLSB), int(xi), y + lheight * i, 0)
                xi += w + hs

        return x, y, W, H

    def big(self, num, **kw):  # blit txt with large font
        return self.text(str(num), size=50, hspace=3, **kw)

    def println(self, txt):  # just calls text with setting for debug printing
        self.text(txt, x=0, size=12, align='l', autobreak=True, scroll=True)
        self.show()


class IOControl:
    # This class handles the cockpit (oled display, green and blue LED), the relay backpack,
    # input button and power status input.

    def __init__(self):
        i2c = I2C(-1, Pin(_SCL), Pin(_SDA))

        # declare MCP output/inputs:
        self._mcp = MCP23017(i2c, _ADDR_MCP, def_inp=0, def_val=0)  # default output, all low (no pullups)
        for pin in list(_RLY.values()) + [_LED_G, _LED_B, _BUZZER]:
            self._mcp.decl_output(pin)
        self._mcp.decl_input(_IN_SWITCH_BLF)
        self._mcp.pullup(_IN_SWITCH_BLF, True)  # additional pullup, default low
        self._mcp.decl_input(_IN_PWR)
        self._mcp.decl_input(_IN_TEST)
        self._mcp.pullup(_IN_TEST, True)  # additional pullup, default high!

        # last read states:
        self.pwr = None
        self.sw_pressed = None  # last switch state (from recent check): down?
        self.rly = {k: False for k in _RLY}  # current relais states (last set)

        self.oled = OLED(64, 128, i2c)
        self.off()

    def clear(self):
        self.pwr = False
        self.sw_pressed = False
        self.oled.clear()
        self.led_b(0)
        self.led_g(0)

    def off(self):  # turns off all outputs
        self.clear()
        self._mcp.output(_BUZZER, 0)
        for rly in _RLY.values():
            self._mcp.output(rly, 0)

    def led_g(self, val):  # turns green LED on/off; 1 = on, 0 = off
        self._mcp.output(_LED_G, val)

    def led_b(self, val):
        self._mcp.output(_LED_B, val)

    def set_rly(self, name, val):  # turns relay name (HO, BL, ST, IG, LED) on/off if <val> is True/False (1/0)
        if not isinstance(val, bool) or name not in self.rly:
            return
        if val != self.rly[name]:
            self.rly[name] = val
            self._mcp.output(_RLY[name], val)

    def switch_pressed(self, test=False):  # returns True if the switch is pressed
        self.sw_pressed = self._mcp.input(_IN_SWITCH_BLF) if not test else not self._mcp.input(_IN_TEST)
        return self.sw_pressed

    def powered(self):  # returns True if the bike is powered on (service output)
        self.pwr = self._mcp.input(_IN_PWR)
        return self.pwr

    def buzz(self, val):  # turns the buzzer on (1) or off (0)
        self._mcp.output(_BUZZER, val)

    def beep(self, duration, freq_pause=0.38):  # params in ms, pause usable for beeping (> 100) or pitch (< 1.00)
        tmr = utime.ticks_ms()
        freq_pause *= 1000  # to us
        while utime.ticks_diff(utime.ticks_ms(), tmr) < duration:
            self.buzz(1)
            utime.sleep_us(freq_pause)
            self.buzz(0)
            utime.sleep_us(freq_pause)
