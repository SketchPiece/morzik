#!/bin/sh
# Run on sketch-server: publish ONLY /v1/chat/completions to the internet with Tailscale Funnel,
# pointing at the voice proxy. Funnel opens a whole HTTPS port, so the port must be free of other
# `tailscale serve` handlers, or they would go public too.
#
#   sh funnel.sh [port]            # port: 443 (default), 8443 or 10000
#
# Now the proxy runs on the Mac (tailnet address below). After Morzik moves to sketch-server, run
# it there and point here at it: MORZIK_VOICE_TARGET=http://127.0.0.1:8650 sh funnel.sh
set -eu
PORT="${1:-443}"
TARGET="${MORZIK_VOICE_TARGET:-http://100.106.22.52:8650}"
ROUTE=/v1/chat/completions

if tailscale serve status --json | grep -q "ts.net:$PORT\""; then
  echo "port $PORT already has serve handlers; pick another port or clear them first:" >&2
  tailscale serve status >&2
  exit 1
fi
sudo tailscale funnel --bg --https="$PORT" --set-path="$ROUTE" "$TARGET$ROUTE"
tailscale funnel status
