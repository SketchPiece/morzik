"""Tests for the voice copy routes: python3 -m unittest voice/test_brain.py"""

import datetime
import hashlib
import hmac
import http.client
import json
import pathlib
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import brain  # noqa: E402
import proxy  # noqa: E402

KEY = "k" * 40
CONTEXT_KEY = "c" * 40
SECRET = "wsec_test"
AGENT = "agent_test"


def signed(body: bytes, secret: str = SECRET, stamp: int | None = None) -> str:
    stamp = int(time.time()) if stamp is None else stamp
    digest = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={stamp},v0={digest}"


def make_home(root: pathlib.Path, messages=()) -> pathlib.Path:
    (root / "memories").mkdir()
    (root / "SOUL.md").write_text("Ты Морзик.")
    (root / "memories/USER.md").write_text("Пользователь живёт в Springfield.")
    db = sqlite3.connect(root / "state.db")
    db.execute("CREATE TABLE sessions (id TEXT, source TEXT)")
    db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL)")
    db.execute("INSERT INTO sessions VALUES ('tg', 'telegram'), ('api', 'api_server')")
    db.executemany("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)", messages)
    db.commit()
    db.close()
    return root


class BrainTest(unittest.TestCase):
    def test_signature(self):
        body = b'{"type":"post_call_transcription"}'
        self.assertTrue(brain.verify_signature(signed(body), body, SECRET))
        self.assertFalse(brain.verify_signature(signed(body), body + b" ", SECRET))
        self.assertFalse(brain.verify_signature(signed(body, "other"), body, SECRET))
        self.assertFalse(brain.verify_signature(signed(body, stamp=int(time.time()) - 7200), body, SECRET))
        self.assertFalse(brain.verify_signature("", body, SECRET))
        self.assertFalse(brain.verify_signature(signed(body), body, ""))

    def test_recent_messages_only_telegram_and_fresh(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(pathlib.Path(tmp), [
                ("tg", "user", "старое", now - 10 * 86400),
                ("tg", "user", "Привет,   как дела?", now - 60),
                ("tg", "assistant", "Мур, хорошо", now - 30),
                ("tg", "tool", "{}", now - 20),
                ("api", "user", "голосовое", now - 10)])
            text = brain.recent_messages(home / "state.db", now=now)
        lines = text.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("Пользователь: Привет, как дела?"))
        self.assertTrue(lines[1].endswith("Морзик: Мур, хорошо"))

    def test_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = brain.snapshot(make_home(pathlib.Path(tmp)), datetime.datetime(2026, 10, 23, 17, 5))
        self.assertNotIn("soul", snap)
        self.assertEqual(snap["memory"], "Пользователь живёт в Springfield.")
        self.assertEqual(snap["recent"], "(давно не переписывались)")
        self.assertEqual(snap["now"], "пятница, 23 октября 2026, 17:05")

    def test_transcript_text(self):
        text = brain.transcript_text([
            {"role": "agent", "message": "Мрр, привет!"},
            {"role": "user", "message": "Что  завтра?"},
            {"role": "agent", "message": None, "tool_results": [{"result_value": '{"answer": "Дождь"}'}]},
            {"role": "agent", "message": "Завтра дождь."}])
        self.assertEqual(text, 'Копия: Мрр, привет!\nПользователь: Что завтра?\n(ответ Морзика копии: {"answer": "Дождь"})\n'
                               "Копия: Завтра дождь.")


class FakeHermes(BaseHTTPRequestHandler):
    calls: list = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeHermes.calls.append((dict(self.headers), body))
        session = self.headers.get("X-Hermes-Session-Id") or f"api-{len(FakeHermes.calls)}"
        payload = json.dumps({"choices": [{"message": {"content": "Сделано."}, "finish_reason": "stop"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Hermes-Session-Id", session)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class RoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.hermes = ThreadingHTTPServer(("127.0.0.1", 0), FakeHermes)
        threading.Thread(target=cls.hermes.serve_forever, daemon=True).start()
        proxy.Handler.settings = {
            "upstream_host": "127.0.0.1", "upstream_port": cls.hermes.server_address[1], "upstream_key": "up",
            "key": KEY, "context_key": CONTEXT_KEY, "webhook_secret": SECRET, "agent_id": AGENT,
            "allowed_ips": set(), "ip_header": "X-Forwarded-For", "trusted_proxies": {"127.0.0.1"},
            "max_body": 512 * 1024, "max_transcript_body": 4 * 1024 * 1024, "fillers": ["Секунду... "],
            "hermes_home": make_home(pathlib.Path(cls.tmp.name))}
        proxy.Handler.limiter = proxy.RateLimiter(1000, 10000)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.hermes.shutdown()
        cls.tmp.cleanup()

    def setUp(self):
        FakeHermes.calls.clear()

    def post(self, path, data, headers=None):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json", **(headers or {})})
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp.status, (json.loads(payload) if payload else None)

    def test_context_needs_its_own_key(self):
        self.assertEqual(self.post("/voice/context", {}, {"Authorization": f"Bearer {KEY}"})[0], 401)
        status, snap = self.post("/voice/context", {}, {"Authorization": f"Bearer {CONTEXT_KEY}"})
        self.assertEqual(status, 200)
        self.assertEqual(snap["memory"], "Пользователь живёт в Springfield.")

    def test_ask_keeps_one_session_per_call(self):
        auth = {"Authorization": f"Bearer {KEY}"}
        self.assertEqual(self.post("/voice/ask", {"request": "x"}, {"Authorization": f"Bearer {CONTEXT_KEY}"})[0], 401)
        status, answer = self.post("/voice/ask", {"request": "Что в календаре?", "conversation_id": "conv_1"}, auth)
        self.assertEqual((status, answer), (200, {"answer": "Сделано."}))
        self.post("/voice/ask", {"request": "А послезавтра?", "conversation_id": "conv_1"}, auth)
        self.post("/voice/ask", {"request": "Погода?", "conversation_id": "conv_2"}, auth)
        sent = [(h.get("X-Hermes-Session-Id"), b["messages"][-1]["content"]) for h, b in FakeHermes.calls]
        self.assertEqual(sent, [(None, "Что в календаре?"), ("api-1", "А послезавтра?"), (None, "Погода?")])
        self.assertEqual(FakeHermes.calls[0][1]["model"], "morzik-voice")
        self.assertEqual(FakeHermes.calls[0][1]["messages"][0]["content"], brain.ASK_SYSTEM)

    def test_after_call_signed_once_and_saved(self):
        event = {"type": "post_call_transcription", "data": {
            "agent_id": AGENT, "conversation_id": "conv_9",
            "transcript": [{"role": "agent", "message": "Привет"}, {"role": "user", "message": "Напомни про врача"}]}}
        body = json.dumps(event).encode()
        self.assertEqual(self.post("/voice/after-call", body, {"ElevenLabs-Signature": signed(body, "x")})[0], 401)
        self.assertEqual(self.post("/voice/after-call", body, {"ElevenLabs-Signature": signed(body)})[0], 200)
        self.assertEqual(self.post("/voice/after-call", body, {"ElevenLabs-Signature": signed(body)})[0], 200)
        for _ in range(50):
            if FakeHermes.calls:
                break
            time.sleep(0.05)
        time.sleep(0.2)
        self.assertEqual(len(FakeHermes.calls), 1)  # the retry was not processed again
        self.assertIn("Пользователь: Напомни про врача", FakeHermes.calls[0][1]["messages"][0]["content"])

    def test_after_call_for_another_agent_is_ignored(self):
        event = {"type": "post_call_transcription", "data": {
            "agent_id": "agent_other", "conversation_id": "conv_10", "transcript": [{"role": "user", "message": "Привет"}]}}
        body = json.dumps(event).encode()
        self.assertEqual(self.post("/voice/after-call", body, {"ElevenLabs-Signature": signed(body)})[0], 200)
        time.sleep(0.3)
        self.assertEqual(FakeHermes.calls, [])

    def test_unknown_route(self):
        self.assertEqual(self.post("/voice/other", {}, {"Authorization": f"Bearer {KEY}"})[0], 404)


if __name__ == "__main__":
    unittest.main()
