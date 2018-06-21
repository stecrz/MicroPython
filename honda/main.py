from machine import Pin, I2C, SPI
from utime import ticks_diff as tdiff, ticks_ms as tms, sleep_ms
#from display import Display
from ecu import CBR500Sniffer
from io import OutputController
from power import setup_motion_switch


ADDR_MCP1 = 0x22
ADDR_MCP2 = 0x23
CS = 15
SCL = 5
SDA = 4

SHIFT_LIGHT_RPM_THRESH = 8000


def main():
    #display = Display(I2C(-1, Pin(5), Pin(4)), 128, 64)
    #display.clear()

    # setup required buses:
    i2c = I2C(-1, Pin(SCL), Pin(SDA))
    #spi = SPI(1, polarity=0, phase=0)
    #cs = Pin(CS, Pin.OUT)

    # initialize all my interfaces:
    ecu = CBR500Sniffer()
    cockpit = OutputController(i2c, ADDR_MCP1)
    #setup_motion_switch(spi, cs)

    cockpit.seg_char('C')
    tmr_init = tms()
    while not ecu.init():  # try to connect to ECU
        cockpit.seg_dot()  # blink the 7-segment dot to indicate activity
        if tdiff(tms(), tmr_init) > 10000:  # check for connection timeout
            cockpit.seg_dot(0)
            cockpit.seg_char('L')
    cockpit.seg_char('A')
    cockpit.seg_dot(0)  # switch dot off (if on)

    while True:
        try:
            while not ecu.ready:
                cockpit.seg_char('F')
                return
                # display.print("Connect...")
                # if not ecu.init():
                #     display.println(" Fail!")
                # else:
                #     display.println(" O.K.")

            # logmsg = ecu.update()
            # if logmsg != "":
            #     #with open("honda.log", "a") as file:
            #     #    file.write(logmsg)
            #     display.println(logmsg)

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
            #display.println(repr(ex))
            sleep_ms(500)


if __name__ == '__main__':
    main()
