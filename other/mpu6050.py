# Accelerometer Module: GY-521, MPU-6050
import machine
from display import Display


PWR_MGMT_1 = 0x6B

class MPU6050:
    def __init__(self, i2c, addr=0x68):
        self.i2c = i2c
        self.addr = addr
        self.i2c.start()
        self.i2c.writeto(self.addr, bytearray([PWR_MGMT_1, 0]))  # set powered mgmt register to 0 (wake up MPU)
        self.i2c.stop()

    def get_raw_values(self):
        self.i2c.start()
        a = self.i2c.readfrom_mem(self.addr, 0x3B, 14)  # read 14 registers
        self.i2c.stop()
        return a

    def read(self, register):
        self.i2c.start()
        a = self.i2c.readfrom_mem(self.addr, 0x3B)
        self.i2c.stop()

    def get_ints(self):
        b = self.get_raw_values()
        c = []
        for i in b:
            c.append(i)
        return c

    def bytes_toint(self, firstbyte, secondbyte):
        if not firstbyte & 0x80:
            return firstbyte << 8 | secondbyte
        return - (((firstbyte ^ 255) << 8) | (secondbyte ^ 255) + 1)

    def get_values(self):
        raw_ints = self.get_raw_values()
        vals = {}
        vals["AcX"] = self.bytes_toint(raw_ints[0], raw_ints[1])
        vals["AcY"] = self.bytes_toint(raw_ints[2], raw_ints[3])
        vals["AcZ"] = self.bytes_toint(raw_ints[4], raw_ints[5])
        vals["Tmp"] = self.bytes_toint(raw_ints[6], raw_ints[7]) / 340.00 + 36.53
        vals["GyX"] = self.bytes_toint(raw_ints[8], raw_ints[9])
        vals["GyY"] = self.bytes_toint(raw_ints[10], raw_ints[11])
        vals["GyZ"] = self.bytes_toint(raw_ints[12], raw_ints[13])
        return vals  # returned in range of Int16
        # -32768 to 32767

    def val_test(self):  # ONLY FOR TESTING! Also, fast reading sometimes crashes IIC
        from time import sleep
        while 1:
            print(self.get_values())
            sleep(0.05)


i2c = machine.I2C(-1, machine.Pin(5), machine.Pin(4), freq=9600)
accel = MPU6050(i2c)
oled = Display(i2c, 128, 64)
while True:
    oled.print(accel.get_values())
