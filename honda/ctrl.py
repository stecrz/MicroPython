# MODULE FOR IO
from mcp23017 import MCP23017
from machine import Pin, I2C
from uasyncio import sleep_ms as d
import utime


async def blink(outfun, d1=150, d2=0):  # coro to indicate activity
    # Blinks one of the LEDs or the dot segment by turning it on for <d1> ms followed by
    # turning it off for <d2> m2. Simply pass the switch function <outfun>, which turns
    # the LED on by passing param 1 and off by param 0.
    outfun(1)
    await d(d1)  # await asyncio.sleep_ms(d1)
    outfun(0)
    if d2:
        await d(d2)


_SCL = 5
_SDA = 4

_ADDR_MCP1 = 0x22
_LED_G = 11
_LED_Y = 8
_BUZZER = 14  # TODO

# binary codes for digits 0-9 (index) for 7 segment output h (MSB) to a (LSB), 1 meaning active
_CODE_DIGIT = (0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F)
_CODE_CHAR = {'A': 0x77, 'C': 0x39, 'E': 0x79, 'F': 0x71, 'H': 0x76, 'I': 0x06,
              'J': 0x0E, 'L': 0x38, 'O': 0x3F, 'P': 0x73, 'S': 0x6D, 'U': 0x3E,
              'b': 0x7C, 'c': 0x58, 'd': 0x5E, 'h': 0x74, 'u': 0x1C, '-': 0x40}

_ADDR_MCP2 = 0x24
_IN_SWITCH_BLF = 8  # input pin for break light flash switch pin on MCP
_IN_PWR = 10  # input pin for powered status of the bike

# MCP output pins for relays (for class user; using constants internally!):
_RLY = {'BL': 0, 'HO': 1, 'ST': 2, 'IG': 3}


class IOControl:
    # This class handles the cockpit (7 segment display, green and yellow LED), the relay backpack,
    # input button and power status input.
    # The 7 segment display must be connected to the MCP on pins GPA0 (a) to GPA7 (h).

    def __init__(self):
        i2c = I2C(-1, Pin(_SCL), Pin(_SDA))

        self._mcp1 = MCP23017(i2c, _ADDR_MCP1, def_inp=0, def_val=1)  # all outputs, all high
        # for pin in range(8):
        #     self._mcp1.decl_output(pin)
        # self._mcp1.decl_output(OutputController._LED_Y)
        # self._mcp1.decl_output(OutputController._LED_G)

        self._mcp2 = MCP23017(i2c, _ADDR_MCP2, def_inp=0, def_val=0)  # default outputs, all low (no pullups)
        for pin in range(4):  # reset relay outputs (off)
            self._mcp2.decl_output(pin)
            self._mcp2.output(pin, 0)
        self._mcp2.decl_input(_IN_SWITCH_BLF)  # switch input
        self._mcp2.pullup(_IN_SWITCH_BLF, True)  # additional pullup (also there is the 82k pullup)
        self._mcp2.decl_input(_IN_PWR)  # powered status input

        self._dot = 0  # dot currently lighted?
        self._pattern = 0  # currently displayed segment pattern (without dot)
        self._circle = 1  # lighting pattern of circle if used (1, 2, 4, 8, 16, 32, 1, 2, ...)

        # last read states:
        self.pwr = None
        self.sw_pressed = None  # last switch state (from recent check): down?

        # 0 = normal, 1/2/3/... = special modes (after holding switch down), (-x = reset from special mode)
        # special modes: 1 = 0-100 km/h measurement
        #                on shutdown: mode = 1-9: network control stays on for <mode> hours
        #                             mode >= 10: return to console (hard reset required for normal operation)
        self.mode = 0
        self.rly = {k: False for k in _RLY}  # current relais states (last set)

        self.off()

    def clear(self):
        self.pwr = False
        self.sw_pressed = False
        self.seg_clear()
        self.led_y(0)
        self.led_g(0)

    def off(self):  # turns off all outputs
        self.clear()
        self._mcp1.output(_BUZZER, 0)
        for rly in range(4):
            self._mcp2.output(rly, 0)

    def seg_dot(self, val=None):
        # Turns the 7-segment dot on/off; 1 = on, 0 = off, None = switch
        self._dot = val if val is not None else not self._dot
        self._mcp1.output(7, not self._dot)

    def seg_clear(self):  # turns the seven segment display off
        self.seg_pattern(0)
        self.seg_dot(0)

    def seg_digit(self, dig):
        # Shows a single digit on the 7 segment display.
        if dig not in range(10):
            self.seg_clear()
        else:
            self.seg_pattern(_CODE_DIGIT[dig])

    async def seg_show_num(self, num, f=None, t=650):
        # Shows a whole number on the 7 segment display. <num> must be any integer. If you want to display a float
        # number, you can use <f> for the decimal places (must be a positive integer). E.g.: 15.21 = seg_num(15, 21)
        # Each digit (and separator) will be showed for <t> ms. The display will be cleared after displaying.

        self.seg_dot(0)
        if num < 0:
            self.seg_char('-')

        for dig in str(num):  # iterate over digits
            self.seg_digit(int(dig))
            await d(t)
        self.seg_clear()

        if f is not None:
            self.seg_dot(1)
            await d(t)
            self.seg_dot(0)

            for dig in str(f):
                self.seg_digit(int(dig))
                await d(t)
            self.seg_clear()

    def seg_char(self, char):
        self.seg_pattern(_CODE_CHAR[char])

    def seg_pattern(self, bits):
        # Shows the binary pattern <bits> on the 7 segment display where 1 means on.
        # E.g. 0b0000101 lights up pin C and A. For dot please use seg_dot().
        self._pattern = bits
        pins = {}  # maps pins (0-7) to a val, where True means OFF (double positive) and False means ON
        for i in range(7):
            pins[i] = not (bits & 1)  # get i-th bit and invert it so that finally True means ON again (for the user)
            bits >>= 1
        self._mcp1.output_pins(pins)

    def seg_circle(self, clockwise=False, invert=False):
        # invert: False = only one segment is displayed, True: all segments apart from one displayed
        # clockwise: direction of movement

        if clockwise:
            self._circle <<= 1
            if self._circle >= 0b1000000:  # would be middle seg -
                self._circle = 1
        else:
            self._circle >>= 1
            if self._circle == 0:
                self._circle = 0b100000

        if invert:
            self.seg_pattern(self._circle ^ 0x3F)
        else:
            self.seg_pattern(self._circle)

    async def seg_flash(self, pause):
        pttrn = self._pattern  # currently displayed num/char
        self.seg_clear()
        await d(pause)
        self.seg_pattern(pttrn)
        await d(pause)

    def led_g(self, val):  # turns green LED on/off; 1 = on, 0 = off
        self._mcp1.output(_LED_G, not val)

    def led_y(self, val):  # turns yellow LED on/off; 1 = on, 0 = off
        self._mcp1.output(_LED_Y, not val)

    def set_rly(self, name, val):
        # turns relay name (HO, BL, ST, IG) on/off if <val> is True/False (1/0)
        if not isinstance(val, bool) or name not in self.rly:
            return
        if val != self.rly[name]:
            self.rly[name] = val
            self._mcp2.output(_RLY[name], val)

    def switch_pressed(self):  # returns True if the switch is pressed and False if it is not
        self.sw_pressed = self._mcp2.input(_IN_SWITCH_BLF)
        return self.sw_pressed

    def powered(self):  # returns True if the bike is powered on (service output), False if not
        self.pwr = self._mcp2.input(_IN_PWR)
        return self.pwr

    def beep(self, duration, freq_pause=380):  # duration in ms, freq_pause in us
        duration *= 1000  # ms to us
        tmr = utime.ticks_us()
        while utime.ticks_diff(utime.ticks_us(), tmr) < duration:
            self._mcp1.output(_BUZZER, 0)
            utime.sleep_us(freq_pause)
            self._mcp1.output(_BUZZER, 1)
            utime.sleep_us(freq_pause)
