from time import ticks_ms as tms, ticks_diff as tdiff
from net import NetServer
import urandom


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
        self.fuelInjTime = 0  # TODO probably fuel injection duration (ms?)
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
            ctrl.pwr = bool(urandom.getrandbits(1))
            print("PWR", ctrl.pwr)


RLY = {'BL': 0, 'HO': 1, 'ST': 2, 'IG': 3, 'LED': 4}
class FakeControl:
    def __init__(self):
        self.pwr = True
        self.sw_pressed = False
        self.mode = 0
        self.rly = {k: False for k in RLY}

        self.pattern = 0
        self._circle = 1
        self.dot = 0

        self._tmr = tms()

    def set_rly(self, name, val):
        if not isinstance(val, bool) or name not in self.rly:
            return
        if val != self.rly[name]:
            print("RLY " + name + " TO " + str(val))
            self.rly[name] = val

    def seg_print(self, msg, t=650):
        print("PRINTING (in %.1fs) '%s'..." % (len(msg) * t / 1000, msg))

    def dosth(self):
        if tdiff(tms(), self._tmr) > 400:
            self._tmr = tms()
            self.seg_circle()

    def seg_circle(self, clockwise=False, invert=False):
        if clockwise:
            self._circle <<= 1
            if self._circle >= 0b1000000:  # would be middle seg -
                self._circle = 1
        else:
            self._circle >>= 1
            if self._circle == 0:
                self._circle = 0b100000

        if invert:
            self.pattern = self._circle ^ 0x3F
        else:
            self.pattern = self._circle


ecu = FakeECU()
ctrl = FakeControl()
net = NetServer()

num_clients = 0

net.start()
print("NetServer started")
try:
    while True:
        if net.client_count() != num_clients:
            num_clients = net.client_count()
            print("client count changed to " + str(num_clients))
        net.process()  # update all clients and handle requests
        # some other stuff:
        ecu.update()
        ctrl.dosth()
finally:
    net.stop()
