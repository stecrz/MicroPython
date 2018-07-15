from webserver import WebSocketServer, WebSocketClient  # see package websocketserver
import net_helper
from utime import ticks_ms as tms, ticks_diff as tdiff
import ujson as json
from pwr import deepsleep
from machine import reset
import network


_OBJS = ('ecu', 'ctrl')  # all non-private vars in these objects will be monitored and sent to clients on update
_WS_INACT_TO = 20  # client is closed when no message (incl SYN!) received for _ s (>= WS_SYN_INTERVAL)
                       # don't use too small value, as cient will not send SYN message if JS alert is displayed
_AP_CONF = ('192.168.0.1', '255.255.255.0', '192.168.0.1', '')  # ip, subnet, gateway, dns
_HTML_INDEX = "/html/index.html"  # None = unsued
_HTML_404 = "/404.html"  # None = unused


class NetClient(WebSocketClient):
    def __init__(self):
        super().__init__()

        # assuming module references don't change over time, so once e.g. ecu is defined, only its contents will
        # change. data is stored in format {obj1: {...}, obj2: {...}, ...}
        self.obj = {o: locals()[o] for o in _OBJS}
        self.data = {o: {} for o in _OBJS}
        # initial update cannot be done here (write only allowed after setup()) -> _update

        self.conn_tmr = tms()  # for checking if client is connected

    def routine(self):  # main routine, executed all the time the client is active
        msg = self.read()
        if msg:  # client is asking for sth (not empty or None)
            msg = str(msg)
            print(msg)
            try:
                if "}{" not in msg:  # simple fast
                    self.execute_json(json.loads(msg))
                else:
                    msg = json.loads('[' + msg.replace("}{", "},{") + ']')  # can be multiple, therefore this shit...
                    for m in msg:
                        self.execute_json(m)
            except ValueError:  # invalid JSON
                pass
            self.conn_tmr = tms()  # reset timer

        self._update()  # update data locally and submit changes to the client

        if tdiff(tms(), self.conn_tmr) > _WS_INACT_TO*1000:
            self.close()

    def send(self, **msg):
        self.write(json.dumps(net_helper.json_prep_dict(msg)))

    def execute_json(self, msg):  # json msg received from websocket
        try:
            if 'SYN' in msg:
                self.send(ACK=msg['SYN'])
            elif 'SET' in msg and 'TO' in msg:  # client wants to set local variable
                net_helper.set_var(msg['SET'], msg['TO'], self.data, self.obj)
            elif 'CMD' in msg:  # ESP command without args
                cmd = msg['CMD']
                if cmd == "reboot":
                    reset()  # soft reset
                elif cmd == "deepsleep":
                    deepsleep()
                elif cmd == "console":
                    raise Exception("return by net")
                elif cmd == "ifconfig":  # returns AP and STA IP and Port; 0.0.0.0 if not connected
                    self.send(ALERT="AP:\n{}\n\nStation:\n{}\n\nPort: {}".
                                    format(str(network.WLAN(network.AP_IF).ifconfig()),
                                    str(network.WLAN(network.STA_IF).ifconfig()),
                                    str(net_helper.read_cfg("port"))))
                # elif cmd == "netls":
                #     self.send(ALERT='\n'.join(["ID: %s - PW: %s" % (kid, kpw) for (kid, kpw) in read_cfg("knets")]))
                # elif cmd == "netadd":
                #     cfg = read_cfg()
                #     knets = cfg["knets"]
                #     for i in range(len(knets)):
                #         if knets[i][0] == msg['ID']:
                #             knets[i][1] = msg['PW']
                #             break
                #     else:  # not found
                #         cfg["knets"].append((msg['ID'], msg['PW']))
                #     write_cfg(cfg)
                # elif cmd == "netrm":
                #     cfg = read_cfg()
                #     knets = cfg["knets"]
                #     for i in range(len(knets)):
                #         if knets[i][0] == msg['ID']:
                #             knets.pop(i)
                #             break
                #     else:
                #         return  # not found -> nothing to do
                #     write_cfg(cfg)
            elif 'GET' in msg:  # client wants to get local variable(s)
                if not msg['GET']:  # empty string or None -> enquiring all cached data
                    self.send(UPDATE=self.data)
                else:
                    jmsg = net_helper.get_var(msg['GET'], self.data)
                    if jmsg:
                        self.send(UPDATE=jmsg)
        except KeyError:  # wrong command format (key expected but not given)
            pass

    def _update(self):
        # update the local data by comparing with original modules data and submit the changes to the client
        mods = {}
        for obj_name in self.obj:
            dat_cache = self.data[obj_name]
            dat_real = self.obj[obj_name].__dict__
            obj_mods = net_helper.find_changed_vals(dat_cache, dat_real)
            if obj_mods:  # at least one public var modified in this object
                mods[obj_name] = obj_mods

        if mods:  # - " - at all (all public)#
            self.send(UPDATE=mods)


class NetServer(WebSocketServer):
    def __init__(self):
        super().__init__(NetClient, _HTML_INDEX, 3, 2, _HTML_404)

        cfg = net_helper.read_cfg()
        self._name = cfg["hostname"]
        self._pw = cfg["passwd"]
        self._port = cfg["port"]
        self._knets = tuple(tuple(idpw) for idpw in cfg["knets"])

        self.active = False

    def start(self):
        if not self.active:
            self.active = True
            self._set_ap()
            self._set_sta()
            super().start(self._port)

    def stop(self):
        if self.active:
            self.active = False
            self._set_ap()
            self._set_sta()
            super().stop()

    def client_count(self):
        return len(self.clients)

    def _set_sta(self):
        sta = network.WLAN(network.STA_IF)
        sta.active(self.active)

        if self.active:
            sta.config(dhcp_hostname=self._name)

            if not sta.isconnected():  # not conn already
                # searching for known networks by iterating over all 2.4 GHz networks around, starting
                # at the one with the strongest signal and checking if the network is in my database:
                for net in sorted(sta.scan(), key=lambda n: n[3], reverse=True):
                    for knet in self._knets:  # check all known networks
                        if net[0].decode('utf-8') == knet[0]:
                            sta.connect(knet[0], knet[1])
                            while sta.status() == network.STAT_CONNECTING:  # connecting ...
                                pass
                            if sta.isconnected():  # success
                                break
                    else:
                        continue  # to break outer loop on inner break
                    # executed when connected
                    # setup access point with same local IP as in wifi network
                    # ap.ifconfig(sta.ifconfig())
                    break
                else:  # no matching network found
                    sta.active(False)

        #print(sta.ifconfig())

    def _set_ap(self):
        ap = network.WLAN(network.AP_IF)
        ap.active(self.active)

        if self.active:
            ap.config(essid=self._name, password=self._pw)
            ap.ifconfig(_AP_CONF)

        #print(ap.ifconfig())
