from ecu import CBR500Sniffer, ECUError
from uasyncio import get_event_loop, sleep_ms as d
from utime import ticks_diff as tdiff, ticks_ms as tms, sleep_ms as sleep_ms
import machine
import display  # move ssd1306_vert.py & display.py to ESP first!


loop = get_event_loop()

UART0 = machine.UART(0, 115200)
ecu = CBR500Sniffer(UART0)

i2c = machine.I2C(-1, machine.Pin(5), machine.Pin(4))
oled = display.Display(i2c, 128, 64)


async def task_ecu():
    oled.println("task_ecu()")
    err_counter = 0

    while True:
        for table in ecu.TABLES:
            try:
                if not ecu.ready:
                    oled.println("init()")
                    await ecu.init()
                    if not ecu.ready:
                        oled.println("TIMEOUT")
                        await d(3000)
                        continue
                oled.println("update(%s)" % str(table))
                await ecu.update(table)
                oled.println("OK")
                err_counter = 0
            except ECUError:
                err_counter += 1
                oled.println("ERR: " + repr(ECUError))
                if err_counter >= 5:
                    break
            await d(0)

        await d(50)
        
    oled.println("Program Exit")

        
loop.run_until_complete(task_ecu())
