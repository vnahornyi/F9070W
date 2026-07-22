"""Pins down MINFS reading and patching on the real data_udisk.fex partition.

The whole file needs the unpacked firmware, so every test carries
@pytest.mark.stock. The regression that would brick the device is
test_patch_keeps_257_files_and_moves_no_other_entry: a patch must be strictly
local, or a neighbouring file is silently truncated.

walk() costs ~1.4 s on this partition (see the note on _read_entry below), so
the baseline snapshot is taken once per module.
"""
import struct

import pytest

from formats import minfs

pytestmark = pytest.mark.stock

TARGET = '/apps/Data/Black.data'
TARGET_SIZE = 592


@pytest.fixture(scope='module')
def part(stock) -> bytes:
    return stock.partition('data_udisk.fex')


@pytest.fixture(scope='module')
def baseline(part) -> dict[str, tuple[int, int, int]]:
    return offsets(part)


def offsets(d: bytes) -> dict[str, tuple[int, int, int]]:
    return {f.path: (f.offset, f.stored, f.size) for f in minfs.files(d)}


def test_partition_is_a_minfs_image(part):
    assert part[:5] == minfs.MAGIC
    assert minfs.walk(part).is_dir


def test_not_a_minfs_image_raises():
    with pytest.raises(ValueError):
        minfs.walk(b'NOPE' + b'\0' * 512)


def test_walk_sees_257_files_of_which_188_are_uncompressed(baseline, part):
    files = minfs.files(part)
    assert len(files) == len(baseline) == 257
    assert sum(1 for f in files if not f.compressed) == 188
    assert sum(1 for f in files if f.compressed) == 69


def test_every_data_screen_is_stored_uncompressed(part):
    screens = [f for f in minfs.files(part) if f.path.startswith('/apps/Data/')]
    assert len(screens) == 75
    assert all(f.stored == f.size for f in screens)


def test_compressed_entries_carry_an_oversized_record(part):
    """The 69 compressed entries are not plain 20 + padded-name records.

    Their u32 at +0x10 has high bits set (0x00a0_0000 / 0x00c0_0000 /
    0x0140_0000) on top of the name length, and entry_size runs to 188-348
    bytes. The trailing bytes hold per-chunk offsets - init.axf's record
    contains 904944 and 1075560, exactly the boundaries melislzma guesses by
    signature scanning. Pinned here so the layout is not lost.
    """
    wide = []
    for f in minfs.files(part):
        nlen = struct.unpack_from('<I', part, f.entry + 16)[0]
        esize = struct.unpack_from('<H', part, f.entry + 12)[0]
        name = f.path.rsplit('/', 1)[-1]
        plain = 20 + (len(name) + 3) // 4 * 4
        if f.compressed:
            assert nlen > 0xffff
            assert nlen & 0xffff == len(name)
            assert esize > plain
            wide.append(f.path)
        else:
            assert nlen == len(name)
            assert esize == plain
    assert len(wide) == 69

    axf = minfs.find(part, '/apps/init.axf')
    rec = part[axf.entry:axf.entry + struct.unpack_from('<H', part, axf.entry + 12)[0]]
    words = struct.unpack_from(f'<{len(rec) // 4}I', rec)
    assert 904944 in words and 1075560 in words


def test_find_returns_the_entry_and_raises_for_a_missing_path(part):
    node = minfs.find(part, TARGET)
    assert node.path == TARGET
    assert node.stored == node.size == TARGET_SIZE
    with pytest.raises(KeyError):
        minfs.find(part, '/nope/nope.bin')


def test_free_offset_is_aligned_and_past_every_referenced_byte(part):
    free = minfs.free_offset(part)
    assert free % 16 == 0
    assert free == 11_950_720
    assert len(part) - free == 2_663_808
    for f in minfs.files(part):
        assert f.offset + f.stored <= free


def test_replace_with_identical_content_changes_nothing(part):
    node = minfs.find(part, TARGET)
    same = part[node.offset:node.offset + node.stored]
    assert minfs.replace(part, TARGET, same) == part


def test_smaller_blob_stays_in_place(part, baseline):
    out = minfs.replace(part, TARGET, b'\xa5' * 100)
    after = minfs.find(out, TARGET)
    assert after.offset == baseline[TARGET][0]
    assert (after.stored, after.size) == (100, 100)
    assert out[after.offset:after.offset + 100] == b'\xa5' * 100
    assert len(out) == len(part)
    assert minfs.free_offset(out) == 11_950_720


def test_larger_blob_relocates_to_the_free_tail(part, baseline):
    blob = b'\x5a' * (TARGET_SIZE + 4096)
    out = minfs.replace(part, TARGET, blob)
    after = minfs.find(out, TARGET)
    assert after.offset == 11_950_720 != baseline[TARGET][0]
    assert (after.stored, after.size) == (len(blob), len(blob))
    assert out[after.offset:after.offset + len(blob)] == blob
    assert len(out) == len(part)
    assert minfs.free_offset(out) > 11_950_720


def test_free_offset_grows_with_the_relocated_block_but_is_not_monotonic(part):
    """free_offset is max(offset + stored), so shrinking the tail file lowers it.

    The plan calls free_offset "monotonic"; measured, it only grows while the
    relocated block grows. Pinned as-is because relocation depends on it.
    """
    grown = minfs.replace(part, TARGET, b'\x5a' * (64 * 1024))
    high = minfs.free_offset(grown)
    assert high == (11_950_720 + 64 * 1024 + 15) // 16 * 16

    shrunk = minfs.replace(grown, TARGET, b'\0' * 16)
    assert minfs.free_offset(shrunk) < high


def test_blob_larger_than_the_free_tail_raises(part):
    with pytest.raises(ValueError, match='no room'):
        minfs.replace(part, TARGET, b'\0' * (2_663_808 + 1))


@pytest.mark.parametrize('size', [100, TARGET_SIZE, TARGET_SIZE + 4096])
def test_patch_keeps_257_files_and_moves_no_other_entry(part, baseline, size):
    """The regression that bricks the device: a patch must be strictly local."""
    after = offsets(minfs.replace(part, TARGET, b'\xa5' * size))
    assert len(after) == 257
    assert set(after) == set(baseline)
    assert {p: v for p, v in after.items() if p != TARGET} == \
           {p: v for p, v in baseline.items() if p != TARGET}


def test_patch_touches_only_the_target_entry_in_the_metadata_region(part):
    node = minfs.find(part, TARGET)
    meta_end = struct.unpack_from('<I', part, 0x14)[0]
    out = minfs.replace(part, TARGET, b'\xa5' * 100)
    assert out[:0x200] == part[:0x200]
    changed = [i for i in range(0x200, meta_end) if out[i] != part[i]]
    assert changed
    assert min(changed) >= node.entry
    assert max(changed) < node.entry + 12


def test_patch_does_not_disturb_the_69_compressed_files(part):
    before = {f.path: part[f.offset:f.offset + f.stored]
              for f in minfs.files(part) if f.compressed}
    out = minfs.replace(part, TARGET, b'\xa5' * (TARGET_SIZE + 4096))
    after = {f.path: out[f.offset:f.offset + f.stored]
             for f in minfs.files(out) if f.compressed}
    assert len(before) == 69
    assert after == before
