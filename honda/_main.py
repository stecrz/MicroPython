# IMPORTANT NOTES:
# - reading from ECU only shows valid values if HISS system is disarmed.
#   disarming only possible until ESP is connected (not afterwards)
# - erase_flash not working? disconnect ESP from all power sources
# - Flash errors / ampy upload errors / \x00: Probably hardware issure. Make sure connections (RX/TX + power) are stable
#   Disconnect OLED. After initial setup is performed ESP will not restart automatically
# - os.listdir() shows many \x00\x00\x00 entries after flashing? maybe because of neopixel, probably loose connections
#   import uos, flashbdev
#   uos.VfsFat.mkfs(flashbdev.bdev)
# - OSError 28 = no more space (maybe because filesystem corrupted -> erase flash)
# - Debugging: If OLED works, you can simply use io.oled.println("msg")
#              Use mini-Test-Switch by changeing to switch_pressed()

# Required modules:
# a) Self-defined:
#    - ecu
#    - ctrl
#    - net
#    - pwr
# b) Drivers (modified from others):
#    - webserver (MicroPython/websocketserver/webserver.py)
#    - mcp23017 (minimal version of mcp.py)
#    - ssd1306_vert (MicroPython/display/ssd1306_vert.py)
# c) Drivers:
#    - uasyncio (clone from https://github.com/micropython/micropython-lib)
# d) Other files (not frozen into flash):
#    - html/ (contains html content for webserver)
#    - netconf.json
#    - img/ (contains images for OLED, e.g. font letters)
#
# WORKING VERSION FROM 2018: uPython v1.9.4-29-g1b7487e-dirty on 2018-07-20
# FILES: 'boot.py', 'main.py', '_main.mpy', 'netconf.json', 'html/', 'img/'
# PRECOMPILE:  python -m mpy_cross _main.py

#                       BOARD LAYOUT
# ▛▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▛▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▜
# ▌  ┌───────────┐           ▌  ┌FUSE+REV.CURRENT┐   RST◉  ▌
# ▌⬲│ RELAY1/BL │           ▌  └PROT.DIODE(+3.3)┘   TX┌┬━┐ ▌
# ▌  ╞═══════════╡           ▌ ┌─┐             ┌─┐ /RX└┴━┘ ▌
# ▌⬲│ RELAY2/HO │           ▌ │:│            │:│         ▌
# ▌  ╞═══════════╡           ▌ │:│  ESP8266   │:│        ▌
# ▌⬲│ RELAY3/ST │           ▌ │:│  headers   │:│ FLASH◉ ▌
# ▌  ╞═══════════╡           ▌ │:│            │:│ UART: ▐
# ▌⬲│ RELAY4/IG │           ▌ └─┘ I2C-ext:    └─┘ □□□□ ▌
# ▌  ╞═══════════╡   SW-wake ▎┌─┐  □□□□           ┌─────┐▌
# ▌⬲│ RELAY5/LED│   -enable ▎│▋│         I2C-out: │▪▪▪▪│▌
# ▌  └───────────┘           ▎└─┘                  └─────┘▌
# ▌  GND◯◯+12-in          ╼🠴c▭╾                 ┌────┐▌
# ▌ ┌────────────────────┐  ╼🠴o▭╾      K-LINE-in: │▪▪▪│▌
# ▌ │     MCP23017 #2    ◖  ╼🠴n▭╾                 └────┘ ▌
# ▌ └────────────────────┘  ╼🠴n▭╾ ╼🠴c                  ▐
# ▌   MCP-out: □□□□□□□□  ╼🠴e▭╾ ╼🠴o                  ▐
# ▌          ┌────────────┐  ╼🠴c▭╾ ╼🠴n                  ▐
# ▌ RLY-out: │▪▪▪▪▪▪▪▪│   ╼🠴t▭╾ ╼🠴v                  ▐
# ▙▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▙▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▟
#
# CONNECTORS:
# - RLY-out: GND, relay 5...1 outputs (+12), 12V(testing), BLF-switch input (+3.3)
# - I2C-ext (for additional I2C device(s)): GND, +3.3, SCL, SDA
# - K-LINE-in: GND, k-line, +12
# PIN HEADER:
# - MCP-out: GPA 0...7 signals from MCP#2 (e.g. to control relays)
# - connect (board connection pins from Relay board to Main board):
#   BLFS wake (R->M), SCL, SDA, bike-on K-line (R<-M), +12 (R->M), GND, +3.3 (R<-M)
# - I2C-out (I2C output to OLED): GND, +3.3, SDA, SCL
# - UART pins: GND, +3.3, ESP-RX, ESP-TX
# - conv (12V to 3.3V step-down module): NC/SHDN, +12V(->conv), GND, +3.3V(<-conv)
# SWITCHES:
# - SW-wake-enable: bottom = allow ESP deepsleep wakeup by BLF-switch
# - TX/RX switch: left = ESP<->K-line; right = ESP<->UART pins
# - SCL/SDA switch: left = bus connected; right = disconnected
# - RST: hard reset ESP
# - FLASH: enable flash mode (press RST while holding FLASH)
# NOTE: pin descriptions from left to right / top to bottom


from net import NetServer
from ecu import CBR500Sniffer, ECUError
from ctrl import IOControl, blink
from uasyncio import get_event_loop, cancel, sleep_ms as d  # for shorting delays: "await d(1)"
from utime import ticks_diff as tdiff, ticks_ms as tms, sleep_ms as sleep_ms
from pwr import deepsleep
import machine
import gc
from ucollections import OrderedDict
# from sys import print_exception


# Constants:

_SHIFT_LIGHT_RPM_THRESH = 8000  # >= _ rpm -> shift light (for gear 1-5)
_DRIVING_SPEED_THRESH = 5  # assume waiting (or revving if throttle is used) if speed <= _ km/h
_SW_HOLD_THRESH = 1000  # switch held down for at least _ ms = long press
_SW_PWRUP_TIMEOUT = 7000  # switch must not be pressed at powerup. wait for at most _ ms, otherwise activate wlan
_NET_DEFAULT_ONTIME = 60  # network remains active for _ minutes by default if activated


# Additional Classes:

class MenuView:
    def __init__(self):
        self.__VS = 15  # vertical spacing constant
        self._idx_sel = -1  # currently selected option
        self._num_opt = 0  # number of options

    def selected(self):  # returns the current selection index
        return self._idx_sel

    def _sel_show(self, c):  # displays the current selection, c = color (0/1)
        io.oled.rect(-1, 34 + self._idx_sel * self.__VS, io.oled.w + 2, 14, c)

    def select_next(self):  # moves the selection one element further
        self._sel_show(0)  # remove current sel
        self._idx_sel = (self._idx_sel + 1) % self._num_opt
        self._sel_show(1)
        io.oled.show()

    def show(self):  # displays the menu major view with first item selected
        io.oled.text("Loading...")
        io.oled.show()

        io.oled.fill(0)
        io.oled.text("MENU", y=19, hspace=2)
        self._idx_sel = -1

        def opt(txt, **kw):  # displays an option
            self._idx_sel += 1
            io.oled.text(txt, y=37 + self._idx_sel * self.__VS, **kw)

        opt("Brakeflash")
        opt("Timer 0-100")
        opt("Turn LED " + ("off" if io.rly['LED'] else "on"))
        opt("Turn WiFi " + ("off" if net.active else "on"))
        opt("Warn Mode")
        opt("Close")

        self._num_opt = self._idx_sel + 1
        self._idx_sel = 0
        self._sel_show(1)
        io.oled.show()


class IOTasks:
    VIEW_ECU_ATTR = OrderedDict([  # add all ECU attributes (with description + unit) that should be displayed in a view
        ("ect", ("Engine\nCoolant", "° Celsius")),
        ("iat", ("Intake Air", "° Celsius")),
        ("map", ("Manifold\nPressure", "kPa")),
        ("bat", ("Battery", "Volt")),
        ("speed", ("Real\nSpeed", "km/h")),
    ])

    def __init__(self):
        self._area = None  # used to hold an OLED area to be cleared later (should be reset on each task change)
        self.task = None  # currently running oled view task gen-object (will be killed on view change)
        self.view = 1  # current view state (int), that may map to one task function (see __num_to_task())
        self.stay_on = False  # set to True if the ECU is expected to stay on because of the current view

    def _area_clear(self):
        if self._area is not None:
            io.oled.fill_rect(*(self._area + (0,)))  # clear previous area

    def _area_big(self, t, **kw):  # clears old area and displays the txt with big font
        self._area_clear()
        self._area = io.oled.big(t, **kw)
        io.oled.show()

    def _area_text(self, t, **kw):
        self._area_clear()
        self._area = io.oled.text(t, **kw)
        io.oled.show()

    async def brakeflash(self):
        io.oled.img("brake")
        io.oled.show()

        while True:
            io.set_rly('BL', True)
            sleep_ms(90)  # no intr (not to be canceled here)
            io.set_rly('BL', False)
            await d(70)  # todo: flashing not fast enough => use sleep_ms + replace while (await after every nth flash)

    async def timer(self):
        io.oled.img("timer", voff=-10)

        self._area_text("Slow down\nto 0 km/h", voff=38, lspace=1.2)
        while ecu.speed > 0:
            await d(500)

        self._area_text("Buffering...", voff=38)
        gc.collect()
        cbuf = io.oled.prefetch_chrs("0123456789.", 50)  # for faster oled update

        try:
            io.led_g(1)
            self._area_text("Let's go!", voff=38)
            while ecu.speed <= 0:
                await d(0)
        finally:  # also if cancelled
            io.led_g(0)

        tmr = tms()
        cdiff = -1
        io.oled.fill(0)
        while ecu.speed < 100:
            diff = round(tdiff(tms(), tmr) / 1000, 1)
            if diff >= 10:
                diff = int(diff)
            if diff != cdiff:
                cdiff = diff
                self._area_big(diff, buf=cbuf)
            await d(0)  # todo scheduling required for speed update, but may be too slow for blitting every 0.1 s

        await blink(io.led_g, 150)

    async def warn(self):
        self.stay_on = True
        io.oled.text("Hold switch\nto add horn" if self.view != -4 else "Press to stop", voff=40, lspace=1.2)

        try:
            while True:
                if self.view == -4:
                    io.set_rly('HO', not io.rly['HO'])

                for _ in range(3):  # horn on/off time = x * breaklight on/off time
                    io.set_rly('BL', not io.rly['BL'])

                    if io.rly['BL']:
                        self._area = io.oled.img("warn", voff=-6)
                    else:
                        self._area_clear()
                    io.oled.show()

                    await d(180)  # todo decrease because oled takes ~80 ms?
        finally:  # make sure to turn off relay when task gets cancelled
            io.set_rly('BL', False)
            if self.view == -4:
                io.set_rly('HO', False)
            self.stay_on = False

    async def view_gear(self):
        cgear = None  # currently displayed on OLED

        if not ecu.ready:
            await d(100)  # since view gear is the first task, it will be killed and restarted immediately

        while True:
            if not ecu.engine or ecu.rpm <= 0:  # engine not running (probably parking) or just starting up
                self._area_big('P')
                cgear = None
            elif ecu.idle or ecu.gear is None:
                cgear = None
                if ecu.sidestand:  # idling in parkmode
                    self._area_big('S')
                elif ecu.speed <= 0:  # idling while standing
                    self._area_big('-')
                else:  # idling while driving = probably shifting (maybe revving)
                    await blink(io.oled.power, 200, 350, 0)  # todo test
                    continue  # skip second yield
            else:
                if cgear != ecu.gear:
                    cgear = ecu.gear
                    self._area_big(cgear)
                if ecu.rpm > _SHIFT_LIGHT_RPM_THRESH and ecu.gear < 6:
                    await blink(io.led_b, 60, 60)  # shift light
                    continue  # skip second yield

            await d(0)

    async def view_ecu(self, attr):
        io.oled.text(IOTasks.VIEW_ECU_ATTR[attr][0], voff=-33, lspace=1.2)
        io.oled.text(IOTasks.VIEW_ECU_ATTR[attr][1], y=105)

        cval = None
        while True:
            val = getattr(ecu, attr)
            if cval != val:
                cval = val
                self._area_big(cval, voff=8)

            await d(100)

    async def _kill_task(self):
        if self.task is not None:
            await d(0)  # the task has to be started, otherwise cancel will block  todo: remove if possible
            cancel(self.task)
            await d(0)  # be sure it gets killed

        io.oled.fill(0)  # prepare oled for next task
        self._area = None  # no area in use

    async def _setup_task(self):  # starts the task that should run given self.view
        await self._kill_task()
        self.task = self.__num_to_task(self.view)
        if self.task is not None:
            loop.create_task(self.task)

    def __num_to_task(self, nr):  # returns view task: simple views (> 0), menu view (= 0), special modes (< 0)
        if nr == 1:
            return self.view_gear()
        elif 0 <= nr-2 < len(IOTasks.VIEW_ECU_ATTR):
            return self.view_ecu(list(IOTasks.VIEW_ECU_ATTR.keys())[self.view-2])
        elif nr == -1:
            return self.brakeflash()
        elif nr == -2:
            return self.timer()
        elif nr == -3 or nr == -4:
            return self.warn()
        # else invalid or menu: no view => None

    def __menu_sel_to_view(self, sel_idx):
        # Maps the index of a menu selection to the corresponding view and returns it. setup_task has to be called.
        # For some menu entries only one action takes place, but the view will return to gear view.
        if sel_idx == 0:  # brakeflash
            return -1
        elif sel_idx == 1:  # timer
            return -2
        elif sel_idx == 2:  # led on/off
            io.set_rly('LED', not io.rly['LED'])
        elif sel_idx == 3:  # wifi on/off
            if not net.active:
                start_net(0)  # until bike shutdown
            else:
                net.stop()
        elif sel_idx == 4:  # warn mode
            return -3

        return 1  # for selection 'Close', no selection (None/-1), and the ones without a specific view (autoreturn)

    async def run(self):  # reacts to switch state changes (eg by mode change), should run all the time
        menu = MenuView()

        if ecu.ready:  # this should not happen, but just in case the ECU is ready before display task starts, show gear
            await self._setup_task()  # initial task

        while True:
            if not ecu.ready and io.powered():  # wait for ECU to be connected (only if powered, otherwise don't wait)
                await self._kill_task()  # suspend current view task

                while not ecu.ready:
                    while ecu.connecting:
                        await blink(io.led_b, 100, 400)
                    else:
                        await d(300)

                await self._setup_task()  # now bring it up again

            if (not io.sw_pressed) & io.switch_pressed():  # new BLF switch press; binary and to avoid short-circuiting
                sw_tmr = tms()
                while tdiff(tms(), sw_tmr) < _SW_HOLD_THRESH and io.switch_pressed():  # until released or long press
                    await d(10)

                if io.sw_pressed:  # long press
                    if self.view > 0:
                        self.view = 0  # show menu
                        await self._kill_task()
                        menu.show()
                    elif self.view == 0:  # menu selection
                        self.view = self.__menu_sel_to_view(menu.selected())
                        await self._setup_task()
                    elif self.view == -3:  # silent warn
                        self.view = -4  # horn warn
                        await self._setup_task()  # restart required to load text
                    elif self.view == -2:  # timer
                        await self._setup_task()  # restart timer
                else:  # short press
                    if self.view > 0:
                        self.view += 1  # display next view
                        if self.view > 1+len(IOTasks.VIEW_ECU_ATTR):
                            self.view = 1
                        await self._setup_task()
                    elif self.view == 0:
                        menu.select_next()
                    else:  # exit special mode
                        self.view = 1
                        await self._setup_task()

            await d(0)  # let ECU work


# Global Variables:

loop = get_event_loop()
io = IOControl()
task_ctrl = IOTasks()
net = NetServer()
ecu = CBR500Sniffer(machine.UART(0, 10400))


# Functions:

def reset_loop():  # resets the asyncio eventloop by removing all coros from run and wait queue
    try:
        while True:
            loop.runq.popleft()
    except IndexError:
        pass
    try:
        while True:
            loop.waitq.pop([0, 0, 0])
    except IndexError:
        pass


def show_logo():
    io.oled.img("logo")
    io.oled.show()


async def task_ecu():
    errc = 0  # errors in a row

    while True:
        for table in ecu.TABLES:
            try:
                if not ecu.ready:
                    # io.led_g(1)
                    await ecu.init()
                    if not ecu.ready:  # timeout
                        await d(5000)
                        continue
                await ecu.update(table)
                # io.led_g(0)
                errc = 0  # update was successful
            except ECUError:
                errc += 1
                if errc >= 5:
                    for _ in range(5):
                        await blink(io.buzz, 500, 500)
                    break
            # except Exception as ex:  # should not happen
            #     debug("repr(ex)")
            #     raise ex
            await d(0)

        await d(50)  # not too many updates per second


async def task_net():  # runs until network is not active any more for some reason (if you stop)
    while net.active:  # will not change from inside this loop, but you can set it by calling net.stop() outside
        if net.client_count() == 0:
            await d(200)  # long delay, more time for ECU
        else:
            net.process()  # performs all updates server <-> clients (including relays sets, ...)
            await d(0)  # short delay


async def await_pwroff():
    while io.powered() or task_ctrl.stay_on:
        await d(1000)


async def await_pwron():
    while not io.powered():
        if not net.stay_on():
            io.off()
            deepsleep()
        await d(1000)


def start_net(dur=_NET_DEFAULT_ONTIME):
    io.oled.fill(0)
    # io.oled.text("Bringing\nWiFi up...", lspace=1.2)
    io.oled.text("Network is\nnot working\nin this version", lspace=1.2)
    io.oled.show()

    # net.start(dur)  # at least this time (sec) (more if bike powerdown is later)  # TODO
    # loop.create_task(task_net())
    sleep_ms(2000)

    io.oled.clear()


def run():
    if machine.reset_cause() == machine.HARD_RESET:
        io.off()
        show_logo()
    elif machine.reset_cause() == machine.SOFT_RESET:  # this must be a webapp reset, so start it again
        start_net()
        show_logo()
    else:
        tmr = tms()
        while io.switch_pressed():  # wait for switch to be released. NC = remains on until timeout
            if tdiff(tms(), tmr) > _SW_PWRUP_TIMEOUT:  # brakelight flash switch NC or hold down long for special fun
                start_net()
                break
        else:  # BLF switch not pressed (or long enough)
            if not io.powered():  # bike not powered on startup; was motion wakeup
                io.off()  # nothing should be on, but ok...
                deepsleep()
            else:
                show_logo()

    while True:
        if io.powered():  # bike (and maybe network) running
            loop.create_task(task_ctrl.run())  # first start display
            loop.create_task(task_ecu())
            loop.run_until_complete(await_pwroff())  # wait for poweroff (bike shutdown)

            # -> bike powered off

            # only required if net started afterwards, so no wrong data is displayed:
            reset_loop()  # clear ecu and ctrl task as these are not required now
            io.clear()
            ecu.reset()

            if io.switch_pressed():  # switch held down during shutdown
                start_net()
            elif not net.stay_on():
                io.off()
                net.stop()  # stop running network (explicitly kick clients), we want to deepsleep
                deepsleep()
            else:  # stay_on time not over -> reschedule task
                loop.create_task(task_net())

        # -> only network running, should stay on (and check for powerup meanwhile)
        loop.run_until_complete(await_pwron())
        # waits for power on, then continue outer loop; goes to deepsleep if timeout exceeded


def main():
    try:
        run()
    except Exception as e:
        try:
            io.oled.println(str(e))
        except:
            pass
        raise e
