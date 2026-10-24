"""End-to-end check of the adapter against the real Hermes code, without the gateway (run on the server):

    sudo -u morzik env PYTHONPATH=<hermes-agent>:<site-packages> <hermes python> app/smoke_adapter.py

A throwaway state dir and port 8661; an echo handler stands in for Morzik. Checks sign-in (the code is read
from the store, Telegram is stubbed), send + idempotent resend, the live socket (backlog, typing, split parts),
reconnect from a revision, history, read marks, media round trip and a button posted from another thread.
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


async def main():
    tmp = tempfile.mkdtemp()
    adapter = A.MorzikAppAdapter(PlatformConfig(enabled=True, extra={"state_dir": tmp, "port": 8661}))
    sent_codes = []

    async def fake_telegram(method, **params):
        sent_codes.append(params["text"])
        return {}
    adapter._telegram = fake_telegram
    A.MIN_PAUSE, A.MAX_PAUSE = .05, .1

    async def echo(event):
        await adapter.on_processing_start(event)
        await adapter.send(A.CHAT_ID, f"эхо: {event.text}\n\nвторая мысль")
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
