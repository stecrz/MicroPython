from machine import Pin, I2C, SPI, UART
from os import dupterm  # for enabling/disabling REPL
from utime import ticks_diff as tdiff, ticks_ms as tms, sleep_ms
from display import Display
from ecu import CBR500Sniffer
from io import OutputController
from power import setup_motion_switch


ADDR_MCP1 = 0x22
ADDR_MCP2 = 0x23
CS = 15
SCL = 5
SDA = 4

SHIFT_LIGHT_RPM_THRESH = 8000


uart0 = UART(0, 115200)  # global UART0 object, can be reinitialized, given baudrate is for REPL


def main():
    # setup required buses:
    i2c = I2C(-1, Pin(SCL), Pin(SDA))
    spi = SPI(1, polarity=0, phase=0)
    cs = Pin(CS, Pin.OUT)

    # initialize all my interfaces:
    display = Display(i2c, 128, 64)
    ecu = CBR500Sniffer(uart0)
    cockpit = OutputController(i2c, ADDR_MCP1)
    setup_motion_switch(spi, cs)

    display.println("Hello")
    cockpit.led_y(1)
    cockpit.seg_char('C')
    if not ecu.init():  # try to connect to ECU
        display.println("init failed")
        cockpit.seg_char('L')
        return
    cockpit.seg_char('A')
    display.println("init ok")
    cockpit.seg_dot(0)  # switch dot off (if on)
    cockpit.led_y(0)

    while True:
        try:
            if not ecu.ready:
                cockpit.seg_char('F')
                display.print("Connect...")
                if not ecu.init():
                    display.println(" Fail!")
                    return
                else:
                    display.println(" O.K.")

            ecu.update()

            if not ecu.engine or ecu.rpm <= 0:  # engine not running (parking) or engine just starting up
                #cockpit.seg_clear()
                cockpit.seg_char('P')
            elif ecu.sidestand:  # 1000-9000 RPM -> sleep time 90-30 ms
                cockpit.seg_char('S')
            elif ecu.idle or ecu.gear is None:
                if ecu.speed == 0 and ecu.tp > 0:  # revving
                    cockpit.seg_circle(500, clockwise=False)
                else:
                    cockpit.seg_char('-')
            else:
                cockpit.seg_digit(ecu.gear)
                # shift light if required:
                if ecu.rpm > SHIFT_LIGHT_RPM_THRESH:
                    cockpit.seg_dot_blink()
        except Exception as ex:
            cockpit.seg_char('E')
            display.println(repr(ex))


if __name__ == '__main__':
    # dupterm(None)  # disable output/input on WebREPL
    # dupterm(None, 1)  # disable REPL (v1.9.4)

    ex = None
    try:
        main()
    except Exception as e:
        ex = e  # save exception that happend in my program using UART0

    uart0.init(115200, bits=8, parity=None, stop=1)  # so that it fits REPL again

    if ex is not None:
        raise ex  # show the exception on REPL

    # dupterm(uart0)  # enable WebREPL
    # dupterm(uart0, 1)  # enable REPL (v1.9.4)
