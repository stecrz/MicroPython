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

# binary codes for for 7 segment output h (MSB) to a (LSB), 1 meaning active
_CODE_CHAR = {'A': 0x77, 'C': 0x39, 'E': 0x79, 'F': 0x71, 'G': 0x3D, 'H': 0x76, 'I': 0x30,
              'J': 0x1E, 'L': 0x38, 'O': 0x3F, 'P': 0x73, 'S': 0x6D, 'U': 0x3E, 'Y': 0x6E,
              'b': 0x7C, 'c': 0x58, 'd': 0x5E, 'h': 0x74, 'n': 0x54, 'o': 0x5C, 'q': 0x67,
              'r': 0x50, 't': 0x78, 'u': 0x1C, '-': 0x40, ' ': 0x00, '0': 0x3F, '1': 0x06,
              '2': 0x5B, '3': 0x4F, '4': 0x66, '5': 0x6D, '6': 0x7D, '7': 0x07, '8': 0x7F, '9': 0x6F}
# impossible chars: K, M, V, W, X, Z

_ADDR_MCP2 = 0x24
_IN_SWITCH_BLF = 8  # input pin for break light flash switch pin on MCP
_IN_PWR = 10  # input pin for powered status of the bike

# MCP output pins for relays (for class user; using constants internally!):
_RLY = {'BL': 0, 'HO': 1, 'ST': 2, 'IG': 3, 'LED': 4}


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
        for pin in range(len(_RLY)):  # reset relay outputs (off)
            self._mcp2.decl_output(pin)
            self._mcp2.output(pin, 0)
        self._mcp2.decl_input(_IN_SWITCH_BLF)  # switch input
        self._mcp2.pullup(_IN_SWITCH_BLF, True)  # additional pullup (also there is the 82k pullup)
        self._mcp2.decl_input(_IN_PWR)  # powered status input

        self.dot = 0  # dot currently lighted? (read-only from outside this class)
        self.pattern = 0  # currently displayed segment pattern (without dot) (read-only from outside this class)
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
        for rly in range(len(_RLY)):
            self._mcp2.output(rly, 0)

    def seg_dot(self, val=None):
        # Turns the 7-segment dot on/off; 1 = on, 0 = off, None = switch; does not affect pattern
        self.dot = val if val is not None else not self.dot
        self._mcp1.output(7, not self.dot)

    def seg_clear(self):  # turns the seven segment display off
        self._seg_pattern(0)
        self.seg_dot(0)

    def seg_show(self, c):  # shows a single symbol on the 7-seg
        c = str(c)
        if c == '.':
            self.seg_dot(1)  # seg_pattern will clear the rest
        if c not in _CODE_CHAR:
            c = c.lower() if c.isupper() else c.upper()
            if c not in _CODE_CHAR:
                c = ' '
        self._seg_pattern(_CODE_CHAR[c])

    async def seg_print(self, msg, t=600, p=100):
        # Shows a text or number (could be negative or float)
        # Each symbol will be shown for <t> ms, followed by a <p> ms pause (nothing displayed)
        # The display will be cleared after displaying.
        for c in str(msg):
            self.seg_clear()
            await d(p)
            self.seg_show(c)
            await d(t)
        self.seg_clear()

    def _seg_pattern(self, bits):
        # Shows the binary pattern <bits> on the 7 segment display where 1 means on.
        # E.g. 0b0000101 lights up pin C and A. For dot please use seg_dot().
        self.pattern = bits
        pins = {}  # maps pins (0-6) to a val, where True means OFF (double positive) and False means ON
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
            self._seg_pattern(self._circle ^ 0x3F)
        else:
            self._seg_pattern(self._circle)

    async def seg_flash(self, pause):
        pttrn = self.pattern  # currently displayed num/char
        self.seg_clear()
        await d(pause)
        self._seg_pattern(pttrn)
        await d(pause)

    def led_g(self, val):  # turns green LED on/off; 1 = on, 0 = off
        self._mcp1.output(_LED_G, not val)

    def led_y(self, val):  # turns yellow LED on/off; 1 = on, 0 = off
        self._mcp1.output(_LED_Y, not val)

    def set_rly(self, name, val):
        # turns relay name (HO, BL, ST, IG, LED) on/off if <val> is True/False (1/0)
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
