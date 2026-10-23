#!/bin/zsh
# Install the voice proxy as a LaunchAgent and (re)start it. Keys live in ~/.hermes/.env:
# API_SERVER_KEY (Hermes) and MORZIK_VOICE_KEY (what ElevenLabs sends); a missing voice key is created.
set -euo pipefail
cd "${0:A:h}"

LABEL="dev.sketchpiece.morzik-voice"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/morzik-voice.log"
ENV_FILE="$HOME/.hermes/.env"
PYTHON="$(command -v python3)"

if ! grep -q '^MORZIK_VOICE_KEY=' "$ENV_FILE"; then
  print "MORZIK_VOICE_KEY=$(openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-54)" >> "$ENV_FILE"
fi

cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>$LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>$PYTHON</string><string>-I</string><string>$PWD/proxy.py</string>
	</array>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>StandardErrorPath</key><string>$LOG</string>
	<key>StandardOutPath</key><string>$LOG</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$AGENT"
print "started $LABEL, log: $LOG"
