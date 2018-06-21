import ssd1306
import machine


class ADCVisualizer:
    def __init__(self, width, height, scl=5, sda=4, adc=0, speed=1):
        self._WIDTH = width
        self._HEIGHT = height
        self._DX = speed  # delta x = each ADC value uses <dx> pixels on screen (width)
        self.oled = ssd1306.SSD1306_I2C(self._WIDTH, self._HEIGHT, machine.I2C(-1, machine.Pin(scl), machine.Pin(sda)))
        self.adc = machine.ADC(adc)
        self.oled.fill(0)  # init (if sth drawn before)
        self.oled.show()
        self.last_y = 0  # recently drawn y-value (last on visible graph)

    def _append_value(self, y):
        # """ appends the given y-value to the graph on the oled display by connecting the
        # new point to the last value with a line (dx = horizontal distance to last point). """
        self.oled.scroll(-self._DX, 0)  # move current graph to the left
        self.oled.fill_rect(self._WIDTH-self._DX, 0, self._DX, self._HEIGHT, 0)  # clear last columns for connection
        self.oled.line(self._WIDTH-self._DX, self.last_y, self._WIDTH-1, y, 1)  # draw connection line and new y
        self.last_y = y

    def update(self):
        # """ updates the display with the next value from the ADC """
        y = int(self.adc.read()*self._HEIGHT/1025)  # transform 0-1024 (adc value) to 0-height
        y = self._HEIGHT-1 - y  # invert value (because display top is 0 (inverted y axis))
        self._append_value(y)  # takes 85ms on 128x64
        self.oled.show()


def main():
    adc = ADCVisualizer(128, 64)
    while True:
        adc.update()


if __name__ == "__main__":
    main()
