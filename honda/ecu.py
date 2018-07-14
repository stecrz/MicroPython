from machine import Pin
from utime import sleep_ms, ticks_ms as tms, ticks_diff as tdiff
from uasyncio import sleep_ms as d


def to_hex(b):  # bytes to hex string
    return ' '.join('%02X' % x for x in b) if b is not None else "None"


class HondaECU:
    # This class is asynchronous. On errors an HondaECU.Error will be raised. If it is an UART
    # timeout (meaning we wanted to read x bytes from UART but it took too long) this ready
    # state will be set to False in addition.

    TX_DELAY = 25  # minimum delay between two write-procedures on the UART (ms)

    class Error(Exception):  # eg wrong checksum
        pass

    def __init__(self, uart, baud=10400, uart_timeout=300, tx_pin=1):
        # note that <uart_timeout> is the timeout for reading a single byte from UART, meaning that reading e. g.
        # 10 bytes could take up to 10*<uart_timeout>. timeout exceed cause an Error and set ECU to not ready state

        # save params for init method
        self.__txp = tx_pin
        self.__baud = baud

        self._uart = uart
        self._uart_to = uart_timeout
        # self.sreader = asyncio.StreamReader(uart)
        self._wTmr = tms()  # to make sure there is a delay between two msgs being sent over UART

        self.ready = False  # set to False whenever the ECU has to be woken up using init-method
        self._fir = 0  # fails in a row counter. will be increased and set back to zero if read was successful
        self.connecting = False  # set to True while the ECU is trying to connect to K-Line

    async def init(self, timeout=4000):
        # Performs the ECU wakeup and initialize procedure if required (not ready).
        # ready state is True if it was finished successfully and false it failed (= timeout).
        # Also setup K-line by pulling it low before (what uart.sendbreak() normally does).

        tmr = tms()
        while True:
            self.connecting = True

            # K-line pulldown: only has to be done whenever the ECU was turned off
            tx = Pin(self.__txp, Pin.OUT)  # => pulls RX LOW (only when ECU connection achieved for first time)
            tx(0)
            sleep_ms(70)  # no intr here
            tx(1)
            del tx
            sleep_ms(130)  # TODO await d(130)

            self._uart.init(self.__baud, timeout=self._uart_to, bits=8, parity=None, stop=1)
            self._wTmr = tms()

            try:
                await self.query((0xFE,), 0xFF)  # no resp excepted. alt: use 0x72 instead of 0xFF for response rType=0E
                await d(200)  # default delay might not be enough, just to be safe on startup
                await self.diag_query(0x00, 0xF0)  # return packet (02 04 00 FA) is validated, Exception otherwise
                self.ready = True  # this point is only reached when no error occurs
                return
            except HondaECU.Error:
                if tdiff(self._wTmr, tmr) > timeout:
                    return
                await d(400)  # relax
            finally:
                self.connecting = False

    async def diag_query(self, sType, *data):
        # Performs a diagnostic query. See query method, but additionally verifies the subtype.
        resp = await self.query((0x72,), sType, *data, rType=(0x02,))  # subtype is part of data
        if resp[0] != sType:
            raise HondaECU.Error(4)  # wrong subtype
        return resp[1:]

    async def query(self, qType, *qData, rType=None):
        # Sends a query/packet of type <qType> (must be tuple/list of ints) containing the request <qData> (some
        # integers, any subtype may be part of data) to the UART. Echo is awaited. Retrieves and returns the
        # replied data (without packet type, length, checksum) if <rType> is not None. <rType> specifies the
        # expected response packet type (int tuple). Error if no echo received, response type or checksum wrong.

        await self._uread()  # clear buffer if necessary (should not be the case)

        # build and send request message:
        qLen = len(qType) + len(qData) + 2  # incl. length & checksum byte
        msg = qType + (qLen,) + qData
        msg = bytes(msg + (HondaECU._cksm(msg),))
        await self._uwrite(msg)

        # retrieve echo:
        echo = await self._uread(qLen)
        if echo != msg:
            raise HondaECU.Error(1)  # wrong echo

        # receive and check response, return data from reply:
        if rType is not None:
            rType = bytes(rType)
            if rType != await self._uread(len(rType)):
                raise HondaECU.Error(2)  # wrong response type

            rLen = await self._uread(1)
            rData = await self._uread(ord(rLen) - len(rType) - 2)  # rLen includes field: type, len, chk
            rChk = await self._uread(1)

            if HondaECU._cksm(rType + rLen + rData) != ord(rChk):
                raise HondaECU.Error(1)  # wrong checksum

            return rData

    @staticmethod
    def _cksm(msg):
        # Calculate checksum (as int) for bytes <msg>.
        return ((sum(msg) ^ 0xFF) + 1) & 0xFF

    async def _uread(self, n=None):
        # Read and return <n> bytes (blocking) from UART. Exception on timeout.
        # Read all available (meaning non-blocking) bytes if <n> is None.

        r = b''
        if n is None:
            if self._uart.any():
                # use StreamReader.read()?
                r = self._uart.read()  # reads all
        else:
            # problem: StreamWriter is blocking (does not support timeouts neither in read nor in readexactly)
            #          therefore we are reading byte by byte (uart.any() returns only 1 or 0, not the amount!)
            while n > 0:
                # if n % 5 == 0: await d(0) # allow interrupts in large data bundles
                tmr = tms()
                while not self._uart.any():
                    if tdiff(tms(), tmr) > self._uart_to:
                        if self._fir >= 9:  # this must be the _th fail -> now reconnect required
                            self.ready = False
                        else:
                            self._fir += 1
                            raise HondaECU.Error(0)  # UART timeout
                    await d(0)
                r += self._uart.read(1)
                n -= 1

        if self._fir > 0:
            self._fir -= 1
        return r

    async def _uwrite(self, msg):
        # Writes the bytes <msg> to the UART.
        # Waits for some ms, ensuring a minimum delay between two msgs (prevents UART timeout).

        diff = tdiff(tms(), self._wTmr)
        if diff < HondaECU.TX_DELAY:
            await d(HondaECU.TX_DELAY - diff)
        self._uart.write(msg)  # no StreamWriter, as it would cause too much scheduling
        self._wTmr = tms()


class CBR500Sniffer(HondaECU):
    # Class for reading the registers of a Honda CBR500R ECM.

    # | GEAR | RATIO |
    # |--------------|
    # |   1  |  155  |
    # |   2  |   99  |
    # |   3  |   75  |
    # |   4  |   61  |
    # |   5  |   54  |
    # |   6  |   49  |
    # I am using thresholds, so e.g.: ratio > {ratio between 1 and 2} => gear 1
    # higher threshold = next gear indicated later; lower threshold = previous gear skipped earlier
    # (alt.: approximated formula: 2736.8 * x^-1.577)
    GEAR_RATIO_THRESH = (400, 120, 85, 67.5, 57.5, 51.8)  # highest ratio for gear 1,2,3,4,5,6 (above first = neutral)

    def __init__(self, uart):  # UART will be reinitialized (baudrate, parity, ...), just object required
        super().__init__(uart)

        # rare register data, e.g. regMap[0x11][13] = 14th byte (index 13) in table 0x11 as unsigned integer
        TABLES = ((0x11, 20), (0x20, 3), (0x61, 20), (0x70, 3), (0xD0, 21), (0xD1, 6))  # tables + length (len>0!!!)
        self.regMap = {t: bytearray(l) for t, l in TABLES}

        # known relevant registers:
        self.rpm = 0        # rounds per minute (CKP sensor)
        self.tp = 0         # throttle position (%)
        self.tp_v = 0       # +- TP sensor voltage
        self.ect = 0        # engine coolant temperature (°C)
        self.ect_v = 0      # +- ECT sensor voltage
        self.iat = 0        # intake air temperature (°C)
        self.iat_v = 0      # +- IAT sensor voltage
        self.map = 0        # manifold absolute pressure (kPa)
        self.map_v = 0      # +- MAP sensor voltage
        self.bat = 0        # battery voltage
        self.speed = 0      # VS sensor (km/h)
        self.fuelInjTime = 0  # TODO probably fuel injection duration (ms?)
        self.sidestand = None  # driving/parking state: True = kickstand used, False = unused, None = not calculable
        self.engine = False  # running?
        self.idle = True  # True = engine is idling or STARTABLE (clutch pulled and/or neutral (no gear))
                          # False = bike already running or NOT STARTABLE (no clutch + gear, but
                          #         kickstand + gear means idle=False although clutch might be pulled)
        self.gear = None  # calculated gear (1...6, None = Neutral or not calculatable)

        # TODO missing:
        # - fuel injector 1 & 2?
        # - oxygen O2 sensor
        # - engine oil pressure EOP switch
        # - bank angle sensor (readable or online for emergency poweroff when bike dropped?)
        # - AT sensor

    async def update(self, tab):
        v_new = await self.diag_query(0x71, tab)  # returns content/values of table t
        v_old = self.regMap[tab]

        if len(v_new)-1 != len(v_old):
            return  # should not happen ever
        v_new = v_new[1:]  # trim first (is not a register)

        if v_new != v_old:  # sth changed
            for i in range(len(v_old)):  # offset in table
                if v_old[i] != v_new[i]:  # register changed
                    self._update_reg(tab, i, v_new[i])

    def _update_reg(self, tab, reg, val):
        # Writes int <val> to the register in table <tab> with offset <reg>. Additionally updates attributes.
        self.regMap[tab][reg] = val

        if tab == 0xD1:
            if reg == 0:
                v = val & 0b11
                self.sidestand = None if v == 1 else bool(v)  # 2/3 = KS, 0 = no KS
                self.idle = bool(v & 0b1)  # 0/2 = not startable, 1/3 = startable
            elif reg == 4:
                self.engine = bool(val & 0b1)  # 0/1
        elif tab == 0x11:
            if reg == 0 or reg == 1:
                self.rpm = (self.regMap[tab][0] << 8) + self.regMap[tab][1]
                self._calc_gear()
            elif reg == 2:
                self.tp_v = val * 5 / 256
            elif reg == 3:
                self.tp = int(val * 100 / 158)  # val / 16
            elif reg == 4:
                self.ect_v = val * 5 / 256
            elif reg == 5:
                self.ect = val - 40
            elif reg == 6:
                self.iat_v = val * 5 / 256
            elif reg == 7:
                self.iat = val - 40
            elif reg == 8:
                self.map_v = val * 5 / 256
            elif reg == 9:
                self.map = val
            elif reg == 12:
                self.bat = val / 10
            elif reg == 13:
                self.speed = val
                self._calc_gear()
            elif reg == 14 or reg == 15:
                self.fuelInjTime = (self.regMap[tab][14] << 8) + self.regMap[tab][15]

    def _calc_gear(self):  # sets the gear based on the ratio (RPM/speed), 0 = probably neutral
        if self.speed <= 0:  # not driving
            self.gear = None
            return 0

        ratio = self.rpm / self.speed
        if ratio > CBR500Sniffer.GEAR_RATIO_THRESH[0]:  # too high, clutch must be pulled
            self.gear = None
        else:
            for i in range(1, len(CBR500Sniffer.GEAR_RATIO_THRESH)):
                if ratio > CBR500Sniffer.GEAR_RATIO_THRESH[i]:
                    self.gear = i
                    break
            else:  # not above any threshold -> <=last -> last gear
                self.gear = 6
