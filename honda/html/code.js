var $ = function(id) { return document.getElementById(id); };


var PORT = 80;
var WS_SYN_INTERVAL = 4;  // send SYN msg every _ s to check if connection is still ok ("server working?")
var WS_SYN_TRIES = 3;  // try one and the same SYN at most  _ times (e.g. 3 means: at most 2 retries)
var WS_RECONN_TIMEOUT = 5;  // reconnect after _ s on close

var ws;
var synNr, ackNr;  // last SYN number that we sent to the server, last ACK that we received
var synTry;  // count how many times I tried one and the same synNr

var cache = {};


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
		elem.ontouchstart = function() { };  // to show :active state
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
	setBg("ctrl.powered", '#777');
	setBg("ecu.engine", '#777');
	setBg("ecu.ready", '#777');

	// cached variables cleared on screen:
	for (var obj in cache) {
		for (var attr in cache[obj]) {
			var elem = $(obj + '.' + attr);
			if (elem != null && !elem.classList.contains("circle"))  // skip circle shapes
				setTxt(obj + '.' + attr, "~");
		}
	}
	cache = {'ctrl': {}, 'ecu': {}};
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
    ws.send(JSON.stringify(dictObj));
}
function sendVar(vname, val) {
	sendObj({'SET': vname.split('.'), 'TO': val});
}

function connect() {
	ws = new WebSocket("ws://" + "192.168.178.51" + ":" + PORT);  // TODO remove
	//ws = new WebSocket("ws://" + location.hostname + ":" + PORT);

	ws.onopen = function() {
		setTxt("ackState", "Gestartet");

		var synInterval = setInterval (function () {
			if (ackNr !== synNr && synTry >= WS_SYN_TRIES) {
			    // did not receive ACK from server for last client SYN msg and has no more fail retries left
                setTxt("ackState", "Keine Antwort");
                resetAll();
                ws.close();
                clearInterval(synInterval);  // -> probably disconnected without close() call (e.g. network fail)
				synTry = 0;
			} else {
				synNr++;
				synTry++;
				setTxt("ackState", "Warten (" + synNr + ")");
				sendObj({'SYN': synNr}));
			}
		}, WS_SYN_INTERVAL*1000);

		synNr = 0;
		ackNr = -1;
		synTry = 1;
		sendObj{{'SYN': 0}));  // first to enable buttons on first ACK
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

	ws.onmessage = function(evt) {
		var dataObj = JSON.parse(evt.data);
		//console.log(dataObj);

		if ('UPDATE' in dataObj) {  // server is sending data
			var data = dataObj.UPDATE

			deepmerge(data, cache);

			// check the differences:

			if ("ctrl" in data) {
				for (var attr in data.ctrl) {
					switch (attr) {
						case "rly":
							for (var rlyName in data.ctrl.rly) {
								setBtnPrssd($("ctrl.rly." + rlyName), cache.ctrl.rly[rlyName]);
							}
							break;
						case "powered":
							setBg("ctrl.powered", cache.ctrl.powered ? '#393' : '#d00');
							if (!data.ctrl.powered)
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

			if ("ecu" in data) {
				for (var attr in data.ecu) {
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

			// check other local variables
		}
		else if ('ACK' in dataObj) {  // message to keep connection alive, server acknowledges SYn msg
			ackNr = dataObj['ACK'];
			setTxt("ackState", "OK (" + ackNr + ")");
			synTry = 0;  // reset amount of tries

			if (ackNr === 0) // first message acknowledged by server -> enable the interface
				disableBtns(false);
		}
		else if ('ALERT' in dataObj) {
			alert(dataObj['ALERT']);  // TODO: use HTML popup window instead, as JS popup is blocking JS
		}
	}

	ws.onclose = function(evt) {
		resetAll();
		setTxt("ackState", "Beendet");

		setTimeout(connect, WS_RECONN_TIMEOUT*1000); // reconnect
	}
}
