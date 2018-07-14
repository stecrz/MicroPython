from webserver import WebSocketServer, WebSocketClient  # see package websocketserver
from utime import ticks_ms as tms, ticks_diff as tdiff
from ujson import dumps, loads
from pwr import deepsleep
from machine import reset
import network


OBJECTS = ('ecu', 'ctrl')  # all non-private vars in these objects will be monitored and sent to clients on update
WS_INACT_TIMEOUT = 20  # client is closed when no message (incl SYN!) received for _ s (>= WS_SYN_INTERVAL)
                       # don't use too small value, as cient will not send SYN message if JS alert is displayed
PORT = 80  # to listen on


def deepcopy(v):  # recursive, but only for lists/tuples/dicts (and atomic values of course, but not objects)
    if isinstance(v, (int, float, bool, bytes, str, type, range, type(None), type(Ellipsis))):
        return v  # atomic value
    elif isinstance(v, (tuple, list)):
        return type(v)(deepcopy(x) for x in v)
    elif isinstance(v, bytearray):
        return bytearray(v)  # only consists of ints/bytes
    elif isinstance(v, dict):
        return {deepcopy(k): deepcopy(v[k]) for k in v}
    else:
        raise NotImplementedError  # obj not supported, use official copy.deepcopy in micropython-lib


def json_prep_dict(v):
    # Modifies the given dict <v> (any value) by changing all dict-keys recursivly to strings.
    # This is required for 8.7.2018 as the ujson module does not work properly, because it
    # converts dicts like {1: 2} to '{1: 2}' instead of '{"1": 2}' (keys need to be strings!).
    # Returns the modified dict (v remains unchanged).

    if isinstance(v, (tuple, list)):
        return (json_prep_dict(x) for x in v)  # list and tuples same in JSON
    elif isinstance(v, dict):
        return {str(k): json_prep_dict(v) for k, v in v.items()}
    else:  # note: objects with dicts as attr or anything will not be recognized!
        return v


class Client(WebSocketClient):
    def __init__(self):
        super().__init__()

        # assuming module references don't change over time, so once e.g. ecu is defined, only its contents will
        # change. data is stored in format {obj1: {...}, obj2: {...}, ...}
        self.obj = {o: locals()[o] for o in OBJECTS}
        self.data = {o: {} for o in OBJECTS}
        # initial update cannot be done here (write only allowed after setup()) -> _update

        self.conn_tmr = tms()  # for checking if client is connected

    def routine(self):  # main routine, executed all the time the client is active
        msg = self.read()
        if msg:  # client is asking for sth (not empty or None)
            self.execute(msg)
            self.conn_tmr = tms()  # reset timer

        self._update()  # update data locally and submit changes to the client

        if tdiff(tms(), self.conn_tmr) > WS_INACT_TIMEOUT*1000:
            self.close()

    def send(self, **msg):
        self.write(dumps(json_prep_dict(msg)))

    def execute(self, msg):  # msg received from websocket
        try:
            msg = loads(msg)  # can be multiple, therefore use single ifs beyond?
            print(msg)

            if 'SYN' in msg:
                self.send(ACK=msg['SYN'])
            if 'SET' in msg and 'TO' in msg:  # client wants to set local variable
                self._set_var(msg['SET'], msg['TO'])
            if 'GET' in msg:  # client wants to get local variable(s)
                if not msg['GET']:  # empty string or None -> enquiring all cached data
                    self.send(UPDATE=self.data)
                else:
                    self._get_var(msg['GET'])
            if 'CMD' in msg:  # ESP command without args
                if msg['CMD'] == "reboot":
                    reset()  # soft reset
                elif msg['CMD'] == "deepsleep":
                    deepsleep()
                elif msg['CMD'] == "console":
                    raise Exception("return by net")
                elif msg['CMD'] == "ifconfig":  # returns AP and STA IP and Port; 0.0.0.0 if not connected
                    self.send(ALERT="Access Point (AP): " + network.WLAN(network.AP_IF).ifconfig()[0] + '\n'
                                    "Station/WLAN (STA): " + network.WLAN(network.STA_IF).ifconfig()[0] + '\n'
                                    "Port: " + str(PORT))
        except ValueError:  # not in JSON format
            pass

    def _update(self):
        # update the local data by comparing with original modules data and submit the changes to the client

        def find_changed_vals(dat_old, dat_new):
            data_changed = {}  # changed attributes

            for attr in dat_new:  # check every key, if it has changed or is new (only non-private)
                if attr in dat_old:
                    if dat_old[attr] != dat_new[attr]:
                        if isinstance(dat_new[attr], dict) and isinstance(dat_old[attr], dict):  # only send
                            data_changed[attr] = find_changed_vals(dat_old[attr], dat_new[attr])  # changed keys
                        else:
                            data_changed[attr] = dat_old[attr] = deepcopy(dat_new[attr])  # local and com change
                elif len(attr) != 0 and attr[0] != '_':  # new key
                    data_changed[attr] = dat_old[attr] = deepcopy(dat_new[attr])  # local and comm change

            return data_changed

        mods = {}
        for obj_name in self.obj:
            dat_cache = self.data[obj_name]
            dat_real = self.obj[obj_name].__dict__
            obj_mods = find_changed_vals(dat_cache, dat_real)
            if obj_mods:  # at least one public var modified in this object
                mods[obj_name] = obj_mods

        if mods:  # - " - at all (all public)#
            self.send(UPDATE=mods)

    def _get_var(self, varls):  # execute GET command: find local variable and return it (no cache lookup)
        # <varls> can be a single variable or a list of variables/keys to support objects, dicts, list and tuples,
        # e.g. ['objA', 'objB', 'keyC', 'attrD', indexE] for objA.objB[keyC].attrD[indexE]
        # the variable found is cached (or updated in cache if was before)
        if isinstance(varls, str):
            varls = (varls,)
        elif not isinstance(varls, (list, tuple)):
            return

        val = locals()
        for var in varls:
            if isinstance(val, dict):  # dict[var_anything]
                if var not in val or isinstance(var, str) and len(var) != 0 and var[0] == '_':
                    return  # key err or private member
                val = val[var]
            elif isinstance(val, (list, tuple)):  # list/tuple[var_int]
                if not isinstance(var, int):
                    return
                val = val[var]
            else:  # data.var_str
                if not isinstance(var, str) or len(var) == 0 or var[0] == '_' or not hasattr(val, var):
                    return  # attribute err. non-private attribute must be given a non-empty string and has to exist
                val = getattr(val, var)

        # variable needs to be returned in a dict; additionally set the variable in cached data
        cache = self.data
        retmsg = {}
        msg = retmsg
        for var in varls[:-1]:
            if var not in cache:
                cache[var] = {}
            cache = cache[var]
            msg[var] = {}
            msg = msg[var]
        cache[varls[-1]] = val
        msg[varls[-1]] = val

        if retmsg:
            self.send(UPDATE=retmsg)  # send the value found as dict to be handled like an update

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


class NetworkIface:
    def __init__(self, hostname, passwd):
        self.active = False
        self.server = WebSocketServer(Client, ("/html/index.html"), 3, 2, "/404.html")

        self._hostname = hostname
        self._ap_pass = passwd

        # known networks, TODO database
        # make it possible to add a network via the webserver when connected directly. show ifconfig in html!
        self._knets = [(b"Network", b"Password")]

    def start(self):
        if not self.active:
            self.active = True
            self._set_ap()
            self._set_sta()
            self.server.start(PORT)

    def stop(self):
        if self.active:
            self.active = False
            self._set_ap()
            self._set_sta()
            self.server.stop()

    def update(self):
        self.server.process()  # update all clients and handle requests

    def client_count(self):
        return len(self.server.clients)

    def _set_sta(self):
        sta = network.WLAN(network.STA_IF)
        sta.active(self.active)

        if self.active:
            sta.config(dhcp_hostname=self._hostname)

            if not sta.isconnected():  # not conn already
                # searching for known networks by iterating over all 2.4 GHz networks around, starting
                # at the one with the strongest signal and checking if the network is in my database:
                for net in sorted(sta.scan(), key=lambda n: n[3], reverse=True):
                    for knet in self._knets:  # check all known networks
                        if net[0] == knet[0]:
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

    def _set_ap(self):
        ap = network.WLAN(network.AP_IF)
        ap.active(self.active)

        if self.active:
            ap.config(essid=self._hostname, password=self._ap_pass)
            ap.ifconfig(('192.168.0.1', '255.255.255.0', '192.168.0.1', ''))  # ip, subnet, gateway, dns
