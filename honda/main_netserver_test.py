from time import ticks_ms as tms, ticks_diff as tdiff
from uasyncio import get_event_loop, sleep_ms as d
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


_CODE_CHAR = {'A': 0x77, 'C': 0x39, 'E': 0x79, 'F': 0x71, 'G': 0x3D, 'H': 0x76, 'I': 0x30,
              'J': 0x1E, 'L': 0x38, 'O': 0x3F, 'P': 0x73, 'S': 0x6D, 'U': 0x3E, 'Y': 0x6E,
              'b': 0x7C, 'c': 0x58, 'd': 0x5E, 'h': 0x74, 'n': 0x54, 'o': 0x5C, 'q': 0x67,
              'r': 0x50, 't': 0x78, 'u': 0x1C, '-': 0x40, ' ': 0x00, '0': 0x3F, '1': 0x06,
              '2': 0x5B, '3': 0x4F, '4': 0x66, '5': 0x6D, '6': 0x7D, '7': 0x07, '8': 0x7F, '9': 0x6F}
RLY = {'BL': 0, 'HO': 1, 'ST': 2, 'IG': 3, 'LED': 4}
class FakeControl:
    def __init__(self):
        self.pwr = True
        self.sw_pressed = True
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

    def seg_show(self, c):  # shows a single symbol (no dot) on the 7-seg
        c = str(c)
        if c == '.':
            self.dot = 1
        if c not in _CODE_CHAR:
            c = c.lower() if c.isupper() else c.upper()
            if c not in _CODE_CHAR:
                c = ' '
        self.pattern = _CODE_CHAR[c]

    async def seg_print(self, msg, t=600, p=100):
        print("PRINTING (in %.1fs) '%s'..." % (len(msg) * t / 1000, msg))
        # Shows a text or number (could be negative or float)
        # Each symbol will be shown for <t> ms, followed by a <p> ms pause (nothing displayed)
        # The display will be cleared after displaying.
        for c in str(msg):
            self.seg_clear()
            await d(p)
            self.seg_show(c)
            await d(t)
        self.seg_clear()

    def seg_clear(self):
        self.pattern = 0
        self.dot = 0

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


loop = get_event_loop()
ecu = FakeECU()
ctrl = FakeControl()
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
            net.process()  # update all clients and handle requests
            # some other stuff:
            ecu.update()
            await d(20)  # for some test stuff
    finally:
        net.stop()


loop.create_task(some_main_task())
loop.run_forever()
