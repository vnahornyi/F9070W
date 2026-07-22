"""Shared pytest fixtures.

Two sources of test data:

    tests/fixtures/   golden files committed to the repo, always available
    stock/            the ~40 MB unpacked firmware, gitignored and optional

Tests that need the full tree carry @pytest.mark.stock and are skipped, not
failed, when stock/ is missing - a fresh clone must stay green.
Regenerate the golden files with `python tools/mkfixtures.py --update`.
"""
import json
import os
from dataclasses import dataclass

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, 'tests', 'fixtures')
STOCK = os.path.join(ROOT, 'stock')

GOLDEN_NAMES = ['black.data', 'wallpaper.data', 'tipbox.data',
                'volumebar.data', 'setupversion.data', 'setuplogo.data']


@dataclass
class Stock:
    """Paths inside the unpacked firmware tree."""
    root: str
    partitions: str
    rootfs: str
    data: str

    @property
    def image(self) -> str:
        """The pristine .img kept by tools/unpack.py."""
        for n in sorted(os.listdir(self.root)):
            if n.lower().endswith('.img'):
                return os.path.join(self.root, n)
        pytest.skip(f'no .img in {self.root} - re-run tools/unpack.py')

    def partition(self, name: str) -> bytes:
        return open(os.path.join(self.partitions, name), 'rb').read()


def has_stock() -> bool:
    return os.path.isdir(os.path.join(STOCK, 'rootfs', 'apps', 'Data'))


def pytest_collection_modifyitems(config, items):
    if has_stock():
        return
    skip = pytest.mark.skip(reason='no stock/ tree - run tools/unpack.py')
    for item in items:
        if 'stock' in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope='session')
def fixtures_dir() -> str:
    return FIXTURES


@pytest.fixture(scope='session')
def golden() -> dict[str, bytes]:
    """Every golden .data file, keyed by its fixture name."""
    return {n: open(os.path.join(FIXTURES, n), 'rb').read() for n in GOLDEN_NAMES}


@pytest.fixture(scope='session')
def sprites_snapshot() -> dict[str, list[dict]]:
    """Expected w/h/depth/stride/raw_len/header per sprite, from sprites.json.

    The golden screens cover both header variants (24 B and 32 B) but only
    depths 2 and 3: every screen containing a depth-4 sprite is far over the
    fixture budget, so depth-4 assertions need @pytest.mark.stock.
    """
    with open(os.path.join(FIXTURES, 'sprites.json'), encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope='session')
def png_snapshot() -> dict[str, str]:
    """PNG export digests from png.sha256, keyed by '<fixture>/<idx>.png'."""
    out = {}
    with open(os.path.join(FIXTURES, 'png.sha256'), encoding='utf-8') as f:
        for line in f:
            if line.strip():
                digest, name = line.split(maxsplit=1)
                out[name.strip()] = digest
    return out


@pytest.fixture(scope='session')
def stock() -> Stock:
    if not has_stock():
        pytest.skip('no stock/ tree - run tools/unpack.py')
    return Stock(STOCK,
                 os.path.join(STOCK, 'partitions'),
                 os.path.join(STOCK, 'rootfs'),
                 os.path.join(STOCK, 'rootfs', 'apps', 'Data'))
