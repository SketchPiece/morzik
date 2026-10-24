"""Morzik login gate: the only way to Morzik's screen from a phone, inside the Morzik App.

Phone (Telegram, Tailscale on) -> Tailscale Serve https://sketch-server.<tailnet>.ts.net:6080 (tailnet only)
  -> this gate on a Unix socket -> websockify 127.0.0.1:6080 -> TigerVNC 127.0.0.1:5901

Every /login/ call needs all three:
- the tailnet: Tailscale Serve puts the caller's login and address in Tailscale-User-Login and
  X-Forwarded-For; the login must be the user's and the device one of MORZIK_LOGIN_DEVICES (`tailscale whois`).
  The gate listens on a Unix socket owned by `morzik`, so other users of the server cannot forge these headers;
- Telegram: initData signed for Morzik's bot, the user's user id, opened minutes ago;
- Face ID: a device key the gate issued once, kept by Telegram in the phone's biometric storage
  (BiometricManager) and released only after Face ID. The gate stores its hash.

Routes:
- GET /novnc/core/…, /novnc/vendor/… — the noVNC client modules (public code), with CORS for the app;
- POST /login/state {initData, request} — what the page should show: the site, whether a key can be issued;
- POST /login/enroll {initData, deviceId} — a new device key; only while no device is set up, or within
  a window opened on the server with `gate.py allow-enroll [minutes]`. A key counts once it opened a session;
- POST /login/session {initData, deviceKey, request} — the VNC password, a one-time websocket ticket
  (60 s) and a session id for /login/done;
- POST /login/done {initData, session, outcome} — "done" or "cancel", seen by Morzik's request_login tool;
- GET /login/ws?ticket=… — websocket to the screen, proxied as is to websockify.

Login requests are files in ~/.morzik-login/requests/<id>.json, created by the morzik-login Hermes plugin.
Settings: environment, falling back to ~/.hermes/.env. Standard library only.
"""

import hashlib
import hmac
import json
import logging
import mimetypes
import os
import pathlib
import re
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
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

    def can_enroll(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        try:
            window = float(self.window.read_text().strip())
        except (OSError, ValueError):
            window = 0
        return now < window or not self._active(self._load())

    def enroll(self, device_id: str, now: float | None = None) -> str | None:
        now = time.time() if now is None else now
        with self.lock:
            if not self.can_enroll(now):
                return None
            key = secrets.token_urlsafe(32)
            devices = [d for d in self._load() if d.get("active") or now - d.get("created", 0) < PENDING_KEY_TTL]
            devices.append({"hash": key_hash(key), "device": device_id[:80], "created": now, "active": False})
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
                  "/login/session": self.session, "/login/done": self.done}
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
        max_age = DONE_MAX_AGE if route == self.done else INIT_DATA_MAX_AGE
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

    def state(self, body: dict, device: str) -> None:
        self.json_reply(200, {"request": self.request_info(body.get("request")),
                              "canEnroll": self.devices.can_enroll(), "device": device})

    def enroll(self, body: dict, device: str) -> None:
        key = self.devices.enroll(f"{device}/{str(body.get('deviceId') or '')}")
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

    def done(self, body: dict, device: str) -> None:
        session = self.sessions.get(str(body.get("session") or ""))
        if session is None:
            return self.error(401, "session")
        outcome = "done" if body.get("outcome") == "done" else "cancelled"
        heard = bool(session["request"]) and self.requests.finish(session["request"], outcome)
        log.info("request %s %s from %s (Morzik %s)", session["request"], outcome, device,
                 "notified" if heard else "not waiting")
        self.json_reply(200, {"heard": heard})

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
