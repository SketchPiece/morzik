"""Morzik's voice copy: what the ElevenLabs agent knows at the start of a call and how it gets back.

ElevenLabs runs its own fast model in the call. Its character is written in the agent prompt
(voice/agent-prompt.md, a voice version of SOUL.md: SOUL is half about Telegram formatting and in
places contradicts the voice rules). Before the call the Mini App backend asks for a snapshot (his
memory about the user, the latest Telegram messages, the time) and passes it to the agent as dynamic
variables. During the call the agent hands real work to Morzik in Hermes
("ask Morzik" tool). After the call ElevenLabs sends the transcript and Morzik saves what matters.

Standard library only; the HTTP side lives in proxy.py.
"""

import datetime
import hashlib
import hmac
import pathlib
import sqlite3
import threading
import time

WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
          "октября", "ноября", "декабря")

# System prompt for tasks handed over from a call (the "ask Morzik" tool).
ASK_SYSTEM = (
    "Это задача из голосового звонка с пользователем. Звонок ведёт твоя голосовая копия: она слышит "
    "Пользователя и передала тебе его просьбу. Сделай, что просят, своими инструментами. Ответ копия "
    "перескажет голосом, поэтому отвечай коротко, одной-тремя фразами, без разметки, списков и "
    "ссылок. Если без уточнения не обойтись, скажи, что именно уточнить. Необратимые действия "
    "(отправить письмо, удалить) копия сначала подтверждает у пользователя голосом; если в просьбе сказано, "
    "что пользователь подтвердил, делай без повторного вопроса.")

# Sent to Morzik after a call, with the transcript.
SAVE_REQUEST = (
    "Закончился голосовой звонок с пользователем, ниже запись. Его вела твоя голосовая копия. Сохрани "
    "в память только то, что стоит помнить дальше: договорённости и обещания, новые факты об "
    "Пользователе, просьбы на потом. Если такого нет, ничего не сохраняй. Ответь одним словом: готово."
    "\n\n{transcript}")


def spoken_time(moment: datetime.datetime) -> str:
    return (f"{WEEKDAYS[moment.weekday()]}, {moment.day} {MONTHS[moment.month - 1]} {moment.year}, "
            f"{moment:%H:%M}")


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def recent_messages(db_path: pathlib.Path, limit: int = 20, max_age_days: float = 3,
                    max_chars: int = 400, now: float | None = None) -> str:
    """The latest Telegram exchange with the user, oldest first, as plain lines."""
    now = time.time() if now is None else now
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return ""
    try:
        rows = conn.execute(
            "SELECT m.role, m.content, m.timestamp FROM messages m JOIN sessions s ON s.id = m.session_id "
            "WHERE s.source = 'telegram' AND m.role IN ('user', 'assistant') AND m.content IS NOT NULL "
            "AND trim(m.content) != '' AND m.timestamp >= ? ORDER BY m.timestamp DESC LIMIT ?",
            (now - max_age_days * 86400, limit)).fetchall()
    except sqlite3.Error:
        return ""
    finally:
        conn.close()
    lines = []
    for role, content, stamp in reversed(rows):
        text = " ".join(str(content).split())
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "…"
        who = "Пользователь" if role == "user" else "Морзик"
        lines.append(f"[{datetime.datetime.fromtimestamp(stamp):%d.%m %H:%M}] {who}: {text}")
    return "\n".join(lines)


def snapshot(hermes_home: pathlib.Path, now: datetime.datetime | None = None) -> dict:
    """Dynamic variables for the ElevenLabs agent: what Morzik knows right now."""
    now = now or datetime.datetime.now()
    memory = "\n\n".join(text for text in (_read(hermes_home / "memories/USER.md"),
                                           _read(hermes_home / "memories/MEMORY.md")) if text)
    return {
        "memory": memory or "(пусто)",
        "recent": recent_messages(hermes_home / "state.db") or "(давно не переписывались)",
        "now": spoken_time(now),
    }


def verify_signature(header: str, body: bytes, secret: str, tolerance: float = 1800,
                     now: float | None = None) -> bool:
    """ElevenLabs-Signature: "t=<unix>,v0=<hex hmac-sha256 of '<t>.<body>'>"."""
    if not header or not secret:
        return False
    parts = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    stamp, signature = parts.get("t", ""), parts.get("v0", "")
    if not stamp.isdigit() or not signature:
        return False
    now = time.time() if now is None else now
    if abs(now - int(stamp)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def transcript_text(transcript: list, max_tool_chars: int = 300) -> str:
    """ElevenLabs post-call transcript -> lines for Morzik."""
    lines = []
    for turn in transcript or []:
        if not isinstance(turn, dict):
            continue
        who = "Пользователь" if turn.get("role") == "user" else "Копия"
        message = " ".join(str(turn.get("message") or "").split())
        if message:
            lines.append(f"{who}: {message}")
        for result in turn.get("tool_results") or []:
            if isinstance(result, dict):
                value = " ".join(str(result.get("result_value") or "").split())[:max_tool_chars]
                if value:
                    lines.append(f"(ответ Морзика копии: {value})")
    return "\n".join(lines)


class CallSessions:
    """ElevenLabs conversation id -> Hermes session id, so one call's tasks share a session."""

    def __init__(self, ttl: float = 6 * 3600, size: int = 200):
        self.ttl, self.size = ttl, size
        self.items: dict[str, tuple[str, float]] = {}
        self.lock = threading.Lock()

    def get(self, conversation_id: str) -> str | None:
        with self.lock:
            hit = self.items.get(conversation_id)
            if hit and time.monotonic() - hit[1] <= self.ttl:
                return hit[0]
            self.items.pop(conversation_id, None)
            return None

    def put(self, conversation_id: str, session_id: str) -> None:
        with self.lock:
            self.items[conversation_id] = (session_id, time.monotonic())
            while len(self.items) > self.size:
                self.items.pop(next(iter(self.items)))


class Seen:
    """Conversation ids already handled (ElevenLabs retries webhooks)."""

    def __init__(self, size: int = 500):
        self.size, self.items, self.lock = size, {}, threading.Lock()

    def first_time(self, key: str) -> bool:
        with self.lock:
            if key in self.items:
                return False
            self.items[key] = True
            while len(self.items) > self.size:
                self.items.pop(next(iter(self.items)))
            return True
