"""Pins tools/patchfile.py: an arbitrary rootfs file in, an unchanged image out.

The tool is deliberately blind to what it stores, so the only thing keeping it
honest is measurement on the real partition: feeding /apps/Config.ini back
unchanged has to reproduce stock/LTTF133.img byte for byte, and any real change
has to move exactly one entry and nothing else - not one of the other 256 files,
not one of the 69 compressed blobs, not one of the 1128 sprites.

Everything here needs the unpacked firmware, so the module carries
@pytest.mark.stock. minfs.replace re-walks the whole directory tree per call
(~1.4 s), so the three patched partitions the assertions share - same bytes,
shorter, longer - are produced once per module rather than per test.
"""
import os
import sys

import pytest

from formats import datav1, imagewty, minfs
from tools import patchfile

pytestmark = pytest.mark.stock

TARGET = '/apps/Config.ini'
ROOTFS_PARTITION = 'data_udisk.fex'
V_PARTITION = 'Vdata_udisk.fex'

FILE_COUNT = 257
COMPRESSED_COUNT = 69
SPRITE_COUNT = 1128


@pytest.fixture(scope='module')
def part(stock) -> bytes:
    return stock.partition(ROOTFS_PARTITION)


@pytest.fixture(scope='module')
def original(part) -> bytes:
    node = minfs.find(part, TARGET)
    return part[node.offset:node.offset + node.stored]


@pytest.fixture(scope='module')
def unchanged(original) -> tuple[str, bytes]:
    return patchfile.patch_files({TARGET: original})


@pytest.fixture(scope='module')
def smaller_blob(original) -> bytes:
    return original[:len(original) - 100]


@pytest.fixture(scope='module')
def smaller(smaller_blob) -> bytes:
    return patchfile.patch_files({TARGET: smaller_blob})[1]


@pytest.fixture(scope='module')
def larger_blob(original) -> bytes:
    return original + b'\n; padding\n' * 512


@pytest.fixture(scope='module')
def larger(larger_blob) -> bytes:
    return patchfile.patch_files({TARGET: larger_blob})[1]


def offsets(d: bytes) -> dict[str, tuple[int, int, int]]:
    return {f.path: (f.offset, f.stored, f.size) for f in minfs.files(d)}


def contents(d: bytes) -> dict[str, bytes]:
    return {f.path: d[f.offset:f.offset + f.stored] for f in minfs.files(d)}


def sprites(d: bytes) -> dict[str, bytes]:
    """Every sprite of every apps/Data screen, keyed '<screen>/<idx>'."""
    out = {}
    for f in minfs.files(d):
        if not f.path.startswith('/apps/Data/'):
            continue
        screen = os.path.basename(f.path)
        for sp in datav1.sprites(d[f.offset:f.offset + f.stored]):
            out[f'{screen}/{sp.idx}'] = sp.decode()
    return out


def test_the_stock_file_is_found_and_the_tool_agrees_on_the_partition(part):
    name, d = patchfile.rootfs_partition()
    assert name == ROOTFS_PARTITION
    assert d == part
    assert minfs.find(d, TARGET).path == TARGET


def test_replacing_a_file_with_its_own_bytes_changes_no_byte(part, unchanged):
    name, out = unchanged
    assert name == ROOTFS_PARTITION
    assert out == part


def test_the_rebuilt_image_is_byte_identical_to_the_vendor_image(
        stock, original, tmp_path, monkeypatch):
    """§4 Step 1 done-when, run through the CLI exactly as a user would."""
    src = tmp_path / 'Config.ini'
    src.write_bytes(original)
    out = tmp_path / 'out'
    monkeypatch.setattr(sys, 'argv',
                        ['patchfile.py', TARGET, str(src), '--img', '--out', str(out)])
    patchfile.main()

    img = open(stock.image, 'rb').read()
    built = (out / os.path.basename(stock.image)).read_bytes()
    assert len(built) == len(img)
    assert built == img
    assert (out / ROOTFS_PARTITION).read_bytes() == stock.partition(ROOTFS_PARTITION)


def test_a_smaller_file_stays_in_place_and_moves_no_other_entry(
        part, smaller_blob, smaller):
    blob, out = smaller_blob, smaller
    before, after = offsets(part), offsets(out)

    assert after[TARGET][0] == before[TARGET][0]
    assert after[TARGET][1:] == (len(blob), len(blob))
    assert len(out) == len(part)
    assert minfs.free_offset(out) == minfs.free_offset(part)
    assert {p: v for p, v in after.items() if p != TARGET} == \
           {p: v for p, v in before.items() if p != TARGET}


def test_a_larger_file_relocates_to_the_free_tail(part, larger_blob, larger):
    blob, out = larger_blob, larger
    free = minfs.free_offset(part)
    node = minfs.find(out, TARGET)

    assert node.offset == free != minfs.find(part, TARGET).offset
    assert (node.stored, node.size) == (len(blob), len(blob))
    assert out[node.offset:node.offset + len(blob)] == blob
    assert len(out) == len(part)
    assert minfs.free_offset(out) > free


def test_a_relocation_leaves_the_other_256_files_byte_identical(part, larger):
    before, after = contents(part), contents(larger)

    assert len(before) == len(after) == FILE_COUNT
    del before[TARGET], after[TARGET]
    assert len(after) == FILE_COUNT - 1
    assert after == before


def test_the_patched_partition_still_holds_257_files(part, larger):
    assert len(minfs.files(larger)) == len(minfs.files(part)) == FILE_COUNT


def test_the_69_compressed_files_are_untouched(part, larger):
    was = {f.path: part[f.offset:f.offset + f.stored]
           for f in minfs.files(part) if f.compressed}
    now = {f.path: larger[f.offset:f.offset + f.stored]
           for f in minfs.files(larger) if f.compressed}
    assert len(was) == COMPRESSED_COUNT
    assert now == was


def test_all_1128_sprites_are_untouched(part, larger):
    was, now = sprites(part), sprites(larger)
    assert len(was) == SPRITE_COUNT
    assert now == was


def test_the_v_sum_is_recomputed_from_the_patched_partition(
        stock, original, tmp_path, monkeypatch):
    src = tmp_path / 'Config.ini'
    src.write_bytes(original.replace(b'backLightMode=0', b'backLightMode=2'))
    assert src.read_bytes() != original
    out = tmp_path / 'out'
    monkeypatch.setattr(sys, 'argv',
                        ['patchfile.py', TARGET, str(src), '--img', '--out', str(out)])
    patchfile.main()

    img = open(stock.image, 'rb').read()
    built = (out / os.path.basename(stock.image)).read_bytes()
    part = (out / ROOTFS_PARTITION).read_bytes()
    assert built != img

    items = imagewty.parse(built)
    moved = [a.name for a, b in zip(imagewty.parse(img), items)
             if imagewty.extract(img, a) != imagewty.extract(built, b)]
    assert moved == [ROOTFS_PARTITION, V_PARTITION]

    v = next(it for it in items if it.name == V_PARTITION)
    assert imagewty.extract(built, v) == imagewty.vsum(part)
    assert imagewty.extract(built, v) != stock.partition(V_PARTITION)[:4]


def test_a_path_that_is_not_in_the_rootfs_is_refused(original, tmp_path,
                                                     monkeypatch):
    src = tmp_path / 'Config.ini'
    src.write_bytes(original)
    out = tmp_path / 'out'
    monkeypatch.setattr(sys, 'argv',
                        ['patchfile.py', '/apps/Nope.ini', str(src),
                         '--img', '--out', str(out)])
    with pytest.raises(SystemExit, match='never creates'):
        patchfile.main()
    assert not out.exists()


def test_a_relative_rootfs_path_is_refused(original, tmp_path):
    src = tmp_path / 'Config.ini'
    src.write_bytes(original)
    with pytest.raises(SystemExit, match='absolute'):
        patchfile.read_pairs(['apps/Config.ini', str(src)])


def test_an_odd_number_of_arguments_is_refused(tmp_path):
    with pytest.raises(SystemExit, match='pairs'):
        patchfile.read_pairs([TARGET])


def test_a_missing_local_file_is_refused(tmp_path):
    with pytest.raises(SystemExit, match='no such file'):
        patchfile.read_pairs([TARGET, str(tmp_path / 'nope.ini')])
