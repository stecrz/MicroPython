from time import ticks_ms as tms, ticks_diff as tdiff
from uasyncio import get_event_loop, sleep_ms as d
from net import NetServer
import urandom
from ctrl import OLED
from machine import I2C, Pin


class ECUBase:
    def __init__(self):
        self.connecting = False
        self.ready = False


class FakeECU(ECUBase):
    def __init__(self):
        super().__init__()
        TABLES = ((0x11, 20), (0x20, 3), (0x61, 20), (0x70, 3), (0xD0, 21), (0xD1, 6))  # tables + length (len>0!!!)
        self._regMap = {t: l for t, l in TABLES}

        # known relevant registers:
        self.rpm = 0  # rounds per minute (CKP sensor)
        self.tp = 0  # throttle position (%)
        self.tp_v = 0  # +- TP sensor voltage
        self.ect = 0  # engine coolant temperature (°C)
        self.ect_v = 0  # +- ECT sensor voltage
        self.iat = 0  # intake air temperature (°C)
        self.iat_v = 0  # +- IAT sensor voltage
        self.map = 0  # manifold absolute pressure (kPa)
        self.map_v = 0  # +- MAP sensor voltage
        self.bat = 0  # battery voltage
        self.speed = 0  # VS sensor (km/h)
        self.sidestand = None  # driving/parking state: True = kickstand used, False = unused, None = not calculable
        self.engine = False  # running?
        self.idle = True  # True = engine is idling or STARTABLE (clutch pulled and/or neutral (no gear))
        self.gear = None  # calculated gear (1...6, None = Neutral)

        self._tmr = tms()

    def update(self):
        if tdiff(tms(), self._tmr) > 3000:
            self._tmr = tms()

            self.rpm = urandom.getrandbits(10)
            print("RPM", self.rpm)
            self.tp = urandom.getrandbits(2)
            print("TP", self.tp)
            self.ect_v = urandom.getrandbits(2)
            print("ECT_V", self.ect_v)
            self.bat = urandom.getrandbits(10) / 10
            print("BAT", self.bat)
            self.sidestand = None if urandom.getrandbits(1) else bool(urandom.getrandbits(1))
            print("SIDESTAND", self.sidestand)
            self.engine = bool(urandom.getrandbits(1))
            print("ENGINE", self.engine)
            self.gear = None if urandom.getrandbits(3) == 0 else urandom.getrandbits(3)
            print("GEAR", self.gear)
            self.speed = urandom.getrandbits(8)
            print("SPEED", self.speed)
            self.ready = bool(urandom.getrandbits(1))
            print("READY", self.ready)
            self.connecting = bool(urandom.getrandbits(1))
            print("CONNECTING", self.connecting)
            io.pwr = bool(urandom.getrandbits(1))
            print("PWR", io.pwr)


RLY = {'BL': 0, 'HO': 1, 'ST': 2, 'IG': 3, 'LED': 4}


class FakeControlWithOLED:
    def __init__(self):
        i2c = I2C(-1, Pin(5), Pin(4))
        self.oled = OLED(64, 128, i2c)

        self.pwr = True
        self.sw_pressed = True
        self.rly = {k: False for k in RLY}

        self._tmr = tms()

    def set_rly(self, name, val):
        if not isinstance(val, bool) or name not in self.rly:
            return
        if val != self.rly[name]:
            print("RLY " + name + " TO " + str(val))
            self.rly[name] = val

    def clear(self):
        self.pwr = False
        self.sw_pressed = False
        self.oled.clear()
        self.led_b(0)
        self.led_g(0)
        print("Cleared.")

    def led_g(self, val):
        print("LED G", "on" if val else "off")

    def led_b(self, val):
        print("LED B", "on" if val else "off")

    def buzz(self, val):
        print("BUZZER", "on" if val else "off")


loop = get_event_loop()
ecu = FakeECU()
io = FakeControlWithOLED()
net = NetServer()


async def some_main_task():
    num_clients = 0

    net.start()
    print("NetServer started")
    try:
        while True:
            if net.client_count() != num_clients:
                num_clients = net.client_count()
                print("client count changed to " + str(num_clients))
            net.process()  # update all clients and handle  requests
            # some other stuff:
            ecu.update()
            await d(20)  # for some test stuff
    finally:
        net.stop()


loop.create_task(some_main_task())
loop.run_forever()
