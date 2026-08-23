#!/bin/bash
set -e
cd "$(dirname "$0")"
SRC="$(pwd)"

LABEL="com.memorycat.desktop"
# 테스트에서 설치 위치를 갈아끼울 수 있게 열어 둔 구멍. 평소엔 ~/Applications.
APPS_DIR="${MEMORY_CAT_APPS_DIR:-$HOME/Applications}"
APP="$APPS_DIR/Memory Cat.app"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/Memory Cat/cat.log"

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

# 앱을 통째로 다시 만드니까, 돌고 있으면 먼저 내린다.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

case "$APP" in
    *.app) ;;
    *)
        echo "❌ 설치 경로가 .app 으로 끝나지 않습니다: $APP"
        exit 1
        ;;
esac
rm -rf "$APP"
mkdir -p "$APPS_DIR" "$APP/Contents/Resources"

# 가상환경은 번들 안에 둔다. 앱 하나만 지우면 런타임까지 같이 사라진다.
python3 -m venv "$APP/Contents/Resources/venv"
VENVPY="$APP/Contents/Resources/venv/bin/python"

# 이 순서는 바꾸면 안 된다. macOS 기본 python3 의 venv 에 딸려오는 pip 21.2.4 는
# pyobjc-core 휠을 찾지 못해 소스 빌드로 넘어가고 "Cannot locate a working
# compiler" 로 죽는다. pip 를 먼저 올려야 휠이 잡힌다.
"$VENVPY" -m pip install -q --upgrade pip
"$VENVPY" -m pip install -q -r requirements.txt

# 번들 조립 + LaunchAgent plist 생성. plist 는 plistlib 이 구조적으로 쓴다.
# (예전처럼 셸 변수를 XML 히어독에 끼워 넣으면 경로에 & 가 있을 때 깨진다.)
"$VENVPY" "$SRC/macos/build_app.py" \
    --source "$SRC" \
    --app "$APP" \
    --launch-agent "$PLIST" \
    --log "$LOG"

if ! plutil -lint "$APP/Contents/Info.plist" >/dev/null; then
    echo "❌ 번들 Info.plist 가 깨졌습니다. 설치를 멈춥니다."
    exit 1
fi
if ! plutil -lint "$PLIST" >/dev/null; then
    echo "❌ LaunchAgent plist 가 깨졌습니다. 설치를 멈춥니다."
    exit 1
fi

# 아이콘은 CFBundleIconFile 이 가리키는 파일이 Resources 안에 실제로 있을
# 때만 붙는다. 어긋나면 Finder 가 조용히 기본 아이콘을 보여 줄 뿐 아무
# 오류도 내지 않아서, 여기서 짚어 준다. (아이콘은 장식이니 설치는 계속한다.)
ICON_NAME="$(plutil -extract CFBundleIconFile raw -o - "$APP/Contents/Info.plist" 2>/dev/null || true)"
if [ -z "$ICON_NAME" ]; then
    echo "⚠️  번들에 앱 아이콘이 없습니다. 기본 아이콘으로 표시됩니다."
elif [ ! -f "$APP/Contents/Resources/$ICON_NAME" ]; then
    echo "⚠️  Info.plist 가 없는 아이콘을 가리킵니다: $ICON_NAME"
fi

if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/tmp/memorycat-bootstrap.$$; then
    rm -f "/tmp/memorycat-bootstrap.$$"

    # bootstrap 이 성공해도 launchd 가 RunAtLoad 를 무시하는 경우가 있다.
    # 그때 "떴어요" 라고 말하면 사용자는 뜨지도 않은 고양이를 찾게 되므로,
    # 실제로 떴는지 보고 안 떴으면 한 번 밀어 준다.
    started=""
    for _ in 1 2 3 4 5 6; do
        if launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -q "state = running"; then
            started="yes"
            break
        fi
        sleep 0.5
    done

    if [ -z "$started" ]; then
        launchctl kickstart "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
        for _ in 1 2 3 4 5 6; do
            if launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -q "state = running"; then
                started="yes"
                break
            fi
            sleep 0.5
        done
    fi

    if [ -n "$started" ]; then
        echo "✅ 완료! 화면 어딘가에 고양이가 떴어요. 드래그로 옮기고 우클릭해보세요."
    else
        echo ""
        echo "⚠️  앱은 설치했는데 고양이가 아직 안 떴어요."
        echo "    ▸ 지금 바로 보려면:"
        echo "        open -a \"$APP\""
        echo "    ▸ 로그인할 때 자동으로 뜨게 하려면 시스템 설정 >"
        echo "      일반 > 로그인 항목 및 확장 프로그램에서 'Memory Cat' 을 켜 주세요."
        echo "    ▸ 그래도 안 되면 로그를 봐 주세요: $LOG"
        echo ""
    fi
else
    # 여기서 조용히 죽으면 사용자는 설치가 됐는지조차 알 수 없다.
    # macOS 13+ 의 백그라운드 항목 승인 대기(Bootstrap failed: 5)가 흔한 원인.
    echo ""
    echo "⚠️  앱은 설치했지만 로그인 자동 실행 등록에 실패했습니다."
    echo "    이유:"
    sed 's/^/      /' "/tmp/memorycat-bootstrap.$$" 2>/dev/null || true
    rm -f "/tmp/memorycat-bootstrap.$$"
    echo ""
    echo "    ▸ 시스템 설정 > 일반 > 로그인 항목에서 'Memory Cat' 을 허용한 뒤"
    echo "      이 설치 파일을 다시 실행해 보세요."
    echo "    ▸ 지금 바로 실행하려면:"
    echo "        open -a \"$APP\""
    echo ""
fi

echo ""
echo "   앱:          $APP"
echo "   설정·내 테마: $HOME/Library/Application Support/Memory Cat"
echo "   로그:        $LOG"
echo "   제거:        uninstall_mac.command"
echo "                (저장소를 지웠다면 아래 파일을 실행하세요)"
echo "                \"$APP/Contents/Resources/uninstall_mac.command\""
