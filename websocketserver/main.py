from webserver import WebSocketServer, WebSocketClient, ClientClosedError
import utime as time
import esp


class Client(WebSocketClient):
    def __init__(self):
        super().__init__()

    def routine(self):
        msg = self.read()
        if msg is not None:
            msg = msg.decode("utf-8")
            items = msg.split(" ")
            cmd = items[0]
            if cmd == "Question":
                self.write(cmd + " Answer")
                print("Q A")
        else:
            self.write(str(self.address) + "; time: %d; freemem: %d" % (time.ticks_ms(), esp.freemem()))


def main():
    # setup STA_IF network before!
    server = WebSocketServer(Client, "test.html", 3)
    server.start()
    try:
        while True:
            server.process()
    except KeyboardInterrupt:
        pass
    server.stop()

    
if __name__ == "__main__":
    main()
