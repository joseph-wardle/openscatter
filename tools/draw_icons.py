"""Draw OpenScatter's effect icons as BIP files in icons/.

    python tools/draw_icons.py

The icons are white shapes on a transparent background, drawn here from simple
geometry so OpenScatter owns them. They are dedicated to the public domain
under CC0 1.0 (https://creativecommons.org/publicdomain/zero/1.0/).

Each BIP file holds a 32x32 icon and a 500x500 image: b"BIP2", the image count,
then each image's width, height (u16) and data length (u32), big-endian, then
the zlib-compressed premultiplied RGBA pixels, bottom row first.
"""

import struct
import zlib
from pathlib import Path

import numpy as np

ICONS = Path(__file__).resolve().parent.parent / "icons"
SAMPLES = 4  # per pixel along each axis, for anti-aliasing


# Shapes take the sample coordinates x and y (0 to 1, y downwards) and return
# how much of each sample they cover, 0 or 1. Combine them with np.maximum.


def circle(x, y, cx, cy, r):
    return ((x - cx) ** 2 + (y - cy) ** 2 < r**2).astype(float)


def ring(x, y, cx, cy, r, width):
    d = np.hypot(x - cx, y - cy)
    return (abs(d - r) < width / 2).astype(float)


def rounded_rect(x, y, x0, y0, x1, y1, r):
    dx = np.maximum(np.maximum(x0 + r - x, x - (x1 - r)), 0)
    dy = np.maximum(np.maximum(y0 + r - y, y - (y1 - r)), 0)
    inside = (x > x0) & (x < x1) & (y > y0) & (y < y1)
    return (inside & (dx**2 + dy**2 < r**2)).astype(float)


def segment(x, y, ax, ay, bx, by, width):
    """A stroke from a to b with round ends."""
    px, py, vx, vy = x - ax, y - ay, bx - ax, by - ay
    t = np.clip((px * vx + py * vy) / (vx**2 + vy**2), 0, 1)
    return (np.hypot(px - t * vx, py - t * vy) < width / 2).astype(float)


def triangle(x, y, a, b, c):
    def side(p, q):
        return (q[0] - p[0]) * (y - p[1]) - (q[1] - p[1]) * (x - p[0])

    s1, s2, s3 = side(a, b), side(b, c), side(c, a)
    inside = ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))
    return inside.astype(float)


def arrowhead(x, y, tip, direction, length, width):
    """A triangle pointing in direction (degrees, 0 = right, 90 = down)."""
    a = np.radians(direction)
    ux, uy = np.cos(a), np.sin(a)
    bx, by = tip[0] - ux * length, tip[1] - uy * length
    nx, ny = -uy * width / 2, ux * width / 2
    return triangle(x, y, tip, (bx + nx, by + ny), (bx - nx, by - ny))


def sine(x, y, x0, x1, cy, amplitude, period, width):
    """A sine wave stroke from x0 to x1 with round ends."""
    xs = np.linspace(x0, x1, 120)
    ys = cy + amplitude * np.sin(2 * np.pi / period * (xs - x0))
    result = np.zeros_like(x)
    for i in range(len(xs) - 1):
        stroke = segment(x, y, xs[i], ys[i], xs[i + 1], ys[i + 1], width)
        result = np.maximum(result, stroke)
    return result


# The icons


def brick(x, y):
    rows = ((0.13, 0.33), (0.40, 0.60), (0.67, 0.87))
    joints = (
        ((0.08, 0.47), (0.53, 0.92)),
        ((0.08, 0.26), (0.32, 0.68), (0.74, 0.92)),
        ((0.08, 0.47), (0.53, 0.92)),
    )
    result = np.zeros_like(x)
    for (y0, y1), bricks in zip(rows, joints):
        for x0, x1 in bricks:
            result = np.maximum(result, rounded_rect(x, y, x0, y0, x1, y1, 0.035))
    return result


def gradient(x, y):
    outline = rounded_rect(x, y, 0.1, 0.1, 0.9, 0.9, 0.1) - rounded_rect(
        x, y, 0.17, 0.17, 0.83, 0.83, 0.04
    )
    fill = rounded_rect(x, y, 0.23, 0.23, 0.77, 0.77, 0.01)
    ramp = np.clip((0.77 - x) / 0.54, 0, 1) ** 1.2
    return np.maximum(outline, fill * ramp)


def look_at(x, y):
    target = np.maximum(ring(x, y, 0.6, 0.4, 0.22, 0.08), circle(x, y, 0.6, 0.4, 0.07))
    shaft = segment(x, y, 0.1, 0.9, 0.3, 0.7, 0.08)
    head = arrowhead(x, y, (0.38, 0.62), -45, 0.17, 0.2)
    return np.maximum(target, np.maximum(shaft, head))


def noise(x, y):
    dots = (
        (0.20, 0.18, 0.08), (0.52, 0.14, 0.05), (0.80, 0.24, 0.10),
        (0.36, 0.42, 0.11), (0.70, 0.52, 0.06), (0.14, 0.58, 0.05),
        (0.86, 0.80, 0.07), (0.50, 0.76, 0.08), (0.20, 0.86, 0.09),
    )
    result = np.zeros_like(x)
    for cx, cy, r in dots:
        result = np.maximum(result, circle(x, y, cx, cy, r))
    return result


def randomize_translation(x, y):
    result = circle(x, y, 0.5, 0.5, 0.09)
    for angle in (0, 90, 180, 270):
        a = np.radians(angle)
        ux, uy = np.cos(a), np.sin(a)
        stroke = segment(
            x, y, 0.5 + ux * 0.18, 0.5 + uy * 0.18, 0.5 + ux * 0.34, 0.5 + uy * 0.34, 0.08
        )
        head = arrowhead(x, y, (0.5 + ux * 0.46, 0.5 + uy * 0.46), angle, 0.15, 0.22)
        result = np.maximum(result, np.maximum(stroke, head))
    return result


def rotate(x, y):
    angle = np.degrees(np.arctan2(y - 0.5, x - 0.5)) % 360
    arc = ring(x, y, 0.5, 0.5, 0.31, 0.09) * ((angle < 280) | (angle > 330))
    tip = 0.5 + 0.31 * np.cos(np.radians(278)), 0.5 + 0.31 * np.sin(np.radians(278))
    head = arrowhead(x, y, (tip[0] + 0.1, tip[1]), 0, 0.2, 0.26)
    return np.maximum(arc, head)


def wave(x, y):
    result = np.zeros_like(x)
    for cy in (0.27, 0.5, 0.73):
        result = np.maximum(result, sine(x, y, 0.13, 0.87, cy, 0.06, 0.37, 0.075))
    return result


VORONOI_SEEDS = np.array([(0.36, 0.40), (0.66, 0.22), (0.30, 0.10), (0.84, 0.50),
                          (0.62, 0.62), (0.32, 0.78), (0.70, 0.94), (0.06, 0.60)])


def voronoi(x, y):
    """Voronoi cells inside a circle, with a gap along each cell border."""
    p = np.stack([x, y], -1)[..., None, :]
    d2 = ((p - VORONOI_SEEDS) ** 2).sum(-1)  # squared distance to each seed
    nearest = VORONOI_SEEDS[d2.argmin(-1)][..., None, :]
    separation = np.linalg.norm(VORONOI_SEEDS - nearest, axis=-1)
    border = (d2 - d2.min(-1)[..., None]) / (2 * np.where(separation == 0, 1, separation))
    border[separation == 0] = np.inf  # distance to the nearest cell border
    inside = (border.min(-1) > 0.035) & ((x - 0.5) ** 2 + (y - 0.5) ** 2 < 0.45**2)
    return inside.astype(float)


ICON_SHAPES = {
    "custom_brick": brick,
    "custom_gradient": gradient,
    "custom_look_at": look_at,
    "custom_noise": noise,
    "custom_randomize_translation": randomize_translation,
    "custom_rotate": rotate,
    "custom_voronoi": voronoi,
    "custom_wave": wave,
}


def pixels(shape, size: int) -> bytes:
    o = (np.arange(size * SAMPLES) + 0.5) / (size * SAMPLES)
    x, y = np.meshgrid(o, o)
    cover = np.clip(shape(x, y), 0, 1)
    alpha = cover.reshape(size, SAMPLES, size, SAMPLES).mean((1, 3))[::-1]
    a = np.round(alpha * 255).astype(np.uint8)
    return zlib.compress(np.repeat(a[..., None], 4, -1).tobytes())  # white, premultiplied


def bip(shape) -> bytes:
    icon, image = pixels(shape, 32), pixels(shape, 500)
    return (
        b"BIP2"
        + bytes([2])
        + struct.pack(">HHI", 32, 32, len(icon))
        + struct.pack(">HHI", 500, 500, len(image))
        + icon
        + image
    )


if __name__ == "__main__":
    for name, shape in ICON_SHAPES.items():
        ICONS.joinpath(name + ".bip").write_bytes(bip(shape))
        print("wrote", name)
