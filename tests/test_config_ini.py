"""Pins /apps/Config.ini and the working copy that changes it.

Config.ini is the device's main configuration file - audio, backlight, radio,
CAN, steering wheel - so the only safe edit is a byte-level one: AGENTS.md rule
4 forbids "normalising" anything, and a round trip through configparser would
rewrite key order, comments and line endings without anyone noticing.

    tests/fixtures/Config.ini   golden copy of the stock file, always available
    themes/config/Config.ini    the working copy

The point of these tests is not that the working copy is *correct* - only the
device can say that - but that it differs from stock in exactly the changes
declared below and in nothing else. CHANGED, ADDED and ADDED_SECTION are the
whole contract; anything else moving is a bug in whatever produced the file.

Some of the declared changes are confirmed on hardware, the rest are
experiments, and docs/findings.md says which is which. The tests do not
distinguish - a wrong byte is a wrong byte either way.

Only the case that reads the file out of the stock MINFS partition carries
@pytest.mark.stock; everything else runs on a fresh clone.
"""
import configparser
import os

import pytest

from formats import minfs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = '/apps/Config.ini'
ROOTFS_PARTITION = 'data_udisk.fex'

SECTION_COUNT = 29

# (section, key): (stock value, working-copy value)
CHANGED = {
    ('SETUP', 'bBackMute'): ('1', '0'),
    ('SETUP', 'colorLampMode'): ('0', '6'),
    ('CAN', 'carType'): ('22', '19'),
    ('LINK', 'carplayVolume'): ('10', '15'),
    ('RADIO', 'bRadioBackgroundRun'): ('1', '0'),
    ('STARTUP', 'startUpDefVolume'): ('10', '5'),
    ('BACKLIGHT', 'backLightMode'): ('0', '2'),
    ('BACKLIGHT', 'backLightNight'): ('40', '50'),
}

# (section, key): value - keys the stock file does not contain at all
ADDED = {
    ('SETUP', 'wallPaper'): '12.JPG',
    ('AUDIO', 'bLoudness'): '1',
    ('CAN', 'carModel'): '0',
}

# A section the stock file does not contain, added as a copy of [AMERICA2]
# with one FM1 field changed to a recognisable value.
ADDED_SECTION = 'EUROPE'
ADDED_SECTION_KEYS = {
    'FM1': '7600,10260,9980,9090,9130,9050,9200,10,10',
    'FM2': '7600,7600,9010,9810,10610,10800,7600,10,10',
    'FM3': '7600,7600,9010,9810,10610,10800,7600,10,10',
    'AM1': '520,520,600,1000,1400,1620,520,10,10',
    'AM2': '520,520,600,1000,1400,1620,520,10,10',
}


@pytest.fixture(scope='module')
def golden_ini() -> bytes:
    return open(os.path.join(ROOT, 'tests', 'fixtures', 'Config.ini'), 'rb').read()


@pytest.fixture(scope='module')
def working_ini() -> bytes:
    return open(os.path.join(ROOT, 'themes', 'config', 'Config.ini'), 'rb').read()


def parse(blob: bytes) -> configparser.ConfigParser:
    cp = configparser.ConfigParser()
    cp.read_string(blob.decode('ascii'))
    return cp


def flatten(blob: bytes) -> dict[tuple[str, str], str]:
    """Every value keyed (section, key). configparser lowercases key names."""
    cp = parse(blob)
    return {(s, k): v for s in cp.sections() for k, v in cp[s].items()}


def declared(mapping: dict) -> dict:
    """The declarations above, in the case configparser reports."""
    return {(s, k.lower()): v for (s, k), v in mapping.items()}


@pytest.mark.stock
def test_the_golden_fixture_is_the_file_that_is_in_the_firmware(stock, golden_ini):
    part = stock.partition(ROOTFS_PARTITION)
    node = minfs.find(part, TARGET)
    assert not node.compressed
    assert part[node.offset:node.offset + node.stored] == golden_ini


def test_the_stock_file_parses_into_29_sections(golden_ini):
    assert len(parse(golden_ini).sections()) == SECTION_COUNT


def test_the_keys_this_task_reads_are_present(golden_ini):
    cp = parse(golden_ini)
    assert cp['BACKLIGHT']['backLightMode'] == '0'
    assert cp['STARTUP']['startUpDefVolume'] == '10'
    assert cp['RADIO']['radioArea'] == '6'


def test_every_declared_change_starts_from_the_value_it_claims(golden_ini):
    """A stale 'from' value would silently turn a change into a no-op."""
    stock = flatten(golden_ini)
    for key, (was, _) in declared(CHANGED).items():
        assert stock[key] == was, key
    for key in declared(ADDED):
        assert key not in stock, key
    assert ADDED_SECTION not in parse(golden_ini).sections()


def test_the_working_copy_changes_exactly_the_declared_keys(golden_ini,
                                                           working_ini):
    stock, now = flatten(golden_ini), flatten(working_ini)

    moved = {k: (stock[k], now[k]) for k in stock if now.get(k) != stock[k]}
    assert moved == declared(CHANGED)

    added = {k: v for k, v in now.items() if k not in stock}
    assert added == {**declared(ADDED),
                     **declared({(ADDED_SECTION, k): v
                                 for k, v in ADDED_SECTION_KEYS.items()})}

    assert [k for k in stock if k not in now] == [], 'a key was removed'


def test_the_working_copy_adds_one_section_and_removes_none(golden_ini,
                                                            working_ini):
    was, now = parse(golden_ini).sections(), parse(working_ini).sections()
    assert set(now) - set(was) == {ADDED_SECTION}
    assert set(was) - set(now) == set()
    cut = was.index('DVD')
    assert now[:cut] == was[:cut], 'the existing sections were reordered'


def test_the_working_copy_keeps_the_encoding_and_every_line_ending(working_ini):
    assert working_ini.decode('ascii')
    assert working_ini.count(b'\n') == working_ini.count(b'\r\n')
    assert working_ini.count(b'\r') == working_ini.count(b'\r\n')
    assert b'\t' not in working_ini


def test_the_added_section_carries_the_six_wanted_presets(golden_ini,
                                                          working_ini):
    """Fields 2..7 of FM1 are the six preset cells; 1, 8 and 9 stay stock.

    Field 2 is measured - it moved the first cell on the device. The other five
    ride on the same reading and are what this delivery tests.
    """
    src = dict(parse(golden_ini)['AMERICA2'])
    added = dict(parse(working_ini)[ADDED_SECTION])
    assert set(added) == set(src)
    assert [k for k in src if added[k] != src[k]] == ['fm1']

    was, now = src['fm1'].split(','), added['fm1'].split(',')
    assert len(was) == len(now) == 9
    assert now[1:7] == ['10260', '9980', '9090', '9130', '9050', '9200']
    assert [now[0], now[7], now[8]] == [was[0], was[7], was[8]]
    assert [i for i, (a, b) in enumerate(zip(was, now)) if a != b] == [1, 2, 3, 4, 5, 6]


def test_no_source_gain_is_pushed_past_what_the_stock_file_attests(golden_ini,
                                                                   working_ini):
    """100 is the highest *VolGain the vendor ships. Above it is unattested."""
    stock, now = flatten(golden_ini), flatten(working_ini)
    gains = [k for k in stock if k[1].endswith('volgain')]
    assert len(gains) == 10
    ceiling = max(int(stock[k]) for k in gains)
    assert ceiling == 100
    for k in gains:
        assert int(now[k]) <= ceiling, f'{k} is above anything the vendor ships'


@pytest.mark.stock
def test_the_wallpaper_the_working_copy_names_exists_in_the_rootfs(stock,
                                                                  working_ini):
    """A misspelt file name would leave the setting silently doing nothing."""
    part = stock.partition(ROOTFS_PARTITION)
    name = parse(working_ini)['SETUP']['wallPaper']
    paths = {f.path for f in minfs.files(part)}
    assert f'/apps/WallPaper/{name}' in paths
    assert '/apps/WallPaper/0.jpg' in paths, 'the default named in init.axf'


def test_the_new_default_volume_stays_inside_the_files_own_limits(working_ini):
    """§9: startUpDefVolume=5 must not fall below startUpMinVolume."""
    startup = parse(working_ini)['STARTUP']
    low = startup.getint('startUpMinVolume')
    default = startup.getint('startUpDefVolume')
    high = startup.getint('startUpMaxVolume')
    assert low <= default <= high
