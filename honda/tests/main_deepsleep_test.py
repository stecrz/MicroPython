import machine


rtc = machine.RTC()
mem = rtc.memory()

with open("reset_cause.txt", "a") as f:
    f.write("rst: %d; rtc: %s\n" % (machine.reset_cause(), str(mem)))

if machine.reset_cause() != machine.HARD_RESET:  # to two hard resets fast
    rtc.irq(trigger=rtc.ALARM0, wake=machine.DEEPSLEEP)
    machine.deepsleep()

# first time manually deepsleep and remove old reset_cause before
