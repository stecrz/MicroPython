import machine
from ssd1306_vert import SSD1306_I2C

i2c = machine.I2C(-1, machine.Pin(5), machine.Pin(4))
oled = SSD1306_I2C(128, 64, i2c, vertical=True)

oled.text("Hello", 20, 100)
oled.show()
