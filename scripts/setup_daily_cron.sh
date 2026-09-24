#!/usr/bin/env bash
# Setup Daily Updates for Claude Code Changelog Observatory on macOS
# Generates and optionally installs a launchd user agent running daily at 04:00 AM.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Absolute path to Python executable (launchd does not inherit shell PATH)
PYTHON_EXEC="$(python3 -c 'import sys; print(sys.executable)')"
UPDATE_SCRIPT="$PROJECT_ROOT/scripts/update_changelog.py"
LOGS_DIR="$PROJECT_ROOT/logs"

mkdir -p "$LOGS_DIR"

PLIST_NAME="com.claude.changelog.daily.plist"
LOCAL_PLIST="$SCRIPT_DIR/$PLIST_NAME"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo "================================================================"
echo "⚡ Configuration launchd (mise à jour quotidienne)"
echo "================================================================"
echo "Projet : $PROJECT_ROOT"
echo "Python : $PYTHON_EXEC"
echo "Script : $UPDATE_SCRIPT"
echo "Logs   : $LOGS_DIR/daily_update.log"
echo "----------------------------------------------------------------"

# Generate plist with RunAtLoad=false and absolute Python path
cat <<EOF > "$LOCAL_PLIST"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.changelog.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_EXEC</string>
        <string>$UPDATE_SCRIPT</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>4</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOGS_DIR/daily_update.log</string>
    <key>StandardErrorPath</key>
    <string>$LOGS_DIR/daily_update.error.log</string>
    <key>WorkingDirectory</key>
    <string>$PROJECT_ROOT</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

echo "✓ Fichier plist généré localement dans : $LOCAL_PLIST"

# Installation into ~/Library/LaunchAgents only if explicitly requested with --install flag
if [[ "${1:-}" == "--install" ]]; then
    mkdir -p "$LAUNCH_AGENTS_DIR"
    cp "$LOCAL_PLIST" "$TARGET_PLIST"
    launchctl unload "$TARGET_PLIST" 2>/dev/null || true
    launchctl load "$TARGET_PLIST"
    echo "✓ Tâche installée et chargée dans : $TARGET_PLIST"
else
    echo "ℹ Note : Le fichier plist a été créé dans le dépôt."
    echo "  Pour l'enregistrer dans ~/Library/LaunchAgents, relancez avec : $0 --install"
fi
echo "================================================================"
