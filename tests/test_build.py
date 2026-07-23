"""The end-to-end pipeline: sprite -> PNG -> .data -> MINFS -> IMAGEWTY -> .img.

Every other test file pins one layer. This one pins the composition of all of
them, which is the only claim a user actually relies on: what comes out of
tools/build.py differs from the vendor image exactly where the theme says it
differs, and nowhere else.

Two things are measured here rather than assumed:

  * zlib level 9 reproduces the vendor's own sprite compression, so a sprite
    that went out as a PNG and came back is bit-for-bit what it was;
  * RGB565 (depth 2) survives the PNG detour without loss. Pillow has a BGR;16
    decoder but no encoder, so tools/build.py packs RGB565 by hand; the packing
    is asserted to invert the decoder over all 65536 code points and over all
    65 depth-2 sprites in the firmware. The quantisation is lossy in principle
    - 8-bit values that never come out of the decoder would not survive - but
    every value in a stock-exported PNG does come out of it, so the measured
    loss on stock content is zero.

The 18 MB image, the 75 screens and the 1128 exported PNGs are produced once
per module; per-test they would cost minutes. Even so the module runs for
minutes, and almost all of it is minfs.replace, which re-walks the whole
directory tree per call - see the _read_entry note in docs/findings.md.
"""
import os
import struct
import sys

import pytest

from formats import datav1, imagewty, minfs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import build as builder  # noqa: E402
import unpack  # noqa: E402

SPRITE_COUNT = 1128
SCREEN_COUNT = 75
# Six stock screens are pure layout and carry no sprite at all, so a theme can
# never touch them and build_screens never rewrites them.
SCREENS_WITH_SPRITES = 69
DEPTHS = {4: 132, 3: 931, 2: 65}

ROOTFS_PARTITION = 'data_udisk.fex'
V_PARTITION = 'Vdata_udisk.fex'

# §8 case 2/4: Main sprite 9 is 1024x184 BGRA, sprite 10 is 150x166.
EDIT_SCREEN, EDIT_SPRITE = 'Main', 9
WRONG_SIZE_SPRITE = 10


def screen_of(name: str) -> str:
    return name.removesuffix('.data')


@pytest.fixture(scope='module')
def img(stock) -> bytes:
    return open(stock.image, 'rb').read()


@pytest.fixture(scope='module')
def screens(stock) -> dict[str, bytes]:
    return {n: open(os.path.join(stock.data, n), 'rb').read()
            for n in sorted(os.listdir(stock.data))}


@pytest.fixture(scope='module')
def sprited(screens) -> dict[str, bytes]:
    """The screens a theme can actually reach: those with at least one sprite."""
    out = {n: d for n, d in screens.items() if datav1.sprites(d)}
    assert len(out) == SCREENS_WITH_SPRITES
    return out


@pytest.fixture(scope='module')
def png_theme(screens, tmp_path_factory):
    """Every stock sprite exported as a PNG - a theme that changes nothing."""
    root = tmp_path_factory.mktemp('stock-png')
    for name, d in screens.items():
        sdir = root / screen_of(name)
        sdir.mkdir()
        for sp in datav1.sprites(d):
            im = unpack.sprite_image(sp)
            assert im is not None, f'{name}/{sp.idx}: depth {sp.depth}'
            im.save(sdir / f'{sp.idx:02}.png')
    return root


@pytest.fixture(scope='module')
def rebuilt(png_theme, tmp_path_factory) -> tuple[dict[str, bytes], bytes, bytes]:
    """The full chain run over the untouched export: screens, partition, image."""
    out = str(tmp_path_factory.mktemp('out'))
    built = builder.build_screens(str(png_theme))
    name, part = builder.patch_partition(built)
    assert name == ROOTFS_PARTITION
    dst = builder.write_img(name, part, out)
    return built, part, open(dst, 'rb').read()


def data_files(partition: bytes) -> dict[str, bytes]:
    """The apps/Data screens as stored inside a MINFS partition."""
    out = {}
    for f in minfs.files(partition):
        if f.path.startswith('/apps/Data/'):
            out[os.path.basename(f.path)] = \
                partition[f.offset:f.offset + f.stored]
    return out


def changed_sprites(before: dict[str, bytes],
                    after: dict[str, bytes]) -> list[tuple[str, int]]:
    assert sorted(before) == sorted(after)
    diff = []
    for name, old in before.items():
        was = datav1.sprites(old)
        now = datav1.sprites(after[name])
        assert len(was) == len(now), name
        for a, b in zip(was, now):
            if a.decode() != b.decode():
                diff.append((screen_of(name), a.idx))
    return diff


def test_pillow_still_has_no_bgr16_encoder():
    """Why tools/build.py packs RGB565 by hand - remove the packer if this fails."""
    from PIL import Image
    with pytest.raises(ValueError):
        Image.new('RGB', (1, 1)).tobytes('raw', 'BGR;16')


def test_rgb565_packing_inverts_the_decoder_for_every_code_point():
    from PIL import Image
    blob = b''.join(struct.pack('<H', v) for v in range(0x10000))
    im = Image.frombytes('RGB', (256, 256), blob, 'raw', 'BGR;16')
    assert builder.rgb_to_565(im.tobytes('raw', 'RGB')) == blob


@pytest.mark.stock
def test_the_export_covers_every_sprite_at_every_depth(screens, png_theme):
    assert len(screens) == SCREEN_COUNT
    seen = {}
    for name, d in screens.items():
        for sp in datav1.sprites(d):
            seen[sp.depth] = seen.get(sp.depth, 0) + 1
            assert (png_theme / screen_of(name) / f'{sp.idx:02}.png').exists()
    assert seen == DEPTHS
    assert sum(seen.values()) == SPRITE_COUNT


@pytest.mark.stock
def test_every_depth_two_sprite_survives_the_png_detour_with_zero_loss(
        screens, png_theme):
    """The measured RGB565 loss on stock content: none, on all 65 sprites.

    Named separately from the whole-image test so that if quantisation ever
    does cost a byte, the failure says which layer lost it.
    """
    checked = 0
    for name, d in screens.items():
        for sp in datav1.sprites(d):
            if sp.depth != 2:
                continue
            png = png_theme / screen_of(name) / f'{sp.idx:02}.png'
            assert builder.png_to_raw(str(png), sp) == sp.decode(), \
                f'{name}/{sp.idx}'
            checked += 1
    assert checked == DEPTHS[2]


@pytest.mark.stock
def test_every_sprite_survives_the_png_detour(sprited, rebuilt):
    built, _, _ = rebuilt
    assert len(built) == SCREENS_WITH_SPRITES
    assert changed_sprites(sprited, built) == []


@pytest.mark.stock
def test_the_rebuilt_screens_are_byte_identical(sprited, rebuilt):
    built, _, _ = rebuilt
    assert built == sprited


@pytest.mark.stock
def test_the_patched_partition_is_byte_identical(stock, rebuilt):
    _, part, _ = rebuilt
    assert part == stock.partition(ROOTFS_PARTITION)


@pytest.mark.stock
def test_stock_pngs_through_the_whole_chain_change_zero_bytes(img, rebuilt):
    """The claim the project exists to keep true."""
    _, _, out = rebuilt
    assert len(out) == len(img)
    assert out == img


@pytest.mark.stock
def test_img_with_no_theme_yields_the_original_image(img, stock, tmp_path):
    theme = tmp_path / 'empty'
    theme.mkdir()
    built = builder.build_screens(str(theme))
    assert built == {}
    name, part = builder.patch_partition(built)
    assert part == stock.partition(ROOTFS_PARTITION)
    dst = builder.write_img(name, part, str(tmp_path / 'out'))
    assert open(dst, 'rb').read() == img


@pytest.mark.stock
def test_one_png_changes_exactly_one_sprite_out_of_1128(
        img, stock, screens, png_theme, tmp_path):
    from PIL import Image
    theme = tmp_path / 'one'
    (theme / EDIT_SCREEN).mkdir(parents=True)
    src = png_theme / EDIT_SCREEN / f'{EDIT_SPRITE:02}.png'
    im = Image.open(src).convert('RGBA')
    was = im.getpixel((0, 0))
    im.putpixel((0, 0), (was[0] ^ 0xff, was[1], was[2], was[3]))
    im.save(theme / EDIT_SCREEN / f'{EDIT_SPRITE:02}.png')

    built = builder.build_screens(str(theme))
    assert list(built) == [f'{EDIT_SCREEN}.data']
    name, part = builder.patch_partition(built)
    dst = builder.write_img(name, part, str(tmp_path / 'out'))
    out = open(dst, 'rb').read()

    assert len(out) == len(img)
    assert changed_sprites(screens, data_files(part)) == \
           [(EDIT_SCREEN, EDIT_SPRITE)]

    before, after = imagewty.parse(img), imagewty.parse(out)
    moved = [a.name for a, b in zip(before, after)
             if imagewty.extract(img, a) != imagewty.extract(out, b)]
    assert moved == [ROOTFS_PARTITION, V_PARTITION]

    v = next(it for it in after if it.name == V_PARTITION)
    rootfs = next(it for it in after if it.name == ROOTFS_PARTITION)
    assert imagewty.extract(out, rootfs) == part
    assert imagewty.extract(out, v) == imagewty.vsum(part)
    assert imagewty.extract(out, v) != stock.partition(V_PARTITION)[:4]


@pytest.mark.stock
def test_a_png_of_the_wrong_size_is_rejected_and_no_image_is_written(
        tmp_path):
    from PIL import Image
    theme = tmp_path / 'bad'
    (theme / EDIT_SCREEN).mkdir(parents=True)
    Image.new('RGBA', (100, 100)).save(
        theme / EDIT_SCREEN / f'{WRONG_SIZE_SPRITE:02}.png')
    out = tmp_path / 'out'

    with pytest.raises(ValueError, match='is 100x100, stock sprite is 150x166'):
        builder.build_screens(str(theme))
    assert not out.exists()


@pytest.mark.stock
def test_a_sprite_index_that_does_not_exist_is_rejected(tmp_path):
    from PIL import Image
    theme = tmp_path / 'oob'
    (theme / EDIT_SCREEN).mkdir(parents=True)
    Image.new('RGBA', (10, 10)).save(theme / EDIT_SCREEN / '99.png')
    with pytest.raises(SystemExit, match='sprite 99 does not exist'):
        builder.build_screens(str(theme))
