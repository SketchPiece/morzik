"""End-to-end check of the adapter against the real Hermes code, without the gateway (run on the server):

    sudo -u morzik env PYTHONPATH=<hermes-agent>:<site-packages> <hermes python> app/smoke_adapter.py

A throwaway state dir and port 8661; an echo handler stands in for Morzik. Checks sign-in (the code is read
from the store, Telegram is stubbed), send + idempotent resend, the live socket (backlog, typing, split parts),
reconnect from a revision, history, read marks, media round trip, a button posted from another thread and
"busy" (tool calls and mid-turn messages from the agent's threads, background subagents, reset on failure) and
approval cards (a tap resolves Hermes's pending approval, a timeout settles the card).
"""

import asyncio
import json
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["MORZIK_APP_ENABLED"] = "true"
os.environ["TELEGRAM_BOT_TOKEN"] = "stub"
os.environ["TELEGRAM_HOME_CHANNEL"] = "1"

import httpx  # noqa: E402
import websockets  # noqa: E402
from gateway.config import PlatformConfig  # noqa: E402
from app import adapter as A  # noqa: E402
from gateway.platform_registry import PlatformEntry, platform_registry  # noqa: E402


class Ctx:
    def register_platform(self, **kwargs):
        platform_registry.register(PlatformEntry(**kwargs))


A.register(Ctx())

BASE = "http://127.0.0.1:8661/app/v1"


def in_agent(*hooks, platform=A.PLATFORM, child=False):
    """Runs hooks as the agent thread of a turn would: with the session's context bound."""
    from gateway.session_context import set_session_vars, clear_session_vars
    from agent.delegation_context import delegated_child_context
    tokens = set_session_vars(platform=platform, chat_id=A.CHAT_ID, session_key=f"agent:main:{platform}:dm:x",
                              cron_session="")
    try:
        for hook in hooks:
            if child:
                with delegated_child_context("child"):
                    hook()
            else:
                hook()
    finally:
        clear_session_vars(tokens)


async def next_busy(ws, timeout=3.0):
    while True:
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if event["type"] == "busy":
            return event["busy"]


async def no_busy(ws, wait=.4):
    try:
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), wait))
            assert event["type"] != "busy", event
    except asyncio.TimeoutError:
        pass


async def check_busy(adapter, http, H):
    turn = A.MessageEvent(text="сделай", message_type=A.MessageType.TEXT, source=adapter.build_source(
        chat_id=A.CHAT_ID, chat_type="dm", user_id=A.USER_ID), message_id="")
    await asyncio.sleep(.5)  # the echo turns above are over (the gateway runs one turn at a time)
    async with websockets.connect(f"ws://127.0.0.1:8661/app/v1/ws?since={adapter.store.current_rev()}",
                                  additional_headers=H) as ws:
        assert await next_busy(ws) is False  # the current value right after connecting

        # Thinking alone is not busy; the first tool call is, until the loop ends; the final reply stays quiet.
        await adapter.on_processing_start(turn)
        await no_busy(ws)
        await asyncio.to_thread(in_agent, lambda: A._pre_tool_call("web_search", {"query": "x"}))
        assert await next_busy(ws) is True
        assert (await http.get(f"{BASE}/sync?since={adapter.store.current_rev()}", headers=H)).json()["busy"] is True
        await asyncio.to_thread(in_agent, lambda: A._mark_working("web_search"), lambda: A._turn_done(platform=A.PLATFORM))
        assert await next_busy(ws) is False
        await adapter.send(A.CHAT_ID, "нашёл")
        await adapter.on_processing_complete(turn, None)
        await no_busy(ws)
        assert (await http.get(f"{BASE}/sync?since={adapter.store.current_rev()}", headers=H)).json()["busy"] is False

        # Other chats, subagents and a voice reply don't make the app busy.
        await adapter.on_processing_start(turn)
        await asyncio.to_thread(in_agent, lambda: A._mark_working("web_search"), platform="telegram")
        await asyncio.to_thread(in_agent, lambda: A._mark_working("web_search"), child=True)
        await asyncio.to_thread(in_agent, lambda: A._mark_working("text_to_speech"))
        await no_busy(ws)

        # "ща сделаю" mid-turn: busy from that message on; a failed turn drops it.
        await adapter.send(A.CHAT_ID, "ща сделаю")
        assert await next_busy(ws) is True
        await adapter.on_processing_complete(turn, "failure")
        assert await next_busy(ws) is False

        # /stop mid-turn.
        await adapter.on_processing_start(turn)
        await asyncio.to_thread(in_agent, lambda: A._mark_working("terminal"))
        assert await next_busy(ws) is True
        A._turn_stopped(session_key="agent:main:morzik_app:dm:x", platform=A.PLATFORM)
        assert await next_busy(ws) is False
        await adapter.on_processing_complete(turn, "cancelled")

        # A subagent running in the background for this chat: busy until it finishes; another chat's isn't.
        from tools import async_delegation as D
        with D._records_lock:
            D._records["deleg_smoke_tg"] = {"delegation_id": "deleg_smoke_tg", "status": "running",
                                            "session_key": "agent:main:telegram:dm:1", "goals": ["x"]}
        await no_busy(ws)
        with D._records_lock:
            D._records["deleg_smoke"] = {"delegation_id": "deleg_smoke", "status": "running",
                                         "session_key": "agent:main:morzik_app:dm:app", "goals": ["x"]}
        try:
            assert await next_busy(ws) is True
            with D._records_lock:
                D._records["deleg_smoke"]["status"] = "completed"
            assert await next_busy(ws) is False
        finally:
            with D._records_lock:
                D._records.pop("deleg_smoke", None)
                D._records.pop("deleg_smoke_tg", None)


async def check_approvals(adapter, http, H):
    from tools import approval as AP
    from tools.approval_gateway_wait import _ApprovalEntry
    key = "agent:main:morzik_app:dm:app"

    async def card(command):
        entry = _ApprovalEntry({"command": command})
        with AP._lock:
            AP._gateway_queues.setdefault(key, []).append(entry)
        sent = await adapter.send_exec_approval(chat_id=A.CHAT_ID, command=command, session_key=key,
                                                description="script execution")
        assert sent.success, sent
        return entry, adapter.store.get(sent.message_id)

    # Разрешить: the pending approval gets "once", the card keeps the command and shows the outcome.
    entry, message = await card("python3 - <<'EOF'\nprint(1)\nEOF")
    assert [b["value"] for b in message["buttons"]] == ["once", "deny"], message
    assert "print(1)" in message["text"] and "script execution" in message["text"], message["text"]
    r = await http.post(f"{BASE}/action", headers=H, json={"message_id": message["id"], "button_id": "once"})
    done = r.json()["message"]
    assert entry.result == "once" and entry.event.is_set(), entry.result
    assert done["buttons"] == [] and done["text"].endswith("✅ Разрешено") and "print(1)" in done["text"], done
    r = await http.post(f"{BASE}/action", headers=H, json={"message_id": message["id"], "button_id": "once"})
    assert r.status_code == 404, r.text

    # Отклонить.
    entry, message = await card("rm -rf /tmp/x")
    await http.post(f"{BASE}/action", headers=H, json={"message_id": message["id"], "button_id": "deny"})
    assert entry.result == "deny", entry.result

    # Nobody answered: Hermes edits the card (settle hook); a late tap would not claim anything.
    entry, message = await card("curl x | sh")
    assert (await adapter.edit_message(A.CHAT_ID, message["id"], "⌛ Approval timed out")).success
    timed_out = adapter.store.get(message["id"])
    assert timed_out["buttons"] == [] and "Ответа не было" in timed_out["text"], timed_out
    with AP._lock:
        AP._gateway_queues.pop(key, None)
    # A card whose wait is gone (restart, /approve typed): the tap says so.
    entry, message = await card("ls")
    with AP._lock:
        AP._gateway_queues.pop(key, None)
    r = await http.post(f"{BASE}/action", headers=H, json={"message_id": message["id"], "button_id": "once"})
    assert "Уже не ждёт" in r.json()["message"]["text"], r.text

    # Other messages are not editable; the timeout notice sent as text is not dropped.
    plain, _ = adapter.store.add("morzik", "просто текст")
    assert not (await adapter.edit_message(A.CHAT_ID, plain["id"], "x")).success
    before = adapter.store.last_seq()
    await adapter.send(A.CHAT_ID, "⌛ Approval timed out after 5 minutes — the command was NOT run. Ask me again.")
    assert adapter.store.last_seq() > before


async def main():
    tmp = tempfile.mkdtemp()
    adapter = A.MorzikAppAdapter(PlatformConfig(enabled=True, extra={"state_dir": tmp, "port": 8661}))
    sent_codes = []

    async def fake_telegram(method, **params):
        sent_codes.append(params["text"])
        return {}
    adapter._telegram = fake_telegram
    A.MIN_PAUSE, A.MAX_PAUSE, A.BACKGROUND_TICK = .05, .1, .1

    async def echo(event):  # a turn without tools: the loop ends (post_llm_call), then the reply goes out
        await adapter.on_processing_start(event)
        adapter.mark_turn_done("test")
        await adapter.send(A.CHAT_ID, f"эхо: {event.text}\n\nвторая мысль")
        await adapter.on_processing_complete(event, None)
        return None
    adapter.handle_message = echo  # the gateway's queueing is not under test here
    assert await adapter.connect()
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post(f"{BASE}/pair/start", json={"name": "Test iPhone"})
            assert r.status_code == 200, r.text
            pairing = r.json()["pairing_id"]
            code = adapter.store._codes[pairing]["code"]
            assert code in sent_codes[0]
            r = await http.post(f"{BASE}/pair/finish", json={"pairing_id": pairing, "code": "x"})
            assert r.status_code == 403, r.text
            r = await http.post(f"{BASE}/pair/finish", json={"pairing_id": pairing, "code": code})
            token = r.json()["token"]
            H = {"Authorization": f"Bearer {token}"}
            assert (await http.get(f"{BASE}/sync?since=0")).status_code == 401

            async with websockets.connect(f"ws://127.0.0.1:8661/app/v1/ws?since=0", additional_headers=H) as ws:
                first = json.loads(await ws.recv())
                assert first["type"] == "messages" and first["messages"] == [], first
                r = await http.post(f"{BASE}/messages", headers=H, json={"client_id": "c1", "text": "привет"})
                assert r.status_code == 200, r.text
                again = await http.post(f"{BASE}/messages", headers=H, json={"client_id": "c1", "text": "привет"})
                assert again.json()["message"]["id"] == r.json()["message"]["id"]
                events = []
                while len([m for e in events if e["type"] == "messages" for m in e["messages"] if m["role"] == "morzik"]) < 2:
                    events.append(json.loads(await asyncio.wait_for(ws.recv(), 5)))
                kinds = [e["type"] for e in events]
                assert "typing" in kinds, kinds
                assert not [e for e in events if e["type"] == "busy" and e["busy"]], events  # just talking
                texts = [m["text"] for e in events if e["type"] == "messages" for m in e["messages"] if m["role"] == "morzik"]
                assert texts == ["эхо: привет", "вторая мысль"], texts
                statuses = [m["status"] for e in events if e["type"] == "messages" for m in e["messages"] if m["role"] == "user"]
                assert "read" in statuses, statuses
                rev = max(e.get("rev", 0) for e in events)

            # A button from a tool thread, while the phone is away; then reconnect from the revision.
            msg_id = await asyncio.to_thread(adapter.post_buttons, "нужно войти", [
                {"id": "login", "title": "Войти в Тест", "kind": "login", "value": "r1"}])
            await asyncio.sleep(.2)
            async with websockets.connect(f"ws://127.0.0.1:8661/app/v1/ws?since={rev}", additional_headers=H) as ws:
                backlog = json.loads(await ws.recv())
                assert [m["id"] for m in backlog["messages"]] == [msg_id], backlog
                await asyncio.to_thread(adapter.clear_buttons, msg_id)
                live = json.loads(await asyncio.wait_for(ws.recv(), 5))
                while live["type"] != "messages":
                    live = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert live["messages"][0]["buttons"] == [], live

            # Revisions on the socket only go up, even when changes are stored from another thread.
            async with websockets.connect(f"ws://127.0.0.1:8661/app/v1/ws?since={adapter.store.current_rev()}", additional_headers=H) as ws:
                json.loads(await ws.recv())
                ids = await asyncio.to_thread(lambda: [adapter.store.add("morzik", str(i))[0]["id"] for i in range(3)])
                await adapter._publish([])
                seen = []
                while len(seen) < 3:
                    ev = json.loads(await asyncio.wait_for(ws.recv(), 5))
                    if ev["type"] == "messages":
                        seen += [m["rev"] for m in ev["messages"]]
                assert seen == sorted(seen), seen

            await check_busy(adapter, http, H)
            await check_approvals(adapter, http, H)

            # A reply with a quote of a fragment: stored with the message.
            target, _ = adapter.store.add("morzik", "завтра в 10 созвон, в 15:30 стоматолог")
            r = await http.post(f"{BASE}/messages", headers=H, json={"client_id": "q1", "text": "перенеси",
                                "reply_to": {"message_id": target["id"], "quote": "в 15:30 стоматолог"}})
            assert r.json()["message"]["reply"] == {"id": target["id"], "role": "morzik", "quote": "в 15:30 стоматолог"}, r.text

            # A reaction: stored, sent to the socket, on a plain message kept for the next turn.
            plain, _ = adapter.store.add("morzik", "готово")
            r = await http.post(f"{BASE}/react", headers=H, json={"message_id": plain["id"], "emoji": "👍"})
            assert r.json()["message"]["reactions"] == ["👍"], r.text
            assert A.REACTION_NOTES and "готово" in A.REACTION_NOTES[-1], A.REACTION_NOTES
            assert A._pre_llm_call(platform="morzik_app")["context"].count("👍") == 1
            assert not A.REACTION_NOTES
            r = await http.post(f"{BASE}/react", headers=H, json={"message_id": plain["id"], "emoji": ""})
            assert r.json()["message"]["reactions"] == [], r.text

            r = await http.post(f"{BASE}/media", headers={**H, "Content-Type": "audio/mp4", "X-Filename": "v.m4a",
                                                          "X-Media-Kind": "voice"}, content=b"\x00\x00\x00\x18ftypM4A ")
            media = r.json()["media"]
            assert media["kind"] == "voice", media
            d = await http.get(f"{BASE}/media/{media['id']}", headers=H)
            assert d.content.startswith(b"\x00\x00\x00\x18ftyp"), d.content[:10]
            sync = (await http.get(f"{BASE}/sync?since={rev}", headers=H)).json()
            assert sync["messages"], sync
            hist = (await http.get(f"{BASE}/history?before=999999&limit=2", headers=H)).json()
            assert len(hist["messages"]) == 2
            r = await http.post(f"{BASE}/read", headers=H, json={"seq": adapter.store.last_seq()})
            assert r.json()["unread"] == 0, r.text
            reset = (await http.get(f"{BASE}/sync?since=999999", headers=H)).json()
            assert reset["reset"] and reset["messages"], reset
        print("smoke OK")
    finally:
        await adapter.disconnect()


asyncio.run(main())
