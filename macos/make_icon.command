#!/bin/bash
# macos/MemoryCat.icns 를 다시 굽는다. **개발자 전용, 설치할 때는 돌지 않는다.**
#
# 결과물(.icns)은 저장소에 커밋되어 있다. 설치 스크립트는 그걸 복사만 하므로
# 사용자 Mac 에 Pillow 나 iconutil 이 없어도 아이콘이 붙는다. 이 파일은
# 스프라이트를 바꿨을 때만 실행하면 된다.
#
# 역할 분담:
#   make_iconset.py  자르기·여백·리샘플링 (Pillow, 서브프로세스 없음)
#   이 스크립트       iconutil 호출 (셸에서 명령을 부르는 건 셸의 일이다)
#
# 저장소의 파이썬 소스에는 subprocess/os.system/osascript 가 하나도 없다.
# iconutil 을 파이썬에서 부르면 그 성질이 깨지므로 여기에 둔다.
set -e
cd "$(dirname "$0")"

SPRITE="${1:-../frames/cute/cat_16.png}"
ICONSET="MemoryCat.iconset"
ICNS="MemoryCat.icns"

if ! command -v iconutil >/dev/null 2>&1; then
    echo "❌ iconutil 이 없습니다. macOS 에서 실행하세요."
    exit 1
fi

echo "🎨 Memory Cat 아이콘 굽는 중..."
python3 make_iconset.py --sprite "$SPRITE" --iconset "$ICONSET"

# iconutil 은 .iconset 폴더를 통째로 읽어 10칸을 다 채운 .icns 를 만든다.
# (Pillow 의 ICNS 저장은 icp4/icp5 — 16pt·32pt 1x 칸을 만들지 않는다.)
iconutil --convert icns --output "$ICNS" "$ICONSET"

# 중간 산출물은 남기지 않는다. 커밋되는 건 .icns 하나뿐이다.
rm -rf "$ICONSET"

echo "✅ $(cd "$(dirname "$ICNS")" && pwd)/$ICNS"
iconutil --convert iconset --output /dev/null "$ICNS" 2>/dev/null || true
ls -l "$ICNS"
