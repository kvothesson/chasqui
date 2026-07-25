"""The chasqui icon, drawn in code.

No image files in the repo and no Pillow: a rounded terracotta tile with two
opposing arrows — the same ⇄ the window uses between the language pickers,
which is the whole product in one glyph. Everything here is stdlib (zlib and
struct), so the icon exists on any machine that can run chasqui.

Legibility at 16px drove the design. A running chasqui, a quipu, anything with
detail turns to mud at taskbar size; two thick arrows survive.

    write_ico(path)     → a real multi-size .ico for the taskbar and shortcuts
    tk_photo_image(tk)  → an in-memory image for root.iconphoto()
"""

import struct
import zlib
from pathlib import Path
from typing import Iterable, Optional

# The window's accent, so the icon and the app are visibly the same thing.
ACCENT = (226, 104, 61)
GLYPH = (255, 255, 255)

ICO_SIZES = (16, 32, 48, 64, 128, 256)

CORNER_RADIUS = 0.22          # fraction of the side

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
# and antialias into a pink smudge — the taskbar would show a blob. Below
# SMALL_SIZE the glyph gets its own fatter geometry: fewer, thicker strokes
# filling more of the tile, which is what survives at that scale.
SMALL_SIZE = 32
SMALL_ARROW_RIGHT = [
    (0.12, 0.22), (0.56, 0.22), (0.56, 0.12), (0.88, 0.31),
    (0.56, 0.50), (0.56, 0.40), (0.12, 0.40),
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


def _in_rounded_square(x: float, y: float, radius: float) -> bool:
    """Unit square with rounded corners, tested analytically."""
    cx = min(max(x, radius), 1.0 - radius)
    cy = min(max(y, radius), 1.0 - radius)
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy <= radius * radius


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
                    if not _in_rounded_square(x, y, CORNER_RADIUS):
                        continue
                    tile_hits += 1
                    for poly, (x0, y0, x1, y1) in polygons:
                        if x0 <= x <= x1 and y0 <= y <= y1 and _in_polygon(x, y, poly):
                            glyph_hits += 1
                            break

            if not tile_hits:
                out += b"\x00\x00\x00\x00"
                continue

            alpha = tile_hits / total
            glyph = glyph_hits / tile_hits
            out += bytes((
                round(ACCENT[0] + (GLYPH[0] - ACCENT[0]) * glyph),
                round(ACCENT[1] + (GLYPH[1] - ACCENT[1]) * glyph),
                round(ACCENT[2] + (GLYPH[2] - ACCENT[2]) * glyph),
                round(alpha * 255),
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


def ensure_ico(path: Optional[Path] = None) -> Optional[Path]:
    """Write the .ico if it isn't there yet. None if the disk says no —
    an icon is never worth failing a launch over."""
    path = Path(path) if path else DEFAULT_ICON_PATH
    try:
        if not path.exists() or path.stat().st_size == 0:
            write_ico(path)
        return path
    except Exception:
        return None
