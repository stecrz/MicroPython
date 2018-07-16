var $ = function(id) { return document.getElementById(id); };


var PORT = 80;
var WS_MAX_PINGS = 3;  // assume connection failed if _ pings fail in a row
var WS_PING_INTERVAL = 3500;  // send ping message to server every ... ms (so that server does not close conn)
var WS_RECONN_TIMEOUT = 5000;  // reconnect after _ ms on close

var ws;
var cache = null;

var pingNr = 0;
var pingTries = 0;
var recvdReply = false;

//var scrolling = false;
//document.ontouchmove = function(e) { scrolling = true; }
//document.ontouchend = function(e) { scrolling = false; }

setupBtn("ctrl.rly.IG");
setupBtn("ctrl.rly.BL");
setupBtn("ctrl.rly.ST");
setupBtn("ctrl.rly.HO");
setupBtn("reboot", 	"Warnung: Der Chip wird über einen SOFTRESET zurückgesetzt.\n" +
					"Das Netzwerk-Interface wird anschließend reaktiviert.\n\nFortfahren?", true);
setupBtn("deepsleep", "Warnung: Der Chip wird in den DEEPSLEEP-Modus versetzt.\n\nFortfahren?", true);
setupBtn("console", "Warnung: Das laufende Programm wird durch die Rückkehr zur Konsole abgebrochen.\n\nFortfahren?", true);
setupBtn("ifconfig");
setupBtn("netls");
setupBtnNetwork("netadd", "Name des zu neuen/geänderten Netzwerks:", "Netzwerksicherheitsschlüssel:");
setupBtnNetwork("netrm", "Name des zu entfernenden Netzwerks:");
setupBtnMode()  // for ctrl.mode

resetAll();  // initial setup

connect();


// setup the button with id <id> as specified by class in HTML file.
// <msg> can be specified for: clickbtn = confirm the click before firing (alert); inputbtn = secify value to be sent
// <reset> can be set to true if everthing should be reset afterwards (buttons disabled, cache cleared); clickbtn only
function setupBtn(id, msg, reset=false) {
	var elem = $(id);

	elem.oncontextmenu = function(evt) { evt.preventDefault(); }  // class "switch"

	if (elem.classList.contains("switch-onoff")) {
		elem.parentNode.oncontextmenu = elem.oncontextmenu;
		elem.onclick = function(evt) { sendVar(this.id, this.checked); }
	} else if (elem.classList.contains("holdbtn")) {
		elem.onmousedown = elem.ontouchstart = function(evt) {
		    // TODO cannot check if is moving instead of really clicking, as ontouchmove is fired after ontouchstart
			if (evt.button != 2 && !elem.classList.contains("disabled") && !elem.classList.contains("pressed")) {
				this.classList.add("pressed");
				sendVar(this.id, true);
			}
		}
		elem.onmouseup = elem.ontouchend = function(evt) {
			if (evt.button != 2 && !elem.classList.contains("disabled") && elem.classList.contains("pressed")) {
				evt.preventDefault();
				this.classList.remove("pressed");
				sendVar(this.id, false);
			}
		}
	} else if (elem.classList.contains("clickbtn")) {
		elem.onclick = function(evt) {
			if (typeof msg === 'undefined' || confirm(msg))
				sendObj({'CMD': this.id});
			if (reset) {
				resetAll();
				//ws.onclose();  // faster reconnect, but no good solution
			}
		}
		elem.ontouchstart = function() { }  // to show :active state
	}
}
function setupBtnNetwork(id, hintId, hintPw=null) {
	var elem = $(id);

	elem.oncontextmenu = function(evt) { evt.preventDefault(); }  // class "switch"
    elem.onclick = function(evt) {
        var valId = prompt(hintId, '');
        if (valId == null || valId === '')
            return;
        if (hintPw == null) {
            sendObj({'CMD': this.id, 'ID': valId});
            return;
        }
        var valPw = prompt(hintPw, '');
        if (valPw == null || valPw === '')
            return;
        sendObj({'CMD': this.id, 'ID': valId, 'PW': valPw});
    }
    elem.ontouchstart = function() { };  // to show :active state
}
function setupBtnMode() {
	var elem = $("ctrl.mode");
	elem.onclick = function(evt) {
		if (evt.button != 2 && !elem.classList.contains("disabled")) {
			var inp = parseInt(prompt("Modus ändern:", cache.ctrl.mode));
			if (!isNaN(inp))
				sendVar(this.id, inp);
		}
	}
}

function disableBtn(elem, disabled) {
	if (elem.classList.contains("holdbtn") || elem.classList.contains("inputbtn"))
		if (disabled)
			elem.classList.add("disabled");
		else
			elem.classList.remove("disabled");
	else
		elem.disabled = disabled;
}
function disableBtns(disable) {
	var btns = document.querySelectorAll(".holdbtn,.switch-onoff,.clickbtn,.inputbtn");
	[].forEach.call(btns, function(elem) { disableBtn(elem, disable); } );
}
function resetAll() {
	disableBtns(true);
	setBg("ctrl.pwr", '#777');
	setBg("ecu.engine", '#777');
	setBg("ecu.ready", '#777');

	// cached variables cleared on screen:
	if (cache != null) {
        for (var obj in cache) {
            for (var attr in cache[obj]) {
                var elem = $(obj + '.' + attr);
                if (elem != null && !elem.classList.contains("circle"))  // skip circle shapes
                    setTxt(obj + '.' + attr, "~");
            }
        }
    }
    cache = null;
}

function setBtnPrssd(elem, pressed) {
	if (elem.classList.contains("holdbtn")) {
		if (pressed)
			elem.classList.add("pressed");
		else
			elem.classList.remove("pressed");
	} else if (elem.classList.contains("switch-onoff")) {
		elem.checked = pressed;
	} else if (elem.classList.contains("clickbtn")) {
		elem.active = pressed;  // TODO remove, nothing to do for clickbtn
	}
}
function setTxt(id, value) {
	var elem = $(id);
	if (elem != null)
		elem.innerHTML = value;
	else
		console.log(id + " not existing");
}
function setBg(id, color) {
	$(id).style.backgroundColor = color;
}

function sendObj(dictObj) {
    console.log(JSON.stringify(dictObj));
    ws.send(JSON.stringify(dictObj));
}
function sendVar(vname, val) {
	sendObj({'SET': vname.split('.'), 'TO': val});
}

function connect() {
	//ws = new WebSocket("ws://" + "192.168.178.51" + ":" + PORT);  // TODO remove
	ws = new WebSocket("ws://" + location.hostname + ":" + PORT);
	cache = {};
	pingNr = 0;
	pingTries = WS_MAX_PINGS; // remaining tries
	recvdReply = false;  // set to true if current ping was replied

    var keepConn = setInterval( function() {
        if (recvdReply) {
            if (pingNr == 0)  // enable buttons on first ping reply
		        disableBtns(false);
            pingNr++;
            pingTries = WS_MAX_PINGS;
            recvdReply = false;
        } else if (pingTries <= 0) {
            console.log("ping-timeout");
            setTxt("ackState", "Timeout (" + pingNr + ")");
            clearInterval(keepConn);
		    disableBtns(true);
            ws.close();
            return;
        }
        console.log("pinging " + pingNr);
        pingTries--;
        setTxt("ackState", "Ping (" + pingNr + ")");
        sendObj({'PING': pingNr});
    }, WS_PING_INTERVAL);

	ws.onopen = function() {
		setTxt("ackState", "Verbunden");
		disableBtns(false); // or enable buttons on open event
	}

	ws.onmessage = function(evt) {
		//console.log(evt.data);
		var jsonData = JSON.parse(evt.data);

        if ('ACK' in jsonData) {
            if (jsonData.ACK == pingNr) {
                recvdReply = true;
                setTxt("ackState", "OK (" + pingNr + ")");
            } else {
                console.log("ping answer, but wrong");
                setTxt("ackState", "Wrong Reply (" + pingNr + ")");
            }
        }
		else if ('UPD' in jsonData) { // server is sending all data
			deepmerge(jsonData.UPD, cache);

			// check the differences:

			if ("ctrl" in jsonData.UPD) {
				for (var attr in jsonData.UPD.ctrl) {
					switch (attr) {
						case "rly":
							for (var rlyName in jsonData.UPD.ctrl.rly) {
								setBtnPrssd($("ctrl.rly." + rlyName), cache.ctrl.rly[rlyName]);
							}
							break;
						case "pwr":
							setBg("ctrl.pwr", cache.ctrl.pwr ? '#393' : '#d00');
							if (!cache.ctrl.pwr)
								disableBtn($("ctrl.rly.ST"), false);  // motor won't start anyway so don't care about neutral
							break;
						case "sw_pressed":  // TODO
							break;
						case "mode":
							setTxt('ctrl.mode', cache.ctrl.mode);
							break;
					}
				}
			}

			if ("ecu" in jsonData.UPD) {
				for (var attr in jsonData.UPD.ecu) {
					switch (attr) {
						case "connecting":
						case "ready":
							setBg("ecu.ready", cache.ecu.connecting ? '#f93' : (cache.ecu.ready ? '#393' : '#d00'));
							break;
						case "idle":
							disableBtn($("ctrl.rly.ST"), !cache.ecu.idle || !("engine" in cache.ecu) || cache.ecu.engine);
						case "sidestand":
							setTxt("ecu." + attr, (cache.ecu[attr] == null) ? '?' :
												  (cache.ecu[attr] ? '\u2713' : '\u2715'));
							break;
						case "engine":
							disableBtn($("ctrl.rly.ST"), !cache.ecu.idle || cache.ecu.engine);
							setBg("ecu.engine", cache.ecu.engine ? '#393' : '#d00');
							break;
						case "gear":
							setTxt("ecu.gear", (cache.ecu.gear == null) ? 'N' : cache.ecu.gear);
							break;
						case "regMap":
							break;  // TODO currently regMap not used
						default:  // rest = all the values that are matched 1:1 from script to HTML text fields
							setTxt("ecu." + attr, cache.ecu[attr]);
							break;
					}
				}
			}

		}
		else if ('ALERT' in jsonData) {
			alert(jsonData['ALERT']);  // TODO: use HTML popup window instead, as JS popup is blocking JS
		}
	}

	ws.onclose = function(evt) {
		resetAll();
		setTxt("ackState", "Beendet");

		setTimeout(connect, WS_RECONN_TIMEOUT); // auto-reconnect
	}
}

function isJSONDict(v) {
    return v !== null && v.constructor == Object;  // another: Array
}

function deepmerge(src, dest) { // simple deepmerge working for recursive dicts; writing src to dest
    for (var attr in src) {
        if (attr in dest && isJSONDict(src[attr]) && isJSONDict(dest[attr])) { // some parts of dict modified
            deepmerge(src[attr], dest[attr]);
        } else {  // new key or was not dict before or simply atomic value (list/tuple incl.) change
            dest[attr] = src[attr];
        }
    }
}
