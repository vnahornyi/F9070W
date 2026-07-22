"""Pins down what formats/melislzma.py currently cannot do.

This module is deliberately not on the theming path. The tests exist so that the
day someone makes decompress() exact - or implements compress() - the change is
noticed instead of silently assumed. The +30-byte discrepancy on init.axf is the
whole reason the module's docstring calls itself lossy.
"""
import pytest

from formats import melislzma, minfs

AXF = '/apps/init.axf'
DECLARED = 2_501_564
HEURISTIC = 2_501_594
BOUNDS = [0, 904944, 1075560]


def test_compress_exists_but_refuses():
    with pytest.raises(NotImplementedError):
        melislzma.compress(b'anything')


def test_props_signature_is_the_only_chunk_marker():
    assert melislzma.PROPS == b'\x5d\x00\x80\x00\x00'


def test_chunk_bounds_scans_for_every_occurrence():
    blob = b'..' + melislzma.PROPS + b'xx' + melislzma.PROPS
    assert melislzma._chunk_bounds(blob) == [2, 9]
    assert melislzma._chunk_bounds(b'no signature here') == []


@pytest.fixture(scope='module')
def axf(stock) -> tuple[bytes, int]:
    part = stock.partition('data_udisk.fex')
    node = minfs.find(part, AXF)
    return part[node.offset:node.offset + node.stored], node.size


@pytest.mark.stock
def test_init_axf_is_the_compressed_file_we_measured(axf):
    blob, size = axf
    assert size == DECLARED
    assert len(blob) == 1_177_392


@pytest.mark.stock
def test_chunk_boundaries_of_init_axf(axf):
    assert melislzma._chunk_bounds(axf[0]) == BOUNDS


@pytest.mark.stock
def test_decompress_overshoots_the_declared_size_by_thirty_bytes(axf):
    """The known inaccuracy, pinned to the byte."""
    out = melislzma.decompress(axf[0])
    assert len(out) == HEURISTIC
    assert len(out) - DECLARED == 30


@pytest.mark.stock
def test_passing_the_declared_size_only_truncates(axf):
    blob, size = axf
    sized = melislzma.decompress(blob, size)
    assert len(sized) == DECLARED
    assert sized == melislzma.decompress(blob)[:DECLARED]


@pytest.mark.stock
def test_output_is_good_enough_to_read_strings_out_of_the_binary(axf):
    out = melislzma.decompress(axf[0], axf[1])
    assert b'CarPlay' in out
    assert b'sourceSave' in out
