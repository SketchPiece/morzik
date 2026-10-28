"""Morzik's voice copy: what the ElevenLabs agent knows at the start of a call and how it gets back.

ElevenLabs runs its own fast model in the call. Its character is written in the agent prompt
(voice/agent-prompt.md, a voice version of SOUL.md: SOUL is half about Telegram formatting and in
places contradicts the voice rules). Before the call the Mini App backend asks for a snapshot (his
memory about the user, calendar, reminders, weather, the time) and passes it to the agent as dynamic
variables. During the call the agent hands real work to Morzik in Hermes (perform_task) and reads
the app chat and past calls with its own tools when it needs them (read_chat, read_calls). After the call ElevenLabs sends the transcript and Morzik saves what matters;
the transcript also reaches his chats with the next turn there (log_call, app/calls.py).

Standard library only; the HTTP side lives in proxy.py.
"""

import concurrent.futures
import datetime
import hashlib
import hmac
import json
import logging
import pathlib
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request

WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
          "октября", "ноября", "декабря")
log = logging.getLogger("morzik-voice")

# System prompt for tasks from the perform_task tool.
ASK_SYSTEM = (
    "Это просьба пользователя из голосового звонка. Сделай, что просят, своими инструментами. "
    "Ответ будет произнесён голосом, поэтому отвечай коротко, одной-тремя фразами, без разметки, "
    "списков и ссылок. Если без уточнения не обойтись, скажи, что именно уточнить. Необратимые "
    "действия (отправить письмо, удалить) сначала подтверждаются у пользователя голосом; если в просьбе "
    "сказано, что пользователь подтвердил, делай без повторного вопроса.\n\n"
    "Пользователь ждёт ответа в звонке, поэтому частые инструменты вызывай сразу через tool_call, без "
    "tool_search и tool_describe (время без смещения считается местным временем Мака):\n"
    "- mcp__apple__calendar_list_events {start, end, query?}: события, start/end в ISO 8601;\n"
    "- mcp__apple__reminders_list {due_before?, query?, list?}: открытые напоминания;\n"
    "- mcp__apple__reminders_create {title, due?, list?, notes?}: новое напоминание;\n"
    "- mcp__email__triage_inbox {}: непрочитанная почта; mcp__email__search_threads {query}: поиск "
    "писем (запрос в стиле Gmail);\n"
    "- mcp__semafor__get_unread_summary {}: непрочитанное в Telegram;\n"
    "- mcp__helm__helm_list_unsettled_threads {}: что висит в Helm.\n"
    "Погоду и факты из интернета ищи через web_search {query, limit: 3}. Для остального ищи инструмент "
    "через tool_search.")

# Sent to Morzik after a call, with the transcript.
SAVE_REQUEST = (
    "Закончился голосовой звонок с пользователем, ниже запись. Сохрани "
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


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


# Hermes stores a few things as user turns; for the call they become who really said what.
# Cron delivery: Morzik's own message from a background job (hermes cron/scheduler_delivery.py).
CRON = re.compile(r"\[Cron delivery: [^\]]*\]\s*", re.S)
# Reaction from the Morzik App (app/adapter.py) -> «👍 на «…»».
REACTION = re.compile(r"\[Пользователь поставил реакцию (\S+) на твоё сообщение «(.*?)»\. .*\]\s*$", re.S)
REPLY = re.compile(r"\[Replying to your previous message: \"(.*?)\"\]\s*", re.S)
OUT_OF_BAND = re.compile(r"\[OUT-OF-BAND USER MESSAGE[^\]]*\].*?\n\n(.*?)\s*\[/OUT-OF-BAND USER MESSAGE\]", re.S)
# Morzik's short «on it» before the real answer: nothing for the call to know.
FILLER = re.compile(r"(ща|щас|секунду|сек)\b[^.!?]{0,15}[.!]?", re.I)


def _turn(role: str, content: str) -> tuple[str, str, str, bool] | None:
    """One stored message -> (speaker, text, quoted message, own line) as the user saw it.

    None when there is nothing to say. A cron delivery gets its own line, never glued to the one before."""
    text = content.strip()
    if role == "assistant":
        text = text.replace("[[split]]", "\n")
        return None if FILLER.fullmatch(text) else ("Морзик", text, "", False)
    if CRON.match(text):
        return "Морзик", CRON.sub("", text, count=1).replace("[[split]]", "\n"), "", True
    if match := OUT_OF_BAND.search(text):
        text = match.group(1)
    if match := REACTION.match(text):
        return "Пользователь", f"{match.group(1)} на «{_short(match.group(2), 60)}»", "", False
    if match := REPLY.match(text):
        return "Пользователь", text[match.end():], match.group(1), False
    return "Пользователь", text, "", False


def recent_messages(db_path: pathlib.Path, limit: int = 20, max_age_days: float = 3,
                    max_chars: int = 400, now: float | None = None) -> str:
    """The latest exchange with the user (the Morzik App, Telegram if any), oldest first.

    A heading per day, then «[HH:MM] Кто: текст»; a run of messages from one side is one line."""
    now = time.time() if now is None else now
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return ""
    try:
        rows = conn.execute(
            "SELECT m.role, m.content, m.timestamp FROM messages m JOIN sessions s ON s.id = m.session_id "
            "WHERE s.source IN ('telegram', 'morzik_app') AND m.role IN ('user', 'assistant') AND m.content IS NOT NULL "
            "AND trim(m.content) != '' AND m.timestamp >= ? ORDER BY m.timestamp DESC LIMIT ?",
            (now - max_age_days * 86400, limit * 3)).fetchall()
    except sqlite3.Error:
        return ""
    finally:
        conn.close()
    turns = []  # [speaker, text, first stamp, last stamp]
    for role, content, stamp in reversed(rows):
        turn = _turn(role, str(content))
        if turn is None or not turn[1].strip():
            continue
        who, text, quote, alone = turn
        # A reply quotes its message, unless that message is the line right above.
        if quote and not (turns and turns[-1][0] != who and " ".join(quote.split()) in " ".join(turns[-1][1].split())):
            text = f"(в ответ на «{_short(quote, 60)}») {text}"
        if turns and turns[-1][0] == who and stamp - turns[-1][3] < 120 and not alone:
            turns[-1][1] += "\n" + text
            turns[-1][3] = stamp
        else:
            turns.append([who, text, stamp, stamp])
    lines, day = [], None
    for who, text, stamp, _ in turns[-limit:]:
        moment = datetime.datetime.fromtimestamp(stamp)
        if moment.date() != day:
            day = moment.date()
            lines.append(f"{_day(moment)}:")
        text = " / ".join(part.strip() for part in text.splitlines() if part.strip())
        lines.append(f"[{moment:%H:%M}] {who}: {_short(text, max_chars)}")
    return "\n".join(lines)


# Said in place of a live source (calendar, reminders, weather) that did not answer in time.
UNAVAILABLE = "(не удалось получить, узнай через perform_task)"
# WMO weather codes (Open-Meteo) -> words.
WEATHER_WORDS = ((0, "ясно"), (1, "в основном ясно"), (2, "переменная облачность"), (3, "пасмурно"),
                 (48, "туман"), (57, "морось"), (67, "дождь"), (77, "снег"), (82, "ливни"),
                 (86, "снегопад"), (99, "гроза"))


def mcp_tool(url: str, auth: str, name: str, arguments: dict, timeout: float = 3):
    """One tools/call on a stateless MCP server answering plain JSON (Morzik Bridge) -> parsed result."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}}).encode()
    request = urllib.request.Request(url, body, {
        "Authorization": auth, "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        result = json.loads(resp.read())["result"]
    text = "".join(part.get("text", "") for part in result.get("content", []))
    if result.get("isError"):
        raise RuntimeError(text[:200])
    return json.loads(text)


def _moment(value: str) -> datetime.datetime:
    """Bridge time (ISO 8601, offset or date only) -> naive local time of this machine."""
    moment = datetime.datetime.fromisoformat(value)
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo else moment


def _day(moment: datetime.datetime) -> str:
    return f"{WEEKDAYS[moment.weekday()]}, {moment.day} {MONTHS[moment.month - 1]}"


def calendar_text(events: list) -> str:
    """Bridge calendar_list_events -> a line per day, then a line per event: «- 11:00–11:30 Daily»."""
    days: dict[datetime.date, list[str]] = {}
    for event in events:
        start, end = _moment(event["start"]), _moment(event["end"])
        if event.get("all_day"):
            what = f"весь день {event.get('title') or 'без названия'}"
        else:
            what = f"{start:%H:%M}–{end:%H:%M} {event.get('title') or 'без названия'}"
        # A place by its name only («ICBC Metrotown», not the street address); none if the title has it.
        place = " ".join(str(event.get("location") or "").split(",")[0].split())[:60]
        if place and place.lower() not in what.lower():
            what += f" ({place})"
        items = days.setdefault(start.date(), [])
        if what not in items:
            items.append(what)
    return "\n".join(f"{_day(datetime.datetime.combine(day, datetime.time()))}:\n" + "\n".join(
        f"- {item}" for item in items) for day, items in sorted(days.items()))


def reminders_text(reminders: list, now: datetime.datetime) -> str:
    """Bridge reminders_list -> open reminders with a due date, soonest first, overdue marked."""
    lines = []
    for item in sorted((r for r in reminders if r.get("due") and not r.get("completed")),
                       key=lambda r: _moment(r["due"])):
        due = _moment(item["due"])
        when = _day(due) + ("" if len(item["due"]) == 10 else f" {due:%H:%M}")
        late = ", просрочено" if (due.date() < now.date() if len(item["due"]) == 10 else due < now) else ""
        lines.append(f"{item.get('title') or 'без названия'} (срок: {when}{late})")
    return "\n".join(lines)


def weather_text(forecast: dict) -> str:
    """Open-Meteo forecast (current + daily) -> a few spoken lines in degrees Celsius."""
    def words(code):
        return next((word for limit, word in WEATHER_WORDS if code <= limit), "непогода")

    lines = []
    current = forecast.get("current") or {}
    if "temperature_2m" in current:
        lines.append(f"сейчас {round(current['temperature_2m'])} °C, {words(current.get('weather_code', 0))}")
    daily = forecast.get("daily") or {}
    for i, day in enumerate(daily.get("time") or []):
        lines.append(
            f"{_day(datetime.datetime.fromisoformat(day))}: от {round(daily['temperature_2m_min'][i])} "
            f"до {round(daily['temperature_2m_max'][i])} °C, {words(daily['weather_code'][i])}, "
            f"вероятность осадков {daily['precipitation_probability_max'][i]}%")
    return "\n".join(lines)


def live_sources(bridge_url: str, bridge_auth: str, latitude: str, longitude: str,
                 now: datetime.datetime | None = None) -> dict:
    """Name -> fetcher of a live snapshot part; a part without its settings is left out."""
    now = now or datetime.datetime.now()
    sources = {}
    if bridge_url and bridge_auth:
        week = (now + datetime.timedelta(days=7)).date().isoformat()
        sources["calendar"] = lambda: calendar_text(mcp_tool(
            bridge_url, bridge_auth, "calendar_list_events",
            {"start": now.date().isoformat(), "end": week})) or "(на неделю ничего)"
        sources["reminders"] = lambda: reminders_text(mcp_tool(
            bridge_url, bridge_auth, "reminders_list",
            {"due_before": (now + datetime.timedelta(days=14)).date().isoformat()}), now) or "(ничего со сроком)"
    if latitude and longitude:
        query = urllib.parse.urlencode({
            "latitude": latitude, "longitude": longitude, "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})

        def weather():
            with urllib.request.urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=3) as resp:
                return weather_text(json.loads(resp.read()))
        sources["weather"] = weather
    return sources


def _gather(sources: dict, timeout: float) -> dict:
    """Run the fetchers in parallel; whatever fails or is late becomes UNAVAILABLE."""
    if not sources:
        return {}
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(sources))
    futures = {name: pool.submit(fetch) for name, fetch in sources.items()}
    concurrent.futures.wait(futures.values(), timeout=timeout)
    pool.shutdown(wait=False)
    parts = {}
    for name, future in futures.items():
        try:
            parts[name] = future.result(timeout=0) or UNAVAILABLE
        except Exception as exc:  # noqa: BLE001 - a dead source must not stop the call
            log.warning("snapshot %s unavailable: %s", name, str(exc) or "too slow")
            parts[name] = UNAVAILABLE
    return parts


def snapshot(hermes_home: pathlib.Path, now: datetime.datetime | None = None,
             sources: dict | None = None, timeout: float = 2) -> dict:
    """Dynamic variables for the ElevenLabs agent: what Morzik knows right now.

    sources: live parts (see live_sources), fetched in parallel within timeout seconds."""
    now = now or datetime.datetime.now()
    memory = "\n\n".join(text for text in (_read(hermes_home / "memories/USER.md"),
                                           _read(hermes_home / "memories/MEMORY.md")) if text)
    return {
        "memory": memory or "(пусто)",
        "now": spoken_time(now),
        **_gather(sources or {}, timeout),
    }


def verify_init_data(init_data: str, bot_token: str, max_age: float = 86400,
                     now: float | None = None) -> dict | None:
    """Telegram Mini App initData -> the user dict if Telegram signed it for this bot, else None.

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    import json
    import urllib.parse
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


def verify_app_token(token: str, hermes_home: pathlib.Path) -> bool:
    """A device token of the Morzik App (its own chat database keeps only the hashes)."""
    if not token or len(token) > 200:
        return False
    try:
        conn = sqlite3.connect(f"file:{hermes_home / 'morzik-app' / 'chat.db'}?mode=ro", uri=True, timeout=5)
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
        who = "Пользователь" if turn.get("role") == "user" else "Морзик"
        message = " ".join(str(turn.get("message") or "").split())
        if message:
            lines.append(f"{who}: {message}")
        for result in turn.get("tool_results") or []:
            if isinstance(result, dict):
                value = " ".join(str(result.get("result_value") or "").split())[:max_tool_chars]
                if value:
                    lines.append(f"(результат инструмента: {value})")
    return "\n".join(lines)


# Finished calls for the chats: the morzik-app plugin (app/calls.py) hands each one to Morzik with his next
# turn in Telegram and in the Morzik App, so he remembers the call there. One JSON object per line:
# {"id", "started", "duration", "ended", "transcript"} (unix seconds, seconds, unix seconds, text).
CALLS_LOG = pathlib.Path("morzik-voice") / "calls.jsonl"
_calls_lock = threading.Lock()


def log_call(hermes_home: pathlib.Path, conversation_id: str, transcript: str, started: float | None = None,
             duration: float | None = None, keep_days: float = 7, now: float | None = None) -> None:
    """Add a finished call to CALLS_LOG; calls older than keep_days drop out."""
    now = time.time() if now is None else now
    path = pathlib.Path(hermes_home) / CALLS_LOG
    record = {"id": conversation_id, "started": started or now - (duration or 0), "duration": duration or 0,
              "ended": now, "transcript": transcript}
    with _calls_lock:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        kept = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    old = json.loads(line)
                except ValueError:
                    continue
                if isinstance(old, dict) and old.get("id") != conversation_id and \
                        float(old.get("ended") or 0) >= now - keep_days * 86400:
                    kept.append(line)
        except OSError:
            pass
        kept.append(json.dumps(record, ensure_ascii=False))
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(path)


# What the agent says aloud but a reader does not need: audio tags and the tool marker.
SPOKEN_TAGS = re.compile(r"\[(?:[a-z_ ]+|perform_task)\]\s*")
TOOL_RESULT = re.compile(r"^\(результат инструмента: (.*)\)$", re.M)


def recent_calls(hermes_home: pathlib.Path, max_age: float = 3 * 86400, max_calls: int = 5,
                 max_chars: int = 6000, exclude: str = "", now: float | None = None) -> str:
    """The last calls from CALLS_LOG for the read_calls tool, without the call asking (exclude).

    A long call keeps its start (what it was about) and its end (where it stopped)."""
    now = time.time() if now is None else now
    calls = []
    try:
        for line in (pathlib.Path(hermes_home) / CALLS_LOG).read_text(encoding="utf-8").splitlines():
            try:
                call = json.loads(line)
            except ValueError:
                continue
            if isinstance(call, dict) and call.get("transcript") and call.get("id") != exclude and \
                    float(call.get("ended") or 0) >= now - max_age:
                calls.append(call)
    except OSError:
        return ""
    calls = sorted(calls, key=lambda c: float(c.get("started") or 0))[-max_calls:]
    budget = max_chars // max(1, len(calls))
    parts = []
    for call in calls:
        text = TOOL_RESULT.sub(r"(Морзик узнал: \1)", SPOKEN_TAGS.sub("", str(call["transcript"])))
        if len(text) > budget:
            head = budget // 3
            text = text[:head].rstrip() + "\n…\n" + text[-(budget - head):].lstrip()
        start = datetime.datetime.fromtimestamp(float(call.get("started") or call.get("ended")))
        minutes = round(float(call.get("duration") or 0) / 60)
        parts.append(f"Звонок {_day(start)} в {start:%H:%M}" + (f", {minutes} мин" if minutes else "") + f":\n{text}")
    return "\n\n".join(parts)


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
