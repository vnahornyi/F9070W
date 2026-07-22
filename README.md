# F9070W

Reverse-engineered toolchain for the F9070W car head unit — unpack the stock
firmware, redraw the UI, pack it back.

The unit runs **Melis** (Allwinner's RTOS), not Android. The whole chain is:

```
F9070W.rar → LTTF133.img (IMAGEWTY) → data_udisk.fex (MINFS) → apps/Data/*.data (DATAV1.0) → zlib → pixels
```

Every link is decoded. `tools/verify.py` rebuilds all 75 screens with no changes
and asserts the result is byte-identical to the original — if that ever fails,
the writer is lying and no theme built with it can be trusted.

```
screens byte-identical : 75/75
sprites                : 1128  (31.6 Mpx)
MINFS files            : 257 (188 stored uncompressed)
free tail              : 2663808 bytes (2.54 MB)
```

Feeding the untouched stock PNGs back through the full pipeline
(PNG → BGRA → row padding → zlib → `.data` → MINFS patch) reproduces the stock
partition with **0 bytes changed**. The toolchain adds no drift of its own.

## Setup

```bash
python3 -m venv .venv && ./.venv/bin/pip install pillow
```

`bsdtar` (ships with macOS) is used to open the `.rar`.

## Use

```bash
./.venv/bin/python tools/unpack.py ~/Downloads/F9070W.rar   # → stock/
./.venv/bin/python tools/unpack.py --png                    # → stock/png/<Screen>/NN.png
./.venv/bin/python tools/verify.py                          # regression guard
./.venv/bin/python tools/build.py vw --image                # → out/
```

A theme is just PNGs named after the sprite index they replace:

```
themes/vw/Main/00.png        replaces sprite 0 of Main.data
themes/vw/Main/09.png        replaces sprite 9 of Main.data
themes/vw/SystemBar/03.png
```

Each PNG must match the stock sprite's exact width and height — `build.py`
refuses anything else. Sprites you do not supply keep their stock bytes, so a
half-finished theme still boots. Start with `Main` (20 sprites), `SystemBar`,
`VolumeBar`, `MainApp`; that is most of what you look at day to day.

## Formats

### IMAGEWTY (`formats/imagewty.py`)
Allwinner firmware container, header version `0x0300`. Item table at `0x400`,
1024 bytes per entry, 25 partitions. Plaintext — no encryption.

### MINFS (`formats/minfs.py`)
Read-only filesystem on ROOTFS. Entry:

```
u32 data_offset      file: absolute; dir: child table offset
u32 stored_size      bytes on disk
u32 original_size    uncompressed size (0 for dirs)
u16 entry_size       20 + name padded to 4
u16 attr             1 = dir, 0 = file
u32 name_len
... name, NUL padded to a multiple of 4
```

A file is stored uncompressed when `stored_size == original_size`. **All 75
`apps/Data/*.data` are uncompressed**, which is why theming never touches the
LZMA path — the hardest part of the format is simply not on the critical path.

`replace()` patches a file in place, relocating into the 2.54 MB free tail when
the new blob outgrows its slot. Directory tables and header fields are never
rewritten, so nothing outside the one entry moves.

### DATAV1.0 (`formats/datav1.py`)
One UI screen: a layout section, then a sprite section.

```
0x00  "DATAV1.0" UTF-16LE
0x14  layout size  → sprite section starts here
0x30  u32 width, 0x34 u32 height
0x38  u32 window count
0x64  window name UTF-16LE, 208 bytes ("ViewShowWndWallPaper")
...   layout records                                  ← NOT decoded
[sprites]
  u32 count
  count × { u32 record_offset, u32 compressed_size }
  per sprite: 32-byte header {hsize, w, h, flags, format, data_offset, …} + zlib
```

Pixels are **BGRA8888 (132)**, **BGR888 (931)** or **RGB565 (65)**, with rows
padded to a 4-byte boundary (`stride = align4(width × depth)`). Depth is derived
from the decompressed length rather than a header field — exact, and verified
across all 1128 sprites.

Bytes `+0x18..0x20` of each sprite header are non-zero in 14 screens and their
meaning is unknown, so they are preserved verbatim. Zeroing them was the one
thing that broke the round-trip during development.

## What is not decoded

**The layout section** — everything between `0x64` and the sprite section.
Control positions, text colours, bindings to language-string IDs live there. You
can replace artwork today; you cannot yet move an element or restyle text.
Reversing it is tractable (flat structs, and `Black.data` is only 592 bytes)
but it is a separate project.

This matters for a VW/MIB look specifically: swapping bitmaps removes the
skeuomorphic chrome gauges, but element positions and text colours stay stock.
The typeface is `apps/font22.sft` (1.2 MB, another undecoded format). UI strings
are easy — `apps/Language/*.txt`, UTF-16 TSV, 27 languages.

**melis-lzma** (`formats/melislzma.py`) is approximate. Chunk boundaries are
recovered by scanning for the LZMA1 properties signature, which is a heuristic:
stock `init.axf` comes out 30 bytes long against its declared size. Fine for
reading strings out of a binary, not for rebuilding one. Compression is not
implemented and is not needed.

## Patching firmware logic

The SoC is an Allwinner **F133 / D1s — RISC-V 64-bit** (XuanTie C906), not ARM.
`u-boot_nor.fex` contains `riscv`, and `init.axf` disassembles as RV64GC (1193
`c.ret`, 4272 `jal` in the first 200 KB). Ghidra and `objdump` handle it.
`init.axf` is a flat binary, not ELF — load it at the base from the Melis app
header, with no symbols.

Rebuilding `init.axf` would normally be blocked by melis-lzma compression, which
is not implemented. The way around it: MINFS treats a file as uncompressed
whenever `stored_size == original_size`, so a patched binary can simply be
stored **raw**. It fits, with room left over:

```
init.axf  stored=1177392  uncompressed=2501564  grow=1324172
free tail=2663808  ->  fits, 1339636 bytes spare
```

`minfs.replace()` always writes raw and does this automatically. **Unverified on
hardware** — whether the loader honours the raw form for `.axf` has not been
tested. Note this only works for one or two large files: taking all 69
compressed files raw would need 5.6 MB against a 2.5 MB tail.

Config keys that `init.axf` reads but which are absent from the shipped
`Config.ini`, so they sit at built-in defaults: `sourceSave`, `bNewWheelKey`,
`bSavePowerOff`, `bUseUi1Config`, `panelKeyPassword` (`260127`).

(`bRadioSoundAtCarPlay` and `bRadioBackgroundRun` are **not** in that list —
both are present in the shipped `Config.ini`, at lines 115-116, explicitly set
to `1` and `0`. Setting `bRadioSoundAtCarPlay=1` was tested on hardware and
changed nothing observable.)

Audio routing goes through an
audio-focus system — `Link gain audio focus from %s[%d]` / `Link lose audio
focus to %s[%d]` — over the source list `Radio, Dab, Aux, Aux2, AndroidAuto,
CarPlayWireless, AutoWireless, AirPlay, AndroidWireless, EclinkWireless,
PaceWireless, Miracast, YouTube`.

### Why source switching is blocked during CarPlay

Switching source while CarPlay is connected is refused **in code**, not by
configuration. The evidence:

```
无效，CarPlay连接中                          "invalid, CarPlay connected"
CarPlay invalid for other link connected %d
Priority is important,SourceApp:%s,uiID:%d[%d<%d]
Priority is low,SourceApp:%s,uiID:%d[%d<%d]
StartSource %s
StartSource %s Fail,init no end
%s invalid,Change to default source %s,interface %s
```

There is a numeric priority comparison (`[%d<%d]`) between the running source
app and the requested one. Making APS/Band fall back to radio means neutering
that guard — a `StartSource` / priority patch. No config key reaches it;
`bRadioSoundAtCarPlay=1` was tested on hardware and changed nothing.

### melis-lzma: still the blocker for code patches

Chunk boundaries for `init.axf` are at input offsets `0, 904944, 1075560`, and
each chunk now decodes with **no error**. But the three chunks together yield
2_501_594 bytes against a declared 2_501_564 — 30 bytes of decoder tail noise,
because the chunks carry no end marker. The true per-chunk output lengths are
unknown, so everything after chunk 0 is shifted by an unknown few bytes.

Confirmation that this actually bites: a base-address solve over the apparent
pointer tables scores only 14/60 — noise. Alignment guesses (4/8/16/32) all land
on `c0=1646240, c1=564032, c2=291292` but none of them make the base converge.

**Until this is exact, RISC-V patching is not on solid ground** — and the
store-raw hatch does not help, because it still needs a correct binary to start
from. The real fix is to reverse the loader that decompresses `.axf`, which
lives in the kernel (`melis_pkg_nor.fex`), rather than to keep guessing.

Button codes in `[MAINKEY]`, `[SCREENKEY]`, `[PANELKEY1/2]` and `[IRKEY]` are
bare integers with no symbolic names anywhere in the binary. `[DEBUG]
bPrintLog=1` is already on, so the fastest way to map them is to watch the debug
UART while pressing keys, rather than reversing.

## Theme switching

`init.axf` resolves screen resources in this order:

```
apps\UI<N>\Data\<Screen>.data     ← theme N
apps\Data\<Screen>.data           ← stock fallback
```

`N` comes from `uiType` in `apps/Config.ini` (currently `2`). There is also a
GPIO path (`[UI] bGpioSelectUI`, `uiSelectGpio<n>`) and a Setup menu entry
*"Interface selection"* (界面选择, line 203 of `Language/Setup.txt`).

Shipping a theme as `apps/UI3/` instead of overwriting `apps/Data/` leaves the
stock theme untouched as a fallback — roll back by setting `uiType` rather than
reflashing. **This needs a MINFS writer** (creating a new directory), which is
not built yet; `build.py --image` currently patches files in place. The updater
also reads `\Update\UI<N>\` from a USB drive (`logoCardName=F:`), which may let
the device create that directory itself — worth testing first, it would remove
the need for a MINFS writer entirely.

## Before flashing anything

This is a NOR-flash unit. **Confirm you can restore the stock image before you
modify anything.** Recovery tooling is in `stock/partitions/`: `usbtool.fex`
(PhoenixSuit), `cardtool.fex` + `cardscript.fex` (SD card). This is the only
risk in the project that is not already handled, and it is fully preventable.

`apps/Config.ini` is checksummed — `init.axf` contains `config_checksum.bin` and
"Config file checksum fail". The algorithm has not been extracted, so change
`uiType` through the Setup menu, not by editing the file. Setup also has
Export/Import config file to USB.

## Layout

```
formats/    imagewty · minfs · datav1 · melislzma
tools/      unpack · build · verify
stock/      unpacked firmware — regenerate with unpack.py, not committed
themes/vw/  your PNGs
out/        build output
```
