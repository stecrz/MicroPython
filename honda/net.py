from webserver import WebSocketServer, WebSocketClient  # see package websocketserver
from utime import ticks_ms as tms, ticks_diff as tdiff
import ujson as json
from pwr import deepsleep
from machine import reset
import network


_CONFIG_FILE = "netconf.json"  # this file must contain, hosname, password, known networks, port (...)
_OBJS = ('ecu', 'ctrl')  # all non-private vars in these objects will be monitored and sent to clients on update
_WS_INACT_TO = 14  # client is closed when no message (incl PING!) received for _ s (>= WS_SYN_INTERVAL)
                   # don't use too small value, as cient will not send PING message if JS alert is displayed
_AP_CONF = ('192.168.0.1', '255.255.255.0', '192.168.0.1', '')  # ip, subnet, gateway, dns
_HTML_INDEX = "/html/index.html"  # None = unsued
_HTML_404 = "/404.html"  # None = unused


def read_cfg(key=None):  # key can be specified for a single entry, otherwise returns all data
    try:
        with open(_CONFIG_FILE, 'r') as f:
            dat = json.loads(f.read())
            if key is not None:
                return dat[key]
            return dat
    except KeyError:
        return None


def write_cfg(dat):  # dat = data dict (format must be exactly of type see json file)
    with open(_CONFIG_FILE, 'w') as f:
        f.write(json.dumps(dat))


def _deepcopy(v):  # recursive, but only for lists/tuples/dicts (and atomic values of course, but not objects)
    if isinstance(v, (int, float, bool, bytes, str, type, range, type(None), type(Ellipsis))):
        return v  # atomic value
    elif isinstance(v, (tuple, list)):
        return type(v)(_deepcopy(x) for x in v)
    elif isinstance(v, bytearray):
        return bytearray(v)  # only consists of ints/bytes
    elif isinstance(v, dict):
        return {_deepcopy(k): _deepcopy(v[k]) for k in v}
    else:
        raise NotImplementedError  # obj not supported, use official copy.deepcopy in micropython-lib


def _json_prep(v):  # prepare json value so that dumps understands it and it can be loaded by the webclient
    # Modifies the given dict <v> (any value) by changing all dict-keys recursivly to strings.
    # This is required for 8.7.2018 as the ujson module does not work properly, because it
    # converts dicts like {1: 2} to '{1: 2}' instead of '{"1": 2}' (keys need to be strings!).
    # Also replaces python bytearray/bytes values by tuples (converted to list by dumps)
    # Returns the modified dict (v remains unchanged).

    if isinstance(v, (tuple, list)):
        return (_json_prep(x) for x in v)  # list and tuples same in JSON
    elif isinstance(v, (bytearray, bytes)):
        return tuple(v)
    elif isinstance(v, dict):
        return {str(k): _json_prep(v) for k, v in v.items()}
    else:  # note: objects with dicts as attr or anything will not be recognized!
        return v


class _NetClient(WebSocketClient):
    def __init__(self):
        super().__init__()

        # assuming module references don't change over time, so once e.g. ecu is defined, only its contents will
        # change. data is stored in format {obj1: {...}, obj2: {...}, ...}
        self.obj = {o: locals()[o] for o in _OBJS}
        self.data = {o: {} for o in _OBJS}
        # initial update cannot be done here (write only allowed after setup()) -> _update

        self.conn_tmr = tms()  # for checking if client is connected

    def routine(self):  # main routine, executed all the time the client is active
        if tdiff(tms(), self.conn_tmr) > _WS_INACT_TO*1000:
            self.close()
            # print("closed client")
            return

        msg = self.read()
        if msg:  # client is asking for sth (not empty or None)
            msg = msg.decode('utf-8')
            try:
                for m in json.loads('[' + msg.replace("}{", "},{") + ']'):  # can be multiple, therefore this shit...
                    # print(repr(m))
                    self.execute(m)
            except ValueError:  # invalid JSON
                pass

        self._update()  # update data locally and submit changes to the client

    def send(self, **msg):
        self.write(json.dumps(_json_prep(msg)))

    def execute(self, msg):  # execute a msg object (must be dict unpacket from json)
        try:
            if 'PING' in msg:
                self.send(ACK=msg['PING'])
                # print("acknowledged PING " + str(msg["PING"]))
                self.conn_tmr = tms()  # reset timer
            elif 'SET' in msg and 'TO' in msg:  # client wants to set local variable
                self._set_var(msg['SET'], msg['TO'])
            elif 'CMD' in msg:  # ESP command without args
                cmd = msg['CMD']
                if cmd == "reboot":
                    reset()  # soft reset
                elif cmd == "deepsleep":
                    deepsleep()
                elif cmd == "console":
                    raise Exception("ret by net")
                elif cmd == "ifconfig":  # returns AP and STA IP and Port; 0.0.0.0 if not connected
                    aw = ""
                    ap = network.WLAN(network.AP_IF)
                    if ap.active():
                        aw += "AP:\n{}\n\n".format(ap.ifconfig())
                    sta = network.WLAN(network.STA_IF)
                    if sta.active():
                        aw += "Station:\n{}\n\n".format(sta.ifconfig())
                    aw += "Port: " + str(read_cfg("port"))
                    self.send(ALERT=aw)
                elif cmd == "netls":
                    self.send(ALERT='\n\n'.join(["ID: %s\nPW: %s" % (kid, kpw) for (kid, kpw) in read_cfg("knets")]))
                elif cmd == "netadd":
                    cfg = read_cfg()
                    knets = cfg["knets"]
                    for i in range(len(knets)):
                        if knets[i][0] == msg['ID']:
                            knets[i][1] = msg['PW']
                            break
                    else:  # not found
                        cfg["knets"].append((msg['ID'], msg['PW']))
                    write_cfg(cfg)
                elif cmd == "netrm":
                    cfg = read_cfg()
                    knets = cfg["knets"]
                    for i in range(len(knets)):
                        if knets[i][0] == msg['ID']:
                            knets.pop(i)
                            break
                    else:
                        return  # not found -> nothing to do
                    write_cfg(cfg)
            # elif 'GET' in msg:  # client wants to get local variable(s)
            #     if not msg['GET']:  # empty string or None -> enquiring all cached data
            #         self.send(UPDATE=self.data)
            #     else:
            #         self._get_var(msg['GET'])
        except ValueError:  # not in JSON format
            pass

    def _update(self):
        # update the local data by comparing with original modules data and submit the changes to the client

        def _find_changed_vals(dat_old, dat_new):
            data_changed = {}  # changed attributes

            for attr in dat_new:  # check every key, if it has changed or is new (only non-private)
                if attr in dat_old:
                    if dat_old[attr] != dat_new[attr]:
                        if isinstance(dat_new[attr], dict) and isinstance(dat_old[attr], dict):  # only send
                            data_changed[attr] = _find_changed_vals(dat_old[attr], dat_new[attr])  # changed keys
                        else:
                            data_changed[attr] = dat_old[attr] = _deepcopy(dat_new[attr])  # local and com change
                elif len(attr) != 0 and attr[0] != '_':  # new key
                    data_changed[attr] = dat_old[attr] = _deepcopy(dat_new[attr])  # local and comm change

            return data_changed

        mods = {}
        for obj_name in self.obj:
            obj_mods = _find_changed_vals(self.data[obj_name], self.obj[obj_name].__dict__)
            if obj_mods:  # at least one public var modified in this object
                mods[obj_name] = obj_mods

        if mods:  # - " - at all (all public)
            self.send(UPD=mods)

    # def _get_var(self, varls):  # execute GET command: find local variable and return it (no cache lookup)
    #     # <varls> can be a single variable or a list of variables/keys to support objects, dicts, list and tuples,
    #     # e.g. ['objA', 'objB', 'keyC', 'attrD', indexE] for objA.objB[keyC].attrD[indexE]
    #     # the variable found is cached (or updated in cache if was before)
    #     if isinstance(varls, str):
    #         varls = (varls,)
    #     elif not isinstance(varls, (list, tuple)):
    #         return
    #
    #     val = locals()
    #     for var in varls:
    #         if isinstance(val, dict):  # dict[var_anything]
    #             if var not in val or isinstance(var, str) and len(var) != 0 and var[0] == '_':
    #                 return  # key err or private member
    #             val = val[var]
    #         elif isinstance(val, (list, tuple)):  # list/tuple[var_int]
    #             if not isinstance(var, int):
    #                 return
    #             val = val[var]
    #         else:  # data.var_str
    #             if not isinstance(var, str) or len(var) == 0 or var[0] == '_' or not hasattr(val, var):
    #                 return  # attribute err. non-private attribute must be given a non-empty string and has to exist
    #             val = getattr(val, var)
    #
    #     # variable needs to be returned in a dict; additionally set the variable in cached data
    #     cache = self.data
    #     retmsg = {}
    #     msg = retmsg
    #     for var in varls[:-1]:
    #         if var not in cache:
    #             cache[var] = {}
    #         cache = cache[var]
    #         msg[var] = {}
    #         msg = msg[var]
    #     cache[varls[-1]] = val
    #     msg[varls[-1]] = val
    #
    #     if retmsg:
    #         self.send(UPD=retmsg)  # send the value found as dict to be handled like an update

    def _set_var(self, varls, val):  # e.g. set(('io', 'rly', 'BL'), True), possible only if setter fun defined
        if isinstance(varls, str):
            varls = (varls,)
        elif isinstance(varls, list):
            varls = tuple(varls)
        if not isinstance(varls, tuple) or len(varls) <= 1:  # cannot set whole local var like 'ecu' or 'ctrl'
            return

        try:  # first check if variable exists
            data = self.data
            for i in range(len(varls)-1):  # all apart from last to make setting possible
                data = data[varls[i]]
        except KeyError:
            return  # object/attribute/key not existing, not cached or not setable
        if varls[-1] not in data:
            return

        # now do the real job (hard coded); data is reference to the main object like ecu or ctrl:
        if varls[0] == 'ctrl':
            if varls[1] == 'rly':
                # first perform local update of cached data (not req., but prevents unnecessary update()-call)
                data[varls[-1]] = val  # update local data
                self.obj[varls[0]].set_rly(varls[-1], val)
            elif varls[1] == 'mode':  # no local update here to make sure user sees whether change was successful
                if isinstance(val, int):
                    self.obj[varls[0]].mode = val
                    # to apply the mode as if the switch was released, we need to set switch state to pressed
                    # -> main code will find out that switch is not pressed any more and assume we have released it
                    self.obj[varls[0]].sw_pressed = True


class NetServer(WebSocketServer):
    def __init__(self):
        super().__init__(_NetClient, _HTML_INDEX, 3, 2, _HTML_404)

        with open(_CONFIG_FILE, 'r') as f:
            cfg = json.loads(f.read())
            self._name = cfg["hostname"]
            self._pw = cfg["passwd"]
            self._port = cfg["port"]
            self._knets = tuple(tuple(idpw) for idpw in cfg["knets"])

        self.active = False
        # stop network interfaces on start:
        self._set_ap()
        self._set_sta()

        self.stay_on_for = 0  # chip is expected to remain on even if bike powered off for this time
        self._stay_on_tmr = tms()  # in respect to this timer (set on network start)

    def start(self, stay_on=0):
        # with stay_on you can optionally specify a time (minutes), how long the network
        # is expected to stay on after start even if bike is powered off (0 = shutdown network on poweroff)
        self._stay_on_tmr = tms()
        self.stay_on_for = stay_on * 60000  # minutes to ms
        if not self.active:
            self.active = True
            self._set_ap()
            self._set_sta()
            super().start(self._port)

    def stop(self):
        self.stay_on_for = 0
        if self.active:
            self.active = False
            self._set_ap()
            self._set_sta()
            super().stop()

    def stay_on(self):  # returns True, if the chip is expected not to shutdown because of stay_on time
        return tdiff(tms(), self._stay_on_tmr) < self.stay_on_for

    def client_count(self):
        return len(self.clients)

    def _set_sta(self):
        sta = network.WLAN(network.STA_IF)
        sta.active(self.active)

        if self.active and self._knets:  # wants to activate and at least one known network
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
