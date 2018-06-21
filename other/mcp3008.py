from machine import Pin


class MCP3008:
    # """
    # Connection (MCP3008 <---> ESP8266):
    #      |---\_/---|
    # CH0 -|1      16|- V_dd      <--->   +3.3V
    # CH1 -|2      15|- V_ref     <--->   +3.3V
    # CH2 -|3      14|- AGND      <--->   GND
    # CH3 -|4      13|- CLK       <--->   SCK (14)
    # CH4 -|5      12|- D_out     <--->   MISO (12)
    # CH5 -|6      11|- D_in      <--->   MOSI (13)
    # CH6 -|7      10|- CS/SHDN   <--->   15
    # CH7 -|8       9|- DGND      <--->   GND
    #      |---------|
    # """

    def __init__(self, clk=14, mosi=13, miso=12, cs=15):
        self._clk = Pin(clk, Pin.OUT)
        self._mosi = Pin(mosi, Pin.OUT)
        self._miso = Pin(miso, Pin.IN)
        self._cs = Pin(cs, Pin.OUT)

    def read(self, channel):
        # """ Reads an analog value from the given channel (0-7) and returns it. """
        if channel not in range(0, 8):
            raise ValueError("channel must be 0-7")

        self._cs(1)  # negative edge
        self._cs(0)
        self._clk(0)

        send_cmd = channel
        send_cmd |= 0b00011000  # 0x18 (start bit + single/ended)

        # send bits (only 5 bits considered)
        for i in range(5):
            self._mosi(bool(send_cmd & 0x10))  # check bit on index 4
            self._clk(1)  # negative edge
            self._clk(0)
            send_cmd <<= 1

        # receive value from MCP
        v = 0
        for i in range(11):
            self._clk(1)  # negative edge
            self._clk(0)
            v <<= 1
            if self._miso():
                v |= 0x01

        return v
