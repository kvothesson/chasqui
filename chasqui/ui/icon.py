"""The chasqui icon, drawn in code.

No image files in the repo and no Pillow: an ice-blue hexagon with two opposing
arrows cut out of it — the same ⇄ the window uses between the language pickers.
Everything here is stdlib (zlib and struct), so the icon exists on any machine
that can run chasqui.

A hexagon rather than the rounded square it started as: it is the shape the
window's status indicator uses, so icon and app read as one object, and it is
the one silhouette in a taskbar full of rounded squares that is recognisable
without being read.

Legibility at 16px drove the design. A running chasqui, a quipu, anything with
detail turns to mud at taskbar size; two thick arrows survive.

    write_ico(path)     → a real multi-size .ico for the taskbar and shortcuts
    tk_photo_image(tk)  → an in-memory image for root.iconphoto()
"""

import struct
import zlib
from pathlib import Path
from typing import Iterable, Optional

# Ice on night. The tile carries the colour and the arrows are cut out of it:
# a filled tile keeps its silhouette against the near-black Windows taskbar,
# where a dark tile dissolves and leaves the arrows floating with no icon
# around them (checked against #1c1c1c, not guessed).
#
# Same ice as the window's accent, so the icon and the app read as one thing.
TILE = (94, 197, 226)     # ice — the same #5ec5e2 as C_ACCENT in app.py
# Deep blue-green rather than black: near-black on cyan reads as a sticker
# stamped on the tile, this belongs to the same family. It is also the floor
# — white arrows on ice measure 2:1, well under the 3:1 a graphical object
# needs, and turn to mush at 16px. Measured, not eyeballed (see tests).
GLYPH = (23, 57, 74)      # navy

ICO_SIZES = (16, 32, 48, 64, 128, 256)

# Flat-top hexagon in the unit square: vertices left and right, flat edges top
# and bottom. Flat-top and not pointy-top because the arrows run horizontally —
# a pointy-top hexagon is narrowest exactly where they need to be widest, and
# the arrowheads got clipped.
#
# Half-width at height y, which is what the glyph has to stay inside:
#   y <= 0.5 → 0.25 + 0.5 * y        (widening from the flat top)
#   y >  0.5 → 0.25 + 0.5 * (1 - y)  (narrowing back to the flat bottom)
HEX_TOP_HALF = 0.25           # half-width of the flat top and bottom edges

# Arrows in a 0..1 square. Right-pointing on top, left-pointing below —
# deliberately fat: at 16px a thin shaft disappears into the background.
# The 0.30 offset leaves a clear gap between them; overlapping shafts merge
# into one blob at small sizes and stop reading as two directions.
ARROW_RIGHT = [
    (0.18, 0.30), (0.58, 0.30), (0.58, 0.24), (0.82, 0.35),
    (0.58, 0.46), (0.58, 0.40), (0.18, 0.40),
]
ARROW_LEFT = [(1.0 - x, y + 0.30) for x, y in ARROW_RIGHT]

# Hinting, the old-fashioned way. At 16px the shafts above are 1.6 pixels tall
# and antialias into a smudge — the taskbar would show a blob. Below
# SMALL_SIZE the glyph gets its own fatter geometry: fewer, thicker strokes
# filling more of the tile, which is what survives at that scale.
#
# These are also pulled in from the square version's 0.12/0.88: on a hexagon
# the corners are not there to grow into, and a shaft end that overhangs the
# edge gets sliced flat instead of tapering — which looks like a rendering bug,
# not a design. The shaft ends sit 0.01 inside the hexagon edge at the height
# they start (x 0.15 where the half-width is 0.36), which is as wide as they go
# without touching it.
SMALL_SIZE = 32
SMALL_ARROW_RIGHT = [
    (0.15, 0.22), (0.58, 0.22), (0.58, 0.13), (0.86, 0.31),
    (0.58, 0.49), (0.58, 0.40), (0.15, 0.40),
]
SMALL_ARROW_LEFT = [(1.0 - x, y + 0.38) for x, y in SMALL_ARROW_RIGHT]


def arrows_for(size: int) -> list[list[tuple[float, float]]]:
    if size < SMALL_SIZE:
        return [SMALL_ARROW_RIGHT, SMALL_ARROW_LEFT]
    return [ARROW_RIGHT, ARROW_LEFT]


def _in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray casting. Polygons here are small and convex-ish; no need for more."""
    inside = False
    count = len(polygon)
    j = count - 1
    for i in range(count):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def _bounds(polygon: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _in_hexagon(x: float, y: float) -> bool:
    """Flat-top hexagon filling the unit square, tested analytically.

    One comparison against the half-width at this height — cheaper than a
    polygon test, and it is the same formula the arrow geometry was fitted to,
    so the two can't drift apart.
    """
    half = HEX_TOP_HALF + 0.5 * (y if y <= 0.5 else 1.0 - y)
    return abs(x - 0.5) <= half


def render_rgba(size: int, samples: int = 3) -> bytes:
    """Rasterize the icon to raw RGBA rows, supersampled for smooth edges."""
    polygons = [(poly, _bounds(poly)) for poly in arrows_for(size)]
    total = samples * samples
    step = 1.0 / (size * samples)
    out = bytearray()

    for py in range(size):
        for px in range(size):
            tile_hits = 0
            glyph_hits = 0
            for sy in range(samples):
                y = (py * samples + sy + 0.5) * step
                for sx in range(samples):
                    x = (px * samples + sx + 0.5) * step
                    if not _in_hexagon(x, y):
                        continue
                    tile_hits += 1
                    for poly, (x0, y0, x1, y1) in polygons:
                        if x0 <= x <= x1 and y0 <= y <= y1 and _in_polygon(x, y, poly):
                            glyph_hits += 1
                            break

            if not tile_hits:
                out += b"\x00\x00\x00\x00"
                continue

            glyph = glyph_hits / tile_hits
            out += bytes((
                round(TILE[0] + (GLYPH[0] - TILE[0]) * glyph),
                round(TILE[1] + (GLYPH[1] - TILE[1]) * glyph),
                round(TILE[2] + (GLYPH[2] - TILE[2]) * glyph),
                round(tile_hits / total * 255),
            ))
    return bytes(out)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def encode_png(size: int, rgba: bytes) -> bytes:
    """Minimal RGBA PNG — filter type 0 on every row."""
    stride = size * 4
    raw = b"".join(
        b"\x00" + rgba[row * stride:(row + 1) * stride] for row in range(size)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def encode_ico(sizes: Iterable[int] = ICO_SIZES) -> bytes:
    """A PNG-compressed .ico. Windows has read this form since Vista, and it
    keeps a 256px entry from bloating the file to a megabyte."""
    images = [(size, encode_png(size, render_rgba(size))) for size in sorted(sizes)]

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)

    directory = b""
    for size, blob in images:
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,   # 0 means 256 in the ICO format
            0 if size >= 256 else size,
            0, 0, 1, 32, len(blob), offset,
        )
        offset += len(blob)

    return header + directory + b"".join(blob for _size, blob in images)


def write_ico(path: Path, sizes: Iterable[int] = ICO_SIZES) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_ico(sizes))
    return path


def tk_photo_image(tk_module, size: int = 64):
    """A PhotoImage for root.iconphoto() — no temp file involved."""
    import base64
    data = base64.b64encode(encode_png(size, render_rgba(size)))
    return tk_module.PhotoImage(data=data)


# Cached next to the config so a desktop shortcut has a stable path to point at.
DEFAULT_ICON_PATH = Path.home() / ".chasqui" / "chasqui.ico"

# Bump whenever the artwork changes. The path stays the same so existing
# desktop shortcuts keep working — without this marker the first cached file
# would outlive every redesign, and users would keep the old icon forever.
ICON_VERSION = 5


def _version_marker(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".version")


def ensure_ico(path: Optional[Path] = None) -> Optional[Path]:
    """Write the .ico if it's missing or stale. None if the disk says no —
    an icon is never worth failing a launch over."""
    path = Path(path) if path else DEFAULT_ICON_PATH
    marker = _version_marker(path)
    try:
        current = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
        if not path.exists() or path.stat().st_size == 0 or current != str(ICON_VERSION):
            write_ico(path)
            marker.write_text(str(ICON_VERSION), encoding="utf-8")
        return path
    except Exception:
        return None
