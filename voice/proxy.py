"""Morzik voice proxy: the only door from the internet to Hermes' API server.

ElevenLabs (Custom LLM) -> tunnel -> this proxy (127.0.0.1:8650) -> Hermes api_server (127.0.0.1:8642)

- Serves exactly one route, POST /v1/chat/completions; everything else is 404.
- Its own bearer key (MORZIK_VOICE_KEY), so ElevenLabs never holds API_SERVER_KEY, which also
  opens /api/sessions, /v1/runs, /api/jobs and the rest.
- Pins the model to the morzik-voice alias (Haiku, voice toolset) whatever the caller asks for.
- Optional allowlist of caller IPs (MORZIK_VOICE_ALLOWED_IPS, read from MORZIK_VOICE_IP_HEADER
  set by the tunnel), a request rate limit and a body size cap.
- Speech-friendly stream: Hermes' own SSE events are dropped, and when Morzik reaches for a tool
  before saying anything the caller gets a short filler at once ("Секунду, гляну... ") instead of
  silence until the whole turn is done.

Settings come from the environment, falling back to ~/.hermes/.env. Standard library only.
"""

import hmac
import http.client
import json
import logging
import os
import pathlib
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROUTE = "/v1/chat/completions"
MODEL_ALIAS = "morzik-voice"
# Request fields passed on to Hermes; model, provider, model_options and the like are not.
PASSED_FIELDS = ("messages", "stream", "temperature", "max_tokens")

log = logging.getLogger("morzik-voice")


def load_settings() -> dict:
    env = {}
    dotenv = pathlib.Path.home() / ".hermes/.env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                name, value = line.split("=", 1)
                env[name.strip()] = value.strip().strip('"').strip("'")
    env.update(os.environ)

    def get(name, default=""):
        return env.get(name, default)

    settings = {
        "listen_host": get("MORZIK_VOICE_HOST", "127.0.0.1"),
        "listen_port": int(get("MORZIK_VOICE_PORT", "8650")),
        "upstream_host": get("MORZIK_VOICE_UPSTREAM_HOST", "127.0.0.1"),
        "upstream_port": int(get("MORZIK_VOICE_UPSTREAM_PORT", "8642")),
        "upstream_key": get("API_SERVER_KEY"),
        "key": get("MORZIK_VOICE_KEY"),
        "allowed_ips": {ip.strip() for ip in get("MORZIK_VOICE_ALLOWED_IPS").split(",") if ip.strip()},
        "ip_header": get("MORZIK_VOICE_IP_HEADER", "X-Forwarded-For"),
        # Peers allowed to tell us the caller's IP (the tunnel); everyone else is taken at face value.
        "trusted_proxies": {ip.strip() for ip in get(
            "MORZIK_VOICE_TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if ip.strip()},
        "per_minute": int(get("MORZIK_VOICE_PER_MINUTE", "30")),
        "per_day": int(get("MORZIK_VOICE_PER_DAY", "1500")),
        "max_body": int(get("MORZIK_VOICE_MAX_BODY", str(512 * 1024))),
        "filler": get("MORZIK_VOICE_FILLER", "Секунду, гляну... "),
    }
    if len(settings["key"]) < 32 or not settings["upstream_key"]:
        raise SystemExit("MORZIK_VOICE_KEY (32+ chars) and API_SERVER_KEY must be set")
    return settings


class RateLimiter:
    """Sliding windows over all callers: there is one user, so one budget."""

    def __init__(self, per_minute: int, per_day: int):
        self.limits = ((60.0, per_minute), (86400.0, per_day))
        self.hits: deque[float] = deque()
        self.lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self.lock:
            while self.hits and now - self.hits[0] > self.limits[-1][0]:
                self.hits.popleft()
            for window, limit in self.limits:
                if sum(1 for t in self.hits if now - t <= window) >= limit:
                    return False
            self.hits.append(now)
            return True


def sse_events(resp):
    """Yield (event_name, data, raw_lines) per SSE event from an http.client response."""
    name, data, raw = None, [], []
    while True:
        line = resp.readline()
        if not line:
            break
        raw.append(line)
        text = line.decode("utf-8", "replace").rstrip("\r\n")
        if text == "":
            if raw != [line]:
                yield name, "\n".join(data), raw
            name, data, raw = None, [], []
        elif text.startswith("event:"):
            name = text[6:].strip()
        elif text.startswith("data:"):
            data.append(text[5:].lstrip())
    if len(raw) > 1:
        yield name, "\n".join(data), raw


# Spoken instead of Hermes' raw error text (model errors, provider limits), like morzik-chat in Telegram.
LIMIT_LINE = "Ой, я выдохся, лимит кончился. Давай чуть позже."
ERROR_LINE = "Ой, я что-то завис. Повтори, пожалуйста?"


def _frame(data: dict) -> bytes:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def _content_chunk(meta: dict, text: str) -> bytes:
    return _frame({"id": meta.get("id") or "chatcmpl-morzik-voice", "object": "chat.completion.chunk",
                   "created": meta.get("created") or int(time.time()), "model": MODEL_ALIAS,
                   "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]})


def speech_stream(events, filler: str, note=lambda what: None):
    """Hermes chat-completion SSE events -> frames fit to be spoken.

    Drops Hermes' own named events; says *filler* when a tool starts before any words; holds each
    text chunk until the next event, so a failed turn (finish_reason other than "stop") is voiced as
    a short apology instead of the raw error text.
    """
    spoke = False
    meta: dict = {}
    held: list[bytes] = []  # text frames not yet released
    for name, data, raw in events:
        if name == "hermes.tool.progress":
            if not spoke and filler:
                try:
                    running = json.loads(data).get("status") == "running"
                except ValueError:
                    running = False
                if running:
                    yield from held
                    held = []
                    yield _content_chunk(meta, filler)
                    note("filler")
                    spoke = True
            continue
        if name and name.startswith("hermes."):
            continue
        chunk = None
        if data and data != "[DONE]":
            try:
                chunk = json.loads(data)
            except ValueError:
                pass
        if isinstance(chunk, dict):
            meta = meta or {k: chunk.get(k) for k in ("id", "created", "model")}
            choice = (chunk.get("choices") or [{}])[0]
            finish = choice.get("finish_reason")
            if finish and finish != "stop":
                error = json.dumps(chunk.get("error") or chunk.get("hermes") or {})
                limited = any(word in error.lower() for word in ("429", "rate", "limit", "quota"))
                note(f"turn ended with {finish}, held text dropped")
                held = []
                yield _content_chunk(meta, " " + (LIMIT_LINE if limited else ERROR_LINE))
                choice["finish_reason"] = "stop"
                chunk.pop("error", None)
                chunk.pop("hermes", None)
                yield _frame(chunk)
                continue
            if (choice.get("delta") or {}).get("content"):
                if not spoke:
                    note("first content")
                spoke = True
                yield from held
                held = [b"".join(raw)]
                continue
        yield from held
        held = []
        yield b"".join(raw)
    yield from held



class Handler(BaseHTTPRequestHandler):
    server_version = "morzik-voice"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    settings: dict = {}
    limiter: RateLimiter
    streaming = False  # True once the 200 SSE headers are out

    def log_message(self, fmt, *args):
        log.info("%s %s", self.client_ip(), fmt % args)

    def client_ip(self) -> str:
        peer = self.client_address[0]
        if peer not in self.settings["trusted_proxies"]:
            return peer
        headers = getattr(self, "headers", None)  # absent when the request line was malformed
        forwarded = headers.get(self.settings["ip_header"], "") if headers else ""
        # The tunnel appends the address it saw; earlier entries come from the caller and can be forged.
        return forwarded.split(",")[-1].strip() or peer

    def reply(self, status: int, message: str) -> None:
        body = json.dumps({"error": {"message": message, "type": "morzik_voice_proxy"}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # The request body may be left unread: never reuse this connection.
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(404, "not found")

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_GET

    def do_POST(self):
        s = self.settings
        if self.path.split("?")[0] != ROUTE:
            return self.reply(404, "not found")
        if s["allowed_ips"] and self.client_ip() not in s["allowed_ips"]:
            return self.reply(403, "forbidden")
        auth = self.headers.get("Authorization", "")
        if not hmac.compare_digest(auth.encode(), f"Bearer {s['key']}".encode()):
            return self.reply(401, "unauthorized")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > s["max_body"]:
            return self.reply(413, "body too large or empty")
        if not self.limiter.allow():
            return self.reply(429, "rate limited")
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return self.reply(400, "invalid json")
        if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
            return self.reply(400, "messages required")

        upstream_body = {k: body[k] for k in PASSED_FIELDS if k in body}
        upstream_body["model"] = MODEL_ALIAS
        stream = bool(upstream_body.get("stream"))
        conn = http.client.HTTPConnection(s["upstream_host"], s["upstream_port"], timeout=300)
        started = time.monotonic()
        try:
            conn.request("POST", ROUTE, body=json.dumps(upstream_body).encode(), headers={
                "Authorization": f"Bearer {s['upstream_key']}", "Content-Type": "application/json"})
            resp = conn.getresponse()
            if not stream or resp.status != 200:
                payload = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.getheader("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.close_connection = True
                self.end_headers()
                self.wfile.write(payload)
                return
            self.relay_stream(resp, started)
        except (ConnectionError, OSError, http.client.HTTPException) as exc:
            log.warning("upstream failed: %s", exc)
            if not self.streaming:
                try:
                    self.reply(502, "upstream unavailable")
                except OSError:
                    pass
        finally:
            conn.close()

    def relay_stream(self, resp, started: float) -> None:
        self.streaming = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def note(what: str) -> None:
            log.info("%s at %.2fs", what, time.monotonic() - started)

        for frame in speech_stream(sse_events(resp), self.settings["filler"], note):
            self.wfile.write(frame)
            self.wfile.flush()
        note("stream done")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    Handler.settings = settings
    Handler.limiter = RateLimiter(settings["per_minute"], settings["per_day"])
    server = ThreadingHTTPServer((settings["listen_host"], settings["listen_port"]), Handler)
    server.daemon_threads = True
    log.info("listening on %s:%s -> %s:%s, allowlist %s", settings["listen_host"],
             settings["listen_port"], settings["upstream_host"], settings["upstream_port"],
             sorted(settings["allowed_ips"]) or "off")
    server.serve_forever()


if __name__ == "__main__":
    main()
