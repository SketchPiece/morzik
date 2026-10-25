"""Decide whether a Telegram message is light enough for the fast model, by asking Jev.

Jev (TypeSafe, through OpenRouter's Decisions API) answers a typed choice with a confidence. Only
the current message (clipped) and how many tool calls the previous turn made are sent; replies and
the rest of the history stay here. Heavy is the safe answer: no key, an error, a timeout or a
confidence under ``MIN_CONFIDENCE`` keeps the turn on the main model.
"""

import json
import os
import re
import urllib.request

LIGHT = "light"
HEAVY = "heavy"

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "~typesafe/jev-latest"
KEY_ENV = "MORZIK_ROUTER_OPENROUTER_KEY"
TIMEOUT_S = 1.5
MIN_CONFIDENCE = 0.8
MAX_CHARS = 2000

INSTRUCTIONS = (
    "A user wrote this message in Telegram to their personal assistant bot (a friendly cat). "
    "Can a small fast model handle it well, or does it need the strong model?"
)
CRITERIA = {
    LIGHT: (
        "Small talk, greetings, jokes, thanks, short reactions, questions about the bot itself, a "
        "general-knowledge question, or one quick action with an obvious result: check for new mail, "
        "mark mail as read, add or list a reminder, look at the calendar, the weather, a quick web search."
    ),
    HEAVY: (
        "Real work or careful judgement: several steps, browsing or logging in to websites, writing or "
        "sending messages and emails to people, money, bookings and payments, planning or changing trips "
        "and plans, comparing options or giving advice, reading attached images or documents or links, "
        "fixing or setting something up, deleting things, anything irreversible, or a short follow-up "
        "('yes', 'again', 'do it') that continues a task where the previous turn used several tools."
    ),
}


def _text(message):
    if isinstance(message, str):
        return message
    if isinstance(message, list):  # content parts
        parts = []
        for part in message:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, dict):
                parts.append("[attachment]")
        return " ".join(parts)
    return str(message or "")


def previous_turn_tool_calls(history):
    """Tool calls the assistant made after the last user message of *history*."""
    calls = 0
    for message in reversed(history or []):
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user":
            break
        if message.get("role") == "assistant":
            calls += len(message.get("tool_calls") or [])
    return calls


def _key():
    key = os.environ.get(KEY_ENV, "").strip()
    if key:
        return key
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    try:
        with open(os.path.join(home, ".env"), encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"\s*" + KEY_ENV + r"=(.*)", line)
                if m:
                    return m[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def ask_jev(text, tool_calls, key, timeout=TIMEOUT_S, opener=urllib.request.urlopen):
    """``(choice, confidence)`` from Jev; raises on any transport or format problem."""
    body = {
        "model": MODEL,
        "state": {"message": text[:MAX_CHARS], "previous_turn_tool_calls": tool_calls},
        "questions": {"route": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA}},
    }
    request = urllib.request.Request(URL, json.dumps(body).encode("utf-8"), {
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with opener(request, timeout=timeout) as response:
        answer = json.loads(response.read())["answers"]["route"]
    return answer["choice"], float(answer.get("confidence") or 0.0)


def classify(message, history=None, *, key=None, opener=urllib.request.urlopen):
    """``(route, reason, confidence)`` for one user message; route is ``LIGHT`` or ``HEAVY``."""
    text = _text(message).strip()
    if not text:
        return HEAVY, "empty", 0.0
    key = _key() if key is None else key
    if not key:
        return HEAVY, "no-key", 0.0
    try:
        choice, confidence = ask_jev(text, previous_turn_tool_calls(history), key, opener=opener)
    except Exception as exc:  # health: allow BLE001 -- any Jev failure means the main model
        return HEAVY, "error:" + type(exc).__name__, 0.0
    if choice == LIGHT and confidence >= MIN_CONFIDENCE:
        return LIGHT, "jev", confidence
    return HEAVY, "jev" if choice == HEAVY else "unsure", confidence
