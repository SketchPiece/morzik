"""Tests for the login gate: python3 -m unittest login/test_gate.py"""

import hashlib
import hmac
import http.client
import json
import pathlib
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import gate  # noqa: E402

BOT_TOKEN = "123:abc"
OWNER = 123456789
ORIGIN = "https://morzik.pieces.run"


def init_data(user_id=OWNER, age=0, token=BOT_TOKEN):
    fields = {"auth_date": str(int(time.time() - age)), "user": json.dumps({"id": user_id})}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(fields)


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost")
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.path)


class DevicesTest(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.devices = gate.Devices(self.dir)

    def test_first_device_enrolls_then_window_closes(self):
        key = self.devices.enroll("phone")
        self.assertTrue(self.devices.check(key))
        self.assertFalse(self.devices.can_enroll())
        self.assertIsNone(self.devices.enroll("intruder"))

    def test_window_lets_a_second_device_in_once(self):
        self.devices.check(self.devices.enroll("phone"))
        gate.STATE = self.dir
        (self.dir / "enroll-until").write_text(str(time.time() + 60))
        second = self.devices.enroll("new phone")
        self.assertTrue(self.devices.check(second))
        self.assertFalse(self.devices.can_enroll())

    def test_unused_key_expires(self):
        key = self.devices.enroll("phone", now=1000)
        self.assertFalse(self.devices.check(key, now=1000 + gate.PENDING_KEY_TTL + 1))

    def test_unknown_key(self):
        self.assertFalse(self.devices.check("nope"))
        self.assertFalse(self.devices.check(""))


class InitDataTest(unittest.TestCase):
    def test_signed_and_fresh(self):
        self.assertEqual(gate.verify_init_data(init_data(), BOT_TOKEN, 60)["id"], OWNER)

    def test_old_or_forged(self):
        self.assertIsNone(gate.verify_init_data(init_data(age=120), BOT_TOKEN, 60))
        self.assertIsNone(gate.verify_init_data(init_data(token="1:other"), BOT_TOKEN, 60))


class GateTest(unittest.TestCase):
    """The gate on a real Unix socket, with tailscale whois faked."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        (self.dir / "requests").mkdir()
        (self.dir / "vnc").write_text("vncpass\n")
        gate.Handler.settings = {
            "bot_token": BOT_TOKEN, "telegram_user_id": str(OWNER), "tailnet_user": "user@example.com",
            "devices": {"iphone"}, "app_origin": ORIGIN, "websockify": ("127.0.0.1", 1),
            "vnc_password_file": self.dir / "vnc", "novnc": self.dir / "novnc",
        }
        gate.Handler.devices, gate.Handler.requests = gate.Devices(self.dir), gate.Requests(self.dir)
        gate.Handler.whois = staticmethod(lambda ip: {"100.1.1.1": "iphone", "100.2.2.2": "pieces"}.get(ip))
        self.sock = str(self.dir / "gate.sock")
        self.server = gate.Server(self.sock, gate.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        (self.dir / "requests" / "abcdefabcdef0123.json").write_text(json.dumps(
            {"id": "abcdefabcdef0123", "site": "Amazon", "url": "https://amazon.com", "status": "waiting"}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post(self, path, body, ip="100.1.1.1", login="user@example.com", **extra):
        conn = UnixConnection(self.sock)
        headers = {"Content-Type": "application/json", "Origin": ORIGIN, "Tailscale-User-Login": login,
                   "X-Forwarded-For": ip}
        conn.request("POST", path, json.dumps({"initData": init_data(**extra), **body}), headers)
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read()), resp.getheader("Access-Control-Allow-Origin")

    def test_whole_flow(self):
        status, state, cors = self.post("/login/state", {"request": "abcdefabcdef0123"})
        self.assertEqual((status, cors), (200, ORIGIN))
        self.assertEqual(state["request"]["site"], "Amazon")
        self.assertTrue(state["canEnroll"])
        _, enrolled, _ = self.post("/login/enroll", {"deviceId": "x"})
        status, session, _ = self.post("/login/session", {"deviceKey": enrolled["deviceKey"],
                                                          "request": "abcdefabcdef0123"})
        self.assertEqual(status, 200)
        self.assertEqual(session["password"], "vncpass")
        self.assertIsNotNone(gate.Handler.tickets.get(session["ticket"]))
        status, done, _ = self.post("/login/done", {"session": session["session"], "outcome": "done"})
        self.assertEqual((status, done["heard"]), (200, True))
        saved = json.loads((self.dir / "requests" / "abcdefabcdef0123.json").read_text())
        self.assertEqual(saved["status"], "done")
        # Once enrolled, nobody else can get a key.
        self.assertEqual(self.post("/login/enroll", {})[0], 403)

    def test_refuses_other_devices_users_and_forged_addresses(self):
        self.assertEqual(self.post("/login/state", {}, ip="100.2.2.2")[1]["error"], "device")
        self.assertEqual(self.post("/login/state", {}, login="else@example.com")[1]["error"], "device")
        # Tailscale appends the real address; a caller-supplied one in front does not count.
        self.assertEqual(self.post("/login/state", {}, ip="100.1.1.1, 100.2.2.2")[0], 403)
        self.assertEqual(self.post("/login/state", {}, user_id=1)[1]["error"], "telegram_user")
        self.assertEqual(self.post("/login/state", {}, age=gate.INIT_DATA_MAX_AGE + 5)[1]["error"], "telegram")

    def test_session_needs_a_known_key(self):
        status, reply, _ = self.post("/login/session", {"deviceKey": "guess"})
        self.assertEqual((status, reply["error"]), (401, "device_key"))

    def test_websocket_needs_a_ticket(self):
        conn = UnixConnection(self.sock)
        conn.request("GET", "/login/ws?ticket=nope", headers={
            "Upgrade": "websocket", "Connection": "Upgrade", "Origin": ORIGIN,
            "Tailscale-User-Login": "user@example.com", "X-Forwarded-For": "100.1.1.1"})
        self.assertEqual(conn.getresponse().status, 401)

    def test_many_parallel_module_loads(self):
        (self.dir / "novnc" / "core").mkdir(parents=True)
        (self.dir / "novnc" / "core" / "m.js").write_text("export default 1;")
        socks = []
        for _ in range(60):  # open them all before any is served, like a browser loading modules
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.sock)
            socks.append(sock)
        for sock in socks:
            sock.sendall(b"GET /novnc/core/m.js HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        for sock in socks:
            self.assertTrue(sock.makefile("rb").readline().startswith(b"HTTP/1.1 200"))
            sock.close()

    def test_novnc_files_only(self):
        (self.dir / "novnc" / "core").mkdir(parents=True)
        (self.dir / "novnc" / "core" / "rfb.js").write_text("export default 1;")
        (self.dir / "secret.txt").write_text("no")
        for path, expected in (("/novnc/core/rfb.js", 200), ("/novnc/core/../../secret.txt", 404),
                               ("/novnc/app/ui.js", 404)):
            conn = UnixConnection(self.sock)
            conn.request("GET", path)
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, expected, path)


if __name__ == "__main__":
    unittest.main()
