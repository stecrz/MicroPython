# This implementation is largly based on the websocket implementation by BetaRavener at
# https://github.com/BetaRavener/upy-websocket-server. Only a few changes were done.

import os
import socket
from websocket import websocket
import websocket_helper
from gc import collect
from time import sleep_ms


_CHUNK_SIZE = 256  # prevent memory allocation error by limiting data that is sent at once (fragment length)

_CODES = {
    200: "OK",
    404: "Not Found",
    500: "Internal Server Error",
    503: "Service Unavailable"
}

_TYPES = {
    "jpg": "image/jpeg",
    "html": "text/html",
    "htm": "text/html",
    "css": "text/css",
    "js": "application/javascript"
}


class ClientClosedError(Exception):
    pass


class WebSocketClient:
    def __init__(self):  # setup method has to be called after init!
        self._close_req = False       # client should be closed
        self._check_req = False       # should check if still connected
        self.address = None           # address format (IP, port)
        self._s = None                # socket
        self.ws = None                # websocket (based on the socket)
        self._close_clb = None        # close callback (function that is called after closing the socket)

    def setup(self, sock, addr, close_callback):
        self.address = addr
        self._s = sock
        self.ws = websocket(self._s, True)
        self._close_clb = close_callback
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_SOCKET, 0x14, self.notify)

    def notify(self, self_s):  # (self_s == self.s)
        self._check_req = True  # only check state when reading

    def read(self) -> bytes:  # raises a ClientClosedError if connection was closed
        if self._check_req:
            self._check_req = False
            state = int(str(self._s).split(' ')[1].split('=')[1])
            if state == 3:  # connection pending (probably stuck)
                self._close_req = True

        read = None
        try:
            read = self.ws.read()
        except (OSError, AttributeError):  # AE if self.ws is None (connected does not help)
            self._close_req = True

        if not read and self._close_req:
            raise ClientClosedError()
        return read

    def write(self, msg):
        try:
            self.ws.write(msg)
        except (OSError, AttributeError):  # AE if self.ws is None (not conn anymore)
            self._close_req = True

    def close(self):
        if self._s is not None:  # should be the case
            self._s.setsockopt(socket.SOL_SOCKET, 0x14, None)
            self._s.close()
            self._s = None
        if self.ws is not None:  # should be the case
            self.ws.close()
            self.ws = None
        if self._close_clb is not None:
            self._close_clb(self)  # remove client from the client list of the server

    def routine(self):
        # this method implements the routine that will be called while the client is connected.
        # should be be overridden (i. e. implemented) by the a subclass.
        pass


class WebSocketServer:
    def __init__(self, client_cls=WebSocketClient, index_page=None, client_limit=3, client_limit_ip=2, err_404=None):
        # Creates a WebSocket server that is able to accept a maximum of <client_limit> connections. <client_cls>
        # specifies the class of the clients, which should be a subclass of WebSocketClient that implements the process
        # method and offers an empty constructor (__init__ without args). <index_page> specifies a file that is provided
        # to the client if connected directly (http://<this_server>) without a websocket (None = no file).
        # Attention: <index_page> is specified by path (e.g. "/myapp/html/home.html") and all files in the folder of
        #            this file (e.g. "/myapp/html") are served by default. There you should always use a separate
        #            subfolder where all the website stuff is located (HTML, CSS, JPG, JavaScript ... files).
        # <client_limit_ip> specifies the limit of client per IP; when a client tries to connect but there are already
        # <client_limit_ip> connections from the same IP, new conns will be blocked.
        # <err_404> can be used to map error code 404 to a HTML error file (relative to index), e.g. '/err.html'

        self._Client = client_cls          # subclass of WebSocketClient implementing the process() method

        self._index_page = index_page     # name of the index file; sent to client if connected without websocket
        self._web_dir = ''                # directory where all the files (incl index file) are located -> sent!
        self._err_404 = err_404           # relative to the location of index page (web dir)
        if index_page is not None:
            pos_slash = index_page.rfind('/')
            if pos_slash > 0:  # otherwise (e.g. "text.html") use root dir
                self._web_dir = index_page[:pos_slash]
            if pos_slash >= 0:
                self._index_page = self._index_page[pos_slash+1:]

        self._c_max = client_limit        # maximum number of connections at the same time (None = no limit)
        self._c_ip_max = client_limit_ip  # - " - for one single IP (note: new client will kick oldest with the same IP)
        self._c = []                      # list of currently connected client objects
        self._s = None                    # socket (listener)

    @property
    def clients(self):
        return self._c

    def start(self, port=80):
        if self._s is not None:  # started already
            self.stop()
        self._s = socket.socket()
        # self._s.settimeout(0.5)                                          # do not wait forever
        self._s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)      # allow reuse of address for bind() method
        # self._s.bind(socket.getaddrinfo("0.0.0.0", port)[0][-1])         # bind socket to 0.0.0.0:port
        self._s.bind(('', port))
        self._s.setsockopt(socket.SOL_SOCKET, 0x14, self._accept)          # setup accept handler for new connections
        self._s.listen(1)                                                  # queue only a single connect request

    def stop(self):
        if self._s:
            self._s.close()  # close socket
        self._s = None
        for c in self._c:
            c.close()  # will also remove client from list

    def _accept(self, self_s):
        # handler for new incoming connections
        collect()
        sock, addr = self_s.accept()  # client socket, client address (self_s == self._s, passed as param)

        if self._c_ip_max is not None:
            ip_conns = 0  # connections from this IP
            for c in self._c:
                if c.address[0] == addr[0]:
                    ip_conns += 1

            if ip_conns >= self._c_ip_max:  # too many from this IP
                sock.setblocking(True)
                self._serve_static(sock, 503)
                return

        if len(self._c) >= self._c_max:  # too many connections in general
            sock.setblocking(True)
            self._serve_static(sock, 503)
            return

        file_req = None  # path of requested file; set to index page if HTTP GET does not specify
        data = sock.recv(64).decode()
        if data and "Upgrade: websocket" not in data.split('\r\n') and 'GET' == data.split(' ')[0]:
            # data should looks like GET /index.html HTTP/1.1\r\nHost: 19"
            # requested file is on second position in data, ignore all get parameters after question mark
            file_req = data.split(' ')[1].split('?')[0]
            if not file_req or file_req == '/':
                file_req = '/' + self._index_page  # eg "/index.html"

        try:
            websocket_helper.server_handshake(sock)
        except OSError:  # handshake failed (no websocket connection) -> file was required or serve default file
            if file_req:
                sock.setblocking(True)
                self._serve_file(sock, file_req)
            else:
                self._serve_static(sock, 500)
        else:
            c = self._Client()

            def remove(client):
                if client in self._c:
                    self._c.remove(client)
            c.setup(sock, addr, remove)

            self._c.append(c)

    def _serve_static(self, sock, code):  # return static (most likely: error) page to a GET; socket will be closed
        collect()
        sock.sendall(self._http_header(code))

        if code == 404 and self._err_404:
            with open(self._web_dir + self._err_404, 'r') as f:
                while True:
                    data = f.read(_CHUNK_SIZE)
                    collect()
                    sock.sendall(data)
                    if len(data) < _CHUNK_SIZE:
                        break

        sleep_ms(100)
        sock.close()

    def _file_exists(self, frel):
        # This method takes a relative file path <frel> that specifies a file location in the format "/dirX/file.txt"
        # relative to web dir and checks, if the file exists locally -> True/False

        if not frel or frel[0] != '/':  # param was in wrong format, must start with "/" ... simply append
            frel = '/' + frel
        pos_slash = frel.rfind('/')
        fn = frel[pos_slash + 1:]  # filename eg "test.html"
        fsubdir = frel[:pos_slash]  # eg "/sub1/sub2"

        try:
            return fn in os.listdir(self._web_dir + fsubdir)
        except OSError:
            return False

    def _serve_file(self, sock, fpath_rel):
        if not self._file_exists(fpath_rel):
            self._serve_static(sock, 404)
            return

        try:
            fpath = self._web_dir + fpath_rel
            sock.sendall(self._http_header(200, fpath, os.stat(fpath)[6]))

            with open(fpath, 'rb') as f:
                while True:
                    data = f.read(_CHUNK_SIZE)
                    sock.sendall(data)
                    if len(data) < _CHUNK_SIZE:
                        break

            sleep_ms(100)
            sock.close()
        except OSError:  # e.g. ENOMEM (104) while serving content or default file not found
            self._serve_static(sock, 500)

    def _http_header(self, code, fn=None, length=None):
        ctype = "text/html"
        if fn:
            ext = fn.split(".")[-1]
            if ext in _TYPES:
                ctype = _TYPES[ext]

        return "HTTP/1.1 {} {}\n" \
               "Content-Type: {}\n" \
               "Content-Length: {}\n" \
               "Server: ESPServer\n" \
               "Connection: close\n\n".format(code, _CODES[code], ctype, length)

    def process(self):
        for c in self._c:  # for every client
            try:
                c.routine()
            except ClientClosedError:
                c.close()
