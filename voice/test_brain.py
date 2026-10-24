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
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import brain  # noqa: E402
import proxy  # noqa: E402

KEY = "k" * 40
CONTEXT_KEY = "c" * 40
SECRET = "wsec_test"
AGENT = "agent_test"
BOT = "123:bot-token"
OWNER = 123456789


def init_data(user_id=OWNER, bot=BOT, auth_date=None) -> str:
    fields = {"auth_date": str(int(time.time()) if auth_date is None else auth_date), "query_id": "q1",
              "user": json.dumps({"id": user_id, "first_name": "Пользователь"}, ensure_ascii=False)}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(fields)


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

    def test_calendar_text(self):
        text = brain.calendar_text([
            {"title": "Daily Meeting", "all_day": False, "location": None,
             "start": "2026-10-26T11:00:00", "end": "2026-10-26T11:30:00"},
            {"title": "Dentist", "all_day": False, "location": "Downtown,  Springfield",
             "start": "2026-10-27T12:00:00", "end": "2026-10-27T12:45:00"},
            {"title": "День рождения", "all_day": True, "start": "2026-10-26", "end": "2026-10-27"}])
        self.assertEqual(text.splitlines(), [
            "понедельник, 26 октября:", "- 11:00–11:30 Daily Meeting", "- весь день День рождения",
            "вторник, 27 октября:", "- 12:00–12:45 Dentist (Downtown, Springfield)"])

    def test_reminders_text(self):
        now = datetime.datetime(2026, 10, 24, 12, 0)
        text = brain.reminders_text([
            {"title": "Без срока", "due": None},
            {"title": "Отменить подписку", "due": "2026-10-25"},
            {"title": "Оплатить домен", "due": "2026-10-24T10:00:00"},
            {"title": "Сделано", "due": "2026-10-23", "completed": True}], now)
        self.assertEqual(text.splitlines(), [
            "Оплатить домен (срок: суббота, 24 октября 10:00, просрочено)",
            "Отменить подписку (срок: воскресенье, 25 октября)"])

    def test_weather_text(self):
        text = brain.weather_text({
            "current": {"temperature_2m": 5.4, "weather_code": 2},
            "daily": {"time": ["2026-10-24"], "weather_code": [61], "temperature_2m_min": [4.9],
                      "temperature_2m_max": [10.4], "precipitation_probability_max": [73]}})
        self.assertEqual(text.splitlines(), [
            "сейчас 5 °C, переменная облачность",
            "суббота, 24 октября: от 5 до 10 °C, дождь, вероятность осадков 73%"])

    def test_snapshot_live_sources_never_block(self):
        def broken():
            raise OSError("bridge down")
        with tempfile.TemporaryDirectory() as tmp:
            started = time.monotonic()
            snap = brain.snapshot(make_home(pathlib.Path(tmp)), sources={
                "calendar": lambda: "понедельник: Daily", "reminders": broken,
                "weather": lambda: time.sleep(3) or "поздно"}, timeout=0.3)
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(snap["calendar"], "понедельник: Daily")
        self.assertEqual(snap["reminders"], brain.UNAVAILABLE)
        self.assertEqual(snap["weather"], brain.UNAVAILABLE)

    def test_init_data(self):
        self.assertEqual(brain.verify_init_data(init_data(), BOT)["id"], OWNER)
        self.assertIsNone(brain.verify_init_data(init_data(), "999:other-bot"))
        self.assertIsNone(brain.verify_init_data(init_data(auth_date=int(time.time()) - 2 * 86400), BOT))
        self.assertIsNone(brain.verify_init_data(init_data().replace("123456789", "123456780"), BOT))
        self.assertIsNone(brain.verify_init_data("", BOT))

    def test_transcript_text(self):
        text = brain.transcript_text([
            {"role": "agent", "message": "Мрр, привет!"},
            {"role": "user", "message": "Что  завтра?"},
            {"role": "agent", "message": None, "tool_results": [{"result_value": '{"answer": "Дождь"}'}]},
            {"role": "agent", "message": "Завтра дождь."}])
        self.assertEqual(text, 'Морзик: Мрр, привет!\nПользователь: Что завтра?\n(результат инструмента: {"answer": "Дождь"})\n'
                               "Морзик: Завтра дождь.")


class FakeHermes(BaseHTTPRequestHandler):
    """Hermes api_server, and ElevenLabs' conversation token endpoint."""
    calls: list = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        ok = self.path.startswith("/v1/convai/conversation/token?agent_id=agent_test") and \
            self.headers.get("xi-api-key") == "el-key"
        payload = json.dumps({"token": "tok_123"} if ok else {"detail": "no"}).encode()
        self.send_response(200 if ok else 401)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

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
            "bot_token": BOT, "telegram_user_id": str(OWNER), "elevenlabs_key": "el-key",
            "app_origin": "https://morzik.pieces.run",
            "allowed_ips": set(), "ip_header": "X-Forwarded-For", "trusted_proxies": {"127.0.0.1"},
            "max_body": 512 * 1024, "max_transcript_body": 4 * 1024 * 1024, "fillers": ["Секунду... "],
            "hermes_home": make_home(pathlib.Path(cls.tmp.name))}
        proxy.Handler.limiter = proxy.RateLimiter(1000, 10000)
        proxy.Handler.settings["elevenlabs_api"] = f"http://127.0.0.1:{cls.hermes.server_address[1]}"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.hermes.shutdown()
        cls.tmp.cleanup()

    def setUp(self):
        FakeHermes.calls.clear()

    def post(self, path, data, headers=None, method="POST", with_headers=False):
        body = data if isinstance(data, bytes) or data is None else json.dumps(data).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        conn.request(method, path, body=body, headers={"Content-Type": "application/json", **(headers or {})})
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        result = resp.status, (json.loads(payload) if payload else None)
        return (*result, dict(resp.getheaders())) if with_headers else result

    def test_start_for_owner_only(self):
        status, data, headers = self.post("/voice/start", {"initData": init_data()}, with_headers=True)
        self.assertEqual(status, 200)
        self.assertEqual(data["conversationToken"], "tok_123")
        self.assertEqual(data["dynamicVariables"]["memory"], "Пользователь живёт в Springfield.")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://morzik.pieces.run")
        self.assertEqual(self.post("/voice/start", {"initData": init_data(user_id=1)})[0], 403)
        status, _, headers = self.post("/voice/start", {"initData": init_data(bot="1:x")}, with_headers=True)
        self.assertEqual(status, 401)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://morzik.pieces.run")
        self.assertEqual(self.post("/voice/start", None, method="OPTIONS")[0], 204)
        self.assertEqual(self.post("/voice/ask", None, method="OPTIONS")[0], 404)

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
