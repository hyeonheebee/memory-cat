#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "🐱 메모리 뚱냥이 설치 중..."

# 개발자 도구가 없는 Mac 에서 /usr/bin/python3 는 실제 인터프리터가 아니라
# 설치를 유도하는 껍데기다. 그대로 두면 set -e 가 걸려 아무 안내 없이 끝난다.
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    echo ""
    echo "❌ Python 3.9 이상이 필요한데 실행할 수 있는 python3 를 찾지 못했어요."
    echo ""
    echo "   macOS 개발자 도구를 아직 설치하지 않았다면 먼저 실행하세요:"
    echo "       xcode-select --install"
    echo "   설치 창이 끝나면 이 파일을 다시 실행하면 됩니다."
    echo ""
    echo "   또는 https://www.python.org/downloads/ 에서 설치해도 됩니다."
    echo ""
    exit 1
fi

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
