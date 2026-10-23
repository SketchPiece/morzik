#!/bin/zsh
# Build Morzik Bridge, install it to ~/Applications and (re)start its LaunchAgent.
set -euo pipefail
cd "${0:A:h}"

APP="$HOME/Applications/MorzikBridge.app"
LABEL="dev.sketchpiece.morzik-bridge"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
CONF="$HOME/.config/morzik-bridge"
LOG="$HOME/Library/Logs/morzik-bridge.log"
# A stable signing identity keeps the Calendar/Reminders permission across rebuilds.
IDENTITY="${MORZIK_BRIDGE_SIGN:-Apple Development}"

mkdir -p build
swiftc -O -swift-version 5 -o build/morzik-bridge Sources/main.swift

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp Info.plist "$APP/Contents/Info.plist"
cp build/morzik-bridge "$APP/Contents/MacOS/morzik-bridge"
codesign --force --options runtime --entitlements entitlements.plist --sign "$IDENTITY" "$APP"

mkdir -p "$CONF"
if [[ ! -s "$CONF/token" ]]; then
  (umask 077; openssl rand -hex 32 > "$CONF/token")
fi
[[ -f "$CONF/env" ]] || cat > "$CONF/env" <<'ENV'
# Where the bridge listens. Keep 127.0.0.1; open it to the tailnet with `tailscale serve` (see README).
MORZIK_BRIDGE_HOST=127.0.0.1
MORZIK_BRIDGE_PORT=8765
ENV

cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>$LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>/bin/zsh</string><string>-c</string>
		<string>set -a; source "$CONF/env"; exec "$APP/Contents/MacOS/morzik-bridge"</string>
	</array>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>ProcessType</key><string>Interactive</string>
	<key>StandardErrorPath</key><string>$LOG</string>
	<key>StandardOutPath</key><string>$LOG</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENT"
echo "installed: $APP, logs: $LOG, token: $CONF/token"
