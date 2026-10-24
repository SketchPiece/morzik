#!/bin/sh
# Run on sketch-server: publish ONLY the voice proxy's routes to the internet with Tailscale Funnel.
# Funnel opens a whole HTTPS port, so the port must hold no other `tailscale serve` handlers, or
# they would go public too.
#
#   sh funnel.sh [port]            # port: 443 (default), 8443 or 10000
#
# Published: /v1/chat/completions (Custom LLM) and /voice/ (snapshot, ask Morzik, post-call webhook).
set -eu
PORT="${1:-443}"
TARGET="${MORZIK_VOICE_TARGET:-http://127.0.0.1:8650}"
PATHS="/v1/chat/completions /voice/"

# Handlers already on this port that are not ours.
OTHERS=$(tailscale serve status --json | PORT="$PORT" PATHS="$PATHS" python3 -c '
import json, os, sys
web = json.load(sys.stdin).get("Web") or {}
ours = os.environ["PATHS"].split()
for host, cfg in web.items():
    if host.endswith(":" + os.environ["PORT"]):
        for path in (cfg.get("Handlers") or {}):
            if path not in ours:
                print(host + path)
')
if [ -n "$OTHERS" ]; then
  echo "port $PORT already serves other handlers; pick another port or clear them first:" >&2
  echo "$OTHERS" >&2
  exit 1
fi
for P in $PATHS; do
  sudo tailscale funnel --bg --https="$PORT" --set-path="$P" "$TARGET$P"
done
tailscale funnel status
