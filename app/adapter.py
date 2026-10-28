"""Morzik App: the user's own chat with Morzik, a Hermes platform next to Telegram.

The phone app talks to this adapter over HTTPS (Tailscale Funnel → 127.0.0.1:8660, path /app/):

    POST /app/v1/pair/start   {name}                 a sign-in code goes to the user's Telegram
    POST /app/v1/pair/finish  {pairing_id, code}     -> {token, device_id}
    GET  /app/v1/sync?since=REV                      changes after REV (0: the latest messages)
    GET  /app/v1/history?before=SEQ                  older messages
    POST /app/v1/messages     {client_id, text, media_id?, reply_to?: {message_id, quote?}}   idempotent by client_id
    POST /app/v1/media        raw body               upload a photo / voice note / file -> {media}
    GET  /app/v1/media/ID                            download
    POST /app/v1/push         {token, env}           APNs token of this phone
    POST /app/v1/read         {seq}                  read up to here (badge)
    POST /app/v1/action       {message_id, button_id}  tap on a reply button or an approval button
    POST /app/v1/react        {message_id, emoji}    the user's reaction ("" takes it back)
    POST /app/v1/retry        {message_id}           send a 'failed' / 'unanswered' message of the user again
    GET  /app/v1/ws?since=REV                        live: missed changes first, then new ones, typing, busy

A command Hermes wants the user's OK for comes as a message from Morzik with two "approval" buttons (Разрешить /
Отклонить). A tap answers Hermes's approval (as Telegram's buttons do) and the card turns into the outcome; when
nobody answers in time the card says the command was not run.

Everything but pairing needs ``Authorization: Bearer <device token>``. See store.py for how sync works.

Morzik behaves here as in Telegram (morzik-chat): a short reply goes out as several messages, "typing…"
shows only right before each one, Hermes's own notices never reach the chat, a short "ща" goes out when he
goes off to look something up on a long task. When a message of the user did not reach Morzik or his reply to it
broke, Morzik says nothing: the message itself turns 'failed' or 'unanswered', and the app offers to send it again. When no phone is connected, each message from Morzik is pushed.

"busy" (on the socket and in /sync) says Morzik is working on something for the user: in a turn from his
first tool call or a message sent mid-turn until the turn ends, and while background work he started from
this chat (a process that reports on exit, an async subagent) is still running. Thinking alone is not busy, and
neither is waiting for the user: while a card in the chat waits for his tap (an approval, morzik-login's "Войти в
X"), the turn's own work does not count.
"""

import asyncio
import json
import logging
import mimetypes
import os
import random
import re
import shutil
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.platforms.event import MessageEvent, MessageType
from gateway.platforms._shared import get_scoped_secret

try:
    from .store import Store
    from .apns import Apns
    from . import calls
except ImportError:  # loaded as a top-level module
    from store import Store  # type: ignore
    from apns import Apns  # type: ignore
    import calls  # type: ignore

logger = logging.getLogger(__name__)

PLATFORM = "morzik_app"
CHAT_ID = "app"
USER_ID = "owner"
API = "/app/v1"
MAX_MESSAGE_LENGTH = 16000
MAX_UPLOAD = 25 * 1024 * 1024
LIVE_FOR = 45.0  # a phone that said nothing for this long is treated as gone (pushes resume)
TYPING_CHARS_PER_SECOND, MIN_PAUSE, MAX_PAUSE = 25, 1.2, 4.0
COMMANDS = ("/new", "/restart", "/reset")
HEADING_RE = re.compile(r"^#{1,6}\s+\S", re.M)
APPROVAL_TIMED_OUT_RE = re.compile(r"^⌛.*(?:NOT run|НЕ выполнена)", re.S)

# The adapter that is running, for other plugins (morzik-login posts its button here too).
ACTIVE: list = [None]
# The plugin context (to start a turn from a reaction) and reactions waiting for the next turn.
CTX: list = [None]
ORIGIN: list = [None]
REACTION_NOTES: list = []
APPROVAL_CMD_PREVIEW = 1200  # chars of the command shown on an approval card
APPROVAL_OUTCOMES = {"once": "✅ Разрешено", "deny": "🚫 Отклонено",
                     "late": "⌛ Уже не ждёт ответа, команда не выполнялась."}
REACTION_SETTLE = 2.0  # seconds to let the user settle on an emoji before Morzik answers
BACKGROUND_TICK = 2.0  # how often background work from this chat is looked up for "busy"


def _env(name: str, default: str = "") -> str:
    return (get_scoped_secret(name, default) or default).strip()


FAILED_STATUSES = ("failed", "unanswered")


def _morzik_chat():
    """Morzik's Telegram manners plugin, if loaded: its splitter and "is this Morzik talking" filter."""
    for module in list(sys.modules.values()):
        if all(hasattr(module, a) for a in ("_split_parts", "_is_morzik", "_natural_line", "_turn", "_remember")):
            return module
    return None


def _voice_in_progress() -> bool:
    for module in list(sys.modules.values()):
        fn = getattr(module, "_voice_in_progress", None)
        if callable(fn) and getattr(module, "TTS_TOOL", None) == "text_to_speech":
            try:
                return bool(fn())
            except Exception:
                return False
    return False


def _kind_for(mime: str, name: str = "") -> str:
    mime = (mime or mimetypes.guess_type(name)[0] or "").lower()
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "file"


class MorzikAppAdapter(BasePlatformAdapter):
    MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH
    supports_code_blocks = True

    def __init__(self, config: PlatformConfig):
        super().__init__(config=config, platform=Platform(PLATFORM))
        extra = config.extra or {}
        home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
        self.state_dir = Path(extra.get("state_dir") or _env("MORZIK_APP_STATE") or home / "morzik-app")
        self.media_dir = self.state_dir / "media"
        self.host = extra.get("host") or _env("MORZIK_APP_HOST", "127.0.0.1")
        self.port = int(extra.get("port") or _env("MORZIK_APP_PORT", "8660"))
        self.store: Optional[Store] = None
        self.apns = Apns(_env("MORZIK_APP_APNS_KEY"), _env("MORZIK_APP_APNS_KEY_ID"), _env("MORZIK_APP_APNS_TEAM_ID"),
                         _env("MORZIK_APP_APNS_TOPIC", "com.sketchpiece.morzik"))
        self.bot_token = _env("TELEGRAM_BOT_TOKEN")
        self.owner_chat = _env("TELEGRAM_HOME_CHANNEL")
        self._sockets: dict = {}  # ws -> {"device": id, "name": device name, "seen": monotonic}
        self._runner = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._send_lock = asyncio.Lock()
        self._typing_state: Optional[str] = None
        # This turn: open (on_processing_start..complete), done (the agent loop has finished, only the final
        # reply is left), working (a tool was called or a message went out mid-turn). Set from agent threads.
        self._work = {"open": False, "done": False, "working": False}
        self._turn_message_id = None  # the user's message the current turn answers
        self._background = False
        self._busy = False
        self._background_task: Optional[asyncio.Task] = None
        self._approvals: dict = {}  # approval card id -> the session_key whose approval it answers
        self._waiting: set = set()  # cards the turn waits on for the user's tap (approval, login): not busy then

    # --- lifecycle ---------------------------------------------------------------------------

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        from aiohttp import web
        try:
            self.media_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.store = Store(str(self.state_dir / "chat.db"))
            self._broadcast_rev = self.store.current_rev()
            self._flush_lock = asyncio.Lock()
            app = web.Application(client_max_size=MAX_UPLOAD + 1024)
            r = app.router
            r.add_post(f"{API}/pair/start", self._pair_start)
            r.add_post(f"{API}/pair/finish", self._pair_finish)
            r.add_get(f"{API}/sync", self._sync)
            r.add_get(f"{API}/history", self._history)
            r.add_post(f"{API}/messages", self._post_message)
            r.add_post(f"{API}/media", self._upload)
            r.add_get(f"{API}/media/{{media_id}}", self._download)
            r.add_post(f"{API}/push", self._push_token)
            r.add_post(f"{API}/read", self._read)
            r.add_post(f"{API}/action", self._action)
            r.add_post(f"{API}/react", self._react)
            r.add_post(f"{API}/retry", self._retry)
            r.add_get(f"{API}/ws", self._ws)
            r.add_get(f"{API}/health", lambda request: web.json_response({"ok": True}))
            self._runner = web.AppRunner(app, access_log=None)
            await self._runner.setup()
            await web.TCPSite(self._runner, self.host, self.port).start()
        except Exception as exc:
            logger.error("[%s] could not start on %s:%s: %s", self.name, self.host, self.port, exc)
            return False
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._mark_connected()
        ACTIVE[0] = self
        self._wire_plugin_handlers(None)
        self._background_task = asyncio.ensure_future(self._watch_background())
        logger.info("[%s] listening on %s:%s (push %s)", self.name, self.host, self.port,
                    "on" if self.apns.configured else "off")
        return True

    async def disconnect(self) -> None:
        self._running = False
        if ACTIVE[0] is self:
            ACTIVE[0] = None
        if self._background_task is not None:
            self._background_task.cancel()
            self._background_task = None
        self._work.update(open=False, done=False, working=False)
        self._background = False
        self._waiting.clear()
        await self._update_busy("disconnect")
        for ws in list(self._sockets):
            try:
                await ws.close()
            except Exception:
                pass
        self._sockets.clear()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        if self.store is not None:
            self.store.close()
            self.store = None
        self._mark_disconnected()

    # --- auth and helpers ------------------------------------------------------------------------

    def _device(self, request) -> Optional[dict]:
        auth = request.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else request.query.get("token", "")
        device = self.store.device_for(token) if self.store else None
        if device:
            self.store.touch(device["id"])
        return device

    @staticmethod
    def _json(data, status: int = 200):
        from aiohttp import web
        return web.json_response(data, status=status, dumps=lambda d: json.dumps(d, ensure_ascii=False))

    def _error(self, status: int, code: str):
        return self._json({"error": code}, status)

    async def _body(self, request) -> dict:
        try:
            body = await request.json()
        except Exception:
            return {}
        return body if isinstance(body, dict) else {}

    def _live_devices(self) -> set:
        now = time.monotonic()
        return {info["device"] for ws, info in self._sockets.items() if not ws.closed and now - info["seen"] < LIVE_FOR}

    async def _broadcast(self, event: dict) -> list:
        """Sends the event to every open socket; returns the names of the devices it went to."""
        data = json.dumps(event, ensure_ascii=False)
        sent = []
        for ws in list(self._sockets):
            if ws.closed:
                self._sockets.pop(ws, None)
                continue
            try:
                await ws.send_str(data)
                sent.append(self._sockets[ws]["name"])
            except Exception:
                self._sockets.pop(ws, None)
        return sent

    async def _publish(self, messages: list, push: bool = False) -> None:
        """Sends every stored change the phones haven't had yet, read back from the database in revision order.

        Phones remember the highest revision they got and resume from it, so the socket must never carry a
        revision before an earlier one (a button stored from a tool thread could otherwise overtake a reply,
        and a drop right then would lose it). ``messages`` only says which new ones to push."""
        if self.store is None:
            return
        async with self._flush_lock:
            while True:
                changes, _ = self.store.since(self._broadcast_rev, limit=200)
                if not changes:
                    break
                self._broadcast_rev = changes[-1]["rev"]
                await self._broadcast({"type": "messages", "messages": changes, "rev": self._broadcast_rev})
        if push:
            for m in messages:
                if m and m["role"] == "morzik" and not m["deleted"]:
                    asyncio.ensure_future(self._push(m))

    def publish_threadsafe(self, messages: list, push: bool = False) -> None:
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._publish(messages, push), self._loop)

    async def _set_typing(self, state: Optional[str]) -> None:
        if state != self._typing_state:
            self._typing_state = state
            await self._broadcast({"type": "typing", "state": state})

    # --- busy: Morzik is working on something for the user --------------------------------------------

    async def _update_busy(self, reason: str) -> None:
        busy = bool((self._work["working"] and not self._waiting) or self._background)
        if busy != self._busy:
            self._busy = busy
            sent = await self._broadcast({"type": "busy", "busy": busy})
            # WARNING: the gateway's journal shows only warnings and up, and busy is what we look for there.
            logger.warning("morzik-app: busy %s (%s), sent to %s", "true" if busy else "false", reason,
                           ", ".join(sent) or "no socket")

    def _update_busy_threadsafe(self, reason: str) -> None:
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._update_busy(reason), self._loop)

    def mark_working(self, reason: str) -> None:
        """A tool call or a mid-turn message: busy until the turn ends. Safe from any thread."""
        work = self._work
        if work["open"] and not work["done"] and not work["working"]:
            work["working"] = True
            self._update_busy_threadsafe(reason)

    def wait_for_user(self, message_id: str, waiting: bool) -> None:
        """A card the turn waits on (approval, login): not busy until it is answered or gone. Safe from any thread."""
        if not message_id:
            return
        if waiting:
            self._waiting.add(message_id)
        else:
            self._waiting.discard(message_id)
        self._update_busy_threadsafe(("waiting for the user on " if waiting else "answered: ") + message_id)

    def mark_turn_done(self, reason: str) -> None:
        """The agent loop has finished (or was stopped): the turn's work is over. Safe from any thread."""
        self._work.update(done=True, working=False)
        self._update_busy_threadsafe(reason)

    async def _watch_background(self) -> None:
        while True:
            try:
                background = await asyncio.to_thread(_background_work)
                if background != self._background:
                    self._background = background
                    await self._update_busy("background work " + ("running" if background else "over"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("[%s] background work not checked: %s", self.name, exc)
            await asyncio.sleep(BACKGROUND_TICK)

    # --- push -------------------------------------------------------------------------------------

    @staticmethod
    def _preview(message: dict) -> str:
        text = " ".join((message.get("text") or "").split())
        media = message.get("media") or {}
        kind = media.get("kind")
        label = {"voice": "🎤 Голосовое сообщение", "audio": "🎵 Аудио", "image": "📷 Фото", "video": "🎬 Видео",
                 "file": f"📎 {media.get('name') or 'Файл'}"}.get(kind, "")
        if label and text:
            text = f"{label}: {text}"
        text = text or label or "…"
        return text if len(text) <= 240 else text[:239] + "…"

    async def _push(self, message: dict) -> None:
        if not self.apns.configured:
            return
        live = self._live_devices()
        for device in self.store.push_devices():
            if device["id"] in live:
                continue
            payload = {"aps": {"alert": {"title": "Морзик", "body": self._preview(message)}, "sound": "default",
                               "badge": self.store.unread(device["id"]), "thread-id": "morzik", "mutable-content": 1},
                       "seq": message["seq"], "rev": message["rev"]}
            try:
                ok, env, reason = await self.apns.send(device["apns_token"], device["apns_env"] or "development", payload)
            except Exception as exc:
                logger.warning("[%s] push failed: %s", self.name, exc)
                continue
            if ok and env != device["apns_env"]:
                self.store.set_push(device["id"], device["apns_token"], env)
            elif reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
                self.store.drop_push(device["apns_token"])

    # --- HTTP: pairing ------------------------------------------------------------------------------

    async def _telegram(self, method: str, **params) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"https://api.telegram.org/bot{self.bot_token}/{method}", json=params)
        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError(body.get("description", "telegram error"))
        return body["result"]

    async def _pair_start(self, request):
        body = await self._body(request)
        if not (self.bot_token and self.owner_chat):
            return self._error(503, "no_telegram")
        made = self.store.new_code(str(body.get("name") or "iPhone"))
        if made is None:
            return self._error(429, "too_often")
        pairing_id, code = made
        try:
            await self._telegram(
                "sendMessage", chat_id=self.owner_chat, parse_mode="HTML",
                text=(f"Код для входа в приложение Морзика: <code>{code}</code>\n"
                      f"Устройство: {(body.get('name') or 'iPhone')[:60]}. Если это не ты, просто ничего не делай."))
        except Exception as exc:
            logger.warning("[%s] could not send the sign-in code: %s", self.name, exc)
            return self._error(502, "telegram_failed")
        logger.info("[%s] sign-in code sent for %s", self.name, pairing_id)
        return self._json({"pairing_id": pairing_id})

    async def _pair_finish(self, request):
        body = await self._body(request)
        result = self.store.redeem(str(body.get("pairing_id") or ""), str(body.get("code") or ""))
        if isinstance(result, str):
            return self._error(403 if result != "expired" else 410, result)
        device_id, token = result
        logger.warning("[%s] new device signed in: %s", self.name, device_id)
        return self._json({"device_id": device_id, "token": token, "rev": self.store.current_rev()})

    # --- HTTP: chat -------------------------------------------------------------------------------

    def _changes(self, since: int) -> dict:
        current = self.store.current_rev()
        if since <= 0 or since > current:
            # First open, or the server's chat is not the one the phone remembers: start from the latest.
            return {"reset": since > 0, "messages": self.store.tail(), "rev": current, "more": False}
        messages, more = self.store.since(since)
        return {"reset": False, "messages": messages, "rev": messages[-1]["rev"] if more else current, "more": more}

    async def _sync(self, request):
        device = self._device(request)
        if not device:
            return self._error(401, "unauthorized")
        try:
            since = int(request.query.get("since", "0"))
        except ValueError:
            return self._error(400, "bad_since")
        data = self._changes(since)
        data["typing"] = self._typing_state
        data["busy"] = self._busy
        return self._json(data)

    async def _history(self, request):
        if not self._device(request):
            return self._error(401, "unauthorized")
        try:
            before = int(request.query.get("before", "0"))
            limit = max(1, min(200, int(request.query.get("limit", "60"))))
        except ValueError:
            return self._error(400, "bad_before")
        return self._json({"messages": self.store.before(before, limit)})

    async def _post_message(self, request):
        device = self._device(request)
        if not device:
            return self._error(401, "unauthorized")
        body = await self._body(request)
        client_id = str(body.get("client_id") or "").strip()[:64]
        text = str(body.get("text") or "").strip()
        media_id = str(body.get("media_id") or "").strip()
        if not client_id or (not text and not media_id):
            return self._error(400, "empty")
        if len(text) > MAX_MESSAGE_LENGTH:
            return self._error(413, "too_long")
        media = self._media_info(media_id) if media_id else None
        if media_id and media is None:
            return self._error(404, "no_media")
        if media and body.get("duration"):
            try:
                media["duration"] = float(body["duration"])
            except (TypeError, ValueError):
                pass
        reply = self._reply_for(body.get("reply_to"))
        message, created = self.store.add("user", text, client_id=client_id, media=media, reply=reply)
        if created:
            await self._publish([message])
            asyncio.ensure_future(self._dispatch(message))
            if text.lower() in COMMANDS:
                # "Начать заново" from the app's menu is a command, not a line of the chat.
                message = self.store.update(message["id"], deleted=True)
                await self._publish([message])
        return self._json({"message": message, "rev": self.store.current_rev()})

    def _reply_for(self, raw) -> Optional[dict]:
        """An answer to a message, or to a fragment of it selected in the app (a quote), as Telegram does."""
        if not isinstance(raw, dict):
            return None
        target = self.store.get(str(raw.get("message_id") or ""))
        if target is None:
            return None
        quote = " ".join(str(raw.get("quote") or "").split())[:1000]
        whole = " ".join((target.get("text") or "").split())
        return {"id": target["id"], "role": target["role"], "quote": quote or whole[:1000]}

    def _media_info(self, media_id: str) -> Optional[dict]:
        if not media_id or "/" in media_id or media_id.startswith("."):
            return None
        meta = self.media_dir / f"{media_id}.json"
        try:
            return json.loads(meta.read_text())
        except (OSError, ValueError):
            return None

    def _save_media(self, data: bytes, mime: str, name: str, kind: Optional[str] = None, **extra) -> dict:
        media_id = secrets.token_hex(10)
        ext = Path(name).suffix.lower() or mimetypes.guess_extension(mime or "") or ""
        path = self.media_dir / f"{media_id}{ext}"
        path.write_bytes(data)
        os.chmod(path, 0o600)
        info = {"id": media_id, "kind": kind or _kind_for(mime, name), "mime": mime or mimetypes.guess_type(name)[0] or
                "application/octet-stream", "name": name or path.name, "size": len(data), "file": path.name}
        info.update({k: v for k, v in extra.items() if v is not None})
        (self.media_dir / f"{media_id}.json").write_text(json.dumps(info, ensure_ascii=False))
        return info

    async def _upload(self, request):
        if not self._device(request):
            return self._error(401, "unauthorized")
        data = await request.read()
        if not data:
            return self._error(400, "empty")
        if len(data) > MAX_UPLOAD:
            return self._error(413, "too_large")
        mime = request.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
        name = os.path.basename(request.headers.get("X-Filename", "")) or "file"
        kind = request.headers.get("X-Media-Kind") or None
        if kind not in (None, "image", "voice", "audio", "video", "file"):
            kind = None
        info = await asyncio.to_thread(self._save_media, data, mime, name, kind)
        return self._json({"media": info})

    async def _download(self, request):
        from aiohttp import web
        if not self._device(request):
            return self._error(401, "unauthorized")
        info = self._media_info(request.match_info["media_id"])
        if info is None:
            return self._error(404, "not_found")
        path = self.media_dir / info["file"]
        if not path.exists():
            return self._error(404, "not_found")
        return web.FileResponse(path, headers={"Content-Type": info["mime"], "Cache-Control": "private, max-age=31536000, immutable"})

    async def _push_token(self, request):
        device = self._device(request)
        if not device:
            return self._error(401, "unauthorized")
        body = await self._body(request)
        token = str(body.get("token") or "").strip()
        env = "production" if body.get("env") == "production" else "development"
        if not token or len(token) > 200:
            return self._error(400, "bad_token")
        self.store.set_push(device["id"], token, env)
        return self._json({"ok": True})

    async def _read(self, request):
        device = self._device(request)
        if not device:
            return self._error(401, "unauthorized")
        body = await self._body(request)
        try:
            self.store.set_read(device["id"], int(body.get("seq") or 0))
        except (TypeError, ValueError):
            return self._error(400, "bad_seq")
        return self._json({"ok": True, "unread": self.store.unread(device["id"])})

    async def _action(self, request):
        """A tap on a 'reply' button: its text goes to Morzik as the user's message."""
        device = self._device(request)
        if not device:
            return self._error(401, "unauthorized")
        body = await self._body(request)
        message = self.store.get(str(body.get("message_id") or ""))
        button = next((b for b in (message or {}).get("buttons", []) if b.get("id") == body.get("button_id")), None)
        if button is not None and button.get("kind") == "approval":
            return self._json({"message": await self._answer_approval(message, str(button.get("value") or ""))})
        if button is None or button.get("kind") != "reply":
            return self._error(404, "no_button")
        changed = self.store.update(message["id"], buttons=[])
        reply, created = self.store.add("user", str(button.get("value") or button.get("title")),
                                        client_id=f"btn-{message['id']}-{button['id']}")
        await self._publish([changed, reply])
        if created:
            asyncio.ensure_future(self._dispatch(reply))
        return self._json({"message": reply})

    async def _retry(self, request):
        """"Повторить" under a message that did not reach Morzik or got no reply: it goes to him again."""
        if not self._device(request):
            return self._error(401, "unauthorized")
        body = await self._body(request)
        message = self.store.get(str(body.get("message_id") or ""))
        if message is None or message["deleted"] or message["role"] != "user":
            return self._error(404, "no_message")
        if message["status"] not in FAILED_STATUSES:
            return self._json({"message": message})  # a second tap, or already answered
        changed = self.store.update(message["id"], status="sent")
        await self._publish([changed])
        logger.warning("morzik-app: retry of %s (was %s)", message["id"], message["status"])
        asyncio.ensure_future(self._dispatch(changed))
        return self._json({"message": changed})

    async def _answer_approval(self, message: dict, choice: str) -> dict:
        """Hand the user's choice to Hermes's approval wait; the card keeps what was asked and gets the outcome."""
        session_key = self._approvals.pop(message["id"], None)
        self.wait_for_user(message["id"], False)
        count = 0
        if session_key and choice in ("once", "deny"):
            try:
                from tools.approval import resolve_gateway_approval
                count = resolve_gateway_approval(session_key, choice)
            except Exception as exc:
                logger.error("morzik-app: approval not resolved: %s", exc)
        logger.warning("morzik-app: approval %s on %s -> %d resolved", choice, message["id"], count)
        changed = self._settle_card(message, APPROVAL_OUTCOMES[choice if count else "late"])
        await self._publish([changed])
        return changed

    def _settle_card(self, message: dict, outcome: str) -> dict:
        text = (message.get("text") or "").rsplit("\n\n", 1)[0]  # the deadline line goes, the outcome takes its place
        return self.store.update(message["id"], text=f"{text}\n\n{outcome}", buttons=[])

    async def _react(self, request):
        """One reaction per message, as in Telegram. On Morzik's question or offer it is an answer and starts a
        turn (after a moment, in case the user picks another one); on anything else he hears of it next turn."""
        if not self._device(request):
            return self._error(401, "unauthorized")
        body = await self._body(request)
        message = self.store.get(str(body.get("message_id") or ""))
        emoji = str(body.get("emoji") or "").strip()[:16]
        if message is None or message["deleted"]:
            return self._error(404, "no_message")
        changed = self.store.update(message["id"], reactions=[emoji] if emoji else [])
        await self._publish([changed])
        if emoji and changed["role"] == "morzik":
            self._reacted(changed, emoji)
        return self._json({"message": changed})

    def _reacted(self, message: dict, emoji: str) -> None:
        text = " ".join((message.get("text") or "").split()) or "[голосовое или вложение]"
        quote = text if len(text) <= 400 else text[:400] + "…"
        if "?" not in text:
            REACTION_NOTES.append(f"{emoji} на твоё сообщение «{quote}»")
            del REACTION_NOTES[:-10]
            return
        message_id = message["id"]

        async def answer():
            await asyncio.sleep(REACTION_SETTLE)
            current = self.store.get(message_id) if self.store else None
            if not current or current.get("reactions") != [emoji] or CTX[0] is None:
                return  # taken back or changed meanwhile
            prompt = (f"[Пользователь поставил реакцию {emoji} на твоё сообщение «{quote}». "
                      "Это его ответ: пойми его и действуй так, как если бы он ответил словами.]")
            origin = ORIGIN[0] or self._origin()
            ok = CTX[0].inject_message(prompt, role="user", origin=origin)
            logger.warning("morzik-app: reaction %s on %s -> %s", emoji, message_id, "turn started" if ok else "refused")

        asyncio.ensure_future(answer())

    def _origin(self) -> dict:
        """This chat's session identity when no message came in since the start (as build_source makes it)."""
        try:
            return {k: v for k, v in self.build_source(chat_id=CHAT_ID, chat_name="Morzik App", chat_type="dm",
                                                       user_id=USER_ID).to_dict().items() if k != "message_id"}
        except Exception:
            return {"platform": PLATFORM, "chat_id": CHAT_ID, "chat_type": "dm", "user_id": USER_ID}

    async def _ws(self, request):
        from aiohttp import web, WSMsgType
        device = self._device(request)
        if not device:
            return self._error(401, "unauthorized")
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=1 << 20)
        await ws.prepare(request)
        # Registered before the backlog is read: nothing stored meanwhile can slip between the two.
        self._sockets[ws] = {"device": device["id"], "name": device.get("name") or device["id"][:8],
                             "seen": time.monotonic()}
        try:
            since = int(request.query.get("since", "0"))
        except ValueError:
            since = 0
        try:
            while True:
                data = self._changes(since)
                await ws.send_str(json.dumps({"type": "messages", **data}, ensure_ascii=False))
                if not data.get("more"):
                    break
                since = data["rev"]
            await ws.send_str(json.dumps({"type": "typing", "state": self._typing_state}))
            await ws.send_str(json.dumps({"type": "busy", "busy": self._busy}))
            logger.warning("morzik-app: socket open: %s, busy %s", self._sockets[ws]["name"],
                           "true" if self._busy else "false")
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                        break
                    continue
                if ws in self._sockets:
                    self._sockets[ws]["seen"] = time.monotonic()
                try:
                    event = json.loads(msg.data)
                except ValueError:
                    continue
                if event.get("type") == "ping":
                    await ws.send_str('{"type":"pong"}')
                elif event.get("type") == "read":
                    try:
                        self.store.set_read(device["id"], int(event.get("seq") or 0))
                    except (TypeError, ValueError):
                        pass
        finally:
            self._sockets.pop(ws, None)
            logger.warning("morzik-app: socket closed: %s", device.get("name") or device["id"][:8])
        return ws

    # --- inbound: the user's message goes to Morzik ------------------------------------------------

    async def _dispatch(self, message: dict) -> None:
        media = message.get("media") or {}
        media_urls, media_types, message_type = [], [], MessageType.TEXT
        text = message.get("text") or ""
        if media:
            path = self.media_dir / media.get("file", "")
            try:
                data = await asyncio.to_thread(path.read_bytes)
                from gateway.platforms import base
                kind = media.get("kind")
                if kind == "image":
                    cached = await asyncio.to_thread(base.cache_image_from_bytes, data, path.suffix or ".jpg")
                    message_type = MessageType.PHOTO
                elif kind in ("voice", "audio"):
                    cached = await asyncio.to_thread(base.cache_audio_from_bytes, data, path.suffix or ".m4a")
                    message_type = MessageType.VOICE if kind == "voice" else MessageType.AUDIO
                elif kind == "video":
                    cached = await asyncio.to_thread(base.cache_video_from_bytes, data, path.suffix or ".mp4")
                    message_type = MessageType.VIDEO
                else:
                    cached = await asyncio.to_thread(base.cache_document_from_bytes, data, media.get("name") or path.name)
                    message_type = MessageType.DOCUMENT
                media_urls, media_types = [cached], [media.get("mime") or ""]
            except Exception as exc:
                logger.warning("[%s] could not hand over an attachment: %s", self.name, exc)
                text = text or "[вложение не дошло]"
        source = self.build_source(chat_id=CHAT_ID, chat_name="Morzik App", chat_type="dm", user_id=USER_ID,
                                   message_id=message["id"])
        try:  # where a turn started by a reaction goes: exactly this chat's identity, without the message id
            ORIGIN[0] = {k: v for k, v in source.to_dict().items() if k != "message_id"}
        except Exception:
            pass
        reply = message.get("reply") or {}
        event = MessageEvent(text=text, message_type=message_type, source=source, message_id=message["id"],
                             media_urls=media_urls, media_types=media_types, raw_message=message,
                             reply_to_message_id=reply.get("id"), reply_to_text=reply.get("quote"),
                             reply_to_is_own_message=reply.get("role") == "morzik")
        # No event metadata: Hermes refuses events with metadata it doesn't know (session_envelope).
        mc = _morzik_chat()
        if mc is not None and not text.startswith("/"):
            try:  # the "ща" when he goes off to look something up without a word (morzik-chat)
                mc._turn.update(id=mc._turn["id"] + 1, spoke=False, tool=False, tools=0, line=None)
                if hasattr(mc, "_patch_interim"):
                    mc._patch_interim()
                asyncio.ensure_future(mc._ack_if_silent(self, CHAT_ID, mc._turn["id"]))
            except Exception as exc:
                logger.debug("[%s] no ack watcher: %s", self.name, exc)
        await self.handle_message(event)

    async def on_processing_start(self, event: MessageEvent) -> None:
        """Morzik took the message: it and everything before it turn "read"."""
        self._work.update(open=True, done=False, working=False)
        self._turn_message_id = str(event.message_id or "") or None
        await self._update_busy("turn started")
        message = self.store.get(str(event.message_id or "")) if self.store else None
        if message:
            await self._publish(self.store.mark_read_until(int(message["seq"])))

    async def on_processing_complete(self, event, outcome) -> None:
        # Any outcome (success, failure, cancel): the turn is over and so is its "busy".
        self._work.update(open=False, done=False, working=False)
        self._waiting.clear()
        await self._update_busy(f"turn over: {getattr(outcome, 'value', outcome)}")
        await self._set_typing(None)

    # --- outbound: Morzik talks --------------------------------------------------------------------

    def _failure(self, content: str) -> Optional[str]:
        """The status Hermes's notice means for the user's message: 'failed' (it never reached Morzik),
        'unanswered' (he got it, the reply broke) or None (not such a notice)."""
        mc = _morzik_chat()
        if mc is None or not content or mc._is_morzik(content):
            return None
        try:
            kind = next((k for k, pattern, _ in mc.NATURAL if pattern.search(content)), None)
        except Exception:
            return None
        if kind == "resend" or (kind is None and re.search(r"refused|not (?:saved|answered)", content, re.I)):
            return "failed"
        return "unanswered" if kind == "failed" else None

    async def _mark_failed(self, status: str, content: str) -> None:
        """Show the failure on the user's message instead of a line from Morzik."""
        message = self.store.get(self._turn_message_id or "") if self._turn_message_id else None
        if message is None or message["role"] != "user":
            message = self.store.last_user()
        logger.warning("morzik-app: Hermes said %r -> %s on %s", content[:300], status,
                       message["id"] if message else "no message")
        if message is not None and not message["deleted"]:
            await self._publish([self.store.update(message["id"], status=status)])

    def _filter(self, content: str) -> Optional[str]:
        """Only Morzik talks: Hermes's own texts are dropped or turned into a short line in his voice."""
        mc = _morzik_chat()
        if mc is None or not content:
            return content
        try:
            if mc._is_system_banner(content):
                logger.info("[%s] dropped a Hermes banner", self.name)
                return None
            if not mc._is_morzik(content):
                line = mc._natural_line(content)  # "" is morzik-chat's "drop, Morzik says it himself"
                logger.warning("morzik-app: Hermes said %r -> %s", content[:300], repr(line) if line else "dropped")
                if line:
                    mc._remember(line)
                return line or None
        except Exception as exc:
            logger.debug("[%s] filter failed: %s", self.name, exc)
        return content

    def _split(self, content: str) -> list[str]:
        if HEADING_RE.search(content):  # a report written as an article goes out whole
            return [content.strip()]
        mc = _morzik_chat()
        if mc is not None:
            try:
                return mc._split_parts(content)
            except Exception:
                pass
        # The same rule without morzik-chat: a short chatty reply goes out paragraph by paragraph.
        text = content.strip()
        if len(text) > 500 or "```" in text or re.search(r"^\s*([-*•]|\d+[.)])\s", text, re.M):
            return [text] if text else []
        parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        return parts if len(parts) <= 3 else [text]

    async def _type_like_a_human(self, text: str) -> None:
        pause = min(MAX_PAUSE, max(MIN_PAUSE, len(text) / TYPING_CHARS_PER_SECOND)) * random.uniform(.85, 1.15)
        await self._set_typing("typing")
        await asyncio.sleep(pause)

    def _spoke(self) -> None:
        mc = _morzik_chat()
        if mc is not None:
            try:
                mc._turn["spoke"] = True
            except Exception:
                pass

    async def _deliver(self, text: str = "", media: Optional[dict] = None, buttons: Optional[list] = None) -> SendResult:
        message, _ = self.store.add("morzik", text, media=media, buttons=buttons)
        await self._set_typing(None)
        await self._publish([message], push=True)
        self.mark_working("sent mid-turn")  # a message mid-turn ("ща", "ща сделаю"): he goes on working
        return SendResult(success=True, message_id=message["id"])

    async def send(self, chat_id: str, content: str, reply_to: Optional[str] = None,
                   metadata: Optional[dict[str, Any]] = None) -> SendResult:
        if self.store is None:
            return SendResult(success=False, error="not connected", retryable=True)
        if (metadata or {}).get("is_approval_prompt"):
            pass  # the plain-text approval prompt (buttons failed): the user must see it to answer /approve
        elif APPROVAL_TIMED_OUT_RE.search(content or ""):
            content = "не дождался твоего ок, команду не выполнил"  # its card is gone or was never sent
        elif status := self._failure(content or ""):
            await self._mark_failed(status, content)
            return SendResult(success=True)
        else:
            content = self._filter(content or "")
        if not content:
            return SendResult(success=True)
        self._spoke()
        async with self._send_lock:  # parts of two replies never interleave
            parts = self._split(content)
            result, ids = SendResult(success=True), []
            for part in parts:
                await self._type_like_a_human(part)
                result = await self._deliver(part)
                ids.append(result.message_id)
            if len(ids) > 1:
                try:
                    result.continuation_message_ids = tuple(ids[:-1])
                except Exception:
                    pass
            return result

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        # While he thinks the chat stays quiet (as in Telegram); "recording…" while a voice reply is made.
        if _voice_in_progress():
            await self._set_typing("recording")

    async def stop_typing(self, chat_id: str) -> None:
        if self._typing_state == "recording" and not _voice_in_progress():
            await self._set_typing(None)

    async def delete_message(self, chat_id: str, message_id: str) -> bool:
        changed = self.store.update(str(message_id), deleted=True) if self.store else None
        if changed:
            await self._publish([changed])
        return changed is not None

    async def _send_file(self, path: str, caption: Optional[str], kind: Optional[str] = None,
                         file_name: Optional[str] = None) -> SendResult:
        try:
            data = await asyncio.to_thread(Path(path).read_bytes)
        except OSError as exc:
            return SendResult(success=False, error=str(exc))
        name = file_name or Path(path).name
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        extra = {}
        if kind == "voice":
            # Telegram-style Opus in Ogg doesn't play on iPhone: turn it into AAC.
            data, mime, name, extra["duration"] = await asyncio.to_thread(_to_m4a, data, name)
        caption = self._filter(caption) if caption else None
        self._spoke()
        info = await asyncio.to_thread(self._save_media, data, mime, name, kind, **extra)
        async with self._send_lock:
            if kind == "voice":
                await self._set_typing("recording")
                await asyncio.sleep(.6)
            return await self._deliver(caption or "", media=info)

    async def send_voice(self, chat_id, audio_path, caption=None, reply_to=None, metadata=None, **kwargs) -> SendResult:
        return await self._send_file(audio_path, caption, "voice")

    async def send_image_file(self, chat_id, image_path, caption=None, reply_to=None, metadata=None, **kwargs) -> SendResult:
        return await self._send_file(image_path, caption, "image")

    async def send_video(self, chat_id, video_path, caption=None, reply_to=None, metadata=None, **kwargs) -> SendResult:
        return await self._send_file(video_path, caption, "video")

    async def send_document(self, chat_id, file_path, caption=None, file_name=None, reply_to=None, metadata=None,
                            **kwargs) -> SendResult:
        return await self._send_file(file_path, caption, None, file_name)

    async def send_image(self, chat_id, image_url, caption=None, reply_to=None, metadata=None) -> SendResult:
        """A picture by URL: shown from the URL, no copy kept."""
        caption = self._filter(caption) if caption else None
        self._spoke()
        info = {"id": "", "kind": "image", "mime": "image/*", "name": "", "url": image_url}
        async with self._send_lock:
            return await self._deliver(caption or "", media=info)

    async def _send_exec_approval_prompt(self, prompt) -> SendResult:
        """Hermes wants the user's OK for a command: a card with Разрешить / Отклонить (see _answer_approval)."""
        if self.store is None:
            return SendResult(success=False, error="not connected", retryable=True)
        try:
            from gateway.platforms.base_exec_approval import approval_timeout_seconds
            minutes = max(1, round(approval_timeout_seconds() / 60))
        except Exception:
            minutes = 5
        command = prompt.command if len(prompt.command) <= APPROVAL_CMD_PREVIEW \
            else prompt.command[:APPROVAL_CMD_PREVIEW] + "…"
        text = (f"Хочу выполнить команду, нужно твоё ок:\n```\n{command.replace('```', '` ` `')}\n```\n"
                f"Почему спрашиваю: {prompt.description}\n\n"
                f"Если не ответишь за {minutes} мин, команда не выполнится.")
        buttons = [{"id": "once", "title": "Разрешить", "kind": "approval", "value": "once"},
                   {"id": "deny", "title": "Отклонить", "kind": "approval", "value": "deny"}]
        async with self._send_lock:
            message, _ = self.store.add("morzik", text, buttons=buttons)
            self._approvals[message["id"]] = prompt.session_key
            self.wait_for_user(message["id"], True)
            await self._set_typing(None)
            await self._publish([message], push=True)
        logger.warning("morzik-app: approval card %s for %r", message["id"], prompt.command[:200])
        return SendResult(success=True, message_id=message["id"])

    async def edit_message(self, chat_id: str, message_id: str, content: str, *, finalize: bool = False) -> SendResult:
        """Only approval cards are edited: Hermes does it when nobody answered in time. Everything else is
        refused, so callers send a new message as before."""
        message = self.store.get(str(message_id)) if self.store else None
        if not message or not any(b.get("kind") == "approval" for b in message.get("buttons") or []):
            return SendResult(success=False, error="Not supported")
        self._approvals.pop(message["id"], None)
        self.wait_for_user(message["id"], False)
        logger.warning("morzik-app: approval card %s timed out", message["id"])
        await self._publish([self._settle_card(message, "⌛ Ответа не было, команда не выполнена.")])
        return SendResult(success=True, message_id=message["id"])

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        return {"name": "Morzik App", "type": "dm", "chat_id": chat_id}

    # --- for other plugins (called from tool threads) ------------------------------------------------

    def post_buttons(self, text: str, buttons: list) -> Optional[str]:
        """A message from Morzik with buttons (morzik-login's "Войти в X") the turn waits on: not busy until
        clear_buttons; returns its id."""
        if self.store is None:
            return None
        message, _ = self.store.add("morzik", text, buttons=buttons)
        self.publish_threadsafe([message], push=True)
        self.wait_for_user(message["id"], True)
        return message["id"]

    def post_text(self, text: str) -> Optional[str]:
        """A message from Morzik outside a chat turn (send_to_app_chat from a voice call); returns its id."""
        if self.store is None:
            return None
        message, _ = self.store.add("morzik", text)
        self.publish_threadsafe([message], push=True)
        return message["id"]

    def clear_buttons(self, message_id: str) -> None:
        if self.store is None or not message_id:
            return
        changed = self.store.update(message_id, buttons=[])
        self.publish_threadsafe([changed])
        self.wait_for_user(message_id, False)


def _to_m4a(data: bytes, name: str) -> tuple[bytes, str, str, Optional[float]]:
    """Opus/Ogg (or anything ffmpeg reads) -> AAC in M4A, which AVAudioPlayer plays; unchanged on failure."""
    import tempfile
    if not shutil.which("ffmpeg"):
        return data, mimetypes.guess_type(name)[0] or "audio/ogg", name, None
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / ("in" + (Path(name).suffix or ".ogg")), Path(tmp) / "out.m4a"
        src.write_bytes(data)
        done = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-c:a", "aac", "-b:a", "64k",
                               "-ac", "1", str(dst)], capture_output=True, timeout=60)
        if done.returncode != 0 or not dst.exists():
            logger.warning("morzik-app: ffmpeg failed: %s", done.stderr[:200])
            return data, mimetypes.guess_type(name)[0] or "audio/ogg", name, None
        duration = None
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
                                str(dst)], capture_output=True, text=True, timeout=20)
        try:
            duration = round(float(probe.stdout.strip()), 2)
        except ValueError:
            pass
        return dst.read_bytes(), "audio/mp4", Path(name).stem + ".m4a", duration


# --- registration ------------------------------------------------------------------------------------

def check_requirements() -> bool:
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return False
    return _env("MORZIK_APP_ENABLED", "").lower() in ("1", "true", "yes")


def validate_config(config) -> bool:
    return True


def is_connected(config) -> bool:
    return check_requirements()


def _env_enablement() -> Optional[dict]:
    if not check_requirements():
        return None
    return {"home_channel": {"chat_id": CHAT_ID, "name": "Morzik App"}}


PLATFORM_HINT = (
    "Ты в приложении Морзик: это личный чат пользователя с тобой на его iPhone. Манеры те же, что в Telegram: "
    "короткие сообщения, разные мысли через пустую строку. Здесь отображается Markdown: **жирный**, *курсив*, "
    "`код`, ссылки, списки, заголовки, цитаты. Одно исключение из «коротко», только в приложении: когда "
    "пользователь просит отчёт или подробности или ты что-то исследовал и накопилось много важного, пришли одно "
    "длинное сообщение-отчёт вместо статьи в Telegraph (publish_article). Пиши его как статью: заголовок `#`, "
    "разделы `##`, списки, где они помогают, всё одним сообщением. Приложение покажет его начало с «Читать "
    "полностью» и по тапу откроет на весь экран. Всё остальное по-прежнему коротко. Голосовые ответы "
    "(text_to_speech) приходят голосовыми сообщениями, фото и файлы от пользователя приходят тебе вложениями. Если "
    "на сайте нужно, чтобы вошёл пользователь, используй request_login: кнопка появится прямо в этом чате.")


def _pre_llm_call(platform="", **kwargs):
    """Reactions on plain messages reach Morzik with the next turn in the app; voice calls he has not seen in
    this chat yet, with the next turn in the app or in Telegram (calls.py; only the user talks to this bot)."""
    parts = []
    if platform == PLATFORM and REACTION_NOTES:
        parts.append(f"Пользователь поставил реакции на твои сообщения: {'; '.join(REACTION_NOTES)}.")
        REACTION_NOTES.clear()
    if platform in calls.CHATS:
        try:
            call_note = calls.pending_note(Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes"), platform)
        except Exception as exc:
            logger.warning("morzik-app: calls for %s not read: %s", platform, exc)
            call_note = None
        if call_note:
            logger.info("morzik-app: a voice call goes to the %s chat", platform)
            parts.append(call_note)
    return {"context": "\n\n".join(parts)} if parts else None


def _to_app(value, origin_platform: str):
    """A deliver/target value with the user's Telegram (bare, the home chat, 'all' home channels, or an
    origin in a Telegram session) swapped for the app. None when nothing changes. Other chats pass through."""
    home = _env("TELEGRAM_HOME_CHANNEL", "").strip()
    parts = value if isinstance(value, list) else str(value).split(",")
    out, changed = [], False
    for part in (str(p).strip() for p in parts):
        low = part.lower()
        if low in ("telegram", "all") or (home and (low == f"telegram:{home}" or low.startswith(f"telegram:{home}:"))) \
                or (low == "origin" and origin_platform == "telegram"):
            part, changed = PLATFORM, True
        if part and part not in out:
            out.append(part)
    return ",".join(out) if changed else None


def _app_turn() -> bool:
    """Is this hook running for Morzik's own turn in the app (not a subagent, a cron run or another chat)?"""
    try:
        from gateway.session_context import get_session_env
        if get_session_env("HERMES_SESSION_PLATFORM").strip().lower() != PLATFORM or get_session_env("HERMES_CRON_SESSION"):
            return False
        from agent.delegation_context import is_delegated_child_context
        return not is_delegated_child_context()
    except Exception:
        return False


SEND_SCHEMA = {
    "name": "send_to_app_chat",
    "description": (
        "Написать пользователю в чат приложения Морзик: ссылку, адрес, номер, список, то, что удобнее прочитать, "
        "чем услышать. Только для голосового звонка: в чате приложения и в Telegram просто отвечай."),
    "parameters": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Сообщение целиком, как его прочтёт пользователь."}},
        "required": ["text"],
    },
}


def _send_to_app_chat(params, **kwargs):
    text = str((params or {}).get("text") or "").strip()
    if not text:
        return json.dumps({"success": False, "error": "text is empty"})
    adapter = ACTIVE[0]
    message_id = adapter.post_text(text) if adapter is not None else None
    if message_id is None:
        return json.dumps({"success": False, "error": "the Morzik App chat is not running, nothing was sent"})
    logger.info("morzik-app: send_to_app_chat %s (%d chars)", message_id, len(text))
    return json.dumps({"success": True, "message_id": message_id})


def _mark_working(tool_name="", **kwargs):
    # A voice reply is Morzik talking, not working (as in morzik-chat).
    adapter = ACTIVE[0]
    if adapter is not None and tool_name != "text_to_speech" and _app_turn():
        adapter.mark_working(f"tool {tool_name}")
    return None


def _turn_done(**kwargs):
    """post_llm_call: the tool loop is over, only the final reply is left (it shows "typing")."""
    adapter = ACTIVE[0]
    if adapter is not None and _app_turn():
        adapter.mark_turn_done("agent loop over")
    return None


def _turn_stopped(platform="", **kwargs):
    """agent_loop_stopped (/stop, /new mid-turn): fired by the gateway, outside the agent's context."""
    adapter = ACTIVE[0]
    if adapter is not None and str(platform or "").lower() == PLATFORM:
        adapter.mark_turn_done("agent stopped")
    return None


def _background_work() -> bool:
    """Is background work started from the app chat still running, work that reports back here when done:
    a process with notify_on_complete, an async subagent? Both registries live in this process (none survive
    a restart as running)."""
    def ours(key) -> bool:
        return f":{PLATFORM}:" in str(key or "")
    try:
        from tools.process_registry import process_registry
        if process_registry._any_running(lambda p: p.notify_on_complete and ours(p.session_key)):
            return True
    except Exception as exc:
        logger.debug("morzik-app: processes not checked: %s", exc)
    try:
        from tools.async_delegation import _LIVE_STATES, list_async_delegations
        if any(r.get("status") in _LIVE_STATES and ours(r.get("session_key")) for r in list_async_delegations()):
            return True
    except Exception as exc:
        logger.debug("morzik-app: subagents not checked: %s", exc)
    return False


def _pre_tool_call(tool_name="", args=None, **kwargs):
    """Since 26.10.2026 all of Morzik's own messages go to the app, not Telegram: reminders and scheduled
    jobs he sets up (even from a Telegram chat or a cron run), their failure notices, and send_message."""
    try:
        _mark_working(tool_name)
    except Exception:
        pass
    if not isinstance(args, dict):
        return None
    try:
        from gateway.session_context import get_session_env
        origin = (get_session_env("HERMES_CRON_AUTO_DELIVER_PLATFORM") if get_session_env("HERMES_CRON_SESSION")
                  else get_session_env("HERMES_SESSION_PLATFORM")).strip().lower()
    except Exception:
        origin = ""
    changes = {}
    if tool_name == "cronjob":
        action = str(args.get("action") or "").lower()
        deliver = args.get("deliver")
        if deliver in (None, "") and action == "create":
            deliver = "origin"
        for key, value in (("deliver", deliver), ("failure_deliver", args.get("failure_deliver"))):
            if value not in (None, "") and (new := _to_app(value, origin)):
                changes[key] = new
    elif tool_name == "send_message" and str(args.get("action") or "send").lower() == "send":
        target = args.get("target")
        if target and (new := _to_app(target, "")) and "," not in new:
            changes["target"] = new
    if not changes:
        return None
    logger.info("morzik-app: %s %s → %s", tool_name, {k: args.get(k) for k in changes}, changes)
    return {"action": "modify", "args": changes}


def register(ctx) -> None:
    import dataclasses
    CTX[0] = ctx
    if hasattr(ctx, "register_hook"):
        ctx.register_hook("pre_llm_call", _pre_llm_call)
        ctx.register_hook("pre_tool_call", _pre_tool_call)
        ctx.register_hook("post_tool_call", _mark_working)
        ctx.register_hook("post_llm_call", _turn_done)
        ctx.register_hook("agent_loop_stopped", _turn_stopped)
    if hasattr(ctx, "register_tool"):  # for voice calls (api_server toolset morzik-app-send)
        ctx.register_tool(name="send_to_app_chat", toolset="morzik-app-send", schema=SEND_SCHEMA,
                          handler=_send_to_app_chat, emoji="💬")
    kwargs = dict(
        name=PLATFORM, label="Morzik App", adapter_factory=lambda cfg: MorzikAppAdapter(cfg),
        check_fn=check_requirements, validate_config=validate_config, is_connected=is_connected,
        required_env=["MORZIK_APP_ENABLED"], install_hint="set MORZIK_APP_ENABLED=true in ~/.hermes/.env",
        env_enablement_fn=_env_enablement, cron_deliver_env_var="MORZIK_APP_HOME_CHANNEL",
        allowed_users_env="MORZIK_APP_ALLOWED_USERS", allow_all_env="MORZIK_APP_ALLOW_ALL_USERS",
        max_message_length=MAX_MESSAGE_LENGTH, emoji="🐈‍⬛", pii_safe=True, platform_hint=PLATFORM_HINT)
    try:
        from gateway.platform_registry import PlatformEntry
        known = {f.name for f in dataclasses.fields(PlatformEntry)}
        if "allowlist_suppresses_pairing" in known:
            kwargs["allowlist_suppresses_pairing"] = True
    except Exception:
        pass
    ctx.register_platform(**kwargs)
