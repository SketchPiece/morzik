"""morzik-login: Morzik asks the user to log in to a site in his browser.

``request_login`` opens the page in Morzik's own Chrome (CDP, 127.0.0.1:9222), writes a login request for the
gate (~/.morzik-login/requests/<id>.json, see gate.py), sends the user a message with a button that opens the
Morzik App right on that screen, and waits until the user taps "Готово" or "Не сейчас" there (or writes in the
chat, or 15 minutes pass). Morzik never sees the password: the user types it on the screen himself.
"""

import json
import logging
import os
import pathlib
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

STATE = pathlib.Path(os.environ.get("MORZIK_LOGIN_STATE", str(pathlib.Path.home() / ".morzik-login")))
CDP = os.environ.get("MORZIK_LOGIN_CDP", "http://127.0.0.1:9222")
APP_URL = os.environ.get("MORZIK_LOGIN_APP_URL", "https://morzik.pieces.run/login.html")
WAIT = 15 * 60
POLL = 1.0

SCHEMA = {
    "name": "request_login",
    "description": (
        "Log in / sign in to a site in your browser with the user: password, 2FA code, captcha, confirmation on "
        "his phone, a login that is not saved in browser_vault. Sends him a message with a button that opens "
        "your screen in the Morzik App (Face ID); he types the password there himself, and you wait until he "
        "says he is done or not now. Works from Telegram, unlike browser_vault save_login. Never ask for "
        "passwords or codes in the chat; use this instead. While it waits, do not touch the browser. After "
        "'done', check that the login worked and carry on."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "site": {"type": "string", "description": "Short site name for the button, e.g. 'Госуслуги', 'Amazon'."},
            "url": {"type": "string", "description": (
                "Login page to open in a new tab. Leave out to keep the current tab (e.g. you already typed "
                "the email and the password step is open).")},
            "message": {"type": "string", "description": (
                "Your short message to the user above the button, in your usual voice: what for, in a few words.")},
        },
        "required": ["site", "message"],
    },
}


def _open_tab(url: str) -> None:
    """A new tab in front, on the page to log in to."""
    quoted = urllib.parse.quote(url, safe=":/?&=%#+@,;~")
    request = urllib.request.Request(f"{CDP}/json/new?{quoted}", method="PUT")
    with urllib.request.urlopen(request, timeout=10) as resp:
        target = json.load(resp)
    urllib.request.urlopen(f"{CDP}/json/activate/{target['id']}", timeout=10).close()


def _bot(method: str, **params):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}", data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as resp:
        body = json.load(resp)
    if not body.get("ok"):
        raise RuntimeError(body.get("description", "telegram error"))
    return body["result"]


def _write(path: pathlib.Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def _interrupted() -> bool:
    try:
        from tools.interrupt import is_interrupted
    except Exception:
        return False
    return is_interrupted()


def _cleanup(requests: pathlib.Path) -> None:
    for old in requests.glob("*.json"):
        if time.time() - old.stat().st_mtime > 7 * 86400:
            old.unlink(missing_ok=True)


def _request_login(params, **kwargs):
    del kwargs
    site, url = str(params.get("site") or "").strip()[:40], str(params.get("url") or "").strip()
    message = str(params.get("message") or "").strip() or f"нужно войти в {site}"
    if not site or (url and not url.startswith(("https://", "http://"))):
        return json.dumps({"success": False, "error": "site is required, url must be http(s)"})
    requests = STATE / "requests"
    requests.mkdir(parents=True, exist_ok=True, mode=0o700)
    _cleanup(requests)
    try:
        if url:
            _open_tab(url)
    except (OSError, ValueError, KeyError) as exc:
        return json.dumps({"success": False, "error": f"could not open the page in Chrome: {exc}"})

    request_id = secrets.token_hex(8)
    path = requests / f"{request_id}.json"
    _write(path, {"id": request_id, "site": site, "url": url, "status": "waiting", "created": time.time()})
    chat_id = os.environ.get("TELEGRAM_HOME_CHANNEL", "")
    try:
        sent = _bot("sendMessage", chat_id=chat_id, text=message, reply_markup={"inline_keyboard": [[{
            "text": f"Войти в {site}", "web_app": {"url": f"{APP_URL}?r={request_id}"}}]]})
    except (OSError, ValueError, RuntimeError) as exc:
        path.unlink(missing_ok=True)
        return json.dumps({"success": False, "error": f"could not message the user: {exc}"})
    logger.info("morzik-login: asked to log in to %s (%s)", site, request_id)

    status, deadline = "waiting", time.monotonic() + WAIT
    while time.monotonic() < deadline:
        if _interrupted():
            status = "interrupted"
            break
        try:
            status = json.loads(path.read_text()).get("status", "waiting")
        except (OSError, ValueError):
            pass
        if status != "waiting":
            break
        time.sleep(POLL)
    else:
        status = "timeout"
    if status in ("interrupted", "timeout"):
        try:
            request = json.loads(path.read_text())
            if request.get("status") == "waiting":
                request.update(status=status, finished=time.time())
                _write(path, request)
        except (OSError, ValueError):
            pass
    try:  # the button has done its job
        _bot("editMessageReplyMarkup", chat_id=chat_id, message_id=sent["message_id"],
             reply_markup={"inline_keyboard": []})
    except (OSError, ValueError, RuntimeError, KeyError):
        pass
    logger.info("morzik-login: %s -> %s", request_id, status)
    notes = {
        "done": "The user says he logged in. Check the page in the browser and carry on.",
        "cancelled": "The user said not now. Do not ask again in this task unless he brings it up.",
        "interrupted": "The user wrote in the chat before finishing; read his message. The button is gone.",
        "timeout": "No answer in 15 minutes. The button is gone; mention it once if the task still needs it.",
    }
    return json.dumps({"success": status == "done", "status": status, "note": notes.get(status, "")})


def _adjust_registry() -> bool:
    """request_login may wait longer than Hermes' generic 7-minute tool deadline; browser_vault is off:
    its "secure window" for a password does not open from Telegram, and Morzik kept offering it."""
    try:
        from tools.registry import no_cache_check_fn, registry
    except Exception:
        return False
    entries = {e.name: e for e in registry.get_all_entries() if e.name in ("request_login", "browser_vault")}
    if "request_login" in entries:
        entries["request_login"].execution_timeout = WAIT + 60
    vault = entries.get("browser_vault")
    if vault is not None and not getattr(vault.check_fn, "_morzik_off", False):
        off = no_cache_check_fn(lambda: False)
        off._morzik_off = True
        vault.check_fn = off
        logger.info("morzik-login: browser_vault switched off")
    return vault is not None and "request_login" in entries


def register(ctx):
    ctx.register_tool(name="request_login", toolset="morzik-login", schema=SCHEMA, handler=_request_login,
                      emoji="🔑")
    if not _adjust_registry():
        # browser_vault may register after plugins: retry in the background for a while.
        def retry():
            for _ in range(120):
                time.sleep(1)
                if _adjust_registry():
                    return
        import threading
        threading.Thread(target=retry, name="morzik-login-registry", daemon=True).start()
