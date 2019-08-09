from _main import main  # uploaded as .mpy

import gc
gc.collect()


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
