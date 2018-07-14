# NOTE: NEXT TIME USE STANDARD IMPORTS INSTEAD OF FROM-IMPORTS. FROM HAS NO ADVANTAGE

# Required modules:
# User: ecu, ctrl, net, pwr
# Drivers (semi-user): webserver, mcp23017 (don't use general mcp because of code length)
# Drivers: uasyncio
# Other files: html folder

#from net import NetServer #todo
from ecu import CBR500Sniffer, ECUError
from ctrl import IOControl, blink
from pwr import deepsleep
from uasyncio import get_event_loop, sleep_ms as d  # for shorting delays: "await uasyncio.sleep_ms(1)" -> "await d(1)"
from machine import UART
from utime import ticks_diff as tdiff, ticks_ms as tms, sleep_ms as sleep_ms
from math import log


_SHIFT_LIGHT_RPM_THRESH = 6000  # rpm
_SW_HOLD_THRESH = 1000  # switch held down for at least _ ms -> special mode 1 (additional _ ms -> mode 2, 3, ...)
_SW_BL_FLASH_COUNT = 8  # flash break light _ times when pressed
_SW_PWRUP_TIMEOUT = 8000  # switch must not be pressed at powerup. wait for at most _ ms, otherwise special function
_NET_ACTIVE_TIME_MIN = 15  # minutes if mode is 0; otherwise network remains active for <mode> h (BLF switch held on SD)


_UART0 = UART(0, 115200)  # global UART0 object, can be reinitialized, given baudrate is for REPL
loop = get_event_loop()
ecu = CBR500Sniffer(_UART0)
ctrl = IOControl()
#net = NetServer()  # start by running network handler, stop by calling net.stop() todo


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
    err_counter = 0  # errors in a row

    async def task_blink():
        while ecu.connecting:
            await blink(ctrl.seg_dot, 100, 400)

    while True:
        for tab in ecu.regMap:
            try:
                if not ecu.ready:
                    ctrl.led_y(1)  # todo y LED indicates ECU not connected
                    ecu.connecting = True  # not required, but otherwise task_blink will exit its blinking loop
                    loop.create_task(task_blink())
                    await ecu.init()
                    if not ecu.ready:  # timeout
                        await d(5000)
                await ecu.update(tab)
                ctrl.led_y(0)  # todo
                err_counter = 0  # update was successful
            except ECUError:
                err_counter += 1
                if err_counter >= 10:
                    ctrl.seg_char('E')
                    sleep_ms(5000)
                    break
            except Exception as ex:
                ctrl.seg_char('F')  # TODO
                raise ex

            await d(100)  # not too many updates per second  TODO too slow?

        await d(0)  # todo req?


async def task_ctrl():  # mode based on switch (e.g. break light flash)
    sw_tmr = tms()  # timer to check duration of switch down
    lap_tmr = tms()  # timer for special mode 0-100 km/h measurement (reset at 0 km/h)

    while True:
        # check switch (BLF and special modes):
        if ctrl.sw_pressed != ctrl.sw_pressed():  # just pressed or released (state is updated)
            if ctrl.sw_pressed:  # just pressed:
                sw_tmr = tms()  # set timer to check duration later
                if ctrl.mode != 0:  # switch pressed while in special mode
                    ctrl.mode = -ctrl.mode  # to reset from any special mode to mode 0
                    ctrl.led_g(1)
            else:  # just released -> apply mode now
                if ctrl.mode < 0:
                    ctrl.mode = 0  # reset to mode 0 without break light flashing
                    ctrl.led_g(0)
                elif ctrl.mode == 0:
                    for _ in range(_SW_BL_FLASH_COUNT):
                        ctrl.set_rly('BL', 1)
                        sleep_ms(90)
                        ctrl.set_rly('BL', 0)
                        sleep_ms(70)
                elif ctrl.mode == 1:
                    lap_tmr = tms()  # this val is only used if this mode is set when driving and then reaching >100
                elif ctrl.mode == 7:  # activate network (reactivate if already active, handler will do the job)
                    loop.create_task(task_net())
                elif ctrl.mode == 8:  # disable the network iface
                    net.stop()

                ctrl.seg_clear()
        elif ctrl.sw_pressed and ctrl.mode >= 0:  # held down -> check duration
            if tdiff(tms(), sw_tmr) >= _SW_HOLD_THRESH:  # special mode
                ctrl.mode += 1
                ctrl.seg_digit(ctrl.mode % 10)
                ctrl.led_g(1)
                sleep_ms(150)  # TODO: yield if other handlers dont set 7seg
                ctrl.led_g(0)
                sw_tmr = tms()  # for next special mode
            if ctrl.mode != 0:
                await d(0)  # let ECU work
                continue  # skip io.part, cause increasing special mode is non-interruptable on 7-seg

        # handle cockpit stuff:
        if ecu.ready:  # ECU connected
            if ctrl.mode == 1:  # set timer and green LED based on speed
                if ecu.speed == 0:
                    lap_tmr = tms()
                    ctrl.led_g(1)
                elif ecu.speed >= 100:
                    lap_time = tdiff(tms(), lap_tmr)  # e. g. 15762 ms (= 15.8s)
                    ctrl.led_g(1)
                    lt_s = lap_time // 1000  # seconds (front part) e.g. 15
                    lt_h = round((lap_time - lt_s * 1000) / 100)  # hundreth e.g. 8
                    ctrl.seg_clear()
                    sleep_ms(1000)  # TODO: yield if other handlers dont set 7seg
                    ctrl.seg_show_num(lt_s, lt_h)
                    ctrl.led_g(0)
                    ctrl.mode = 0
                    #del lap_tmr  # will be reset when mode is set to 1 again
                elif tdiff(tms(), lap_tmr) > 60000:  # reset mode as it does not seem to be used
                    ctrl.mode = 0
                    await blink(ctrl.led_g)
                else:  # measurement
                    ctrl.led_g(0)

            if not ecu.engine or ecu.rpm <= 0:  # engine not running (parking) or engine just starting up
                # io.seg_clear()
                ctrl.seg_char('P')  # todo debug
            elif ecu.idle or ecu.gear is None:
                if ecu.sidestand or ecu.speed < 5 and ecu.tp > 0:  # revving
                    ctrl.seg_circle()
                    await d(int(-28*log(ecu.rpm) + 262))
                    continue  # skip second yield
                else:
                    ctrl.seg_char('-')
            else:
                # shift light (= flashing gear on display) if required:
                if ecu.rpm > _SHIFT_LIGHT_RPM_THRESH:
                    ctrl.seg_clear()
                    await d(50)
                ctrl.seg_digit(ecu.gear)
                #await d(12)  # todo: remove, as second yield might be ok?
                #continue  # skip second yield

        await d(0)  # let ECU work


async def task_net():  # runs until network is not active any more for some reason (if you stop)
    return #todo
    if net.active:  # another task_net is already running. stop it by calling
        net.stop()  # which will cause their loops (see beyond) to exit
        await d(1000)  # just make sure the another handlers are called meanwhile (delay >= all other delays below)

    net.start()
    while net.active:  # will not change from inside this loop, but you can set it by calling net.stop() outside
        if net.client_count() == 0:
            await d(500)  # long delay, more time for ECU
        else:
            net.update()  # performs all updates server <-> clients (including relays sets, ...)
            await d(0)  # short delay


async def await_pwr(val, limit=12*60):
    # checks the bike power every once in a while and return only if powered state is <val>.
    # limit is used to specify a time limit in minutes, so the chip will go to deepsleep after this time.
    # by default, the bike waits for poweroff or poweron for at most 12 hours (no longer drives expected)
    limit *= 60000  # minutes to ms
    tmr = tms()
    while ctrl.powered() != val:
        if tdiff(tms(), tmr) > limit:
            ctrl.reset()
            deepsleep()
        await d(1000)  # should be <= SW_HOLD_THRESH


def main():
    # todo: GPS/GSM test, maybe SMS

    tmr = tms()
    while ctrl.sw_pressed():  # wait for switch to be released. NC = remains on until timeout
        if tdiff(tms(), tmr) > _SW_PWRUP_TIMEOUT:  # break light flash switch NC or hold down long for special fun
            loop.create_task(task_net())  # special fun = network active while bike powered
            break
    else:  # not pressed long enough
        if not ctrl.powered():  # bike not powered on startup; was hard reset or motion wakeup
            deepsleep()
    del tmr

    while True:
        if ctrl.powered():  # bike (and maybe network) running
            loop.create_task(task_ecu())
            loop.create_task(task_ctrl())
            loop.run_until_complete(await_pwr(False))  # wait for poweroff

            # -> bike powered off
            ctrl.reset()
            if ctrl.sw_pressed():  # switch held down during shutdown
                # -> keep network interface (relay control) active for at least <net_time> ms, then deepsleep
                reset_loop()  # clear ecu and ctrl task as these are not required now
                loop.create_task(task_net())  # and start network task (already running?, will do a restart, but ok...)
                # see beyond
            elif ctrl.mode == 10:
                return  # to console
            else:
                deepsleep()

        # -> only network running
        loop.run_until_complete(await_pwr(True, ctrl.mode * 60 if ctrl.mode > 0 else _NET_ACTIVE_TIME_MIN))
        # waits for power on, then continue outer loop; goes to deepsleep if timeout exceeded


if __name__ == '__main__':
    # dupterm(None)  # disable output/input on WebREPL
    # dupterm(None, 1)  # disable REPL (v1.9.4)

    exc = None
    try:
        main()
    except Exception as e:
        exc = e  # save exception that happend in my program using UART0

    _UART0.init(115200, bits=8, parity=None, stop=1)  # so that it fits REPL again

    if exc is not None:
        raise exc  # show the exception on REPL

    # dupterm(UART0)  # enable WebREPL
    # dupterm(UART0, 1)  # enable REPL (v1.9.4)
