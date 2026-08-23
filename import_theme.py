#!/usr/bin/env python3
"""이미지(가로 단계 시트) -> 테마 프레임 변환기.

사용: import_theme.py <이미지경로> <테마이름> [--center]

가로로 늘어선 N단계 고양이 시트를 받아서:
  1) 흰 배경을 가장자리부터 flood-fill 로 투명 처리 (안쪽 흰 배는 보존)
  2) 단계별로 잘라 정사각형 캔버스에 정렬 (기본: 바닥 정렬)
  3) 11단계(cat_00~10)로 매핑해
     ~/Library/Application Support/Memory Cat/frames/<테마>/ 에 저장
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import apppaths

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = 240
N_OUT = 40
MARGIN = 10
SENTINEL = (0, 255, 1)


def cut_background(path):
    src = Image.open(path).convert("RGB")
    W, H = src.size
    fl = src.copy()
    seeds = [(0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1),
             (W // 2, 0), (W // 2, H - 1), (0, H // 2), (W - 1, H // 2)]
    for s in seeds:
        if min(src.getpixel(s)) > 233:
            ImageDraw.floodfill(fl, s, SENTINEL, thresh=34)
    arr = np.asarray(fl)
    bg = np.all(arr == np.array(SENTINEL), axis=2)
    alpha = np.where(bg, 0, 255).astype("uint8")
    rgba = np.dstack([np.asarray(src), alpha])
    return Image.fromarray(rgba, "RGBA"), alpha


def segments(alpha):
    cols = (alpha > 0).sum(axis=0)
    thr = max(cols.max() * 0.02, 3)
    content = cols > thr
    W = len(content)
    segs, i = [], 0
    while i < W:
        if content[i]:
            j = i
            while j < W and content[j]:
                j += 1
            if (j - i) > W * 0.015:
                segs.append((i, j))
            i = j
        else:
            i += 1
    return segs


def fit_square(crop, bottom=True):
    cw, ch = crop.size
    scale = (FINAL - 2 * MARGIN) / max(cw, ch)
    nw, nh = max(1, int(cw * scale)), max(1, int(ch * scale))
    crop = crop.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (FINAL, FINAL), (0, 0, 0, 0))
    x = (FINAL - nw) // 2
    y = FINAL - MARGIN - nh if bottom else (FINAL - nh) // 2
    canvas.alpha_composite(crop, (x, y))
    return canvas


def save_theme_frames(stages, out, smooth=False):
    """정규화된 단계 이미지를 40프레임과 미리보기로 저장한다."""
    if not stages:
        raise ValueError("저장할 반려동물 단계를 찾지 못했습니다.")
    os.makedirs(out, exist_ok=True)
    ns = len(stages)
    for idx in range(N_OUT):
        p = idx / (N_OUT - 1) * (ns - 1)        # 0 ~ ns-1 연속 위치
        lo = int(math.floor(p))
        hi = min(lo + 1, ns - 1)
        w = p - lo
        if smooth and w > 0 and lo != hi:
            frame = Image.blend(stages[lo], stages[hi], w)   # 크로스페이드
        else:
            frame = stages[round(p)]                          # 가까운 단계 (잔상 없음)
        frame.save(os.path.join(out, f"cat_{idx:02d}.png"))

    pad = 8
    strip = Image.new("RGBA", (ns * (FINAL + pad) + pad, FINAL + 2 * pad),
                      (235, 235, 235, 255))
    for i, im in enumerate(stages):
        strip.paste(im, (pad + i * (FINAL + pad), pad), im)
    strip.save(os.path.join(out, "_preview.png"))


def main():
    if len(sys.argv) < 3:
        print("사용: import_theme.py <이미지> <테마이름> [--center]")
        sys.exit(1)
    path, theme = sys.argv[1], sys.argv[2]
    bottom = "--center" not in sys.argv

    full, alpha = cut_background(path)
    segs = segments(alpha)
    print(f"단계 {len(segs)}개 감지")

    stages = []
    for (x0, x1) in segs:
        sub = alpha[:, x0:x1]
        rows = np.where((sub > 0).sum(axis=1) > 0)[0]
        if len(rows) == 0:
            continue
        y0, y1 = int(rows[0]), int(rows[-1]) + 1
        stages.append(fit_square(full.crop((x0, y0, x1, y1)), bottom))

    if not stages:
        print("고양이를 못 찾음 (배경 따기 실패?)")
        sys.exit(1)

    smooth = "--smooth" in sys.argv   # 자세 비슷할 때만 권장 (다르면 잔상)
    # 직접 만든 테마는 앱 번들이 아니라 사용자 폴더에 쌓인다. 앱을 다시 깔아도
    # 살아남고, 저장소를 지워도 남는다.
    out = os.path.join(apppaths.user_frames_dir(), theme)
    save_theme_frames(stages, out, smooth=smooth)
    print(f"[{theme}] {len(stages)}단계 -> {N_OUT}프레임(크로스페이드) 저장: {out}")


if __name__ == "__main__":
    main()
