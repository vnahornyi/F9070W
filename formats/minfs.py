"""MINFS - the read-only filesystem used by Melis on the ROOTFS partition.

Header:
    0x00  "MINFS"
    0x08  root_table_offset  (0x200)
    0x0c  root_table_size
    0x10  total entry count
    0x14  end of metadata region
    0x1c  image size

Directory entry (variable length, 4-byte aligned):
    0x00  u32 data_offset      (file: absolute data offset; dir: child table offset)
    0x04  u32 stored_size      (file: bytes on disk; dir: child table size)
    0x08  u32 original_size    (file: uncompressed size; dir: 0)
    0x0c  u16 entry_size       (20 + padded name length)
    0x0e  u16 attr             (1 = directory, 0 = file)
    0x10  u32 name_len
    0x14  name, NUL padded to a multiple of 4

A file is stored uncompressed when stored_size == original_size, otherwise it is
melis-lzma compressed (see melislzma.py). All apps/Data/*.data files are stored
uncompressed, which is why theming never needs the LZMA path.
"""
import struct
from dataclasses import dataclass, field

MAGIC = b'MINFS'


@dataclass
class Node:
    path: str
    entry: int          # offset of this entry in the image
    offset: int
    stored: int
    size: int
    is_dir: bool
    children: list = field(default_factory=list)

    @property
    def compressed(self) -> bool:
        return not self.is_dir and self.stored != self.size


def _read_entry(d: bytes, p: int, parent: str):
    off, stored, size = struct.unpack_from('<III', d, p)
    esize, attr = struct.unpack_from('<HH', d, p + 12)
    nlen = struct.unpack_from('<I', d, p + 16)[0]
    name = d[p + 20:p + 20 + nlen].split(b'\0')[0].decode('ascii', 'replace')
    path = f'{parent}/{name}'
    return Node(path, p, off, stored, size, attr == 1), esize


def walk(d: bytes) -> Node:
    if d[:5] != MAGIC:
        raise ValueError('not a MINFS image')
    root_off, root_size = struct.unpack_from('<II', d, 8)
    root = Node('', -1, root_off, root_size, 0, True)

    def rec(node: Node):
        p, end = node.offset, node.offset + node.stored
        while p < end:
            child, esize = _read_entry(d, p, node.path)
            if child.is_dir:
                rec(child)
            node.children.append(child)
            p += esize

    rec(root)
    return root


def files(d: bytes) -> list[Node]:
    out = []

    def rec(n):
        for c in n.children:
            rec(c) if c.is_dir else out.append(c)

    rec(walk(d))
    return out


def find(d: bytes, path: str) -> Node:
    for f in files(d):
        if f.path == path:
            return f
    raise KeyError(path)


def free_offset(d: bytes, align: int = 16) -> int:
    """First byte past all referenced data - start of the unused tail."""
    end = max(f.offset + f.stored for f in files(d))
    return (end + align - 1) // align * align


def replace(d: bytes, path: str, blob: bytes) -> bytes:
    """Replace a file's contents, always storing the new blob uncompressed.

    Writes in place when the new blob fits the original slot, otherwise relocates
    it into the free tail and repoints the entry. Directory tables and every
    header field are left untouched, so nothing outside this one entry moves.

    Because the entry is written with stored_size == original_size, this also
    works on files that were melis-lzma compressed: the replacement is stored
    raw, which sidesteps the fact that we cannot produce a valid melis-lzma
    stream. init.axf fits raw with ~1.3 MB of the free tail to spare. Whether
    the loader honours the raw form for .axf is UNVERIFIED - test on hardware
    you can recover before trusting it.
    """
    node = find(d, path)
    out = bytearray(d)

    if len(blob) <= node.stored:
        dst = node.offset
    else:
        dst = free_offset(d)
        if dst + len(blob) > len(d):
            raise ValueError(
                f'no room: need {len(blob)} bytes at {dst:#x}, image is {len(d):#x}')
    out[dst:dst + len(blob)] = blob
    struct.pack_into('<III', out, node.entry, dst, len(blob), len(blob))
    return bytes(out)
