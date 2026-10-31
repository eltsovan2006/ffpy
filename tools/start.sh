#!/bin/bash
# Быстрый запуск воркфлоу: две вкладки Terminal — Antigravity (agy) и Claude Code — в корне ffpy.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
osascript <<EOF
tell application "Terminal"
  activate
  do script "cd '$ROOT' && agy"
  tell application "System Events" to keystroke "t" using command down
  delay 0.5
  do script "cd '$ROOT' && claude --model sonnet" in front window
end tell
EOF
