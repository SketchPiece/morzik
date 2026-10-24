#!/usr/bin/env bash
# Uploads voice/keywords.txt to the ElevenLabs agent as ASR keywords. Run on sketch-server (reads Morzik's .env).
set -euo pipefail
cd "$(dirname "$0")"
eval "$(sudo grep -E "^(MORZIK_ELEVENLABS_AGENT_KEY|MORZIK_VOICE_AGENT_ID)=" /home/morzik/.hermes/.env | sed "s/^/export /")"
body=$(python3 -c "import json; words=[l.strip() for l in open(\"keywords.txt\") if l.strip() and not l.startswith(\"#\")]; print(json.dumps({\"conversation_config\": {\"asr\": {\"keywords\": words}}}, ensure_ascii=False))")
curl -fsS -X PATCH "https://api.elevenlabs.io/v1/convai/agents/$MORZIK_VOICE_AGENT_ID" \
  -H "xi-api-key: $MORZIK_ELEVENLABS_AGENT_KEY" -H "Content-Type: application/json" -d "$body" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[\"conversation_config\"][\"asr\"][\"keywords\"], d.get(\"version_id\"))"
