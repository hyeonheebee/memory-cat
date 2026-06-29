#!/bin/bash
LABEL="com.memorycat.desktop"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "🐱 메모리 뚱냥이 제거 완료. (폴더는 그대로 남아있어요)"
