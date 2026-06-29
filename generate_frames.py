#!/usr/bin/env python3
"""메모리 뚱냥이 프레임 생성기 — 테마 3종.

- awkward : 첫 식빵냥 (멍하고 좀 불편한 버전)
- cute    : 치비 반짝 (큰 눈·앞발·꼬리·혀)
- derpy   : 하찮은 멍냥 (먹선·회색무늬, 뚱뚱할수록 눈 게슴츠레)

각 테마를 frames/<theme>/cat_00.png ~ cat_10.png 로 저장.
공통: 애기냥 -> 돼지냥, 용량(0~1)에 따라 11단계.
"""
import math
import os
from PIL import Image, ImageDraw, ImageChops

ROOT = os.path.join(os.path.dirname(__file__), "frames")
N = 40
FINAL = 240
SS = 4
S = FINAL * SS


def _h(hexstr):
    return tuple(int(hexstr[i:i + 2], 16) for i in (1, 3, 5))


def lerp(a, b, t):
    return a + (b - a) * t


def blend(c1, c2, t):
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))


def darken(c, f=0.5):
    return tuple(int(round(v * f)) for v in c)


def ramp(t, g, a, r):
    if t < 0.55:
        return blend(g, a, t / 0.55)
    return blend(a, r, (t - 0.55) / 0.45)


# ---------------------------------------------------------------- awkward
def draw_awkward(t):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = S / 2
    pink = _h("#F2A5B5")
    col = ramp(t, _h("#6BBF59"), _h("#E0A33A"), _h("#D9534F"))
    out = darken(col, 0.5)
    lw = max(2, int(S * 0.018))
    bottom = S - 0.085 * S
    bw = lerp(0.42, 0.92, t) * S
    bh = lerp(0.50, 0.74, t) * S
    bx0, bx1 = cx - bw / 2, cx + bw / 2
    by1, by0 = bottom, bottom - lerp(0.50, 0.74, t) * S
    cy = (by0 + by1) / 2
    ear = lerp(0.22, 0.14, t) * S
    ear_y = by0 + bh * 0.06
    ear_dx = bw * 0.30
    for sign in (-1, 1):
        ox = cx + sign * ear_dx
        d.polygon([(ox - ear * 0.5, ear_y + ear * 0.25),
                   (ox + sign * ear * 0.15, ear_y - ear * 0.75),
                   (ox + ear * 0.5, ear_y + ear * 0.25)], fill=col, outline=out)
        d.polygon([(ox - ear * 0.26, ear_y + ear * 0.12),
                   (ox + sign * ear * 0.10, ear_y - ear * 0.42),
                   (ox + ear * 0.26, ear_y + ear * 0.12)], fill=pink)
    d.ellipse([bx0, by0, bx1, by1], fill=col, outline=out, width=lw)
    blush_a = int(lerp(40, 230, t))
    br = lerp(0.06, 0.12, t) * S
    eye_y = cy - bh * 0.02
    for sign in (-1, 1):
        ox = cx + sign * bw * 0.30
        oy = eye_y + bh * 0.16
        d.ellipse([ox - br, oy - br * 0.7, ox + br, oy + br * 0.7],
                  fill=pink + (blush_a,))
    eye_rx = lerp(0.055, 0.052, t) * S
    eye_ry = lerp(0.075, 0.022, t) * S
    for sign in (-1, 1):
        ox = cx + sign * bw * 0.20
        d.ellipse([ox - eye_rx, eye_y - eye_ry, ox + eye_rx, eye_y + eye_ry],
                  fill=(30, 26, 20))
        hl = lerp(0.028, 0.012, t) * S
        d.ellipse([ox - eye_rx * 0.3 - hl, eye_y - eye_ry * 0.3 - hl,
                   ox - eye_rx * 0.3 + hl, eye_y - eye_ry * 0.3 + hl],
                  fill=(255, 255, 255))
    nose_y = eye_y + bh * 0.12
    nr = 0.022 * S
    d.polygon([(cx - nr, nose_y - nr * 0.6), (cx + nr, nose_y - nr * 0.6),
               (cx, nose_y + nr * 0.6)], fill=darken(pink, 0.85))
    mw = lerp(0.05, 0.09, t) * S
    d.arc([cx - mw, nose_y, cx, nose_y + mw], 0, 110, fill=out, width=lw)
    d.arc([cx, nose_y, cx + mw, nose_y + mw], 70, 180, fill=out, width=lw)
    wl = lerp(0.10, 0.16, t) * S
    for sign in (-1, 1):
        sx = cx + sign * bw * 0.18
        for dyf in (-0.03, 0.0, 0.03):
            yy = nose_y + dyf * S
            d.line([(sx, yy), (sx + sign * wl, yy + dyf * S * 0.5)],
                   fill=out, width=max(1, lw // 2))
    return img.resize((FINAL, FINAL), Image.LANCZOS)


# ------------------------------------------------------------------- cute
def draw_cute(t):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = S / 2
    inner_ear, blush, nose, eye = (247, 183, 198), (245, 150, 170), (214, 120, 140), (44, 34, 30)
    col = ramp(t, _h("#7FCB6A"), _h("#EBB14B"), _h("#E8736B"))
    out = darken(col, 0.5)
    lw = max(2, int(S * 0.011))
    rH = lerp(0.235, 0.225, t) * S
    bw = lerp(0.34, 0.86, t) * S
    bh = lerp(0.28, 0.58, t) * S
    ground = S - 0.085 * S
    body_top = ground - bh
    by_c = (body_top + ground) / 2
    bx0, bx1 = cx - bw / 2, cx + bw / 2
    tail_w = max(2, int(lerp(0.045, 0.07, t) * S))
    tb = [cx + bw * 0.16, by_c - bh * 0.5, cx + bw * 0.98, by_c + bh * 0.25]
    d.arc(tb, -35, 150, fill=col, width=tail_w)
    cxb, cyb = (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2
    rxb, ryb = (tb[2] - tb[0]) / 2, (tb[3] - tb[1]) / 2
    ang = math.radians(-35)
    tipx, tipy = cxb + rxb * math.cos(ang), cyb + ryb * math.sin(ang)
    d.ellipse([tipx - tail_w / 2, tipy - tail_w / 2, tipx + tail_w / 2, tipy + tail_w / 2], fill=col)
    d.ellipse([bx0, body_top, bx1, ground], fill=col, outline=out, width=lw)
    paw_r = lerp(0.055, 0.08, t) * S
    for sign in (-1, 1):
        px = cx + sign * bw * 0.24
        py = ground - paw_r * 0.5
        d.ellipse([px - paw_r, py - paw_r * 0.85, px + paw_r, py + paw_r * 0.85], fill=col, outline=out, width=lw)
        d.line([(px, py - paw_r * 0.3), (px, py + paw_r * 0.55)], fill=out, width=max(1, lw // 2))
    hy = body_top + rH * 0.18
    ear_w, ear_h = lerp(0.20, 0.16, t) * S, lerp(0.22, 0.18, t) * S
    ear_dx, ear_baseY = rH * 0.6, hy - rH * 0.7
    for sign in (-1, 1):
        ox = cx + sign * ear_dx
        apex = (ox + sign * ear_w * 0.12, ear_baseY - ear_h)
        d.polygon([(ox - ear_w * 0.5, ear_baseY + ear_h * 0.18), apex,
                   (ox + ear_w * 0.5, ear_baseY + ear_h * 0.18)], fill=col, outline=out)
        d.polygon([(ox - ear_w * 0.24, ear_baseY + ear_h * 0.04),
                   (apex[0], apex[1] + ear_h * 0.36),
                   (ox + ear_w * 0.24, ear_baseY + ear_h * 0.04)], fill=inner_ear)
    d.ellipse([cx - rH, hy - rH, cx + rH, hy + rH], fill=col, outline=out, width=lw)
    blush_a = int(lerp(70, 240, t))
    brx = lerp(0.06, 0.10, t) * S
    eye_y = hy + rH * 0.08
    for sign in (-1, 1):
        bxc, byc = cx + sign * rH * 0.6, eye_y + rH * 0.42
        d.ellipse([bxc - brx, byc - brx * 0.6, bxc + brx, byc + brx * 0.6], fill=blush + (blush_a,))
    rE = lerp(0.10, 0.088, t) * S
    squint = 1.0 - 0.42 * max(0.0, (t - 0.5) / 0.5)
    for sign in (-1, 1):
        ex = cx + sign * rH * 0.43
        d.ellipse([ex - rE, eye_y - rE * squint, ex + rE, eye_y + rE * squint], fill=eye)
        hlr = rE * 0.42
        d.ellipse([ex - rE * 0.32 - hlr, eye_y - rE * 0.42 - hlr,
                   ex - rE * 0.32 + hlr, eye_y - rE * 0.42 + hlr], fill=(255, 255, 255))
        sr = rE * 0.18
        d.ellipse([ex + rE * 0.28 - sr, eye_y + rE * 0.25 - sr,
                   ex + rE * 0.28 + sr, eye_y + rE * 0.25 + sr], fill=(255, 255, 255))
    ny = eye_y + rE * 1.05
    nr = rH * 0.1
    d.polygon([(cx - nr, ny - nr * 0.5), (cx + nr, ny - nr * 0.5), (cx, ny + nr * 0.7)], fill=nose)
    mw = rH * 0.2
    my = ny + nr * 0.3
    d.arc([cx - mw, my, cx, my + mw], 0, 130, fill=out, width=lw)
    d.arc([cx, my, cx + mw, my + mw], 50, 180, fill=out, width=lw)
    if t > 0.7:
        tw = rH * 0.13
        d.ellipse([cx - tw, my + mw * 0.3, cx + tw, my + mw * 0.3 + tw * 1.5], fill=(242, 138, 158))
    wl = lerp(0.11, 0.15, t) * S
    for sign in (-1, 1):
        wx = cx + sign * rH * 0.52
        for dyf in (-0.045, 0.0, 0.045):
            y0 = ny + dyf * S * 0.6
            d.line([(wx, y0), (wx + sign * wl, y0 + dyf * S * 0.45)], fill=out, width=max(1, int(lw * 0.55)))
    if t > 0.85:
        sx, sy = cx + rH * 0.92, hy - rH * 0.25
        d.polygon([(sx, sy), (sx - rH * 0.07, sy + rH * 0.13), (sx + rH * 0.07, sy + rH * 0.13)], fill=(120, 190, 232))
        d.ellipse([sx - rH * 0.07, sy + rH * 0.06, sx + rH * 0.07, sy + rH * 0.2], fill=(120, 190, 232))
    return img.resize((FINAL, FINAL), Image.LANCZOS)


# ------------------------------------------------------------------ derpy
def draw_derpy(t):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = S / 2
    LINE, GREY, GREY_D, PINK = (58, 54, 50), _h("#BFBCB4"), _h("#9C988F"), (236, 150, 165)
    col = ramp(t, _h("#D8EFC8"), _h("#F4E7C6"), _h("#F4C8BD"))
    lw = max(3, int(S * 0.014))
    rH = lerp(0.235, 0.225, t) * S
    bw = lerp(0.34, 0.86, t) * S
    bh = lerp(0.28, 0.58, t) * S
    ground = S - 0.085 * S
    body_top = ground - bh
    by_c = (body_top + ground) / 2
    bx0, bx1 = cx - bw / 2, cx + bw / 2
    tail_w = max(3, int(lerp(0.05, 0.072, t) * S))
    tb = [cx + bw * 0.16, by_c - bh * 0.5, cx + bw * 0.98, by_c + bh * 0.25]
    d.arc(tb, -35, 150, fill=LINE, width=tail_w + lw)
    d.arc(tb, -35, 150, fill=col, width=tail_w)
    cxb, cyb = (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2
    rxb, ryb = (tb[2] - tb[0]) / 2, (tb[3] - tb[1]) / 2
    ang = math.radians(-35)
    tipx, tipy = cxb + rxb * math.cos(ang), cyb + ryb * math.sin(ang)
    r = tail_w / 2 + lw / 2
    d.ellipse([tipx - r, tipy - r, tipx + r, tipy + r], fill=LINE)
    r = tail_w / 2
    d.ellipse([tipx - r, tipy - r, tipx + r, tipy + r], fill=GREY)
    d.ellipse([bx0, body_top, bx1, ground], fill=col, outline=LINE, width=lw)
    paw_r = lerp(0.055, 0.082, t) * S
    for sign in (-1, 1):
        px = cx + sign * bw * 0.24
        py = ground - paw_r * 0.5
        d.ellipse([px - paw_r, py - paw_r * 0.8, px + paw_r, py + paw_r * 0.8], fill=col, outline=LINE, width=lw)
    hy = body_top + rH * 0.16
    ear_w, ear_h = lerp(0.20, 0.16, t) * S, lerp(0.22, 0.18, t) * S
    ear_dx, ear_baseY = rH * 0.6, hy - rH * 0.68
    for sign in (-1, 1):
        ox = cx + sign * ear_dx
        apex = (ox + sign * ear_w * 0.12, ear_baseY - ear_h)
        fill = GREY if sign < 0 else col
        d.polygon([(ox - ear_w * 0.5, ear_baseY + ear_h * 0.18), apex,
                   (ox + ear_w * 0.5, ear_baseY + ear_h * 0.18)], fill=fill, outline=LINE)
        inner = GREY_D if sign < 0 else PINK
        d.polygon([(ox - ear_w * 0.22, ear_baseY + ear_h * 0.02),
                   (apex[0], apex[1] + ear_h * 0.4),
                   (ox + ear_w * 0.22, ear_baseY + ear_h * 0.02)], fill=inner)
    d.ellipse([cx - rH, hy - rH, cx + rH, hy + rH], fill=col, outline=LINE, width=lw)
    patch = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(patch).ellipse([cx - rH * 0.95, hy - rH * 0.95, cx + rH * 0.15, hy + rH * 0.1], fill=GREY + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([cx - rH + lw, hy - rH + lw, cx + rH - lw, hy + rH - lw], fill=255)
    patch.putalpha(ImageChops.multiply(patch.split()[3], mask))
    img.alpha_composite(patch)
    d = ImageDraw.Draw(img)
    op = lerp(0.92, 0.12, t)
    eye_w = lerp(0.05, 0.072, t) * S
    eye_h = eye_w * op
    eye_y = hy + rH * 0.12
    for sign in (-1, 1):
        ex = cx + sign * rH * 0.44
        d.ellipse([ex - eye_w, eye_y - eye_h, ex + eye_w, eye_y + eye_h], fill=LINE)
        if t > 0.4:
            lw2 = eye_w * 1.2
            lidy = eye_y - eye_h - eye_w * 0.25
            d.line([(ex - lw2, lidy + eye_w * 0.18), (ex, lidy), (ex + lw2, lidy + eye_w * 0.18)],
                   fill=LINE, width=max(2, int(lw * 0.7)), joint="curve")
        if t < 0.5:
            hlr = eye_w * 0.34
            d.ellipse([ex - eye_w * 0.2 - hlr, eye_y - eye_h * 0.4 - hlr,
                       ex - eye_w * 0.2 + hlr, eye_y - eye_h * 0.4 + hlr], fill=(255, 255, 255))
    ny = eye_y + eye_w * 1.5
    nr = rH * 0.07
    d.polygon([(cx - nr, ny - nr * 0.5), (cx + nr, ny - nr * 0.5), (cx, ny + nr * 0.7)], fill=(150, 110, 110))
    mw = rH * 0.16
    mh = mw * lerp(0.95, 0.35, t)
    my = ny + nr
    d.arc([cx - mw, my - mh, cx + mw, my + mh], 20, 160, fill=LINE, width=lw)
    wl = lerp(0.1, 0.14, t) * S
    for sign in (-1, 1):
        wx = cx + sign * rH * 0.5
        for dyf in (-0.04, 0.0, 0.04):
            y0 = ny + dyf * S * 0.6
            d.line([(wx, y0), (wx + sign * wl, y0 + dyf * S * 0.4)], fill=LINE, width=max(1, int(lw * 0.45)))
    if t > 0.85:
        sx, sy = cx + rH * 0.9, hy - rH * 0.2
        d.ellipse([sx - rH * 0.07, sy + rH * 0.04, sx + rH * 0.07, sy + rH * 0.2], fill=(120, 190, 232))
        d.polygon([(sx, sy), (sx - rH * 0.07, sy + rH * 0.12), (sx + rH * 0.07, sy + rH * 0.12)], fill=(120, 190, 232))
    return img.resize((FINAL, FINAL), Image.LANCZOS)


# 코드로 그리는 테마. cute(치비)->광기, derpy(멍냥)->경각심 으로 메뉴에 노출.
THEMES = {"madness": draw_cute, "derpy": draw_derpy}


def main():
    for theme, fn in THEMES.items():
        out = os.path.join(ROOT, theme)
        os.makedirs(out, exist_ok=True)
        frames = []
        for i in range(N):
            im = fn(i / (N - 1))
            im.save(os.path.join(out, f"cat_{i:02d}.png"))
            frames.append(im)
        prev = frames[::max(1, N // 6)][:6]
        pad = 8
        strip = Image.new("RGBA", (len(prev) * (FINAL + pad) + pad, FINAL + 2 * pad),
                          (235, 235, 235, 255))
        for i, im in enumerate(prev):
            strip.paste(im, (pad + i * (FINAL + pad), pad), im)
        strip.save(os.path.join(out, "_preview.png"))
        print(f"[{theme}] {N}프레임 + 미리보기 저장 -> {out}")


if __name__ == "__main__":
    main()
