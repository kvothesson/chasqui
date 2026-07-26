"""The generated icon.

Drawn in code rather than stored, so nothing here checks that it looks nice —
it checks that the bytes are a file Windows will actually accept, and that the
one thing which made the first attempt useless (a glyph that dissolves at
taskbar size) stays fixed.
"""

import struct

import pytest

from chasqui.ui.icon import (
    ARROW_LEFT,
    ARROW_RIGHT,
    GLYPH,
    ICO_SIZES,
    SMALL_ARROW_LEFT,
    SMALL_ARROW_RIGHT,
    SMALL_SIZE,
    TILE,
    _in_hexagon,
    arrows_for,
    encode_ico,
    encode_png,
    render_rgba,
    write_ico,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_render_has_four_bytes_per_pixel():
    assert len(render_rgba(16)) == 16 * 16 * 4


def test_corners_are_transparent_and_centre_is_not():
    """A rounded tile: without transparent corners it shows as a square block
    on every desktop that composites it."""
    size = 32
    rgba = render_rgba(size)

    def alpha(x, y):
        return rgba[(y * size + x) * 4 + 3]

    assert alpha(0, 0) == 0, "top-left corner must be fully transparent"
    assert alpha(size - 1, size - 1) == 0, "bottom-right corner must be transparent"
    assert alpha(size // 2, size // 2) == 255, "the middle of the tile must be opaque"


def test_tile_is_a_hexagon_not_a_square():
    """The silhouette is the mark.

    Measured where the two shapes disagree: a hexagon is solid all the way out
    to the middle of its left edge, and empty a tenth of the way in from a
    corner where a rounded square is still solid.
    """
    size = 64
    rgba = render_rgba(size)

    def alpha(fx, fy):
        return rgba[(int(fy * size) * size + int(fx * size)) * 4 + 3]

    assert alpha(0.02, 0.50) > 200, "the left vertex must be solid — a hexagon is widest at its waist"
    assert alpha(0.50, 0.02) > 200, "the flat top edge must be solid"
    assert alpha(0.10, 0.10) == 0, (
        "a hexagon has no corner there. If that pixel is opaque the tile went "
        "back to being a rounded square — check _in_hexagon()."
    )


def test_arrows_stay_inside_the_hexagon():
    """Every arrow vertex, both geometries.

    On the old square tile the arrows had corners to grow into; on a hexagon a
    vertex that overhangs is sliced off flat by the tile edge, and a beheaded
    arrow stops reading as a direction. The 16px pair is the one at risk — it
    is the widest, at the height where the hexagon is still narrowing.
    """
    for arrow in (ARROW_RIGHT, ARROW_LEFT, SMALL_ARROW_RIGHT, SMALL_ARROW_LEFT):
        for x, y in arrow:
            assert _in_hexagon(x, y), (
                f"vertex ({x}, {y}) falls outside the tile and will be clipped"
            )


def test_png_is_a_png():
    blob = encode_png(16, render_rgba(16))
    assert blob.startswith(PNG_MAGIC)
    assert blob.endswith(b"IEND\xaeB`\x82")
    width, height, depth, colour = struct.unpack(">IIBB", blob[16:26])
    assert (width, height, depth, colour) == (16, 16, 8, 6), "8-bit RGBA, 16x16"


def test_ico_header_and_entries_line_up():
    """A malformed .ico does not error — it silently shows no icon at all."""
    blob = encode_ico((16, 32))
    reserved, kind, count = struct.unpack("<HHH", blob[:6])
    assert (reserved, kind, count) == (0, 1, 2), "reserved 0, type 1 (icon), 2 images"

    for index in range(count):
        entry = blob[6 + index * 16: 6 + (index + 1) * 16]
        width, height, colours, _res, planes, bpp, length, offset = struct.unpack(
            "<BBBBHHII", entry)
        assert (colours, planes, bpp) == (0, 1, 32)
        assert blob[offset:offset + 8] == PNG_MAGIC, (
            "each entry must point at its PNG payload — a wrong offset is an "
            "icon that never renders."
        )
        assert len(blob) >= offset + length


def test_256_is_encoded_as_zero():
    """The ICO format stores 256 in a single byte as 0. Writing 256 truncates
    to 0 anyway, but only by accident — be explicit."""
    blob = encode_ico((256,))
    width, height = struct.unpack("<BB", blob[6:8])
    assert (width, height) == (0, 0)


def test_small_sizes_get_their_own_geometry():
    """The first version reused one glyph everywhere and turned into a smudge
    in the taskbar: at 16px its shafts were under two pixels tall."""
    assert arrows_for(16) != arrows_for(64), (
        "Sizes below SMALL_SIZE need the fatter geometry. If this fails, the "
        "taskbar icon is a blob again — check arrows_for()."
    )
    assert arrows_for(SMALL_SIZE) == arrows_for(256)


def _near(pixel, colour, tolerance=45):
    return all(abs(pixel[i] - colour[i]) <= tolerance for i in range(3))


def test_glyph_survives_at_16px():
    """Measure it rather than trust it.

    16px is where an icon quietly stops working: down the middle of the tile
    there must be dark glyph pixels AND ice tile left around them. The first
    version failed exactly here — its arrows antialiased into a smudge at the
    one size the taskbar actually uses.
    """
    size = 16
    rgba = render_rgba(size, samples=4)
    column = size // 2
    glyph = tile = 0
    for y in range(size):
        start = (y * size + column) * 4
        pixel = rgba[start:start + 4]
        if pixel[3] < 200:
            continue
        if _near(pixel, GLYPH):
            glyph += 1
        elif _near(pixel, TILE):
            tile += 1

    assert glyph >= 2, (
        f"only {glyph} arrow pixels down the middle at 16px — the glyph "
        "washed out and the taskbar shows a blob. Thicken SMALL_ARROW_* or "
        "raise the contrast against TILE."
    )
    assert tile >= 2, (
        "no tile colour left between the arrows — they merged into one block "
        "and stopped reading as two directions."
    )


def _relative_luminance(colour):
    channels = []
    for value in colour:
        value /= 255
        channels.append(value / 12.92 if value <= 0.03928
                        else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first, second) -> float:
    high, low = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_arrows_meet_the_contrast_floor_against_the_tile():
    """The arrows are cut out of the tile, so their legibility is entirely a
    contrast question — and at 16px there is no detail left to compensate.

    3:1 is WCAG's floor for a graphical object. White arrows on this ice
    measure 2.0:1 and turn to mush in the taskbar; that is why they are not
    white, however nice they look at 256px.
    """
    ratio = contrast_ratio(TILE, GLYPH)
    assert ratio >= 3.0, (
        f"arrows on tile measure {ratio:.1f}:1, under the 3:1 floor for a "
        "graphical object. Whatever it looks like at 256px, it will be a "
        "coloured smudge at the size the taskbar uses."
    )


def test_tile_separates_from_a_dark_taskbar():
    """A tile as dark as the taskbar has no silhouette: the arrows float and
    the icon disappears. Checked against Windows' near-black #1c1c1c."""
    taskbar = 0x1C
    distance = sum(abs(channel - taskbar) for channel in TILE)
    assert distance > 60, (
        f"TILE {TILE} is too close to a dark taskbar background — the icon "
        "loses its outline there. Lighten it or give it a border."
    )


def test_stale_icon_is_rewritten_when_the_art_changes(tmp_path):
    """The cached .ico lives at a fixed path so shortcuts keep working — which
    means a redesign has to invalidate it explicitly, or every existing user
    keeps the old icon forever."""
    from chasqui.ui.icon import ICON_VERSION, _version_marker, ensure_ico

    target = tmp_path / "chasqui.ico"
    ensure_ico(target)
    marker = _version_marker(target)
    assert marker.read_text(encoding="utf-8").strip() == str(ICON_VERSION)

    target.write_bytes(b"stale")
    marker.write_text("1", encoding="utf-8")
    ensure_ico(target)

    assert target.read_bytes() != b"stale", (
        "An icon cached under an older version must be regenerated. If this "
        "fails, bumping ICON_VERSION does nothing and the redesign never "
        "reaches anyone who already ran chasqui."
    )


def test_ensure_ico_leaves_a_current_icon_alone(tmp_path):
    from chasqui.ui.icon import ensure_ico

    target = tmp_path / "chasqui.ico"
    ensure_ico(target)
    stamp = target.stat().st_mtime_ns
    ensure_ico(target)
    assert target.stat().st_mtime_ns == stamp, (
        "Rewriting the icon on every launch is wasted work at startup."
    )


def test_write_ico_creates_parent_directories(tmp_path):
    target = tmp_path / "nested" / "deeper" / "chasqui.ico"
    write_ico(target, sizes=(16,))
    assert target.exists() and target.stat().st_size > 0


def test_default_sizes_cover_taskbar_and_desktop():
    assert 16 in ICO_SIZES and 32 in ICO_SIZES and 256 in ICO_SIZES, (
        "16 and 32 are the taskbar; 256 is what large desktop icons and the "
        "Windows file dialog scale from."
    )


@pytest.mark.parametrize("size", [16, 32, 256])
def test_every_size_renders_without_error(size):
    assert len(render_rgba(size, samples=2)) == size * size * 4
