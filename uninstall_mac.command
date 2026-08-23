#!/bin/bash
# 이 파일은 저장소와 설치된 앱 번들(Contents/Resources/) 양쪽에 있다.
# 저장소를 지워도 앱 안의 사본으로 제거할 수 있다.
LABEL="com.memorycat.desktop"
APPS_DIR="${MEMORY_CAT_APPS_DIR:-$HOME/Applications}"
APP="$APPS_DIR/Memory Cat.app"
DATA="$HOME/Library/Application Support/Memory Cat"
LOGS="$HOME/Library/Logs/Memory Cat"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"

case "$APP" in
    *.app)
        if [ -d "$APP" ]; then
            rm -rf "$APP"
        fi
        ;;
    *)
        echo "⚠️  앱 경로가 이상해서 지우지 않았습니다: $APP"
        ;;
esac

rm -rf "$LOGS"

echo "🐱 메모리 뚱냥이 제거 완료."
echo ""
echo "   설정과 직접 만든 테마는 남겨 뒀어요:"
echo "       $DATA"
echo "   그것까지 지우려면:"
echo "       rm -rf \"$DATA\""
