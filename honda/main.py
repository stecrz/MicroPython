# NOTE: NEXT TIME USE STANDARD IMPORTS INSTEAD OF FROM-IMPORTS. FROM HAS NO ADVANTAGE

# Required modules:
# a) Self-defined:
#    - ecu
#    - ctrl
#    - net
#    - pwr
# b) Drivers (modified from others):
#    - webserver (see Micropython/websocketserver/webserver on this PC)
#    - mcp23017 (a smaller version of Tony DiCola's general MCP driver)
# c) Drivers:
#    - uasyncio (core library)
# d) Other files (not frozen into flash):
#    - html (complete folder)
#    - netconf.json

from net import NetServer
from ecu import CBR500Sniffer, ECUError
from ctrl import IOControl, blink
from uasyncio import get_event_loop, sleep_ms as d  # for shorting delays: "await uasyncio.sleep_ms(1)" -> "await d(1)"
from utime import ticks_diff as tdiff, ticks_ms as tms, sleep_ms as sleep_ms
from pwr import deepsleep
import machine


_SHIFT_LIGHT_RPM_THRESH = 8000  # rpm
_SW_HOLD_THRESH = 1000  # switch held down for at least _ ms -> special mode 1 (additional _ ms -> mode 2, 3, ...)
_SW_BL_FLASH_COUNT = 7  # flash break light _ times when pressed
_SW_PWRUP_TIMEOUT = 7000  # switch must not be pressed at powerup. wait for at most _ ms, otherwise activate wlan
_NET_DEFAULT_ONTIME = 15  # minutes if mode is 0; otherwise network remains active for <mode> h (BLF switch held on SD)
_DRIVING_SPEED_THRESH = 7  # assume waiting (or revving if throttle is used) if speed <= _ km/h

UART0 = machine.UART(0, 115200)  # global UART0 object, can be reinitialized, given baudrate doesn't matter
loop = get_event_loop()
ctrl = IOControl()
ecu = CBR500Sniffer(UART0)
net = NetServer()


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


async def task_ecu():
    # while True:
    #     await blink(ctrl.seg_dot, 100, 400)

    err_counter = 0  # errors in a row

    async def task_blink():
        while ecu.connecting:
            await blink(ctrl.seg_dot, 100, 400)

    while True:
        for tab in ecu.regMap:
            if ctrl.mode == 1:  # alert mode, don't scan ECU
                await d(2000)
                continue

            try:
                if not ecu.ready:
                    # ctrl.led_y(1)
                    ecu.connecting = True  # not req, but otherwise task_blink will exit its blinking loop  # todo test wihout this line
                    loop.create_task(task_blink())
                    await ecu.init()
                    if not ecu.ready:  # timeout
                        await d(5000)
                        continue
                await ecu.update(tab)
                # ctrl.led_y(0)
                err_counter = 0  # update was successful
            except ECUError as ex:
                err_counter += 1
                if err_counter >= 5:
                    ctrl.seg_char('E')
                    ctrl.beep(5000)
                    ctrl.seg_clear()
                    break
            except Exception as ex:  # should not happen
                ctrl.beep(5000)
                ctrl.seg_char('F')  # TODO
                raise ex

            await d(100)  # TODO not too many updates per second  TODO too slow?

        await d(0)  # todo


async def task_ctrl():  # mode based on switch (e.g. break light flash)
    ctrl.sw_pressed = False
    sw_tmr = tms()  # timer to check duration of switch down
    lap_tmr = tms()  # timer for special mode 0-100 km/h measurement (reset at 0 km/h)

    while True:
        # check switch (BLF and special modes):
        if ctrl.sw_pressed != ctrl.switch_pressed():  # just pressed or released (state is updated after methodcal)
            if ctrl.sw_pressed:  # just pressed:
                sw_tmr = tms()  # set timer to check duration later
                if ctrl.mode != 0:  # switch pressed while in special mode
                    ctrl.mode = -ctrl.mode  # to reset from any special mode to mode 0
                    ctrl.led_g(1)
            else:  # just released -> apply mode now
                if ctrl.mode < 0:
                    if ctrl.mode == -1:  # was mode 1 before
                        ctrl.set_rly('BL', False)
                    ctrl.mode = 0  # reset to mode 0 without break light flashing
                    ctrl.led_g(0)
                elif ctrl.mode == 0:
                    for _ in range(_SW_BL_FLASH_COUNT):
                        ctrl.set_rly('BL', True)
                        sleep_ms(90)
                        ctrl.set_rly('BL', False)
                        sleep_ms(70)
                elif ctrl.mode == 2:
                    lap_tmr = tms()  # this val is only used if this mode is set when driving and then reaching >100
                elif ctrl.mode == 7:  # activate network if not active (no min active time -> until pwrdown)
                    start_net(0)  # already running? just change stayon time to "until poweroff"
                    ctrl.mode = 0  # instant reset
                elif ctrl.mode == 8:  # disable the network iface
                    net.stop()
                    ctrl.mode = 0  # instant reset

                ctrl.seg_clear()
        elif ctrl.sw_pressed and ctrl.mode >= 0:  # held down -> check duration
            if tdiff(tms(), sw_tmr) >= _SW_HOLD_THRESH:  # special mode
                ctrl.mode += 1
                ctrl.seg_digit(ctrl.mode % 10)
                ctrl.led_g(1)
                await d(150)
                ctrl.led_g(0)
                sw_tmr = tms()  # for next special mode
            if ctrl.mode != 0:
                await d(0)  # let ECU work
                continue  # skip io.part, cause increasing special mode is non-interruptable on 7-seg

        # mode-dependent, but ecu independet stuff:
        if ctrl.mode == 1:  # warn mode
            ctrl.set_rly('BL', not ctrl.rly['BL'])
            await d(180)

        # handle cockpit stuff depending on ecu:
        if ecu.ready:  # ECU connected
            if ctrl.mode == 2:  # set timer and green LED based on speed
                if ecu.speed == 0:
                    lap_tmr = tms()
                    ctrl.led_g(1)
                elif ecu.speed >= 100:
                    lap_time = tdiff(tms(), lap_tmr)  # e. g. 15762 ms (= 15.8s)
                    ctrl.led_g(1)
                    lt_s = lap_time // 1000  # seconds (front part) e.g. 15
                    lt_h = round((lap_time - lt_s * 1000) / 100)  # hundreth e.g. 8
                    ctrl.seg_clear()
                    await d(1000)
                    ctrl.seg_show_num(lt_s, lt_h)
                    ctrl.led_g(0)
                    ctrl.mode = 0
                    del lap_tmr  # will be reset when mode is set to 1 again
                elif tdiff(tms(), lap_tmr) > 60000:  # reset mode as it does not seem to be used
                    ctrl.mode = 0
                    await blink(ctrl.led_g)
                else:  # measurement
                    ctrl.led_g(0)

            if not ecu.engine or ecu.rpm <= 0:  # engine not running (probably parking) or engine just starting up
                ctrl.seg_char('-')
            elif ecu.idle or ecu.gear is None:
                if ecu.sidestand or (ecu.speed <= _DRIVING_SPEED_THRESH and ecu.tp > 0):  # idle in parkmode or revving
                    ctrl.seg_circle()
                    # await d(int(-28*log(ecu.rpm) + 262))  # from math import log
                    await d(int(6.05e-14*ecu.rpm**4 - 1.52e-9*ecu.rpm**3 + 1.422e-5*ecu.rpm**2 - 0.0624*ecu.rpm + 124))
                elif ecu.speed <= _DRIVING_SPEED_THRESH:  # idling, but not revving
                    await d(300)  # let prev gear display shortly (first time) / let ECU work
                    ctrl.seg_char('-')
                else:
                    await ctrl.seg_flash(250)
                continue  # skip second yield
            else:
                # shift light if required:
                ctrl.seg_digit(ecu.gear)
                if ecu.rpm > _SHIFT_LIGHT_RPM_THRESH and ecu.gear < 6:
                    await ctrl.seg_flash(60)
                    continue  # skip second yield

        await d(0)  # let ECU work


async def task_net():  # runs until network is not active any more for some reason (if you stop)
    while net.active:  # will not change from inside this loop, but you can set it by calling net.stop() outside
        if net.client_count() == 0:
            await d(200)  # long delay, more time for ECU
        else:
            net.process()  # performs all updates server <-> clients (including relays sets, ...)
            await d(0)  # short delay


async def await_pwroff():
    while ctrl.powered() or ctrl.mode == 1:  # don't shutdown ESP if warn mode is active
        await d(1000)  # should be <= SW_HOLD_THRESH


async def await_pwron():
    while not ctrl.powered():
        if not net.stay_on():
            ctrl.off()
            deepsleep()
        await d(1000)


def start_net(dur=_NET_DEFAULT_ONTIME):
    ctrl.led_y(1)
    net.start(dur)  # at least this time (sec) (more if bike powerdown is later)
    loop.create_task(task_net())
    ctrl.led_y(0)


def main():
    if machine.reset_cause() == machine.HARD_RESET:
        ctrl.off()
    elif machine.reset_cause() == machine.SOFT_RESET:  # this must be a webapp reset, so start it again
        start_net()
    else:
        tmr = tms()
        while ctrl.switch_pressed():  # wait for switch to be released. NC = remains on until timeout
            if tdiff(tms(), tmr) > _SW_PWRUP_TIMEOUT:  # break light flash switch NC or hold down long for special fun
                start_net()
                break
        else:  # not pressed long enough
            if not ctrl.powered():  # bike not powered on startup; was motion wakeup
                ctrl.off()  # nothing should be on, but ok...
                deepsleep()

    while True:
        if ctrl.powered():  # bike (and maybe network) running
            loop.create_task(task_ecu())
            loop.create_task(task_ctrl())
            loop.run_until_complete(await_pwroff())  # wait for poweroff (bike shutdown)

            # -> bike powered off

            # only required if net started afterwards, so no wrong data is displayed:
            reset_loop()  # clear ecu and ctrl task as these are not required now
            ctrl.clear()
            ecu.reset()

            if ctrl.switch_pressed():  # switch held down during shutdown
                start_net(ctrl.mode * 60 if ctrl.mode > 0 else _NET_DEFAULT_ONTIME)  # will only set tmr if alr active
            elif ctrl.mode == 10:
                ctrl.off()
                return  # to console
            else:
                if not net.stay_on():
                    ctrl.off()
                    net.stop()  # stop running network (explicitly kick clients), we want to deepsleep
                    deepsleep()
                else:  # stay_on time not over -> reschedule task
                    loop.create_task(task_net())

        # -> only network running, should stay on (and check for powerup meanwhile)
        loop.run_until_complete(await_pwron())
        # waits for power on, then continue outer loop; goes to deepsleep if timeout exceeded


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


# NOTES:
# reading from ECU only shows valid values if HISS system is disarmed. disarming only possible until ESP is connected
# erase_flash not working? disconnect ESP from all power sources, then reconnect
