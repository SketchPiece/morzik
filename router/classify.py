"""Decide whether a Telegram message is light enough for the fast model.

Pure functions: no Hermes imports, so the rules are testable on their own. Heavy is the safe
answer: anything that looks like several steps, attachments, links, money or a follow-up to a
long task stays on the main model.
"""

import re

LIGHT = "light"
HEAVY = "heavy"

# Longer messages usually carry a real task.
MAX_LIGHT_CHARS = 200
# A turn that took this many tool calls was real work; its follow-ups ("да", "ещё раз") stay heavy.
HEAVY_PREVIOUS_TOOL_CALLS = 3

# Gateway markers: attachments, documents, background process notices.
_HEAVY_MARKERS = (
    "attached at:",
    "[the user sent",
    "[important:",
    "http://",
    "https://",
)

# Word stems (lowercase) of requests that need browsing, writing, money, fixing or planning.
_HEAVY_STEMS = (
    # browsing and accounts
    "зайди", "зайти", "войди", "залогин", "логин", "сайт", "браузер", "скачай", "достань", "загрузи",
    # writing to people
    "письм", "драфт", "черновик", "ответь", "отпис", "напиши ему", "напиши ей", "отправь",
    # money and bookings
    "оплат", "заплат", "куп", "закаж", "брон", "билет",
    # planning and comparing
    "сравни", "план", "маршрут", "подбери", "посовет", "путешеств", "поездк",
    # changing saved things
    "помен", "измени", "замени",
    # fixing and setting up
    "почин", "исправ", "пофикс", "настро", "подключ", "код", "деплой", "сервер",
    # documents
    "pdf", "документ", "анкет", "договор",
    # explicit asks for care
    "подумай", "хорошенько", "внимательно",
    # English equivalents of the most common ones
    "email", "browser", "website", "login", "book", "buy", "pay", "draft", "fix",
)

_WORD = re.compile(r"\w+", re.UNICODE)


def _previous_turn_tool_calls(history):
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


def _text(message):
    if isinstance(message, str):
        return message
    if isinstance(message, list):  # content parts
        parts = []
        for part in message:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, dict):
                parts.append("attached at:")  # an image or file part
        return " ".join(parts)
    return str(message or "")


def classify(message, history=None):
    """``(route, reason)`` for one user message; route is ``LIGHT`` or ``HEAVY``."""
    text = _text(message).strip()
    lowered = text.lower()
    if not text:
        return HEAVY, "empty"
    for marker in _HEAVY_MARKERS:
        if marker in lowered:
            return HEAVY, "marker"
    if len(text) > MAX_LIGHT_CHARS:
        return HEAVY, "long"
    words = _WORD.findall(lowered)
    joined = " ".join(words)
    for stem in _HEAVY_STEMS:
        if " " in stem:
            if stem in joined:
                return HEAVY, "stem"
        elif any(word.startswith(stem) for word in words):
            return HEAVY, "stem"
    if _previous_turn_tool_calls(history) >= HEAVY_PREVIOUS_TOOL_CALLS:
        return HEAVY, "follow-up"
    return LIGHT, "default"
