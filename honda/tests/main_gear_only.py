# Minimal version of main.py - shows gear only

# Required modules:
# a) Self-defined:
#    - ecu
#    - ctrl
#    - pwr
# b) Drivers (modified from others):
#    - mcp23017 (minimal version of mcp.py)
#    - ssd1306_vert (MicroPython/display/ssd1306_vert.py)
# c) Drivers:
#    - uasyncio (clone from https://github.com/micropython/micropython-lib)
# d) Other files (not frozen into flash):
#    - img/ (contains images for OLED, e.g. font letters)

from ecu import CBR500Sniffer, ECUError
from ctrl import IOControl, blink
from uasyncio import get_event_loop, sleep_ms as d  # for shorting delays: "await uasyncio.sleep_ms(1)" -> "await d(1)"
from utime import ticks_diff as tdiff, ticks_ms as tms, sleep_ms as sleep_ms
from pwr import deepsleep
import machine


_SHIFT_LIGHT_RPM_THRESH = 8000  # >= _ rpm -> shift light (for gear 1-5)
_SW_HOLD_THRESH = 1000  # switch held down for at least _ ms -> special mode 1 (additional _ ms -> mode 2, 3, ...)
_SW_BL_FLASH_COUNT = 8  # flash break light _ times when pressed
_SW_PWRUP_TIMEOUT = 7000  # switch must not be pressed at powerup. wait for at most _ ms, otherwise activate wlan
_NET_DEFAULT_ONTIME = 30  # minutes if mode is 0; otherwise network remains active for <mode> h (BLF switch held on SD)
_DRIVING_SPEED_THRESH = 5  # assume waiting (or revving if throttle is used) if speed <= _ km/h

loop = get_event_loop()
io = IOControl()
UART0 = machine.UART(0, 115200)  # global UART0 object, can be reinitialized, given baudrate doesn't matter
ecu = CBR500Sniffer(UART0)


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


def show(num):
    io.oled.fill(0)
    io.oled.big(num)
    io.oled.show()


def debug(txt):
    while len(txt) > 12:
        debug(txt[:12])
        txt = txt[12:]
    io.oled.scroll(0, -12)
    io.oled.fill_rect(0, io.oled.h-20, io.oled.w, 20, 0)
    txt = str(txt)
    if len(txt) > 0:
        io.oled.text(txt, y=io.oled.h-20, align='c')
    io.oled.show()


async def task_ecu():
    errc = 0  # counter for errors in a row

    while True:
        for table in ecu.TABLES:
            try:
                if not ecu.ready:
                    await ecu.init()
                    if not ecu.ready:  # timeout
                        await d(5000)
                        continue
                await ecu.update(table)
                io.led_b(0)
                errc = 0  # update was successful
            except ECUError:
                errc += 1
                if errc >= 5:
                    blink(io.buzz, 5000)
                    break
            # except Exception as ex:
            #     debug("repr(ex)")
            #     raise ex
            await d(0)

        await d(50)  # not too many updates per second


async def task_gear_indicator():  # display gear on 7-seg, runs all the time, waits while ECU not ready
    while True:
        if not ecu.ready:
            io.oled.img("logo")
            io.oled.show()

            while not ecu.ready:  # wait for ECU to be connected
                await d(500)
                while ecu.connecting:
                    await blink(io.led_g, 100, 400)

        if not ecu.engine or ecu.rpm <= 0:  # engine not running (probably parking) or just starting up
            show('-')
        elif ecu.idle or ecu.gear is None:
            if ecu.sidestand or (ecu.speed <= _DRIVING_SPEED_THRESH and ecu.tp > 0):  # idling in parkmode or revving
                show(':')
            elif ecu.speed <= _DRIVING_SPEED_THRESH:  # idling (not revving)
                show('N')
            else:
                await io.oled.blink(250)
        else:
            show(ecu.gear)
            if ecu.rpm > _SHIFT_LIGHT_RPM_THRESH and ecu.gear < 6:
                await blink(io.led_b, 60, 60)  # shift light
                continue  # skip second yield

        await d(0)  # let ECU work


async def await_pwroff():
    while io.powered():
        await d(1000)  # should be <= SW_HOLD_THRESH


def main():
    if machine.reset_cause() == machine.HARD_RESET:
        io.off()
    elif machine.reset_cause() == machine.SOFT_RESET:
        pass  # impossible in this version
    else:
        if not io.powered():  # bike not powered on startup; was motion wakeup
            io.off()  # nothing should be on, but ok...
            deepsleep()

    loop.create_task(task_ecu())
    loop.create_task(task_gear_indicator())
    loop.run_until_complete(await_pwroff())  # wait for poweroff (bike shutdown)

    # -> bike powered off
    io.off()
    deepsleep()


if __name__ == '__main__':
    # dupterm(None)  # disable output/input on WebREPL
    # dupterm(None, 1)  # disable REPL (v1.9.4)

    exc = None
    try:
        main()
    except Exception as e:
        exc = e  # save exception that happend in my program using UART0

    UART0.init(115200, bits=8, parity=None, stop=1)  # so that it fits REPL again

    if exc is not None:
        raise exc  # show the exception on REPL

    # dupterm(UART0)  # enable WebREPL
    # dupterm(UART0, 1)  # enable REPL (v1.9.4)
