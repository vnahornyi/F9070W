"""Pins down the IMAGEWTY layer: parse/extract, vsum and the image builder.

The two claims that protect the device live here: build(img, {}) is
byte-identical to the vendor image, and replacing a partition rewrites its
V-partition and nothing else. If either stops holding, a flashed image either
fails the flasher's verification or carries a silently corrupted partition.

The 18 MB image is read and rebuilt once per module - both are cheap only if
they are not repeated per test.

Only the vsum unit cases run without stock/; everything that asserts a
measured layout needs the real image and carries @pytest.mark.stock.
"""
import collections
import os
import struct

import pytest

from formats import imagewty

STOCK_NAMES = [
    'sys_config_nor.fex', 'config_nor.fex', 'split_xxxx.fex',
    'sys_partition_nor.fex', 'sunxi.fex', 'boot0_nor.fex', 'boot0_card.fex',
    'boot_pkg_uboot_nor.fex', 'boot_pkg_uboot_nor.fex', 'u-boot_nor.fex',
    'fes1.fex', 'usbtool.fex', 'usbtool_crash.fex', 'aultools.fex',
    'aultls32.fex', 'cardtool.fex', 'cardscript.fex', 'sunxi_gpt.fex',
    'sunxi_mbr_nor.fex', 'dlinfo.fex', 'arisc.fex', 'melis_pkg_nor.fex',
    'Vmelis_pkg_nor.fex', 'data_udisk.fex', 'Vdata_udisk.fex',
]

V_PAIRS = [('data_udisk.fex', 'Vdata_udisk.fex', 0x1e3c76a1),
           ('melis_pkg_nor.fex', 'Vmelis_pkg_nor.fex', 0x814cb3db)]

IMAGE_SIZE = 18252800
DATA_UDISK_LEN = 14614528


@pytest.fixture(scope='module')
def img(stock) -> bytes:
    return open(stock.image, 'rb').read()


@pytest.fixture(scope='module')
def items(img) -> list[imagewty.Item]:
    return imagewty.parse(img)


@pytest.fixture(scope='module')
def rebuilt(img) -> bytes:
    return imagewty.build(img, {})


def unpacked_name(names: list[str], i: int) -> str:
    """tools/unpack.py disambiguates repeated item names with a .N suffix."""
    seen = names[:i].count(names[i])
    return names[i] if not seen else f'{names[i]}.{seen}'


def diff_ranges(a: bytes, b: bytes, block: int = 4096) -> list[tuple[int, int]]:
    """Contiguous [start, end) ranges where two equal-length blobs differ."""
    assert len(a) == len(b)
    ranges = []
    for base in range(0, len(a), block):
        if a[base:base + block] == b[base:base + block]:
            continue
        for i in range(base, min(base + block, len(a))):
            if a[i] == b[i]:
                continue
            if ranges and ranges[-1][1] == i:
                ranges[-1][1] = i + 1
            else:
                ranges.append([i, i + 1])
    return [(s, e) for s, e in ranges]


def touched(a: bytes, b: bytes, regions: list[tuple[int, int]]) -> list[int]:
    """Indices of `regions` the diff falls in; raises if anything falls outside.

    A rewritten V-sum whose bytes partly repeat the old value shows up as
    several small diff ranges, so containment - not range equality - is what
    "exactly these two places changed" means here.
    """
    hit = []
    for start, end in diff_ranges(a, b):
        inside = [i for i, (s, e) in enumerate(regions) if s <= start and end <= e]
        assert inside, f'unexpected change at [{start}, {end})'
        hit += inside
    return sorted(set(hit))


def filler(data: bytes, items: list[imagewty.Item]) -> collections.Counter:
    counts = collections.Counter()
    for it in items:
        end = it.offset + it.stored_len
        counts.update(data[it.offset + it.length:end])
        counts.update(data[end:-(-end // imagewty.ALIGN) * imagewty.ALIGN])
    return counts


@pytest.mark.parametrize('blob,expected', [
    (b'', 0),
    (b'\x01\0\0\0', 1),
    (b'\x01\0\0\0\x02\0\0\0', 3),
    (b'\xff\xff\xff\xff', 0xffffffff),
    (b'\x78\x56\x34\x12', 0x12345678),
    (b'\xff\xff\xff\xff\x01\0\0\0', 0),
    (b'\xff\xff\xff\xff\xff\xff\xff\xff', 0xfffffffe),
])
def test_vsum_is_the_modular_sum_of_le_words(blob, expected):
    assert imagewty.vsum(blob) == struct.pack('<I', expected)


@pytest.mark.parametrize('length', [1, 2, 3, 5, 7])
def test_vsum_rejects_a_length_that_is_not_a_multiple_of_four(length):
    with pytest.raises(ValueError):
        imagewty.vsum(b'\0' * length)


def test_parse_rejects_a_blob_without_the_magic():
    with pytest.raises(ValueError):
        imagewty.parse(b'\0' * imagewty.ITEM_TABLE)


@pytest.mark.stock
def test_parse_finds_the_twenty_five_stock_partitions(items):
    assert [it.name for it in items] == STOCK_NAMES
    assert all(it.maintype.strip('\0') and it.subtype.strip('\0')
               for it in items)
    assert all(it.name.isprintable() and '\0' not in it.name for it in items)


@pytest.mark.stock
def test_items_are_ascending_aligned_and_inside_the_image(items, img):
    prev = imagewty.ITEM_TABLE + len(items) * imagewty.ITEM_SIZE
    for it in items:
        assert it.offset % imagewty.ALIGN == 0, it.name
        assert it.offset >= prev, it.name
        assert it.offset + it.length <= len(img), it.name
        prev = it.offset


@pytest.mark.stock
def test_stored_len_is_length_rounded_up_to_sixteen(items):
    for it in items:
        assert it.stored_len == -(-it.length // 16) * 16, it.name


@pytest.mark.stock
def test_image_size_field_matches_the_file(img):
    assert len(img) == IMAGE_SIZE
    assert struct.unpack_from('<I', img, 0x18)[0] == len(img)


@pytest.mark.stock
def test_extract_returns_the_unpacked_partition_files(img, items, stock):
    names = [it.name for it in items]
    for i, it in enumerate(items):
        assert imagewty.extract(img, it) == \
               stock.partition(unpacked_name(names, i)), it.name


@pytest.mark.stock
@pytest.mark.parametrize('name,vname,expected', V_PAIRS)
def test_vsum_matches_the_stock_v_partitions(stock, name, vname, expected):
    v = stock.partition(vname)
    assert imagewty.vsum(stock.partition(name)) == v[:4]
    assert v[:4] == struct.pack('<I', expected)


@pytest.mark.stock
def test_dlinfo_pairs_the_two_checksummed_partitions(stock):
    pairs = imagewty._v_pairs(stock.partition('dlinfo.fex'))
    assert pairs == {'DATA_UDISK_FEX00': 'VDATA_UDISK_FEX0',
                     'MELIS_PKG_NOR_FE': 'VMELIS_PKG_NOR_F'}


@pytest.mark.stock
def test_build_without_changes_is_byte_identical(img, rebuilt):
    assert rebuilt == img


@pytest.mark.stock
def test_every_partition_survives_a_rebuild(img, items, rebuilt):
    after = imagewty.parse(rebuilt)
    assert len(after) == 25
    for before, now in zip(items, after):
        assert (now.name, now.maintype, now.subtype) == \
               (before.name, before.maintype, before.subtype)
        assert imagewty.extract(rebuilt, now) == \
               imagewty.extract(img, before), before.name


@pytest.mark.stock
def test_filler_is_zeroes_up_to_stored_len_then_cd_up_to_the_boundary(img, items):
    """Two regions, not one.

    The plan's §2 calls the padding "byte 0xCD" and stops there; measured, the
    gap between length and stored_len is zero-filled and only the rest of the
    1024-byte block is 0xCD.
    """
    for it in items:
        end = it.offset + it.stored_len
        boundary = -(-end // imagewty.ALIGN) * imagewty.ALIGN
        assert img[it.offset + it.length:end] == bytes(end - it.length -
                                                       it.offset), it.name
        assert img[end:boundary] == bytes([imagewty.PAD_BYTE]) * \
               (boundary - end), it.name


@pytest.mark.stock
def test_whole_image_filler_histogram_is_seventy_zeroes_and_8128_cd(img, items):
    assert filler(img, items) == collections.Counter({0x00: 70, 0xCD: 8128})


@pytest.mark.stock
def test_rebuilt_image_keeps_the_same_filler(rebuilt, items):
    assert filler(rebuilt, imagewty.parse(rebuilt)) == filler(rebuilt, items)
    assert filler(rebuilt, items) == collections.Counter({0x00: 70, 0xCD: 8128})


@pytest.mark.stock
def test_rebuild_keeps_every_partition_aligned_and_contiguous(rebuilt):
    after = imagewty.parse(rebuilt)
    cur = imagewty.ITEM_TABLE + len(after) * imagewty.ITEM_SIZE
    for it in after:
        assert it.offset % imagewty.ALIGN == 0, it.name
        assert it.offset == cur, it.name
        cur = -(-(it.offset + it.stored_len) // imagewty.ALIGN) * imagewty.ALIGN
    assert cur == len(rebuilt)
    assert struct.unpack_from('<I', rebuilt, 0x18)[0] == len(rebuilt)


@pytest.mark.stock
def test_replacing_a_partition_with_its_own_bytes_changes_nothing(img, items):
    by_name = {it.name: it for it in items}
    same = {n: imagewty.extract(img, by_name[n])
            for n in ('data_udisk.fex', 'melis_pkg_nor.fex', 'u-boot_nor.fex')}
    assert imagewty.build(img, same) == img


@pytest.mark.stock
def test_replacing_data_udisk_rewrites_exactly_that_byte_and_its_vsum(img, items):
    by_name = {it.name: it for it in items}
    part = bytearray(imagewty.extract(img, by_name['data_udisk.fex']))
    part[0x1000] ^= 0xff
    out = imagewty.build(img, {'data_udisk.fex': bytes(part)})

    assert len(out) == len(img)
    v = by_name['Vdata_udisk.fex']
    assert touched(img, out, [
        (by_name['data_udisk.fex'].offset + 0x1000,
         by_name['data_udisk.fex'].offset + 0x1001),
        (v.offset, v.offset + 4),
    ]) == [0, 1]
    assert imagewty.extract(out, v) == imagewty.vsum(bytes(part))
    assert imagewty.extract(out, by_name['data_udisk.fex']) == bytes(part)


@pytest.mark.stock
def test_replacing_melis_pkg_rewrites_its_own_vsum(img, items):
    by_name = {it.name: it for it in items}
    part = bytearray(imagewty.extract(img, by_name['melis_pkg_nor.fex']))
    part[7] ^= 0x01
    out = imagewty.build(img, {'melis_pkg_nor.fex': bytes(part)})

    v = by_name['Vmelis_pkg_nor.fex']
    assert touched(img, out, [
        (by_name['melis_pkg_nor.fex'].offset + 7,
         by_name['melis_pkg_nor.fex'].offset + 8),
        (v.offset, v.offset + 4),
    ]) == [0, 1]
    assert imagewty.extract(out, v) == imagewty.vsum(bytes(part))


@pytest.mark.stock
@pytest.mark.parametrize('delta', [1, 1024, -1])
def test_resizing_data_udisk_raises_and_names_the_two_declarations(img, delta):
    part = bytes(DATA_UDISK_LEN + delta)
    with pytest.raises(ValueError) as e:
        imagewty.build(img, {'data_udisk.fex': part})
    assert 'sys_partition_nor.fex' in str(e.value)
    assert 'rootfs_ini.tmp' in str(e.value)


@pytest.mark.stock
def test_replacing_an_unknown_partition_raises(img):
    with pytest.raises(ValueError, match='no such partition'):
        imagewty.build(img, {'nope.fex': b''})
