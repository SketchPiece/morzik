"""Latency bench for Morzik's voice endpoint (OpenAI-compatible /v1/chat/completions).

Sends the same kind of streaming request ElevenLabs' Custom LLM sends and prints, per case:
time to first content token, time to the end of the first sentence (what TTS can start
speaking), total time, and which tools Hermes ran.

    python3 voice/bench.py [--url URL] [--runs N] [case ...]

The key is read from API_SERVER_KEY in ~/.hermes/.env (or VOICE_KEY in the environment).
"""

import argparse
import json
import os
import pathlib
import re
import statistics
import time
import urllib.request

SYSTEM = "Голосовой звонок с пользователем. Отвечай коротко, одной-двумя фразами, как в разговоре."

CASES = {
    "chat": "Привет, Морзик, как дела?",
    "memory": "Что ты обо мне помнишь? Коротко.",
    "calendar": "Что у меня сегодня в календаре?",
    "web": "Какая сейчас погода в Барселоне?",
}

SENTENCE_END = re.compile(r"[.!?…]")


def read_key() -> str:
    if os.environ.get("VOICE_KEY"):
        return os.environ["VOICE_KEY"]
    for line in (pathlib.Path.home() / ".hermes/.env").read_text().splitlines():
        if line.startswith("API_SERVER_KEY="):
            key = line.split("=", 1)[1].strip()
    return key


def run_case(url: str, key: str, text: str) -> dict:
    body = {
        "model": "morzik-voice",
        "stream": True,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "assistant", "content": "Мяу, слушаю."},
            {"role": "user", "content": text},
        ],
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    start = time.monotonic()
    first_byte = first_token = first_sentence = None
    content, tools, event = "", [], None
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw in resp:
            now = time.monotonic() - start
            first_byte = first_byte or now
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("event:"):
                event = line[6:].strip()
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            payload = json.loads(data)
            if event == "hermes.tool.progress":
                if payload.get("status") == "running":
                    tools.append((payload.get("tool"), round(now, 2)))
                event = None
                continue
            event = None
            delta = (payload.get("choices") or [{}])[0].get("delta", {})
            piece = delta.get("content") or ""
            if piece:
                first_token = first_token or now
                content += piece
                if first_sentence is None and SENTENCE_END.search(content):
                    first_sentence = now
    total = time.monotonic() - start
    return {"first_token": first_token, "first_sentence": first_sentence or total,
            "total": total, "tools": tools, "text": content.strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8642/v1/chat/completions")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("cases", nargs="*", default=list(CASES))
    args = parser.parse_args()
    key = read_key()
    for name in args.cases:
        results = []
        for i in range(args.runs):
            r = run_case(args.url, key, CASES[name])
            results.append(r)
            tools = ", ".join(f"{t}@{s}s" for t, s in r["tools"]) or "-"
            print(f"{name} #{i + 1}: first token {r['first_token'] or 0:.2f}s, "
                  f"first sentence {r['first_sentence']:.2f}s, total {r['total']:.2f}s, "
                  f"tools {tools}\n    {r['text'][:160]}")
        med = {k: statistics.median(r[k] or 0 for r in results)
               for k in ("first_token", "first_sentence", "total")}
        print(f"{name} median: first token {med['first_token']:.2f}s, "
              f"first sentence {med['first_sentence']:.2f}s, total {med['total']:.2f}s\n")


if __name__ == "__main__":
    main()
