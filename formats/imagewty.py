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

Payload layout (measured on the stock image, all 25 items):
    offset is a multiple of 1024
    [offset, offset+length)            payload
    [offset+length, offset+stored_len) zero fill, stored_len == align(length, 16)
    up to the next multiple of 1024    0xCD fill

dlinfo.fex (partition DLINFO) — download descriptor, pairs each flashed
partition with the partition holding its checksum:
    0x00  magic 0xfdce73ab
    0x10  record count
    0x20  records, 72 bytes each

dlinfo record:
    0x00  name[16]
    0x10  unknown, start_sector, unknown, size_sectors  (u32 each)
    0x20  subtype[16]        matches an item subtype
    0x30  vsubtype[16]       item subtype holding its V-sum
    0x40  unknown, unknown   (u32 each)
"""
import struct
from dataclasses import dataclass

MAGIC = b'IMAGEWTY'
ITEM_TABLE = 0x400
ITEM_SIZE = 1024
PAD_BYTE = 0xCD
ALIGN = 1024
STORED_ALIGN = 16

DLINFO_NAME = 'dlinfo.fex'
DLINFO_MAGIC = 0xfdce73ab
DLINFO_RECORDS = 0x20
DLINFO_RECORD_SIZE = 72

# data_udisk.fex is the ROOTFS payload; its length is declared in two places
# outside the image, so it may not change. See the ValueError below.
FIXED_SIZE_PARTITION = 'data_udisk.fex'


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


def vsum(partition: bytes) -> bytes:
    """V-partition value: 32-bit sum of little-endian u32 words, mod 2**32."""
    if len(partition) % 4:
        raise ValueError('partition length is not a multiple of 4')
    words = struct.unpack_from('<%dI' % (len(partition) // 4), partition)
    return struct.pack('<I', sum(words) & 0xffffffff)


def _v_pairs(dlinfo: bytes) -> dict[str, str]:
    """Map subtype -> V-subtype, as declared by the dlinfo.fex partition."""
    if struct.unpack_from('<I', dlinfo, 0)[0] != DLINFO_MAGIC:
        raise ValueError('not a dlinfo partition')
    count = struct.unpack_from('<I', dlinfo, 0x10)[0]
    pairs = {}
    for i in range(count):
        p = DLINFO_RECORDS + i * DLINFO_RECORD_SIZE
        subtype = dlinfo[p + 0x20:p + 0x30].decode('ascii', 'replace')
        vsubtype = dlinfo[p + 0x30:p + 0x40].decode('ascii', 'replace')
        pairs[subtype] = vsubtype
    return pairs


def build(image: bytes, replace: dict[str, bytes]) -> bytes:
    """Rebuild the image with the named partitions replaced.

    Header, item table and every unexplained byte are carried over from
    `image`; only offset/stored_len/length, image_size and the V-partitions
    of replaced partitions are recomputed.
    """
    items = parse(image)
    by_name = {it.name: it for it in items}
    unknown = set(replace) - set(by_name)
    if unknown:
        raise ValueError('no such partition: %s' % ', '.join(sorted(unknown)))

    # The vendor image ships boot_pkg_uboot_nor.fex twice, under two subtypes.
    # We do not know why, so a name that hits both is refused rather than
    # resolved: guessing would rewrite a bootloader the caller did not mean.
    for name in replace:
        clash = [it for it in items if it.name == name]
        if len(clash) > 1:
            raise ValueError(
                '%s is ambiguous: %d items carry that name, with subtypes %s '
                '- build() will not guess which one you meant'
                % (name, len(clash),
                   ', '.join(repr(it.subtype) for it in clash))
            )

    stock = by_name.get(FIXED_SIZE_PARTITION)
    new = replace.get(FIXED_SIZE_PARTITION)
    if stock is not None and new is not None and len(new) != stock.length:
        raise ValueError(
            '%s must stay %d bytes, got %d: its size is declared outside the '
            'image, by sys_partition_nor.fex (size=28544 sectors) and '
            'rootfs_ini.tmp (size=14272 KB), which this builder does not '
            'rewrite' % (FIXED_SIZE_PARTITION, stock.length, len(new))
        )

    # Indexed by item, not by name: two items may share a name.
    payload = [replace.get(it.name, extract(image, it)) for it in items]

    pairs = _v_pairs(next(payload[i] for i, it in enumerate(items)
                          if it.name == DLINFO_NAME))
    for i, it in enumerate(items):
        vsubtype = pairs.get(it.subtype)
        if vsubtype is None or it.name not in replace:
            continue
        for j, other in enumerate(items):
            if other.subtype == vsubtype:
                payload[j] = vsum(payload[i])

    out = bytearray(image[:ITEM_TABLE + len(items) * ITEM_SIZE])
    for i, it in enumerate(items):
        data = payload[i]
        stored = (len(data) + STORED_ALIGN - 1) // STORED_ALIGN * STORED_ALIGN
        offset = len(out)
        assert offset % ALIGN == 0
        out += data
        out += bytes(stored - len(data))
        out += bytes([PAD_BYTE]) * (-len(out) % ALIGN)
        p = ITEM_TABLE + i * ITEM_SIZE + 36 + 256
        _, pad1, _, pad2, _ = struct.unpack_from('<5I', image, p)
        struct.pack_into('<5I', out, p, stored, pad1, len(data), pad2, offset)
    struct.pack_into('<I', out, 0x18, len(out))
    return bytes(out)
