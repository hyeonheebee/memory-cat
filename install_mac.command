#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "🐱 메모리 뚱냥이 설치 중..."

python3 -m venv .venv
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -r requirements.txt

PY="$(pwd)/.venv/bin/python"
APP="$(pwd)/desktop_cat.py"
LABEL="com.memorycat.desktop"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array><string>$PY</string><string>$APP</string></array>
    <key>WorkingDirectory</key><string>$(pwd)</string>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>$(pwd)/cat.log</string>
    <key>StandardErrorPath</key><string>$(pwd)/cat.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "✅ 완료! 화면 어딘가에 고양이가 떴어요. 드래그로 옮기고 우클릭해보세요."
echo "   제거하려면 uninstall_mac.command 를 실행하세요."
