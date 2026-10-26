"""Voice calls in Morzik's chats.

A call with Morzik (ElevenLabs, from the Morzik App or the Mini App) runs outside his chats. After it the voice
proxy appends the transcript to ~/.hermes/morzik-voice/calls.jsonl (voice/brain.py, log_call). The next turn in
each chat (Telegram, the Morzik App) gets the calls that chat has not seen yet as a note on the user's message
(pre_llm_call context); Hermes keeps that note in the session, so later turns still have the call.

Which calls a chat has already got: ~/.hermes/morzik-voice/calls-seen.json, {platform: [call id, ...]}.
Standard library only, so it is testable without Hermes.
"""

import datetime
import json
import threading
import time
from pathlib import Path
from typing import Optional

CHATS = ("telegram", "morzik_app")
CALLS_LOG = Path("morzik-voice") / "calls.jsonl"
SEEN = Path("morzik-voice") / "calls-seen.json"
MAX_AGE = 3 * 86400  # an older call is not news for a chat
MAX_CALLS = 5  # a burst of calls (tests) would crowd the note: the latest ones, the rest just counted
MAX_CHARS = 9000  # under Hermes' hooks.output_spill.max_chars (10000): longer context goes to a file
_lock = threading.Lock()


def _calls(home: Path) -> list:
    try:
        lines = (home / CALLS_LOG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    calls = []
    for line in lines:
        try:
            call = json.loads(line)
        except ValueError:
            continue
        if isinstance(call, dict) and call.get("id") and call.get("transcript"):
            calls.append(call)
    return calls


def _shorten(text: str, limit: int) -> str:
    """Too long: the start and the end of the call, the middle left out."""
    if len(text) <= limit:
        return text
    head = limit // 3
    tail = limit - head
    return text[:head].rstrip() + "\n…(середина звонка пропущена)…\n" + text[-tail:].lstrip()


def note(calls: list) -> str:
    """Calls (oldest first) -> the note Morzik reads with the user's message."""
    skipped, calls = max(0, len(calls) - MAX_CALLS), calls[-MAX_CALLS:]
    budget = max(500, (MAX_CHARS - 400) // len(calls))
    parts = []
    for call in calls:
        start = datetime.datetime.fromtimestamp(float(call.get("started") or call.get("ended") or 0))
        minutes = round(float(call.get("duration") or 0) / 60)
        length = f", {minutes} мин" if minutes else ""
        parts.append(f"Звонок {start:%d.%m в %H:%M}{length}:\n{_shorten(str(call['transcript']), budget)}")
    head = ("[Между сообщениями в этом чате вы с пользователем говорили голосом: «Морзик» в записи ниже — это ты. "
            "Это продолжение того же разговора, помни его и опирайся на него. На сообщение пользователя выше "
            "отвечай как обычно, сам звонок не пересказывай.]" if len(calls) == 1 else
            "[Между сообщениями в этом чате вы с пользователем говорили голосом, записи ниже; «Морзик» в них — "
            "это ты. Это продолжение того же разговора, помни его и опирайся на него. На сообщение пользователя "
            "выше отвечай как обычно, сами звонки не пересказывай.]")
    if skipped:
        head += f"\n(Ещё {skipped} звонков раньше этих не показаны.)"
    return head + "\n\n" + "\n\n".join(parts)


def pending_note(home: Path, platform: str, now: Optional[float] = None) -> Optional[str]:
    """The note about calls this chat has not got yet (marked as got), or None."""
    if platform not in CHATS:
        return None
    now = time.time() if now is None else now
    home = Path(home)
    with _lock:
        calls = _calls(home)
        if not calls:
            return None
        try:
            seen = json.loads((home / SEEN).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            seen = {}
        if not isinstance(seen, dict):
            seen = {}
        got = set(seen.get(platform) or [])
        new = [c for c in calls if c["id"] not in got and float(c.get("ended") or 0) >= now - MAX_AGE]
        if not new:
            return None
        known = {c["id"] for c in calls}  # calls gone from the log need no mark
        seen = {p: [i for i in ids if i in known] for p, ids in seen.items() if isinstance(ids, list)}
        seen[platform] = [i for i in seen.get(platform, []) if i not in {c["id"] for c in new}] + [c["id"] for c in new]
        path = home / SEEN
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(seen), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(path)
    new.sort(key=lambda c: float(c.get("started") or c.get("ended") or 0))
    return note(new)
