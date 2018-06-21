from utime import sleep_ms, ticks_ms as tms, ticks_diff as tdiff
from other.mcp import MCP23017


class OutputController:
    # This class handles the cockpit -> outputs on the 7 segment display and the green and yellow LED.
    # The 7 segment display must be connected to the MCP on pins GPA0 (a) to GPA7 (h).

    _LED_G = 11
    _LED_Y = 8

    # binary codes for digits 0-9 (index) for 7 segment output h (MSB) to a (LSB), 1 meaning active
    _CODE_DIGIT = (0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F)
    _CODE_CHAR = {'A': 0x77, 'C': 0x39, 'E': 0x79, 'F': 0x71, 'H': 0x76, 'I': 0x06,
                  'J': 0x0E, 'L': 0x38, 'O': 0x3F, 'P': 0x73, 'S': 0x6D, 'U': 0x3E,
                  'b': 0x7C, 'c': 0x58, 'd': 0x5E, 'h': 0x74, 'u': 0x1C, '-': 0x40}

    def __init__(self, i2c, mcp_addr):
        self._mcp = MCP23017(i2c, mcp_addr)

        for pin in range(8):
            self._mcp.decl_output(pin)
        self._mcp.decl_output(OutputController._LED_Y)
        self._mcp.decl_output(OutputController._LED_G)

        self._dot = 0  # dot currently lighted?

        self.seg_clear()
        self.led_y(0)
        self.led_g(0)

    def seg_dot(self, value=None):
        # Turns the 7-segment dot on/off; 1 = on, 0 = off, None = switch
        self._dot = value if value is not None else not self._dot
        self._mcp.output(7, not self._dot)

    # def seg_dot_blink(self, ms):  # blinks the dot pin; goes back to the original state afterwards
    #     self.seg_dot()
    #     sleep_ms(ms)
    #     self.seg_dot()
    #     sleep_ms(ms)  # time required for stuff afterwards anyway, so value can be lower

    def seg_clear(self):  # turns the seven segment display off
        self.seg_pattern(0)
        self.seg_dot(0)

    def seg_digit(self, dig):
        # Shows a single digit on the 7 segment display.
        if dig not in range(10):
            self.seg_clear()
        else:
            self.seg_pattern(OutputController._CODE_DIGIT[dig])

    def seg_char(self, char):
        self.seg_pattern(OutputController._CODE_CHAR[char])

    def seg_pattern(self, bits):
        # Shows the binary pattern <bits> on the 7 segment display where 1 means on.
        # E.g. 0b0000101 lights up pin C and A. For dot please use seg_dot().
        pins = {}  # maps pins (0-7) to a value, where True means OFF (double positive) and False means ON
        for i in range(7):
            pins[i] = not (bits & 1)  # get i-th bit and invert it so that finally True means ON again (for the user)
            bits >>= 1
        self._mcp.output_pins(pins)

    def seg_circle(self, duration, clockwise=False, invert=False):
        # duration: the circle is displayed completely (from begin to end) in _ ms
        # invert: False = only one segment is displayed, True: all segments apart from one displayed
        # clockwise: direction of movement

        DPS = duration / 6  # duration per segment

        patt = 1 << (0 if clockwise else 5)
        for _ in range(6):
            sleep_ms(DPS)
            self.seg_pattern(patt if not invert else patt ^ 0x3F)
            if clockwise:
                patt <<= 1
            else:
                patt >>= 1

    def led_g(self, value):  # turns green LED on/off; 1 = on, 0 = off
        self._mcp.output(OutputController._LED_G, not value)

    def led_y(self, value):  # turns yellow LED on/off; 1 = on, 0 = off
        self._mcp.output(OutputController._LED_Y, not value)


class IOController:
    # This class is used for handling the relay backpack and input buttons.
    pass
