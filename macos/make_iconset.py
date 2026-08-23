#!/usr/bin/env python3
"""번들 아이콘의 재료가 되는 ``.iconset`` 폴더를 만든다. **개발자 전용.**

이 스크립트는 설치할 때 돌지 않는다. `macos/MemoryCat.icns` 는 저장소에
커밋되어 있고, 설치 스크립트는 그걸 그대로 복사만 한다. 여기 있는 코드는
스프라이트를 바꿨을 때 아이콘을 다시 굽기 위한 것이고, `make_icon.command`
가 이 스크립트를 부른 뒤 `iconutil` 로 `.icns` 를 만든다.

왜 굳이 파이썬과 셸로 나눠 놨냐면:

* 저장소의 파이썬 소스에는 ``subprocess``/``os.system``/``osascript`` 가
  하나도 없다. 그 성질이 보안 검토에서 구조적 강점으로 지목됐다. 그래서
  ``iconutil`` 호출은 셸 스크립트 쪽에 둔다. 파이썬은 픽셀만 만진다.
* 반대로 자르기·여백·리샘플링은 셸(`sips`)로 하기 어렵다. `sips` 의
  ``--padToHeightWidth`` 는 알파를 못 넣고 불투명한 색으로 채운다.
  고양이 뒤에 흰 사각형이 생긴다는 뜻이다.

Pillow 는 ``.icns`` 를 직접 쓸 수도 있지만 쓰지 않는다. Pillow 의
``IcnsImagePlugin._save`` 는 8개 청크(ic07~ic14)만 박아 넣고 ``icp4``(16pt
1x)·``icp5``(32pt 1x)를 아예 만들지 않는다. 게다가 리샘플링 필터를 지정하지
않아 기본 BICUBIC 으로 줄인다. `iconutil` 은 10칸을 다 채운다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: `iconutil` 이 기대하는 파일 이름 → 실제 픽셀 크기.
#: 16/32/128/256/512 를 1x·2x 로 전부 채운다.
ICONSET_SLOTS = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)

CANVAS = 1024

#: 1024 캔버스에서 고양이가 차지하는 비율. macOS 아이콘은 가장자리까지
#: 꽉 채우지 않는다. 다만 우리 아이콘은 둥근 사각형이 아니라 자유 형태라
#: 애플의 824/1024 그리드보다는 넉넉하게 잡아도 된다. 16pt 로 줄었을 때
#: 고양이가 알아볼 수 없을 만큼 작아지지 않는 선.
CONTENT_RATIO = 0.90

#: 기본 소스 스프라이트. `cute` 테마 12~19번 구간(앉아 있는 통통한 단계).
#: 39번(제일 뚱뚱한 프레임)이 아니다 — 39번은 눈을 감고 있어서 16px 로
#: 줄이면 눈이 사라지고 주황색 덩어리만 남는다. 측정값은 README 가 아니라
#: 커밋 메시지에 있다.
DEFAULT_SPRITE = Path("frames") / "cute" / "cat_16.png"


def build_master(sprite_path: Path):
    """스프라이트를 정사각형 1024 캔버스 가운데에 앉힌 마스터 이미지."""
    from PIL import Image

    image = Image.open(sprite_path).convert("RGBA")

    # 스프라이트는 240x240 캔버스 안에 그려져 있고 위쪽에 빈 공간이 많다.
    # 그대로 쓰면 고양이가 아이콘 아래쪽에 쏠린다. 불투명한 부분만 잘라내고
    # 다시 가운데 정렬한다.
    box = image.getchannel("A").getbbox()
    if box is None:
        raise SystemExit(f"스프라이트가 전부 투명합니다: {sprite_path}")
    cropped = image.crop(box)

    limit = int(CANVAS * CONTENT_RATIO)
    scale = min(limit / cropped.width, limit / cropped.height)
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    # 축소가 아니라 확대다(240 → ~920). LANCZOS 가 가장자리를 덜 뭉갠다.
    scaled = cropped.resize(size, Image.LANCZOS)

    master = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    master.alpha_composite(scaled, ((CANVAS - size[0]) // 2, (CANVAS - size[1]) // 2))
    return master


def write_iconset(master, iconset_dir: Path) -> list:
    """10칸짜리 ``.iconset`` 을 채운다. 이미 있던 내용은 지운다."""
    from PIL import Image

    if iconset_dir.exists():
        for stale in iconset_dir.glob("*.png"):
            stale.unlink()
    iconset_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for name, pixels in ICONSET_SLOTS:
        # 항상 1024 마스터에서 한 번에 줄인다. 단계적으로 줄이면 작은 칸에서
        # 눈·귀 같은 얇은 특징이 뭉개진다.
        frame = master if pixels == CANVAS else master.resize(
            (pixels, pixels), Image.LANCZOS
        )
        target = iconset_dir / name
        frame.save(target, "png", optimize=True)
        written.append((name, pixels))
    return written


def main(argv=None) -> int:
    here = Path(__file__).resolve().parent
    repo = here.parent
    parser = argparse.ArgumentParser(description="Memory Cat .iconset 굽기")
    parser.add_argument(
        "--sprite", default=str(repo / DEFAULT_SPRITE), help="소스 스프라이트 PNG"
    )
    parser.add_argument(
        "--iconset", default=str(here / "MemoryCat.iconset"), help="만들 .iconset 폴더"
    )
    args = parser.parse_args(argv)

    sprite = Path(args.sprite).expanduser().resolve()
    if not sprite.is_file():
        print(f"❌ 스프라이트를 찾을 수 없습니다: {sprite}", file=sys.stderr)
        return 1

    try:
        master = build_master(sprite)
    except ImportError:
        print(
            "❌ Pillow 가 필요합니다 (개발자 전용 스크립트입니다).\n"
            "   python3 -m pip install 'Pillow>=10,<13'",
            file=sys.stderr,
        )
        return 1

    iconset = Path(args.iconset).expanduser()
    written = write_iconset(master, iconset)
    print(f"   소스 스프라이트: {sprite}")
    print(f"   iconset: {iconset}")
    for name, pixels in written:
        print(f"     {name:24s} {pixels}x{pixels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
