"""Allwinner IMAGEWTY firmware image (PhoenixSuit / LiveSuit), header version 0x0300.

Layout:
    0x00  "IMAGEWTY"
    0x08  header_version (0x0300)
    0x0c  header_size (0x60)
    0x18  image_size
    0x3c  num_files
    0x400 item table, 1024 bytes per entry

Item entry:
    0x00  filename_len (256)
    0x04  entry_size (1024)
    0x08  maintype[8]
    0x10  subtype[16]
    0x20  unknown
    0x24  filename[256]
    0x124 stored_len, pad, original_len, pad, offset
"""
import struct
from dataclasses import dataclass

MAGIC = b'IMAGEWTY'
ITEM_TABLE = 0x400
ITEM_SIZE = 1024


@dataclass
class Item:
    name: str
    maintype: str
    subtype: str
    offset: int
    stored_len: int
    length: int


def parse(data: bytes) -> list[Item]:
    if data[:8] != MAGIC:
        raise ValueError('not an IMAGEWTY image')
    num = struct.unpack_from('<I', data, 0x3c)[0]
    items = []
    for i in range(num):
        p = ITEM_TABLE + i * ITEM_SIZE
        maintype = data[p + 8:p + 16].decode('ascii', 'replace')
        subtype = data[p + 16:p + 32].decode('ascii', 'replace')
        name = data[p + 36:p + 36 + 256].split(b'\0')[0].decode('ascii', 'replace')
        stored, _, length, _, off = struct.unpack_from('<5I', data, p + 36 + 256)
        items.append(Item(name, maintype, subtype, off, stored, length))
    return items


def extract(data: bytes, item: Item) -> bytes:
    return data[item.offset:item.offset + item.length]
