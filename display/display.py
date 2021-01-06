try:
    import ssd1306_vert as ssd1306  # cp ~/micropython/drivers/display/ssd1306.py ~/micropython/ports/esp8266/modules
except ImportError:
    import ssd1306
# oled = ssd1306.SSD1306_I2C(128, 64, machine.I2C(-1, machine.Pin(5), machine.Pin(4)))


class Display:
    def __init__(self, i2c, width, height, symbol_width=8, symbol_height=8, **kwargs):
        # OLED address can be specified with keyword argument: addr=0x3c
        self._width = width
        self._height = height
        self._swidth = symbol_width
        self._sheight = symbol_height
        self.cursor = None
        self.oled = ssd1306.SSD1306_I2C(self._width, self._height, i2c, **kwargs)
        self.clear()

    def clear(self):
        self.oled.fill(0)
        self.oled.show()
        self.cursor = 0

    def print(self, msg):
        msg = str(msg)
        spl = int(self._width / self._swidth)  # symbols per line
        spl_first = spl-self.cursor  # first line length depends on where the cursor is

        lines = msg.split('\n')
        if len(lines[0]) > spl_first:
            firstline = lines[0][:spl_first]
            lines[0] = lines[0][spl_first:]
            lines.insert(0, firstline)
        lines = [line[i:i+spl] for line in lines for i in range(0, len(line), spl)]

        for i in range(len(lines)):
            if self.cursor >= spl:
                self._newline()
            self.oled.text(lines[i], self.cursor*self._swidth, self._height-self._sheight)
            if i == len(lines) - 1:  # last line
                self.cursor += len(lines[i])  # no automatic newline
            else:
                self.cursor = spl  # newline
        self.oled.show()

    def println(self, msg):
        self.print(msg)
        self._newline()  # not shown

    def _newline(self):
        self.oled.scroll(0, -self._sheight)
        self.oled.fill_rect(0, self._height-self._sheight, self._width, self._sheight, 0)  # clear last line
        self.cursor = 0

    def draw_line(self, x1, y1, x2, y2):
        if x1 > x2:  # swap (makes it easier)
            x1, x2 = x2, x1
            y1, y2 = y2, y1
        m = (y2-y1) / (x2-x1)  # slope (dy/dx)
        x, y = x1, y1
        while x1 <= x2:
            self.oled.pixel(x1, round(y1), 1)
            x1 += 1  # next column
            y1 += m  # add slope (probably float value)
        self.oled.show()
