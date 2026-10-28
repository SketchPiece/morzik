"""morzik-browser: the tab Morzik works in is on his screen, and old tabs do not pile up.

Every browser_exec call gets one line after its leading comment that runs harness.py inside browser_harness:
switch_tab and new_tab show the tab they attach to, the current tab comes to the front at the start and at the
end of the call, and then only the KEEP most recently used tabs stay open. When the browser has been idle for
IDLE seconds (no browser_exec running, no login waiting for the user), only the tab Morzik worked in last
stays. Closing tabs does not log out of anything: cookies live in the Chrome profile.
"""

import json
import logging
import os
import pathlib
import threading
import time
import urllib.request

logger = logging.getLogger(__name__)

HARNESS = str(pathlib.Path(__file__).with_name("harness.py"))
STATE = str(pathlib.Path(os.environ.get("HERMES_HOME", str(pathlib.Path.home() / ".hermes"))) / "state"
            / "browser_tabs.json")
LOGIN = pathlib.Path(os.environ.get("MORZIK_LOGIN_STATE", str(pathlib.Path.home() / ".morzik-login"))) / "requests"
CDP = os.environ.get("MORZIK_LOGIN_CDP", "http://127.0.0.1:9222")
KEEP = 3
IDLE = 15 * 60

_lock = threading.Lock()
_running = 0


def with_harness(code: str) -> str:
    """Morzik's code with the harness line after its leading comments (the UI labels the step by them)."""
    if not code or not code.strip():
        return code
    lines = code.splitlines(keepends=True)
    head = 0
    while head < len(lines) and (not lines[head].strip() or lines[head].lstrip().startswith("#")):
        head += 1
    line = (f"exec(compile(open({HARNESS!r}).read(), {HARNESS!r}, 'exec'), "
            f"{{'__name__': 'morzik_browser', 'G': globals(), 'STATE': {STATE!r}, 'KEEP': {KEEP}}})\n")
    if head and not lines[head - 1].endswith("\n"):
        lines[head - 1] += "\n"
    return "".join(lines[:head]) + line + "".join(lines[head:])


def _wrap(inner):
    def handler(args, **kwargs):
        global _running
        args = dict(args or {})
        args["code"] = with_harness(str(args.get("code") or ""))
        with _lock:
            _running += 1
        try:
            return inner(args, **kwargs)
        finally:
            with _lock:
                _running -= 1
    handler._morzik_browser = True
    return handler


def _adjust_registry() -> bool:
    try:
        from tools.registry import registry
    except Exception:
        return False
    for entry in registry.get_all_entries():
        if entry.name == "browser_exec":
            if not getattr(entry.handler, "_morzik_browser", False):
                entry.handler = _wrap(entry.handler)
                logger.info("morzik-browser: browser_exec wrapped")
            return True
    return False


def _login_waiting(now: float) -> bool:
    for path in LOGIN.glob("*.json"):
        try:
            request = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if request.get("status") == "waiting" and now - float(request.get("created") or 0) < 20 * 60:
            return True
    return False


def _state() -> dict:
    try:
        state = json.loads(pathlib.Path(STATE).read_text())
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def idle_tidy(now: float | None = None) -> list[str]:
    """Close every tab but the one Morzik worked in last, once the browser is idle. Returns closed urls."""
    now = time.time() if now is None else now
    state = _state()
    if _running or now - float(state.get("at") or 0) < IDLE or _login_waiting(now):
        return []
    with urllib.request.urlopen(f"{CDP}/json/list", timeout=5) as resp:
        pages = [t for t in json.load(resp) if t.get("type") == "page"]
    if len(pages) <= 1:
        return []
    ids = [t["id"] for t in pages]
    used = state.get("used") or {}
    keep = state.get("current") if state.get("current") in ids else max(ids, key=lambda i: used.get(i, 0))
    closed = []
    for tab in pages:
        if tab["id"] != keep:
            urllib.request.urlopen(f"{CDP}/json/close/{tab['id']}", timeout=5).close()
            closed.append(tab.get("url", ""))
    return closed


def _idle_loop():
    while True:
        time.sleep(60)
        _adjust_registry()  # a registry reload may bring back the plain handler
        try:
            closed = idle_tidy()
            if closed:
                logger.info("morzik-browser: idle, closed %d tabs", len(closed))
        except Exception as exc:
            logger.debug("morzik-browser: idle tidy failed: %s", exc)


def register(ctx):
    del ctx
    threading.Thread(target=_idle_loop, name="morzik-browser-idle", daemon=True).start()
    if not _adjust_registry():
        # browser_exec registers when its module is imported, maybe after plugins: retry for a while.
        def retry():
            for _ in range(120):
                time.sleep(1)
                if _adjust_registry():
                    return
        threading.Thread(target=retry, name="morzik-browser-registry", daemon=True).start()
