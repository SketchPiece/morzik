"""Run light chat turns (Telegram and the Morzik App) on the fast model, everything else on the main one.

Registers the auxiliary task ``morzik_light`` (Haiku on the session's provider by default; change
it in ``auxiliary.morzik_light`` of config.yaml) and returns ``{"turn_route": "morzik_light"}``
from ``pre_llm_call`` when Jev (``classify``) calls a message light with enough confidence. Hermes binds the route for that
turn only (agent/voice_turn_route.py), so the session, its history and cache stay on the main
model. Needs the ``turn_route`` patch of Hermes (docs/notes.md, «Роутинг лёгких сообщений»).
"""

import json
import logging
import os
import time
from pathlib import Path

try:
    from . import classify as _classify
except ImportError:  # loaded as a top-level module by tests
    import classify as _classify

logger = logging.getLogger(__name__)

TASK = "morzik_light"
PLATFORMS = ("telegram", "morzik_app")


def _log_path():
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    return Path(home) / "logs" / "morzik-router.jsonl"


def _log(record):
    """One line per decision, without the message text."""
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.debug("morzik-router: decision log not written", exc_info=True)


def _pre_llm_call(platform="", user_message=None, conversation_history=None, session_id="", **kwargs):
    del kwargs
    if platform not in PLATFORMS:
        return None
    started = time.monotonic()
    try:
        route, reason, confidence = _classify.classify(user_message, conversation_history)
    except Exception:  # health: allow BLE001 -- a router bug must never break the turn; main model it is
        logger.warning("morzik-router: classify failed, staying on the main model", exc_info=True)
        return None
    _log({
        "ts": round(time.time(), 3),
        "session": session_id,
        "route": route,
        "reason": reason,
        "confidence": round(confidence, 3),
        "chars": len(_classify._text(user_message)),
        "ms": round((time.monotonic() - started) * 1000, 2),
    })
    if route == _classify.LIGHT:
        return {"turn_route": TASK}
    return None


def register(ctx):
    ctx.register_auxiliary_task(
        TASK,
        display_name="Morzik: light messages",
        description="Chat messages the router calls light (small talk, quick lookups)",
        defaults={"provider": "main", "model": "haiku", "reasoning_effort": "low"},
    )
    ctx.register_hook("pre_llm_call", _pre_llm_call)
