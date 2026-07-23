"""Pins /apps/Config.ini and the working copy that changes two of its keys.

Config.ini is the device's main configuration file - audio, backlight, radio,
CAN, steering wheel - so the only safe edit is a byte-level one: AGENTS.md rule
4 forbids "normalising" anything, and a round trip through configparser would
rewrite key order, comments and line endings without anyone noticing. These
tests therefore compare bytes, not parsed values, and use configparser only to
read.

    tests/fixtures/Config.ini   golden copy of the stock file, always available
    themes/config/Config.ini    the working copy, exactly two lines changed

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
CRLF_COUNT = 402

CHANGES = {'startUpDefVolume=10': 'startUpDefVolume=5',
           'backLightMode=0': 'backLightMode=2'}


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


def test_each_changed_key_occurs_exactly_once_as_a_whole_line(golden_ini):
    lines = golden_ini.split(b'\r\n')
    for old in CHANGES:
        assert lines.count(old.encode('ascii')) == 1


def test_the_working_copy_changes_exactly_the_two_declared_lines(golden_ini,
                                                                working_ini):
    was, now = golden_ini.split(b'\r\n'), working_ini.split(b'\r\n')
    assert len(now) == len(was)

    moved = {(a.decode('ascii'), b.decode('ascii'))
             for a, b in zip(was, now) if a != b}
    assert moved == set(CHANGES.items())


def test_the_working_copy_keeps_the_encoding_and_every_line_ending(working_ini):
    assert working_ini.decode('ascii')
    assert working_ini.count(b'\r\n') == CRLF_COUNT
    assert working_ini.count(b'\n') == working_ini.count(b'\r\n')
    assert working_ini.count(b'\r') == working_ini.count(b'\r\n')


def test_the_working_copy_changes_no_section_and_adds_no_key(golden_ini,
                                                            working_ini):
    was, now = parse(golden_ini), parse(working_ini)
    assert now.sections() == was.sections()
    for section in was.sections():
        assert list(now[section]) == list(was[section])


def test_the_new_default_volume_stays_inside_the_files_own_limits(working_ini):
    """§9: startUpDefVolume=5 must not fall below startUpMinVolume."""
    startup = parse(working_ini)['STARTUP']
    low = startup.getint('startUpMinVolume')
    default = startup.getint('startUpDefVolume')
    high = startup.getint('startUpMaxVolume')
    assert low <= default <= high
