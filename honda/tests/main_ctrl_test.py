import ctrl
from utime import ticks_diff as tdiff, ticks_ms as tms, sleep_ms as sleep_ms


io = ctrl.IOControl()


def task_view_menu():  # todo add async
    io.oled.fill(0)
    io.oled.text("MENU", y=14, hspace=3)

    VSPACING = 13
    idx_sel = -1

    def blit_opt(txt, **kw):
        nonlocal idx_sel
        idx_sel += 1
        io.oled.text(txt, y=30 + idx_sel * VSPACING, **kw)

    blit_opt("Brakeflash")
    blit_opt("Turn LED " + ("on" if True else "off"))  # todo read relay state
    blit_opt("Turn WiFi " + ("on" if False else "off"))  # todo read relay state
    blit_opt("Timer 0-100")
    blit_opt("Silent Warn")
    blit_opt("Horn Warn")
    blit_opt("Close")

    IDX_SEL_MAX = idx_sel

    # idx in range of possible selections (0-max), show = 0 or 1
    def sel_draw(idx, show):
        io.oled.rect(-1, 28 + idx * VSPACING, io.oled.w+2, 12, show)

    def sel_move():
        nonlocal idx_sel
        sel_draw(idx_sel, 0)
        idx_sel += 1
        if idx_sel > IDX_SEL_MAX:
            idx_sel = 0
        sel_draw(idx_sel, 1)
        io.oled.show()

    sel_draw(IDX_SEL_MAX, 1)  # initial selection: back
    io.oled.show()

    # todo: loop for checking if button pressed short (move) or long (-> break loop)
    # todo: meanwhile check: reblit menu if wifi/led state changes (over network)
    # todo: also break loop if no action for 12 sec
    for i in range(4):
        sleep_ms(400)
        sel_move()

    io.oled.fill(0)
    if idx_sel == 0:
        io.oled.img("brake")
        io.oled.show()
        # todo flash until key pressed
    elif idx_sel in (4, 5):
        for i in range(20):  # todo async endless
            io.oled.img("warn")
            io.oled.show()
            sleep_ms(150)
            io.oled.fill(0)
            io.oled.show()
            sleep_ms(100)
    elif idx_sel == 3:
        io.oled.img("timer", voff=-10)
        if True:  # todo: kmh is > 0
            io.oled.text("Slow down", y=io.oled.h-35)
            io.oled.text("to 0 km/h", y=io.oled.h-26)
            io.oled.show()

            while False:  # todo: kmh > 0 and not pressed button
                pass
            sleep_ms(1000)  # todo

        io.oled.fill_rect(0, io.oled.h - 35, io.oled.w, 35, 0)
        io.oled.text("Prefetching...", y=io.oled.h-31)
        io.oled.show()
        cbuf = io.oled.prefetch_chrs("0123456789.", 50)  # for faster oled update

        io.oled.fill_rect(0, io.oled.h - 35, io.oled.w, 35, 0)
        io.oled.text("Get going!", y=io.oled.h-31)
        io.oled.show()

        while False:  # todo: kmh <= 0 and not pressed button
            pass
        sleep_ms(1000)  # todo

        tmr = tms()
        area = (0, 0, io.oled.w, io.oled.h)
        cdiff = -1
        while True:  # todo: km/h < 100
            # todo exit on click
            diff = round(tdiff(tms(), tmr) / 1000, 1)
            if diff >= 10:
                diff = int(diff)
            if diff != cdiff:
                cdiff = diff
                io.oled.fill_rect(*(area + (0,)))  # clear previous area
                io.oled.big(diff, buf=cbuf)
                io.oled.show()


def task_view_gear():
    # todo: while loop (update, exit on key press)
    area = (0, 0, io.oled.w, io.oled.h)
    for gear in range(1, 7):
        io.oled.fill_rect(*(area + (0,)))  # clear previous area
        io.oled.big(gear)
        io.oled.show()
        sleep_ms(500)


# 0 = battery voltage, 1 = ECT, 2 = MAP, 3 = IAT
def task_view_ecu(type):
    io.oled.fill(0)
    io.oled.text("Engine Coolant", y=22)
    io.oled.text("° Celsius", y=100)
    # todo: while loop (update, exit on key press)
    val = 12.16
    io.oled.big(round(val, 1))
    io.oled.show()


#blit_img("logo")
#oled.show()
#task_view_gear()
#task_view_ecu(0)
task_view_menu()
