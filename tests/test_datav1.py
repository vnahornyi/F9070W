"""Pins down the current DATAV1.0 behaviour: sprite parsing, stride, the
pixels/pack pair and the byte-identical rebuild.

Nothing here is allowed to change without a matching note in docs/findings.md -
these are the assertions that prove a theme build touches only what it means to.
The golden fixtures cover depths 2 and 3 and both record-header sizes; depth 4
lives only in screens too large to commit, so it is asserted under
@pytest.mark.stock.
"""
import hashlib
import io
import os
import struct

import pytest

from formats import datav1
from tools import unpack

GOLDEN_NAMES = ['black.data', 'wallpaper.data', 'tipbox.data',
                'volumebar.data', 'setupversion.data', 'setuplogo.data']


def all_stock_screens(stock):
    for name in sorted(os.listdir(stock.data)):
        yield name, open(os.path.join(stock.data, name), 'rb').read()


@pytest.mark.parametrize('name', GOLDEN_NAMES)
def test_rebuild_without_changes_is_byte_identical(golden, name):
    assert datav1.rebuild(golden[name]) == golden[name]


@pytest.mark.stock
def test_rebuild_of_every_stock_screen_is_byte_identical(stock):
    screens = list(all_stock_screens(stock))
    assert len(screens) == 75
    for name, blob in screens:
        assert datav1.rebuild(blob) == blob, name


def test_not_a_datav1_file_raises():
    with pytest.raises(ValueError):
        datav1.sprites(b'\0' * 64)


@pytest.mark.parametrize('width,depth,expected', [
    (1, 3, 4), (2, 3, 8), (3, 3, 12), (4, 3, 12),
    (1, 2, 4), (3, 2, 8), (5, 4, 20), (16, 3, 48),
])
def test_stride_rounds_up_to_four(width, depth, expected):
    assert datav1.stride(width, depth) == expected


@pytest.mark.parametrize('name', GOLDEN_NAMES)
def test_sprite_stride_is_align4_of_width_times_depth(golden, name):
    for sp in datav1.sprites(golden[name]):
        assert sp.stride == (sp.width * sp.depth + 3) // 4 * 4
        assert sp.stride * sp.height == sp.raw_len


@pytest.mark.parametrize('name', GOLDEN_NAMES)
def test_pixels_strips_exactly_the_row_padding(golden, name):
    for sp in datav1.sprites(golden[name]):
        assert len(sp.pixels()) == sp.width * sp.depth * sp.height


@pytest.mark.parametrize('name', GOLDEN_NAMES)
def test_pack_of_pixels_reproduces_unpadded_sprites(golden, name):
    for sp in datav1.sprites(golden[name]):
        if sp.stride == sp.width * sp.depth:
            assert sp.pack(sp.pixels()) == sp.decode()


@pytest.mark.xfail(strict=True, reason=(
    'Sprite.pack zero-fills the row padding, but 543 of the 1128 stock sprites '
    'store non-zero bytes there, so pack(pixels(x)) != decode(x). '
    'volumebar.data sprite 1 is the smallest reproducer. Production bug in '
    'formats/datav1.py, left unfixed by design in this block.'))
def test_pack_of_pixels_reproduces_the_stored_buffer(golden):
    for name in GOLDEN_NAMES:
        for sp in datav1.sprites(golden[name]):
            assert sp.pack(sp.pixels()) == sp.decode(), f'{name}/{sp.idx}'


@pytest.mark.stock
def test_padding_loss_affects_exactly_543_stock_sprites(stock):
    """Measured scope of the pack() padding bug, so a fix is noticed here."""
    total = lossy = 0
    for _, blob in all_stock_screens(stock):
        for sp in datav1.sprites(blob):
            total += 1
            if sp.pack(sp.pixels()) != sp.decode():
                lossy += 1
    assert total == 1128
    assert lossy == 543


def test_golden_fixtures_cover_depths_two_and_three(golden):
    depths = {sp.depth for name in GOLDEN_NAMES
              for sp in datav1.sprites(golden[name])}
    assert depths == {2, 3}


@pytest.mark.stock
def test_stock_covers_depths_two_three_and_four(stock):
    counts = {2: 0, 3: 0, 4: 0}
    for _, blob in all_stock_screens(stock):
        for sp in datav1.sprites(blob):
            counts[sp.depth] += 1
    assert counts == {4: 132, 3: 931, 2: 65}


@pytest.mark.stock
def test_depth_four_sprites_are_bgra_and_need_no_row_padding(stock):
    seen = 0
    for _, blob in all_stock_screens(stock):
        for sp in datav1.sprites(blob):
            if sp.depth != 4:
                continue
            assert sp.mode == 'BGRA'
            assert sp.stride == sp.width * 4
            assert sp.pack(sp.pixels()) == sp.decode()
            seen += 1
    assert seen == 132


@pytest.mark.parametrize('name', GOLDEN_NAMES)
def test_replacing_a_sprite_preserves_geometry_and_pixels(golden, name):
    d = golden[name]
    items = datav1.sprites(d)
    if not items:
        pytest.skip(f'{name} has no sprites')
    for sp in items:
        out = datav1.rebuild(d, {sp.idx: sp.pack(sp.pixels())})
        after = datav1.sprites(out)[sp.idx]
        assert (after.width, after.height, after.depth) == \
               (sp.width, sp.height, sp.depth)
        assert after.pixels() == sp.pixels()
        assert after.stride == sp.stride


@pytest.mark.parametrize('name', ['volumebar.data', 'setupversion.data',
                                  'setuplogo.data'])
def test_wrong_size_replacement_raises(golden, name):
    d = golden[name]
    sp = datav1.sprites(d)[0]
    with pytest.raises(ValueError):
        datav1.rebuild(d, {sp.idx: sp.decode()[:-1]})
    with pytest.raises(ValueError):
        datav1.rebuild(d, {sp.idx: sp.decode() + b'\0'})


@pytest.mark.parametrize('name', ['volumebar.data', 'setupversion.data',
                                  'setuplogo.data'])
def test_pack_rejects_a_wrong_sized_pixel_buffer(golden, name):
    sp = datav1.sprites(golden[name])[0]
    with pytest.raises(ValueError):
        sp.pack(sp.pixels()[:-1])


@pytest.mark.parametrize('name', GOLDEN_NAMES)
def test_record_header_is_carried_through_verbatim(golden, name):
    """Only the data offset at +0x14 may differ after a rebuild."""
    d = golden[name]
    items = datav1.sprites(d)
    if not items:
        pytest.skip(f'{name} has no sprites')
    out = datav1.rebuild(d, {items[0].idx: items[0].pack(items[0].pixels())})
    for before, after in zip(items, datav1.sprites(out)):
        assert len(after.header) == len(before.header)
        assert after.header[:0x14] == before.header[:0x14]
        assert after.header[0x18:] == before.header[0x18:]
        assert struct.unpack_from('<I', after.header, 0x14)[0] == after.offset + \
               len(after.header)


def test_thirty_two_byte_headers_carry_a_constant_tail(golden):
    """The 32-byte variant's +0x18..0x20 is always 01 00 00 00 00 00 00 00.

    The plan calls these bytes "non-zero in 14 screens"; measured, the real
    distinction is the header size, and the tail never varies.
    """
    seen = 0
    for name in GOLDEN_NAMES:
        for sp in datav1.sprites(golden[name]):
            assert len(sp.header) in (24, 32)
            if len(sp.header) == 32:
                assert sp.header[0x18:0x20] == b'\x01\0\0\0\0\0\0\0'
                seen += 1
    assert seen == 15


@pytest.mark.stock
def test_stock_header_sizes_split_55_and_14_screens(stock):
    sizes = {24: 0, 32: 0}
    screens = {24: set(), 32: set()}
    for name, blob in all_stock_screens(stock):
        for sp in datav1.sprites(blob):
            assert len(sp.header) in sizes
            sizes[len(sp.header)] += 1
            screens[len(sp.header)].add(name)
            if len(sp.header) == 32:
                assert sp.header[0x18:0x20] == b'\x01\0\0\0\0\0\0\0'
    assert sizes == {24: 788, 32: 340}
    assert (len(screens[24]), len(screens[32])) == (55, 14)
    assert not screens[24] & screens[32]


def test_sprites_snapshot_matches(golden, sprites_snapshot):
    assert set(sprites_snapshot) == set(GOLDEN_NAMES)
    for name, expected in sprites_snapshot.items():
        got = [{'idx': sp.idx, 'width': sp.width, 'height': sp.height,
                'depth': sp.depth, 'stride': sp.stride, 'raw_len': sp.raw_len,
                'header': len(sp.header)}
               for sp in datav1.sprites(golden[name])]
        assert got == expected


def test_png_snapshot_matches(golden, png_snapshot):
    got = {}
    for name in GOLDEN_NAMES:
        for sp in datav1.sprites(golden[name]):
            buf = io.BytesIO()
            unpack.sprite_image(sp).save(buf, format='PNG')
            got[f'{name}/{sp.idx:02}.png'] = hashlib.sha256(
                buf.getvalue()).hexdigest()
    assert got == png_snapshot
