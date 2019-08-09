const $ = function(id) { return document.getElementById(id); };


const PORT = 80;
const WS_MAX_PINGS = 3;  // assume connection failed if _ pings fail in a row
const WS_PING_INTERVAL = 3500;  // send ping message to server every ... ms (so that server does not close conn)
const WS_RECONN_TIMEOUT = 2000;  // reconnect after _ ms on close

var ws;
var cache = null;
window.keepConn = null;  // attach setInterval()-Pinger to DOM-window to prevent oberlapping intervals

var pingNr = 0;
var pingTries = 0;
var recvdReply = false;

var touchmove = false; // for popup close


const popupCnt = $("popupContainer");
const popupConfirm = $("popupConfirm");
const popupCancel = $("popupCancel");
const popupInputs = $("popupInputs");

window.ontouchmove = function(evt) { touchmove = true; }
window.ontouchstart = function(evt) { touchmove = false; }
popupCnt.onclick = window.ontouchend = function(evt) {
	if (evt.target == popupCnt && !touchmove) {
	    evt.preventDefault();  // no new button click
		popupCnt.style.display = "none";
	}
}
$("popupClose").onclick = popupCancel.onclick = function() {
	popupCnt.style.display = "none";
}

/* msg: die anzuzeigende Nachricht
 * confirmHandler: Funktion zur Verarbeitung der Eingabedaten der Inputs nach Klick auf Bestätigen
 *				 (null = keine Funktion => kein Bestätigen/Abbrechen-Button)
 * inputPhs: Array mit den Platzhaltern für Inputs (leer falls keine Inputs gewünscht)
 * timeout: Popup automatisch nach _ ms schließen (0 = niemals schließen)
 * popup() kann u.a. als Abfrage benutzt werden: confirm(question, onSuccessFunction)
 */
function popup(msg, confirmHandler=null, inputPhs=[], timeout=0) {
	$("popupMsg").innerHTML = msg.replace(/\n/g, "<br>");

	var inputHtml = "";
	for (const ph of inputPhs)
		inputHtml += "<input type=\"text\" placeholder=\"" + ph + "\" autofocus>";
	popupInputs.innerHTML = inputHtml;

	popupCancel.style.display = confirmHandler == null ? "none" : "block";
	popupConfirm.style.display = confirmHandler == null ? "none" : "block";

	popupConfirm.onclick = confirmHandler == null ? null : function() {
		var args = [];
		for (var i = 0; i < popupInputs.children.length; i++)
			args.push(popupInputs.children[i].value);
		popupCnt.style.display = "none";
		confirmHandler.apply(this, args);
	}

    if (timeout > 0)
        setTimeout(function() { popupCnt.style.display = "none"; }, timeout);
	popupCnt.style.display = "block";  // show
}



setupBtn("io.rly.IG");
setupBtn("io.rly.BL");
setupBtn("io.rly.ST");
setupBtn("io.rly.HO");
setupBtn("io.rly.LED");
setupBtn("reboot", 	"Der Chip wird über einen <b>Soft-Reset</b> zurückgesetzt. Das Netzwerk-Interface wird anschließend reaktiviert.", true);
setupBtn("deepsleep", "<b>Hinweis:</b> Der Chip wird in den <b>Deepsleep</b>-Modus versetzt.", true);
setupBtn("console", "<b>WARNUNG:</b> Das laufende Programm wird durch die Rückkehr zur Konsole abgebrochen (Hard-Reset zur Wiederherstellung).", true);
setupBtn("ifconfig");
setupBtn("netls");
setupBtnNetwork("netadd", "Neue Netzwerkverbindung hinzufügen (bzw. Passwort ändern):", "SSID", "Sicherheitsschlüssel");
setupBtnNetwork("netrm", "Zu löschendes Netzwerk eingeben:", "SSID");
setupTxtTimer("nettime");
/*
setupTxtMode("io.view");
setupBtnPrint();
*/

resetAll();  // initial setup

connect();


// setup the button with id <id> as specified by class in HTML file.
// <msg> can be specified for: clickbtn = confirm the click before firing (alert); inputbtn = secify value to be sent
// <reset> can be set to true if everthing should be reset afterwards (connection closed); clickbtn only
function setupBtn(id, msg, reset=false) {
	var elem = $(id);

	elem.oncontextmenu = function(evt) { evt.preventDefault(); }  // class "switch"

	if (elem.classList.contains("switch-onoff")) {
		elem.parentNode.oncontextmenu = elem.oncontextmenu;
		elem.onclick = function(evt) { sendVar(id, this.checked); }
	} else if (elem.classList.contains("holdbtn")) {
		elem.onmousedown = elem.ontouchstart = function(evt) {
			if (evt.button != 2 && !elem.classList.contains("disabled") && !elem.classList.contains("pressed")) {
				this.classList.add("pressed");
				sendVar(id, true);
			}
		}
		// TODO: ontouchmove fired after ontouchstart, therefore btn will be activated shortly
		elem.onmousemove = elem.ontouchmove = function(evt) {
			if (evt.button != 2) {  // always allow release
				this.classList.remove("pressed");
				sendVar(id, false);
			}
		}
		elem.onmouseup = elem.ontouchend = function(evt) {
			if (evt.button != 2) {  // always allow release
				evt.preventDefault();
				this.classList.remove("pressed");
				sendVar(id, false);
			}
		}
	} else if (elem.classList.contains("clickbtn")) {
	    function perform() {
	        sendObj({'CMD': id});
			if (reset) {
                setTxt("ackState", "Reset");
			    disconnect();
			}
	    }
		elem.onclick = typeof msg === 'undefined' ? perform : function(){ popup(msg, perform); };
		elem.ontouchstart = function(){}  // to show :active state
	}
}
function setupBtnNetwork(id, msg, hintId, hintPw=null) {
	var elem = $(id);
	elem.oncontextmenu = function(evt) { evt.preventDefault(); }  // class "switch"
	elem.onclick = function(evt) {
		popup(msg, function(valId, valPw) {
		    if (valId === '')
		        popup("Bitte Netzwerkname (SSID) eingeben!");
		    else if (valPw == null) // hintPw was null
		        sendObj({'CMD': id, 'ID': valId});
		    else
		        sendObj({'CMD': id, 'ID': valId, 'PW': valPw});
		}, hintPw == null ? [hintId] : [hintId, hintPw]);
	}
	elem.ontouchstart = function(){};  // to show :active state
}
/*
function setupTxtMode(id) {
	var elem = $(id);
	elem.onclick = function(evt) {
		if (evt.button != 2 && !elem.classList.contains("disabled")) {
            popup("Modus setzen:", function(newMode) {
                var val = parseInt(newMode);
                if (!isNaN(val))
                    sendVar(id, val);
                else
                    popup("Ungültige Eingabe!");
            }, [cache.io.mode]);
		}
	}
}*/
function setupTxtTimer(id) {
	var elem = $(id);
	elem.onclick = function(evt) {
		if (evt.button != 2 && !elem.classList.contains("disabled")) {
            popup("Verbleibende Netzwerk-Ontime:", function(h, m, s) {
                if (h === '' && m === '' && s === '')
                    popup("Bitte mindestens einen Wert angeben!");
                else {
                    var hrs = h === '' ? 0 : parseInt(h);
                    var min = m === '' ? 0 : parseInt(m);
                    var sec = s === '' ? 0 : parseInt(s);
                    if (isNaN(hrs) || isNaN(min) || isNaN(sec))
                        popup("Eingabe ist keine Zahl!");
                    else
		                sendObj({'CMD': id, 'VAL': (hrs*60 + min)*60 + sec});
                }
            }, ["Stunden", "Minuten", "Sekunden"]);
		}
	}
}
/*
function setupBtnPrint() {
    var elem = $("print");  // the real send button
    var form = $("segform");  // surrounding form containing input + btn
    //let txt = $("segout").value;
    //if ((invalidChar = /[^a-zA-Z0-9_\.\-\s]|[KMVWXZkmvwxz]/.exec(txt)) != null)
    //  popup("Das Zeichen '" + invalidChar + "' ist nicht darstellbar.");}
    elem.onmousedown = elem.ontouchstart = function(evt) {
        if (evt.button != 2 && !elem.disabled && !elem.classList.contains("pressed")) {
            elem.classList.add("pressed");
            form.classList.add("pressed");
        }
    }
    form.onsubmit = function(evt) {
        evt.preventDefault();
        if (!elem.disabled) {
            elem.classList.remove("pressed");
            form.classList.remove("pressed");
            sendObj({'CMD': "print", 'MSG': $("segout").value});
        }
        return false;
    }
}
*/

function disableBtn(elem, disabled) {
	if (elem.nodeName == "INPUT")
		elem.disabled = disabled;
	else
		if (disabled)
			elem.classList.add("disabled");
		else
			elem.classList.remove("disabled");
}
function disableBtns(disable) {
	var btns = document.querySelectorAll(".holdbtn,.switch-onoff,.clickbtn,.inputbtn,.submitbtn,.submitbtn-send,.submitbtn-txt");
	[].forEach.call(btns, function(elem) { disableBtn(elem, disable); } );
}
function resetAll() {
	disableBtns(true);
	setBg("io.pwr", '#777');
	setBg("ecu.engine", '#777');
	setBg("ecu.ready", '#777');
	setBg("io.sw_pressed", '#777');

    // for (var i = 0; i < 8; i++)
    //     segShow("seg-" + String.fromCharCode(97 + i), 0);

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
/*
function segShow(segId, active) {
    if (active)
        $(segId).classList.add("seg-show");
    else
        $(segId).classList.remove("seg-show");
}*/

function sendObj(dictObj) {
	console.log(JSON.stringify(dictObj));
	ws.send(JSON.stringify(dictObj));
}
function sendVar(vname, val) {
	sendObj({'SET': vname.split('.'), 'TO': val});
}

function connect() {
	ws = new WebSocket("ws://" + "192.168.0.1" + ":" + PORT);  // TODO remove
	//ws = new WebSocket("ws://" + location.hostname + ":" + PORT);
	cache = {};
	pingNr = 0;
	pingTries = WS_MAX_PINGS; // remaining tries
	recvdReply = false;  // set to true if current ping was replied

	ws.onopen = function() {
		setTxt("ackState", "Verbunden");
		disableBtns(false); // or enable buttons on open event

        window.keepConn = setInterval( function() {
            if (pingTries <= 0) {
                //console.log("ping-timeout");
                setTxt("ackState", "Timeout (" + pingNr + ")");
                disconnect();
                return;
            }
            if (recvdReply) {
                if (pingNr == 0)  // enable buttons on first ping reply
                    disableBtns(false);
                pingNr++;
                pingTries = WS_MAX_PINGS;
                recvdReply = false;
            }
            pingTries--;
            setTxt("ackState", "Ping (" + pingNr + ")");
            sendObj({'PING': pingNr});
        }, WS_PING_INTERVAL);
	}

	ws.onmessage = function(evt) {
		console.log(evt.data); // TODO
		var jsonData = JSON.parse(evt.data);

		if ('ACK' in jsonData) {
			recvdReply = true;
			setTxt("ackState", "OK (" + pingNr + ")");

			var sec = jsonData.ACK;
			var hour = Math.floor(sec / 3600);
			var min = Math.floor((sec - (hour * 3600)) / 60);
			sec -= (hour * 3600) + (min * 60);

			setTxt("stayOnH", hour < 10 ? '0' + hour : hour);
			setTxt("stayOnM", min < 10 ? '0' + min : min);
			setTxt("stayOnS", sec < 10 ? '0' + sec : sec);
		}
		else if ('UPD' in jsonData) { // server is sending all data
			deepmerge(jsonData.UPD, cache);

			// check the differences:

			if ("io" in jsonData.UPD) {
				for (var attr in jsonData.UPD.io) {
					switch (attr) {
						case "rly":
							for (var rlyName in jsonData.UPD.io.rly) {
								setBtnPrssd($("io.rly." + rlyName), cache.io.rly[rlyName]);
							}
							break;
						case "pwr":
							setBg("io.pwr", cache.io.pwr ? '#393' : '#d00');
							if (!cache.io.pwr)
								disableBtn($("io.rly.ST"), false);  // motor won't start anyway so don't care about neutral
							break;
						case "sw_pressed":
							setBg("io.sw_pressed", cache.io.sw_pressed ? '#fc0' : '#a66');
							break;
						/*
						case "dot":
						    segShow("seg-h", cache.io.dot);
						    break;
						case "pattern":
						    for (var i = 0; i < 7; i++)
						        segShow("seg-" + String.fromCharCode(97 + i), cache.io.pattern & (1 << i));
						    break;
						case "mode":
							setTxt('io.mode', cache.io.mode);
							break;
						*/
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
							disableBtn($("io.rly.ST"), !cache.ecu.idle || !("engine" in cache.ecu) || cache.ecu.engine);
							if (cache.ecu.idle)
								setTxt("ecu.gear", 'N');
							break;
						case "sidestand":
							setTxt("ecu.sidestand", (cache.ecu.sidestand == null) ? '?' :
												  (cache.ecu.sidestand ? '\u2713' : '\u2715'));
							break;
						case "engine":
							disableBtn($("io.rly.ST"), !cache.ecu.idle || cache.ecu.engine);
							setBg("ecu.engine", cache.ecu.engine ? '#393' : '#d00');
							break;
						case "gear":
							setTxt("ecu.gear", (cache.ecu.idle || cache.ecu.gear == null) ? 'N' : cache.ecu.gear);
							break;
						default:  // rest = all the values that are matched 1:1 from script to HTML text fields
							setTxt("ecu." + attr, cache.ecu[attr]);
							break;
					}
				}
			}

		}
		else if ('ALERT' in jsonData) {
			popup(jsonData['ALERT']);
		}
	}

	ws.onclose = disconnect;
}
function disconnect() {
    clearInterval(window.keepConn);
    resetAll();
    setTxt("ackState", "Beendet");
    ws = null;
    window.keepConn = null;
    setTimeout(connect, WS_RECONN_TIMEOUT); // auto-reconnect
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
