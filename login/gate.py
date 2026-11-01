"""Morzik login gate: the only way to Morzik's screen from a phone, inside the Morzik App.

Phone (Telegram, Tailscale on) -> Tailscale Serve https://sketch-server.<tailnet>.ts.net:6080 (tailnet only)
  -> this gate on a Unix socket -> websockify 127.0.0.1:6080 -> TigerVNC 127.0.0.1:5901

Every /login/ call needs all three:
- the tailnet: Tailscale Serve puts the caller's login and address in Tailscale-User-Login and
  X-Forwarded-For; the login must be the user's and the device one of MORZIK_LOGIN_DEVICES (`tailscale whois`).
  The gate listens on a Unix socket owned by `morzik`, so other users of the server cannot forge these headers;
- Telegram: initData signed for Morzik's bot, the user's user id, opened minutes ago;
  or, from the Morzik App (the iPhone app), appToken: a device token of its chat (~/.hermes/morzik-app/chat.db);
- Face ID: a device key the gate issued once, kept by Telegram in the phone's biometric storage
  (BiometricManager), or by the Morzik App in the Keychain behind Face ID, and released only after Face ID.
  The gate stores its hash.

Routes:
- GET /novnc/core/…, /novnc/vendor/… — the noVNC client modules (public code), with CORS for the app;
- POST /login/state {initData, request} — what the page should show: the site, whether a key can be issued;
- POST /login/enroll {initData, deviceId} — a new device key; only while no device is set up, or within
  a window opened on the server with `gate.py allow-enroll [minutes]`. A key counts once it opened a session;
- POST /login/session {initData, deviceKey, request} — the VNC password, a one-time websocket ticket
  (60 s) and a session id for /login/done;
- POST /login/reconnect {initData, session} — for a live session, a new one-time ticket and the VNC password
  (no deviceKey: Face ID was asked when the session was made); the page comes back after iOS dropped the socket;
- POST /login/done {initData, session, outcome} — "done" or "cancel", seen by Morzik's request_login tool;
- GET /login/ws?ticket=… — websocket to the screen, proxied as is to websockify;
- POST /login/screen {initData, session, width, height, visible, dpr, device} — from a phone or a tablet:
  Morzik's screen and Chrome take the device's shape for the session (PhoneScreen);
- GET /login/events?session=… — server-sent events for that page: a field on the screen got or lost the focus.

Login requests are files in ~/.morzik-login/requests/<id>.json, created by the morzik-login Hermes plugin.
Settings: environment, falling back to ~/.hermes/.env. Standard library only.
"""

import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import pathlib
import queue
import re
import secrets
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

log = logging.getLogger("morzik-login")

STATE = pathlib.Path(os.environ.get("MORZIK_LOGIN_STATE", str(pathlib.Path.home() / ".morzik-login")))
REQUEST_ID = re.compile(r"^[a-z0-9]{16}$")
INIT_DATA_MAX_AGE = 15 * 60       # from opening the app to Face ID
DONE_MAX_AGE = 3 * 3600           # the page may stay open while the user logs in
TICKET_TTL = 60
SESSION_TTL = 3 * 3600
PENDING_KEY_TTL = 10 * 60
NOVNC_PARTS = ("core", "vendor")


def load_settings() -> dict:
    env = {}
    dotenv = pathlib.Path.home() / ".hermes/.env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                name, value = line.split("=", 1)
                env[name.strip()] = value.strip().strip('"').strip("'")
    env.update(os.environ)
    settings = {
        "socket": env.get("MORZIK_LOGIN_SOCKET", str(STATE / "gate.sock")),
        "bot_token": env.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_user_id": env.get("MORZIK_VOICE_TELEGRAM_USER_ID", env.get("TELEGRAM_HOME_CHANNEL", "")),
        "tailnet_user": env.get("MORZIK_LOGIN_TAILNET_USER", ""),
        "devices": {d.strip().lower() for d in env.get("MORZIK_LOGIN_DEVICES", "").split(",") if d.strip()},
        "app_origin": env.get("MORZIK_VOICE_APP_ORIGIN", "https://morzik.pieces.run"),
        "websockify": (env.get("MORZIK_LOGIN_WEBSOCKIFY_HOST", "127.0.0.1"),
                       int(env.get("MORZIK_LOGIN_WEBSOCKIFY_PORT", "6080"))),
        "vnc_password_file": pathlib.Path(env.get("MORZIK_LOGIN_VNC_PASSWORD_FILE",
                                                  str(pathlib.Path.home() / ".vnc/password.txt"))),
        "novnc": pathlib.Path(env.get("MORZIK_LOGIN_NOVNC", "/usr/share/novnc")),
        "display": env.get("MORZIK_LOGIN_DISPLAY", ":1"),
        "cdp": env.get("MORZIK_LOGIN_CDP", "http://127.0.0.1:9222"),
        "app_db": pathlib.Path(env.get("MORZIK_APP_DB", str(pathlib.Path.home() / ".hermes/morzik-app/chat.db"))),
    }
    missing = [name for name, key in (("TELEGRAM_BOT_TOKEN", "bot_token"),
                                      ("TELEGRAM_HOME_CHANNEL", "telegram_user_id"),
                                      ("MORZIK_LOGIN_TAILNET_USER", "tailnet_user"),
                                      ("MORZIK_LOGIN_DEVICES", "devices")) if not settings[key]]
    if missing:
        raise SystemExit(f"not set: {', '.join(missing)}")
    return settings


def verify_init_data(init_data: str, bot_token: str, max_age: float, now: float | None = None) -> dict | None:
    """Telegram Mini App initData -> the user dict if Telegram signed it for this bot (same as voice/brain.py)."""
    if not init_data or not bot_token:
        return None
    fields = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received = fields.pop("hash", "")
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    if not received or not hmac.compare_digest(
            hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), received):
        return None
    now = time.time() if now is None else now
    if not fields.get("auth_date", "").isdigit() or now - int(fields["auth_date"]) > max_age:
        return None
    try:
        user = json.loads(fields.get("user", ""))
    except ValueError:
        return None
    return user if isinstance(user, dict) else None


def verify_app_token(token: str, db_path: pathlib.Path) -> bool:
    """A device token of the Morzik App: its chat database keeps only the hashes (same as voice/brain.py)."""
    import sqlite3
    if not token or len(token) > 200:
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return False
    try:
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = conn.execute("SELECT token_hash FROM devices WHERE token_hash=? AND revoked=0", (digest,)).fetchone()
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return row is not None and hmac.compare_digest(row[0], digest)


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def write_json(path: pathlib.Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


class Devices:
    """Device keys for Face ID: devices.json with sha256 of each key, and the enrollment window."""

    def __init__(self, state: pathlib.Path):
        self.path, self.window = state / "devices.json", state / "enroll-until"
        self.lock = threading.Lock()

    def _load(self) -> list:
        try:
            return json.loads(self.path.read_text()).get("devices", [])
        except (OSError, ValueError):
            return []

    def _active(self, devices: list) -> list:
        return [d for d in devices if d.get("active")]

    def can_enroll(self, now: float | None = None, app: str | None = None) -> bool:
        """The window is open, no device is set up yet, or (app: the hash of a Morzik App device token) this
        app install has never had a key: it signed in with a code from Telegram and is on the user's tailnet
        device, so its first Face ID key needs no window. A second one does: whoever holds the unlocked phone
        must not be able to swap the key and skip Face ID."""
        now = time.time() if now is None else now
        try:
            window = float(self.window.read_text().strip())
        except (OSError, ValueError):
            window = 0
        devices = self._load()
        if app and not any(d.get("app") == app and d.get("active") for d in devices):
            return True
        return now < window or not self._active(devices)

    def enroll(self, device_id: str, now: float | None = None, app: str | None = None) -> str | None:
        now = time.time() if now is None else now
        with self.lock:
            if not self.can_enroll(now, app):
                return None
            key = secrets.token_urlsafe(32)
            devices = [d for d in self._load() if d.get("active") or now - d.get("created", 0) < PENDING_KEY_TTL]
            entry = {"hash": key_hash(key), "device": device_id[:80], "created": now, "active": False}
            if app:
                entry["app"] = app
            devices.append(entry)
            write_json(self.path, {"devices": devices[-20:]})
            return key

    def check(self, key: str, now: float | None = None) -> bool:
        """A known key; a pending one becomes active (and closes the window) on first use."""
        now = time.time() if now is None else now
        if not key:
            return False
        digest = key_hash(key)
        with self.lock:
            devices = self._load()
            for device in devices:
                if not hmac.compare_digest(device.get("hash", ""), digest):
                    continue
                if not device.get("active") and now - device.get("created", 0) >= PENDING_KEY_TTL:
                    return False
                if not device.get("active"):
                    self.window.unlink(missing_ok=True)
                device.update(active=True, used=now)
                write_json(self.path, {"devices": devices})
                return True
            return False


class Requests:
    """Login requests from Morzik (requests/<id>.json); the gate only reads them and sets the outcome."""

    def __init__(self, state: pathlib.Path):
        self.dir = state / "requests"
        self.lock = threading.Lock()

    def get(self, request_id: str) -> dict | None:
        if not REQUEST_ID.match(request_id or ""):
            return None
        try:
            return json.loads((self.dir / f"{request_id}.json").read_text())
        except (OSError, ValueError):
            return None

    def finish(self, request_id: str, outcome: str) -> bool:
        """Set "done"/"cancelled" on a request Morzik is still waiting for."""
        with self.lock:
            request = self.get(request_id)
            if not request or request.get("status") != "waiting":
                return False
            request.update(status=outcome, finished=time.time())
            write_json(self.dir / f"{request_id}.json", request)
            return True


class Expiring:
    """Short-lived secrets kept in memory: websocket tickets and sessions."""

    def __init__(self):
        self.items: dict[str, tuple[float, dict]] = {}
        self.lock = threading.Lock()

    def add(self, ttl: float, data: dict) -> str:
        token = secrets.token_urlsafe(24)
        with self.lock:
            now = time.monotonic()
            self.items = {k: v for k, v in self.items.items() if v[0] > now}
            self.items[token] = (now + ttl, data)
        return token

    def get(self, token: str, consume: bool = False) -> dict | None:
        with self.lock:
            item = (self.items.pop if consume else self.items.get)(token or "", None)
        return item[1] if item and item[0] > time.monotonic() else None


class Whois:
    """Tailnet address -> device name (first label of the MagicDNS name), cached for a minute."""

    def __init__(self, ttl: float = 60):
        self.ttl, self.cache, self.lock = ttl, {}, threading.Lock()

    def __call__(self, ip: str) -> str | None:
        with self.lock:
            hit = self.cache.get(ip)
            if hit and time.monotonic() - hit[1] < self.ttl:
                return hit[0]
        try:
            out = subprocess.run(["tailscale", "whois", "--json", ip], capture_output=True, text=True, timeout=5)
            name = json.loads(out.stdout)["Node"]["Name"].split(".")[0].lower() if out.returncode == 0 else None
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            name = None
        with self.lock:
            self.cache[ip] = (name, time.monotonic())
        return name


class WebSocket:
    """A minimal websocket client for Chrome's DevTools protocol: text frames, no extensions."""

    def __init__(self, url: str, timeout: float = 10):
        parts = urllib.parse.urlsplit(url)
        self.sock = socket.create_connection((parts.hostname, parts.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {parts.path or '/'} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        self.file = self.sock.makefile("rb")
        status = self.file.readline()
        if b" 101 " not in status:
            self.sock.close()
            raise OSError(f"websocket refused: {status!r}")
        while self.file.readline() not in (b"\r\n", b""):
            pass
        self.sock.settimeout(None)
        self.lock = threading.Lock()

    def send(self, text: str, opcode: int = 1) -> None:
        data, mask = text.encode(), os.urandom(4)
        n = len(data)
        size = bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
                                                   else bytes([0x80 | 127]) + struct.pack(">Q", n))
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(data))
        with self.lock:
            self.sock.sendall(bytes([0x80 | opcode]) + size + mask + masked)

    def recv(self) -> str | None:
        """The next text message, None once the connection is closed."""
        message = b""
        while True:
            head = self.file.read(2)
            if len(head) < 2:
                return None
            n = head[1] & 0x7F
            if n == 126:
                n = struct.unpack(">H", self.file.read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self.file.read(8))[0]
            payload = self.file.read(n)
            opcode = head[0] & 0x0F
            if opcode == 8:
                return None
            if opcode == 9:
                self.send(payload.decode(errors="replace"), opcode=10)
                continue
            if opcode in (0, 1):
                message += payload
                if head[0] & 0x80:
                    return message.decode()

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


class CdpError(Exception):
    pass


class Cdp:
    """One DevTools connection to the whole browser, sessions flattened. Events go to on_event(method, params,
    session) on a thread of their own, so a handler may call back into Chrome."""

    def __init__(self, base: str, on_event):
        with urllib.request.urlopen(f"{base}/json/version", timeout=5) as resp:
            version = json.load(resp)
        self.browser = version.get("Browser", "")
        self.ws = WebSocket(version["webSocketDebuggerUrl"])
        self.on_event, self.events = on_event, queue.Queue()
        self.waiting: dict[int, queue.Queue] = {}
        self.next_id, self.lock, self.alive = 0, threading.Lock(), True
        threading.Thread(target=self._read, name="cdp-read", daemon=True).start()
        threading.Thread(target=self._dispatch, name="cdp-events", daemon=True).start()

    def _read(self) -> None:
        try:
            while (text := self.ws.recv()) is not None:
                message = json.loads(text)
                if "id" in message:
                    waiter = self.waiting.pop(message["id"], None)
                    if waiter:
                        waiter.put(message)
                else:
                    self.events.put(message)
        except (OSError, ValueError):
            pass
        self.alive = False
        self.events.put(None)
        for waiter in list(self.waiting.values()):
            waiter.put({"error": {"message": "connection closed"}})

    def _dispatch(self) -> None:
        while (message := self.events.get()) is not None:
            try:
                self.on_event(message.get("method"), message.get("params", {}), message.get("sessionId"))
            except Exception:
                log.exception("cdp event %s", message.get("method"))

    def call(self, method: str, params: dict | None = None, session: str | None = None, timeout: float = 10) -> dict:
        if not self.alive:
            raise CdpError("connection closed")
        with self.lock:
            self.next_id += 1
            call_id = self.next_id
        waiter = self.waiting[call_id] = queue.Queue()
        message = {"id": call_id, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        try:
            self.ws.send(json.dumps(message))
            reply = waiter.get(timeout=timeout)
        except (OSError, queue.Empty) as exc:
            self.waiting.pop(call_id, None)
            raise CdpError(f"{method}: {exc or 'timeout'}") from None
        if "error" in reply:
            raise CdpError(f"{method}: {reply['error'].get('message')}")
        return reply.get("result", {})

    def close(self) -> None:
        self.alive = False
        self.ws.close()


# Runs in every frame of the pages on the phone's screen: tells the gate which field has the focus, so the
# phone opens its keyboard with the right layout. Only from the tab on screen, and "lost" only from a document
# that reported a field (a background tab reloading must not close the keyboard); pagehide drops the keyboard.
FOCUS_SCRIPT = r"""(() => {
  if (window.__morzikFocusWatch) return;
  window.__morzikFocusWatch = true;
  let reported = false;
  const send = data => {
    if (!data.focus && !reported) return;
    reported = !!data.focus;
    try { window.__morzikLogin(JSON.stringify(data)); } catch (e) {}
  };
  const skip = /^(button|checkbox|radio|submit|reset|range|color|file|image|hidden)$/;
  const field = el => !el ? null : el.tagName === 'TEXTAREA' ? el
    : el.tagName === 'INPUT' ? (skip.test(el.type) || el.readOnly || el.disabled ? null : el)
    : el.isContentEditable ? el : null;
  const types = { email: 'email', tel: 'tel', number: 'number', url: 'url', search: 'search', password: 'password' };
  const modes = { numeric: 'number', decimal: 'number', tel: 'tel', email: 'email', url: 'url', search: 'search' };
  const describe = el => ({
    type: types[(el.type || '').toLowerCase()] || modes[(el.inputMode || '').toLowerCase()] || 'text',
    enter: (el.enterKeyHint || '').toLowerCase(),
    code: (el.getAttribute('autocomplete') || '').toLowerCase().includes('one-time-code'),
  });
  const deep = () => { let el = document.activeElement; while (el && el.shadowRoot && el.shadowRoot.activeElement) el = el.shadowRoot.activeElement; return el; };
  addEventListener('focusin', event => {
    if (document.visibilityState !== 'visible') return;
    const el = field(event.composedPath()[0]);
    send({ focus: el ? describe(el) : null });
  }, true);
  addEventListener('focusout', event => { if (!event.relatedTarget) send({ focus: null }); }, true);
  addEventListener('pagehide', () => send({ focus: null }));
  const el = field(deep());
  if (el && document.hasFocus() && document.visibilityState === 'visible') send({ focus: describe(el) });
})()"""
SCROLL_TO_FOCUS = ("(() => { let el = document.activeElement; while (el && el.shadowRoot && el.shadowRoot.activeElement)"
                   " el = el.shadowRoot.activeElement; if (el && el.scrollIntoViewIfNeeded) el.scrollIntoViewIfNeeded(); })()")
DESKTOP = (1440, 900)
MAX_SIDE, MAX_PIXELS = 4096, 6_000_000
RELEASE_AFTER = 120  # seconds the phone's screen stays after its page went away (app in the background, network)


def screen_metrics(body: dict) -> dict | None:
    """The page's size from /login/screen: CSS pixels of the screen area, the visible part of it (less while
    the keyboard is open), device pixel ratio, phone or tablet. The framebuffer is width*dpr x height*dpr, so the
    phone shows it pixel for pixel, and is kept within MAX_PIXELS by lowering dpr."""
    try:
        width, height = round(float(body["width"])), round(float(body["height"]))
        visible = round(float(body.get("visible") or height))
        dpr = float(body.get("dpr") or 1)
    except (KeyError, TypeError, ValueError):
        return None
    if not (200 <= width <= 2000 and 200 <= height <= 2000 and 0.5 <= dpr <= 5):
        return None
    dpr = max(1.0, min(dpr, 3.0, MAX_SIDE / width, MAX_SIDE / height, (MAX_PIXELS / (width * height)) ** 0.5))
    dpr = int(dpr * 4) / 4  # steps of a quarter: 2.6 -> 2.5
    return {"width": width, "height": height, "visible": max(100, min(visible, height)), "dpr": dpr,
            "device": "tablet" if body.get("device") == "tablet" else "phone",
            "screen": (round(width * dpr), round(height * dpr))}


class PhoneScreen:
    """While the user logs in from the phone, Morzik's screen takes the phone's shape: the X screen is resized to
    the phone's pixels, Chrome goes fullscreen and every tab emulates a mobile device over DevTools (metrics,
    touch from the mouse, Chrome for Android user agent), and fields in focus are reported to the page. All of it
    lives in one DevTools connection; finish() clears it and puts the desktop back the way Morzik works with it."""

    def __init__(self, display: str = ":1", cdp: str = "http://127.0.0.1:9222", output: str = "VNC-0",
                 run=subprocess.run, connect=Cdp):
        self.display, self.cdp_base, self.output, self.run, self.connect = display, cdp, output, run, connect
        self.lock = threading.RLock()
        self.owner: str | None = None    # the gate session the screen is shaped for
        self.metrics: dict | None = None
        self.cdp: Cdp | None = None
        self.pages: dict[str, str] = {}  # DevTools session -> page target
        self.frames: set[str] = set()    # DevTools sessions of out-of-process iframes
        self.windows: dict[int, str] = {}  # Chrome window -> its state before
        self.mode: str | None = None     # our xrandr mode in use
        self.focused: str | None = None  # the session whose field has the focus
        self.ua: dict | None = None
        self.listeners: dict[str, list[queue.Queue]] = {}
        self.timers: dict[str, threading.Timer] = {}

    # -- xrandr --

    def xrandr(self, *args: str) -> bool:
        try:
            done = self.run(["xrandr", *args], env={**os.environ, "DISPLAY": self.display},
                            capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("xrandr %s: %s", " ".join(args), exc)
            return False
        return done.returncode == 0

    def resize(self, width: int, height: int) -> None:
        old = self.mode
        if (width, height) == DESKTOP:
            mode = f"{width}x{height}"
            self.mode = None
        else:
            mode = self.mode = f"morzik-{width}x{height}"
            if mode != old:
                self.xrandr("--newmode", mode, "0", str(width), "0", "0", "0", str(height), "0", "0", "0")
                self.xrandr("--addmode", self.output, mode)
        if not self.xrandr("--fb", f"{width}x{height}", "--output", self.output, "--mode", mode):
            log.warning("could not resize the screen to %sx%s", width, height)
        if old and old != self.mode:
            self.xrandr("--delmode", self.output, old)
            self.xrandr("--rmmode", old)

    def current_size(self) -> tuple[int, int] | None:
        try:
            out = self.run(["xrandr", "--current"], env={**os.environ, "DISPLAY": self.display},
                           capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        found = re.search(r"current (\d+) x (\d+)", out or "")
        return (int(found[1]), int(found[2])) if found else None

    def reset(self) -> None:
        """At start: a session cut short by a restart of the gate may have left the phone's shape behind."""
        size = self.current_size()
        if size is None or size == DESKTOP:
            return
        log.info("screen left at %sx%s: back to the desktop", *size)
        self.resize(*DESKTOP)
        try:
            cdp = self.connect(self.cdp_base, lambda *a: None)
        except (OSError, ValueError, KeyError, CdpError):
            return
        try:
            for target in cdp.call("Target.getTargets")["targetInfos"]:
                if target["type"] == "page":
                    window = cdp.call("Browser.getWindowForTarget", {"targetId": target["targetId"]})
                    if window["bounds"].get("windowState") == "fullscreen":
                        self.window_state(cdp, window["windowId"], "maximized")
        except CdpError as exc:
            log.warning("could not restore Chrome's windows: %s", exc)
        cdp.close()

    @staticmethod
    def window_state(cdp, window: int, state: str) -> None:
        if state != "normal":
            cdp.call("Browser.setWindowBounds", {"windowId": window, "bounds": {"windowState": "normal"}})
        cdp.call("Browser.setWindowBounds", {"windowId": window, "bounds": {"windowState": state}})

    # -- the page's event stream --

    def listen(self, owner: str) -> queue.Queue:
        events = queue.Queue()
        with self.lock:
            self.listeners.setdefault(owner, []).append(events)
            timer = self.timers.pop(owner, None)
        if timer:
            timer.cancel()
        return events

    def unlisten(self, owner: str, events: queue.Queue) -> None:
        with self.lock:
            left = self.listeners.get(owner, [])
            if events in left:
                left.remove(events)
            if left or self.owner != owner:
                return
            if owner in self.timers:
                self.timers[owner].cancel()
            timer = self.timers[owner] = threading.Timer(RELEASE_AFTER, self.release, args=(owner,))
            timer.daemon = True
            timer.start()

    def release(self, owner: str) -> None:
        with self.lock:
            self.timers.pop(owner, None)
            if self.listeners.get(owner):
                return
        log.info("the phone's page went away")
        self.finish(owner)

    def send(self, owner: str | None, event: dict) -> None:
        with self.lock:
            for events in self.listeners.get(owner or "", []):
                events.put(event)

    # -- the session --

    def apply(self, owner: str, metrics: dict) -> dict:
        """Shape the screen for this page (first call) or follow its new size: rotation, keyboard."""
        with self.lock:
            if self.owner and self.owner != owner:
                self.finish(self.owner, "replaced")
            old, self.metrics = self.metrics, metrics
            if self.owner is None or self.cdp is None or not self.cdp.alive:
                self.owner = owner
                try:
                    self.start()
                except (OSError, ValueError, KeyError, CdpError) as exc:
                    log.warning("could not shape the screen for the phone: %s", exc)
                    self.finish(owner, "error")
                    raise CdpError(str(exc)) from None
            elif old and (old["width"], old["height"], old["screen"]) != (metrics["width"], metrics["height"],
                                                                          metrics["screen"]):
                self.resize(*metrics["screen"])
                time.sleep(0.3)  # Chrome's fullscreen window follows the screen
                for session in list(self.pages):
                    self.emulate(session)
            else:
                for session in list(self.pages):
                    self.emulate(session)
            if old and metrics["visible"] < old["visible"] and self.focused:
                self.call("Runtime.evaluate", {"expression": SCROLL_TO_FOCUS}, self.focused)
            if not self.listeners.get(owner) and owner not in self.timers:
                self.unlisten(owner, None)  # no event stream yet: the screen goes back unless one comes
            return {"screen": list(metrics["screen"]), "dpr": metrics["dpr"]}

    def start(self) -> None:
        self.pages, self.frames, self.windows, self.focused = {}, set(), {}, None
        self.resize(*self.metrics["screen"])
        self.cdp = self.connect(self.cdp_base, self.on_event)
        log.info("phone screen %sx%s (%s, %s css px, dpr %s)", *self.metrics["screen"], self.metrics["device"],
                 f"{self.metrics['width']}x{self.metrics['height']}", self.metrics["dpr"])
        self.ua = None
        self.cdp.call("Target.setDiscoverTargets", {"discover": True})
        for target in self.cdp.call("Target.getTargets")["targetInfos"]:
            if target["type"] == "page":
                self.attach(target["targetId"], settle=False)
        time.sleep(0.3)  # fullscreen windows take the new screen size
        for session in list(self.pages):
            self.emulate(session)

    def call(self, method: str, params: dict, session: str | None = None) -> dict | None:
        try:
            return self.cdp.call(method, params, session) if self.cdp else None
        except CdpError as exc:
            log.info("%s", exc)
            return None

    def user_agent(self, session: str) -> dict:
        if self.ua is None:
            major = (re.search(r"/(\d+)", self.cdp.browser or "") or [None, "130"])[1]
            hints = (self.call("Runtime.evaluate", {
                "expression": "navigator.userAgentData && navigator.userAgentData.getHighEntropyValues(['fullVersionList'])",
                "awaitPromise": True, "returnByValue": True}, session) or {}).get("result", {}).get("value") or {}
            brands = hints.get("brands") or [{"brand": "Google Chrome", "version": major},
                                             {"brand": "Chromium", "version": major},
                                             {"brand": "Not_A Brand", "version": "99"}]
            self.ua = {"brands": brands, "fullVersionList": hints.get("fullVersionList") or brands, "major": major}
        phone = self.metrics["device"] == "phone"
        return {
            "userAgent": (f"Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
                          f"Chrome/{self.ua['major']}.0.0.0 {'Mobile ' if phone else ''}Safari/537.36"),
            "platform": "Linux armv8l",
            "userAgentMetadata": {"brands": self.ua["brands"], "fullVersionList": self.ua["fullVersionList"],
                                  "platform": "Android", "platformVersion": "14.0.0", "architecture": "",
                                  "model": "", "mobile": phone},
        }

    def attach(self, target: str, settle: bool = True) -> None:
        reply = self.call("Target.attachToTarget", {"targetId": target, "flatten": True})
        if not reply:
            return
        session = reply["sessionId"]
        self.pages[session] = target
        window = self.call("Browser.getWindowForTarget", {"targetId": target})
        if window and window["windowId"] not in self.windows:
            self.windows[window["windowId"]] = window["bounds"].get("windowState", "normal")
            if self.windows[window["windowId"]] != "fullscreen":
                self.call("Browser.setWindowBounds", {"windowId": window["windowId"],
                                                      "bounds": {"windowState": "fullscreen"}})
        self.call("Emulation.setUserAgentOverride", self.user_agent(session), session)
        self.prepare(session)
        self.call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True,
                                           "filter": [{"type": "iframe"}, {"exclude": True}]}, session)
        if settle:
            time.sleep(0.3)
            self.emulate(session)

    def prepare(self, session: str) -> None:
        """Touch from the mouse and the focus watch, for a page or an iframe."""
        self.call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5}, session)
        self.call("Emulation.setEmitTouchEventsForMouse", {"enabled": True, "configuration": "mobile"}, session)
        self.call("Runtime.enable", {}, session)
        self.call("Runtime.addBinding", {"name": "__morzikLogin"}, session)
        self.call("Page.enable", {}, session)  # without it the script skips new documents
        self.call("Page.addScriptToEvaluateOnNewDocument", {"source": FOCUS_SCRIPT, "runImmediately": True}, session)

    def emulate(self, session: str) -> None:
        m = self.metrics
        landscape = m["width"] > m["height"]
        # The page lays out at the phone's CSS size and draws at its dpr (scale), so one pixel of the screen is
        # one pixel of the phone; setVisibleSize gives the view the whole screen (metrics alone clip it to CSS px).
        self.call("Emulation.setDeviceMetricsOverride", {
            "width": m["width"], "height": m["visible"], "deviceScaleFactor": m["dpr"], "scale": m["dpr"],
            "mobile": True, "screenWidth": m["width"], "screenHeight": m["height"],
            "screenOrientation": {"type": "landscapePrimary" if landscape else "portraitPrimary",
                                  "angle": 90 if landscape else 0}}, session)
        self.call("Emulation.setVisibleSize", {"width": m["screen"][0], "height": m["screen"][1]}, session)

    def on_event(self, method: str, params: dict, session: str | None) -> None:
        if method == "Runtime.bindingCalled" and params.get("name") == "__morzikLogin":
            try:
                focus = json.loads(params.get("payload") or "{}").get("focus")
            except ValueError:
                return
            with self.lock:
                if focus:
                    self.focused = session
                owner = self.owner
            self.send(owner, {"type": "focus", "field": focus if isinstance(focus, dict) else None})
            return
        with self.lock:
            if self.owner is None or self.cdp is None:
                return
            if method == "Target.targetCreated" and params["targetInfo"]["type"] == "page":
                if params["targetInfo"]["targetId"] not in self.pages.values():
                    self.attach(params["targetInfo"]["targetId"])
            elif method == "Target.attachedToTarget" and params["targetInfo"]["type"] == "iframe":
                self.frames.add(params["sessionId"])
                self.prepare(params["sessionId"])
                self.call("Emulation.setUserAgentOverride", self.user_agent(params["sessionId"]), params["sessionId"])
            elif method == "Target.detachedFromTarget":
                self.pages.pop(params.get("sessionId"), None)
                self.frames.discard(params.get("sessionId"))

    def finish(self, owner: str, reason: str = "done") -> bool:
        """Back to the desktop: no emulation, 1440x900, Chrome's windows as they were."""
        with self.lock:
            if self.owner != owner:
                return False
            cdp, pages, windows = self.cdp, list(self.pages), dict(self.windows)
            if cdp and cdp.alive:
                for session in pages:
                    for method, params in (("Emulation.clearDeviceMetricsOverride", {}),
                                           ("Emulation.setEmitTouchEventsForMouse", {"enabled": False}),
                                           ("Emulation.setTouchEmulationEnabled", {"enabled": False})):
                        self.call(method, params, session)
            self.resize(*DESKTOP)
            if cdp and cdp.alive:
                time.sleep(0.2)
                for window, state in windows.items():
                    try:
                        self.window_state(cdp, window, "maximized" if state == "fullscreen" else state)
                    except CdpError as exc:
                        log.info("window %s: %s", window, exc)
            if cdp:
                cdp.close()  # Chrome drops what is left of this connection's emulation with it
            self.owner, self.cdp, self.metrics, self.pages, self.frames = None, None, None, {}, set()
            self.windows, self.focused = {}, None
            self.send(owner, {"type": "end", "reason": reason})
            timer = self.timers.pop(owner, None)
        if timer:
            timer.cancel()
        log.info("desktop screen back (%s)", reason)
        return True


class Handler(BaseHTTPRequestHandler):
    server_version = "morzik-login"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    settings: dict = {}
    devices: Devices
    requests: Requests
    tickets = Expiring()
    sessions = Expiring()
    whois = Whois()
    phone: PhoneScreen | None = None

    def address_string(self):  # a Unix socket has no peer address
        return self.caller_ip() or "-"

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def caller_ip(self) -> str:
        # Tailscale Serve appends the address it saw; anything before it came from the caller.
        headers = getattr(self, "headers", None)
        return (headers.get("X-Forwarded-For", "") if headers else "").split(",")[-1].strip()

    def device(self) -> str | None:
        """The caller's tailnet device if it is the user's and allowed, else None."""
        if self.headers.get("Tailscale-User-Login", "").lower() != self.settings["tailnet_user"].lower():
            return None
        name = self.whois(self.caller_ip()) if self.caller_ip() else None
        return name if name in self.settings["devices"] else None

    def end_headers(self):
        if self.headers and self.headers.get("Origin") == self.settings["app_origin"]:
            self.send_header("Access-Control-Allow-Origin", self.settings["app_origin"])
            self.send_header("Vary", "Origin")
        super().end_headers()

    def json_reply(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def error(self, status: int, code: str) -> None:
        self.json_reply(status, {"error": code})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "POST, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path.startswith("/novnc/"):
            return self.novnc(url.path[len("/novnc/"):])
        if url.path == "/login/ws":
            return self.websocket(urllib.parse.parse_qs(url.query).get("ticket", [""])[0])
        if url.path == "/login/events":
            return self.events(urllib.parse.parse_qs(url.query).get("session", [""])[0])
        self.error(404, "not_found")

    def novnc(self, rel: str) -> None:
        root = self.settings["novnc"].resolve()
        path = (root / rel).resolve()
        if rel.split("/")[0] not in NOVNC_PARTS or root not in path.parents or not path.is_file():
            return self.error(404, "not_found")
        body = path.read_bytes()
        self.send_response(200)
        kind = "text/javascript" if path.suffix in (".js", ".mjs") else (
            mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()
        self.wfile.write(body)

    def do_POST(self):
        routes = {"/login/state": self.state, "/login/enroll": self.enroll,
                  "/login/session": self.session, "/login/reconnect": self.reconnect, "/login/done": self.done,
                  "/login/screen": self.screen}
        route = routes.get(urllib.parse.urlsplit(self.path).path)
        if route is None:
            return self.error(404, "not_found")
        device = self.device()
        if device is None:
            log.warning("refused: tailnet user %r, address %s", self.headers.get("Tailscale-User-Login"),
                        self.caller_ip())
            return self.error(403, "device")
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= 16 * 1024:
            return self.error(413, "body")
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return self.error(400, "json")
        if not isinstance(body, dict):
            return self.error(400, "json")
        if "appToken" in body:  # the Morzik App
            if not verify_app_token(str(body.get("appToken") or ""), self.settings.get("app_db", pathlib.Path("/nonexistent"))):
                log.warning("refused an unknown Morzik App token from %s", device)
                return self.error(401, "app")
            return route(body, device)
        max_age = DONE_MAX_AGE if route in (self.done, self.screen, self.reconnect) else INIT_DATA_MAX_AGE
        user = verify_init_data(str(body.get("initData") or ""), self.settings["bot_token"], max_age)
        if user is None:
            return self.error(401, "telegram")
        if str(user.get("id")) != str(self.settings["telegram_user_id"]):
            log.warning("refused Telegram user %s", user.get("id"))
            return self.error(403, "telegram_user")
        route(body, device)

    def request_info(self, request_id) -> dict | None:
        request = self.requests.get(str(request_id or ""))
        if not request:
            return None
        return {"id": request["id"], "site": request.get("site", ""), "url": request.get("url", ""),
                "waiting": request.get("status") == "waiting"}

    @staticmethod
    def app_id(body: dict) -> str | None:
        """The Morzik App install behind a request (hash of its device token, checked in do_POST)."""
        token = str(body.get("appToken") or "")
        return key_hash(token) if token else None

    def state(self, body: dict, device: str) -> None:
        self.json_reply(200, {"request": self.request_info(body.get("request")),
                              "canEnroll": self.devices.can_enroll(app=self.app_id(body)), "device": device})

    def enroll(self, body: dict, device: str) -> None:
        key = self.devices.enroll(f"{device}/{str(body.get('deviceId') or '')}", app=self.app_id(body))
        if key is None:
            log.warning("enroll refused for %s: no window open", device)
            return self.error(403, "enroll_closed")
        log.info("device key issued for %s", device)
        self.json_reply(200, {"deviceKey": key})

    def session(self, body: dict, device: str) -> None:
        if not self.devices.check(str(body.get("deviceKey") or "")):
            log.warning("unknown device key from %s", device)
            return self.error(401, "device_key")
        try:
            password = self.settings["vnc_password_file"].read_text().strip()
        except OSError:
            return self.error(500, "vnc_password")
        request = self.request_info(body.get("request"))
        session = self.sessions.add(SESSION_TTL, {"request": request and request["id"], "device": device})
        ticket = self.tickets.add(TICKET_TTL, {"device": device})
        log.info("screen session for %s%s", device, f", request {request['id']}" if request else "")
        self.json_reply(200, {"ticket": ticket, "password": password, "session": session, "request": request})

    def reconnect(self, body: dict, device: str) -> None:
        """The websocket of a live session dropped (iOS put the app to sleep): a new ticket, no Face ID again."""
        if self.sessions.get(str(body.get("session") or "")) is None:
            return self.error(401, "session")
        try:
            password = self.settings["vnc_password_file"].read_text().strip()
        except OSError:
            return self.error(500, "vnc_password")
        ticket = self.tickets.add(TICKET_TTL, {"device": device})
        log.info("screen reconnect for %s", device)
        self.json_reply(200, {"ticket": ticket, "password": password})

    def done(self, body: dict, device: str) -> None:
        session = self.sessions.get(str(body.get("session") or ""))
        if session is None:
            return self.error(401, "session")
        outcome = "done" if body.get("outcome") == "done" else "cancelled"
        if self.phone:
            self.phone.finish(str(body.get("session")), outcome)
        heard = bool(session["request"]) and self.requests.finish(session["request"], outcome)
        log.info("request %s %s from %s (Morzik %s)", session["request"], outcome, device,
                 "notified" if heard else "not waiting")
        self.json_reply(200, {"heard": heard})

    def screen(self, body: dict, device: str) -> None:
        """The page's size: Morzik's screen takes the shape of the phone for this session (see PhoneScreen)."""
        session_id = str(body.get("session") or "")
        if self.sessions.get(session_id) is None:
            return self.error(401, "session")
        metrics = screen_metrics(body)
        if metrics is None:
            return self.error(400, "size")
        if self.phone is None:
            return self.error(503, "screen")
        try:
            reply = self.phone.apply(session_id, metrics)
        except CdpError:
            return self.error(502, "browser")
        self.json_reply(200, reply)

    def events(self, session_id: str) -> None:
        """Server-sent events for the page of a session: a field got or lost the focus, the session ended.
        While the stream is open the phone's screen stays; RELEASE_AFTER s after it closes, the desktop is back."""
        if self.headers.get("Origin") != self.settings["app_origin"] or self.device() is None:
            return self.error(403, "device")
        if self.sessions.get(session_id) is None or self.phone is None:
            return self.error(401, "session")
        events = self.phone.listen(session_id)
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = events.get(timeout=15)
                except queue.Empty:
                    event = None
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode() if event else b": ping\n\n")
                self.wfile.flush()
                if event and event["type"] == "end":
                    break
        except OSError:
            pass
        finally:
            self.phone.unlisten(session_id, events)

    def websocket(self, ticket: str) -> None:
        if self.headers.get("Upgrade", "").lower() != "websocket":
            return self.error(400, "upgrade")
        if self.headers.get("Origin") != self.settings["app_origin"] or self.device() is None:
            return self.error(403, "device")
        if self.tickets.get(ticket, consume=True) is None:
            return self.error(401, "ticket")
        try:
            upstream = socket.create_connection(self.settings["websockify"], timeout=10)
        except OSError:
            return self.error(502, "screen")
        passed = ("Upgrade", "Connection", "Sec-WebSocket-Key", "Sec-WebSocket-Version", "Sec-WebSocket-Protocol")
        lines = ["GET /websockify HTTP/1.1", "Host: 127.0.0.1"] + [
            f"{name}: {self.headers[name]}" for name in passed if self.headers.get(name)]
        upstream.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        upstream.settimeout(None)
        log.info("screen opened from %s", self.device())
        self.close_connection = True
        # The client sends nothing more until websockify answers 101, so rfile holds no buffered bytes.
        client = self.connection

        def pipe(src, dst):
            try:
                while data := src.recv(65536):
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                for sock in (src, dst):
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

        back = threading.Thread(target=pipe, args=(upstream, client), daemon=True)
        back.start()
        pipe(client, upstream)
        back.join()
        upstream.close()
        log.info("screen closed")


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    # The page imports ~50 noVNC modules at once; with the default backlog of 5 most of them got 502 from
    # Tailscale Serve, which the browser reports as a CORS error.
    request_queue_size = 256


def allow_enroll(minutes: float) -> None:
    STATE.mkdir(mode=0o700, exist_ok=True)
    (STATE / "enroll-until").write_text(str(time.time() + minutes * 60))
    print(f"a new device can be set up in the next {minutes:g} min")


def main() -> None:
    if sys.argv[1:2] == ["allow-enroll"]:
        return allow_enroll(float(sys.argv[2]) if len(sys.argv) > 2 else 10)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    for path in (STATE, STATE / "requests"):
        path.mkdir(mode=0o700, exist_ok=True)
    Handler.settings = settings
    Handler.devices, Handler.requests = Devices(STATE), Requests(STATE)
    Handler.phone = PhoneScreen(settings["display"], settings["cdp"])
    Handler.phone.reset()
    # Text selected on the screen must not land in the phone's clipboard, only what is copied.
    subprocess.run(["vncconfig", "-display", settings["display"], "-set", "SendPrimary=0"], capture_output=True)
    sock = pathlib.Path(settings["socket"])
    sock.unlink(missing_ok=True)
    old = os.umask(0o177)  # the socket: owner only (root's tailscaled gets in anyway)
    try:
        server = Server(str(sock), Handler)
    finally:
        os.umask(old)
    log.info("listening on %s -> websockify %s:%s, devices %s", sock, *settings["websockify"],
             sorted(settings["devices"]))
    server.serve_forever()


if __name__ == "__main__":
    main()
