#!/usr/bin/env python3
"""make-logo.py — renders the UnBubble logo animation.

A soap bubble grows, wobbles and pops, revealing the cube (the app) that was trapped
inside it — the project set free from Bubble. Output:

  public/brand/unbubble.gif   animated logo (128 px, loops; long hold on the cube)
  public/brand/unbubble.png   static last frame (prefers-reduced-motion fallback)
  src/app/icon.png            favicon (64 px)

Frames are drawn 4x oversampled with Pillow and downscaled, so edges are anti-aliased.

Usage:  python3 scripts/make-logo.py [--size 128] [--fps 25] [--sheet]
Needs:  Pillow (pip install pillow)
"""
from __future__ import annotations

import argparse
import colorsys
import math
import os
import random
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)

SS = 4  # supersampling factor

# Palette — the cube faces echo the pipeline stage colors used across the console:
# orange (audit) on top, purple (level-up) on the left, blue (clone) on the right.
BG = (24, 24, 27)          # zinc-900 tile — reads the same on both themes
BG_CENTER = (39, 39, 46)   # subtle vignette center
CUBE_TOP = (251, 146, 60)   # orange-400
CUBE_LEFT = (124, 58, 237)  # violet-600
CUBE_RIGHT = (37, 99, 235)  # blue-600
CUBE_EDGE = (250, 250, 250)  # near-white edges, drawn at ~50% alpha
GLOW = (129, 140, 248)     # indigo-400, sits between the purple and the blue
LETTER_TOP = (67, 20, 7)        # orange-950, dark on the bright top face
LETTER_SIDE = (245, 243, 255)   # near-white on the purple and blue faces
FACE_LETTERS = {"top": "u", "left": "n", "right": "b"}  # u·n·b — UnBubble
LETTER_SRC = 256  # px of the flat letter square that gets projected onto each face

# Bold rounded fonts first (they match the bubble); Pillow's bundled Aileron is the last resort.
FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
    ("/System/Library/Fonts/Helvetica.ttc", 1),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
    ("C:/Windows/Fonts/arialbd.ttf", 0),
]

# ------------------------------------------------------------------ easing


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def ease_out_cubic(x: float) -> float:
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_in_out_sine(x: float) -> float:
    x = clamp(x)
    return -(math.cos(math.pi * x) - 1) / 2


def ease_out_back(x: float) -> float:
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# ------------------------------------------------------------------ timeline (seconds)
T_GROW_END = 1.4
T_POP = 2.0
T_POP_END = 2.3
T_SETTLE_END = 3.0
HOLD_MS = 4500
T_FADE = 0.32  # cube fade-out before the loop restarts


# ------------------------------------------------------------------ drawing helpers


def radial_alpha_layer(size: int, cx: float, cy: float, radius: float, color, a_center: float, a_edge: float, power: float = 1.0) -> Image.Image:
    """RGBA layer with a radial alpha gradient (a_center at the middle → a_edge at `radius`).
    `power` > 1 pushes the transition toward the edge (Fresnel-like rim)."""
    grad = Image.radial_gradient("L").resize((int(radius * 2) or 1, int(radius * 2) or 1), Image.BILINEAR)
    # radial_gradient goes 0 (center) → 255 (edge); map to a_center..a_edge
    lut = [int(255 * clamp(lerp(a_center, a_edge, (v / 255) ** power))) for v in range(256)]
    alpha = grad.point(lut)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    solid = Image.new("RGBA", alpha.size, color + (255,))
    solid.putalpha(alpha)
    layer.paste(solid, (int(cx - radius), int(cy - radius)), solid)
    return layer


def hsv(h: float, s: float, v: float):
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def draw_bubble(size: int, cx: float, cy: float, rx: float, ry: float, hue_phase: float, alpha: float, gaps: float = 0.0) -> Image.Image:
    """Soap bubble: iridescent rim, Fresnel fill, two speculars. `gaps` in 0..1 breaks the rim."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if rx < 1 or ry < 1 or alpha <= 0:
        return layer
    d = ImageDraw.Draw(layer)
    bbox = [cx - rx, cy - ry, cx + rx, cy + ry]

    # Fresnel fill: transparent center → faint cyan-white rim
    fill = radial_alpha_layer(size, cx, cy, max(rx, ry), (223, 246, 255), 0.0, 0.26 * alpha, power=3.0)
    # squash the round fill to the ellipse shape by resizing horizontally/vertically
    if abs(rx - ry) > 0.5:
        r = max(rx, ry)
        crop = fill.crop((int(cx - r), int(cy - r), int(cx + r), int(cy + r)))
        crop = crop.resize((max(1, int(rx * 2)), max(1, int(ry * 2))), Image.LANCZOS)
        fill = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        fill.paste(crop, (int(cx - rx), int(cy - ry)), crop)
    layer = Image.alpha_composite(layer, fill)
    d = ImageDraw.Draw(layer)

    # Iridescent rim: many short arcs whose hue rotates around the circle
    w = max(2.0 * SS, min(rx, ry) * 0.075)
    step = 6
    rng = random.Random(int(gaps * 1000))
    for a in range(0, 360, step):
        if gaps > 0 and rng.random() < gaps:
            continue  # shattered segment
        col = hsv(hue_phase + a * 1.0, 0.55, 1.0)
        d.arc(bbox, a, a + step + 1, fill=col + (int(235 * alpha),), width=int(w))
    # soft inner ring for volume
    wi = min(w, min(rx, ry) * 0.4)
    inner = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    di = ImageDraw.Draw(inner)
    di.ellipse([cx - rx + wi, cy - ry + wi, cx + rx - wi, cy + ry - wi], outline=(255, 255, 255, int(70 * alpha)), width=max(1, int(wi * 1.6)))
    inner = inner.filter(ImageFilter.GaussianBlur(w * 0.9))
    layer = Image.alpha_composite(layer, inner)

    # Speculars: a long one top-left, a short one bottom-right
    spec = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ds = ImageDraw.Draw(spec)
    inset = min(w * 1.9, min(rx, ry) * 0.5)
    sb = [cx - rx + inset, cy - ry + inset, cx + rx - inset, cy + ry - inset]
    if sb[2] - sb[0] > 2 and sb[3] - sb[1] > 2:
        ds.arc(sb, 196, 242, fill=(255, 255, 255, int(230 * alpha)), width=max(1, int(w * 1.7)))
        ds.arc(sb, 14, 34, fill=(255, 255, 255, int(150 * alpha)), width=max(1, int(w * 1.1)))
    spec = spec.filter(ImageFilter.GaussianBlur(w * 0.45))
    layer = Image.alpha_composite(layer, spec)
    return layer


_font_cache: dict[int, ImageFont.FreeTypeFont] = {}
_letter_cache: dict[tuple, Image.Image] = {}


def load_font(px: int) -> ImageFont.FreeTypeFont:
    if px in _font_cache:
        return _font_cache[px]
    font = None
    for path, index in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, px, index=index)
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default(size=px)
    _font_cache[px] = font
    return font


def letter_square(ch: str, color) -> Image.Image:
    """The letter drawn flat on a square; the square is later warped onto a cube face."""
    key = (ch, color)
    if key in _letter_cache:
        return _letter_cache[key]
    L = LETTER_SRC
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = load_font(int(L * 0.8))
    # anchor "ms": horizontally centered, baseline at 71% of the face so x-height letters sit
    # in the middle and the ascender of "b" still fits.
    d.text((L / 2, L * 0.71), ch, font=font, fill=color + (255,), anchor="ms")
    _letter_cache[key] = img
    return img


def paste_face_letter(layer: Image.Image, ch: str, color, p0, x_vec, y_vec, alpha: float) -> Image.Image:
    """Warp the flat letter square onto the parallelogram p0 + u*x_vec + v*y_vec (u, v in 0..1).

    Pillow's AFFINE transform maps output pixels back to source pixels, so the coefficients are
    the inverse of that parallelogram mapping.
    """
    src = letter_square(ch, color)
    L = LETTER_SRC
    det = x_vec[0] * y_vec[1] - y_vec[0] * x_vec[1]
    if abs(det) < 1e-6:
        return layer
    a = L * y_vec[1] / det
    b = -L * y_vec[0] / det
    c = -(a * p0[0] + b * p0[1])
    d = -L * x_vec[1] / det
    e = L * x_vec[0] / det
    f = -(d * p0[0] + e * p0[1])
    warped = src.transform(layer.size, Image.AFFINE, (a, b, c, d, e, f), resample=Image.BICUBIC)
    if alpha < 1:
        warped.putalpha(warped.getchannel("A").point(lambda v: int(v * alpha)))
    return Image.alpha_composite(layer, warped)


def draw_cube(size: int, cx: float, cy: float, s: float, alpha: float, blur: float = 0.0) -> Image.Image:
    """Isometric cube with edge length ~s (total height 2s)."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if s < 1 or alpha <= 0:
        return layer
    d = ImageDraw.Draw(layer)
    k = math.cos(math.radians(30))
    top = [(cx, cy - s), (cx + s * k, cy - s / 2), (cx, cy), (cx - s * k, cy - s / 2)]
    left = [(cx - s * k, cy - s / 2), (cx, cy), (cx, cy + s), (cx - s * k, cy + s / 2)]
    right = [(cx + s * k, cy - s / 2), (cx, cy), (cx, cy + s), (cx + s * k, cy + s / 2)]
    a = int(255 * alpha)
    d.polygon(top, fill=CUBE_TOP + (a,))
    d.polygon(left, fill=CUBE_LEFT + (a,))
    d.polygon(right, fill=CUBE_RIGHT + (a,))
    # Letters lie flat on each face. Top: baseline along the front-right edge, "up" toward the
    # back-left corner. Sides: baseline along the face's top edge, verticals stay vertical.
    L_pt = (cx - s * k, cy - s / 2)  # left vertex of the top rhombus
    B_pt = (cx, cy)                  # front (bottom) vertex of the top rhombus
    layer = paste_face_letter(layer, FACE_LETTERS["top"], LETTER_TOP, L_pt, (s * k, -s / 2), (s * k, s / 2), alpha)
    layer = paste_face_letter(layer, FACE_LETTERS["left"], LETTER_SIDE, L_pt, (s * k, s / 2), (0, s), alpha)
    layer = paste_face_letter(layer, FACE_LETTERS["right"], LETTER_SIDE, B_pt, (s * k, -s / 2), (0, s), alpha)
    d = ImageDraw.Draw(layer)
    ew = max(1, int(s * 0.05))
    for poly in (top, left, right):
        d.line(poly + [poly[0]], fill=CUBE_EDGE + (int(a * 0.55),), width=ew, joint="curve")
    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return layer


def draw_droplets(size: int, cx: float, cy: float, R: float, p: float, hue_phase: float, alpha: float) -> Image.Image:
    """Burst droplets flying outward from the rim; p in 0..1 is the burst progress."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = random.Random(7)
    n = 14
    for i in range(n):
        ang = math.radians(i * 360 / n + rng.uniform(-10, 10))
        speed = rng.uniform(0.35, 0.75) * R
        dist = R + speed * ease_out_cubic(p)
        r = max(1.0, R * rng.uniform(0.045, 0.085) * (1 - p * 0.8))
        x, y = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist
        col = hsv(hue_phase + i * 27, 0.5, 1.0)
        d.ellipse([x - r, y - r, x + r, y + r], fill=col + (int(255 * alpha * (1 - p)),))
    return layer


# ------------------------------------------------------------------ frame renderer


def render_frame(t: float, out_size: int, bg_layer: Image.Image) -> Image.Image:
    size = out_size * SS
    cx = cy = size / 2
    # The cube's corners all sit at distance S_CUBE from the center, so it fits inside the
    # bubble as long as S_CUBE < R (minus the rim). 0.32 → the cube spans ~64% of the tile height.
    R = size * 0.41
    S_CUBE = size * 0.32
    img = bg_layer.copy()

    # ---- bubble geometry
    if t < T_GROW_END:
        g = ease_out_cubic(t / T_GROW_END)
    else:
        g = 1.0
    wobble_amp = 0.05 * clamp((t - 0.3) / 0.6) * (1.0 if t < T_POP else 0.0)
    wob = math.sin(2 * math.pi * 1.7 * t)
    rx = R * g * (1 + wobble_amp * wob)
    ry = R * g * (1 - wobble_amp * wob)
    hue_phase = t * 140.0

    bubble_alpha = 1.0
    gaps = 0.0
    if t >= T_POP:
        p = clamp((t - T_POP) / (T_POP_END - T_POP))
        grow = 1 + 0.35 * ease_out_cubic(p)
        rx, ry = R * grow, R * grow
        bubble_alpha = 1 - ease_out_cubic(p)
        gaps = ease_out_cubic(p) * 0.9

    # ---- cube geometry (inside the bubble while it grows, revealed at the pop)
    if t < T_POP:
        cube_scale = g
        cube_alpha = 0.34 * clamp((g - 0.15) / 0.5)
        cube_blur = 1.6 * SS
        glow_a = 0.0
    else:
        p = clamp((t - T_POP) / 0.45)
        cube_scale = lerp(1.0, 1.0, p) * (1 + 0.14 * math.sin(math.pi * ease_out_back(p)) if p < 1 else 1.0)
        cube_scale = 1.0 + 0.14 * math.sin(math.pi * clamp(p)) * (1 - 0.3 * p)
        cube_alpha = lerp(0.34, 1.0, clamp((t - T_POP) / 0.18))
        cube_blur = 1.6 * SS * (1 - clamp((t - T_POP) / 0.18))
        glow_a = 0.55 * ease_in_out_sine(clamp((t - T_POP) / 0.6))
        glow_a = lerp(glow_a, 0.34, clamp((t - T_POP - 0.6) / (T_SETTLE_END - T_POP - 0.6)))

    # ---- loop tail: cube fades out so the restart is not a hard cut
    fade = 1.0
    if t >= T_SETTLE_END:
        fade = 1 - ease_in_out_sine(clamp((t - T_SETTLE_END) / T_FADE))
        cube_alpha *= fade
        glow_a *= fade
        cube_scale *= lerp(1.0, 0.6, 1 - fade)

    # ---- compose
    if glow_a > 0:
        img = Image.alpha_composite(img, radial_alpha_layer(size, cx, cy, S_CUBE * 2.2, GLOW, glow_a, 0.0))
    if cube_alpha > 0:
        img = Image.alpha_composite(img, draw_cube(size, cx, cy, S_CUBE * cube_scale, cube_alpha, cube_blur))
    if bubble_alpha > 0 and t < T_POP_END + 0.05:
        img = Image.alpha_composite(img, draw_bubble(size, cx, cy, rx, ry, hue_phase, bubble_alpha, gaps))
    if T_POP <= t < T_POP_END + 0.15:
        p = clamp((t - T_POP) / (T_POP_END + 0.15 - T_POP))
        img = Image.alpha_composite(img, draw_droplets(size, cx, cy, R, p, hue_phase, 1.0))
        # quick flash
        fa = 0.45 * (1 - clamp((t - T_POP) / 0.16))
        if fa > 0:
            img = Image.alpha_composite(img, radial_alpha_layer(size, cx, cy, R * 1.5, (255, 255, 255), fa, 0.0))

    return img.resize((out_size, out_size), Image.LANCZOS)


def make_background(out_size: int) -> Image.Image:
    size = out_size * SS
    bg = Image.new("RGBA", (size, size), BG + (255,))
    bg = Image.alpha_composite(bg, radial_alpha_layer(size, size / 2, size / 2, size * 0.75, BG_CENTER, 1.0, 0.0))
    return bg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--sheet", action="store_true", help="also write a contact sheet of key frames for review")
    ap.add_argument("--out", default=os.path.join(UI, "public", "brand"))
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    dt = 1.0 / args.fps
    bg = make_background(args.size)

    frames: list[Image.Image] = []
    durations: list[int] = []
    t = 0.0
    # motion until the settle point
    while t < T_SETTLE_END - 1e-9:
        frames.append(render_frame(t, args.size, bg))
        durations.append(int(round(dt * 1000)))
        t += dt
    # the hold: one long frame
    hold = render_frame(T_SETTLE_END, args.size, bg)
    frames.append(hold)
    durations.append(HOLD_MS)
    # fade-out tail
    t = T_SETTLE_END + dt
    while t <= T_SETTLE_END + T_FADE + 1e-9:
        frames.append(render_frame(t, args.size, bg))
        durations.append(int(round(dt * 1000)))
        t += dt

    # global palette built from a spread of frames, so colors do not flicker between frames
    sample = Image.new("RGB", (args.size, args.size * 8))
    for i, idx in enumerate([0, len(frames) // 6, len(frames) // 3, len(frames) // 2, int(len(frames) * 0.62), int(len(frames) * 0.7), len(frames) - 10, len(frames) - 1]):
        sample.paste(frames[idx].convert("RGB"), (0, i * args.size))
    palette = sample.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    pframes = [f.convert("RGB").quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG) for f in frames]

    gif_path = os.path.join(args.out, "unbubble.gif")
    pframes[0].save(gif_path, save_all=True, append_images=pframes[1:], duration=durations, loop=0, optimize=True, disposal=1)
    hold.convert("RGB").save(os.path.join(args.out, "unbubble.png"), optimize=True)
    icon = render_frame(T_SETTLE_END, 64, make_background(64)).convert("RGB")
    icon.save(os.path.join(UI, "src", "app", "icon.png"), optimize=True)

    print(f"frames: {len(frames)}  gif: {os.path.getsize(gif_path) / 1024:.0f} KB  →  {gif_path}")
    if args.sheet:
        keys = [0.0, 0.3, 0.7, 1.1, 1.6, 2.0, 2.08, 2.16, 2.26, 2.45, 2.7, 3.0]
        big = 160
        sheet = Image.new("RGB", (big * 6, big * 2), (255, 255, 255))
        bgb = make_background(big)
        for i, tt in enumerate(keys):
            sheet.paste(render_frame(tt, big, bgb).convert("RGB"), ((i % 6) * big, (i // 6) * big))
        sp = os.path.join(tempfile.gettempdir(), "unbubble-logo-sheet.png")
        sheet.save(sp)
        print("sheet:", sp)


if __name__ == "__main__":
    main()
