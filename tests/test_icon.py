"""The generated icon.

Drawn in code rather than stored, so nothing here checks that it looks nice —
it checks that the bytes are a file Windows will actually accept, and that the
one thing which made the first attempt useless (a glyph that dissolves at
taskbar size) stays fixed.
"""

import struct

import pytest

from chasqui.ui.icon import (
    ICO_SIZES,
    SMALL_SIZE,
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
    """The first version reused one glyph everywhere and turned into a pink
    smudge in the taskbar: at 16px its shafts were under two pixels tall."""
    assert arrows_for(16) != arrows_for(64), (
        "Sizes below SMALL_SIZE need the fatter geometry. If this fails, the "
        "taskbar icon is a blob again — check arrows_for()."
    )
    assert arrows_for(SMALL_SIZE) == arrows_for(256)


def test_glyph_survives_at_16px():
    """Measure it rather than trust it: the middle column of the tile must
    contain both near-white glyph pixels and near-accent background."""
    size = 16
    rgba = render_rgba(size, samples=4)
    column = size // 2
    whites = darks = 0
    for y in range(size):
        r, g, b, a = rgba[(y * size + column) * 4: (y * size + column) * 4 + 4]
        if a > 200 and r > 235 and g > 235 and b > 235:
            whites += 1
        elif a > 200 and r > 150 and g < 160:
            darks += 1
    assert whites >= 2, (
        f"only {whites} clearly white pixels down the middle at 16px — the "
        "arrows have washed out into the background and the taskbar shows a "
        "blob. Thicken SMALL_ARROW_*."
    )
    assert darks >= 2, "the tile must still read as a coloured tile, not a white bar"


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
