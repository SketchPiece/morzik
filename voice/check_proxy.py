"""Access checks for the voice proxy: only its own routes, each with its own key, get through.

    python3 voice/check_proxy.py [base_url]

With the IP allowlist on, run it on the server as an ElevenLabs address would come through the tunnel:
CHECK_AS_IP=34.59.11.47 python3 voice/check_proxy.py
"""

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8650"
env = dict(line.split("=", 1) for line in (pathlib.Path.home() / ".hermes/.env").read_text().splitlines()
           if "=" in line and not line.startswith("#"))
VOICE, MASTER = env["MORZIK_VOICE_KEY"].strip(), env["API_SERVER_KEY"].strip()
CONTEXT = env.get("MORZIK_CONTEXT_KEY", "").strip()
AS_IP = os.environ.get("CHECK_AS_IP")
BODY = json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode()

CASES = [
    ("GET", "/health", VOICE, 404),
    ("GET", "/v1/models", VOICE, 404),
    ("GET", "/api/sessions", VOICE, 404),
    ("POST", "/api/sessions", VOICE, 404),
    ("POST", "/v1/runs", VOICE, 404),
    ("POST", "/api/jobs", VOICE, 404),
    ("POST", "/v1/responses", VOICE, 404),
    ("POST", "/p/default/v1/chat/completions", VOICE, 404),
    ("POST", "/v1/chat/completions", None, 401),
    ("POST", "/v1/chat/completions", "wrong", 401),
    ("POST", "/v1/chat/completions", MASTER, 401),
    ("POST", "/v1/chat/completions", CONTEXT or "none", 401),
    ("GET", "/voice/ask", VOICE, 404),
    ("POST", "/voice/ask", None, 401),
    ("POST", "/voice/ask", MASTER, 401),
    ("POST", "/voice/ask", CONTEXT or "none", 401),
    ("POST", "/voice/context", VOICE, 401 if CONTEXT else 404),
    ("POST", "/voice/context", MASTER, 401 if CONTEXT else 404),
    ("POST", "/voice/after-call", VOICE, 401 if env.get("MORZIK_VOICE_WEBHOOK_SECRET") else 404),
    ("POST", "/voice/other", VOICE, 404),
]

failed = 0
for method, path, key, expected in CASES:
    req = urllib.request.Request(BASE + path, data=BODY if method == "POST" else None, method=method)
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    if AS_IP:
        req.add_header("X-Forwarded-For", AS_IP)
    try:
        status = urllib.request.urlopen(req, timeout=30).status
    except urllib.error.HTTPError as exc:
        status = exc.code
    label = {VOICE: "voice key", MASTER: "API_SERVER_KEY", CONTEXT: "context key", None: "no key"}.get(
        key, "wrong key")
    ok = status == expected
    failed += not ok
    print(f"{'ok ' if ok else 'BAD'} {method:4} {path:34} {label:15} -> {status} (want {expected})")
sys.exit(1 if failed else 0)
