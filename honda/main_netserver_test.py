from time import ticks_ms as tms, ticks_diff as tdiff
from net import NetServer


class ECUBase:
    def __init__(self):
        self.connecting = False
        self.ready = False


class FakeECU(ECUBase):
    def __init__(self):
        super().__init__()
        TABLES = ((0x11, 20), (0x20, 3), (0x61, 20), (0x70, 3), (0xD0, 21), (0xD1, 6))  # tables + length (len>0!!!)
        self.regMap = {t: l for t, l in TABLES}

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
        if tdiff(tms(), self._tmr) > 100:
            self._tmr = tms()

            import urandom
            self.rpm = urandom.getrandbits(10)
            self.tp = urandom.getrandbits(2)
            self.ect_v = urandom.getrandbits(2)
            self.bat = urandom.getrandbits(10) / 10
            self.sidestand = None if urandom.getrandbits(1) else bool(urandom.getrandbits(1))
            self.engine = bool(urandom.getrandbits(1))
            self.gear = None if urandom.getrandbits(3) == 0 else urandom.getrandbits(3)
            self.speed = urandom.getrandbits(8)
            self.ready = bool(urandom.getrandbits(1))
            self.connecting = bool(urandom.getrandbits(1))

            ctrl.pwr = bool(urandom.getrandbits(1))


RLY = {'BL': 0, 'HO': 1, 'ST': 2, 'IG': 3}
class FakeControl:
    def __init__(self):
        self.pwr = True
        self.sw_pressed = False
        self.mode = 0
        self.rly = {k: False for k in RLY}

    def set_rly(self, name, val):
        # turns relay name (HO, BL, ST, IG) on/off if <val> is True/False (1/0)
        if not isinstance(val, bool) or name not in self.rly:
            return
        if val != self.rly[name]:
            print("RLY " + name + " TO " + str(val))
            self.rly[name] = val


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
finally:
    net.stop()
