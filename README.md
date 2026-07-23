# F9070W

Black-box reverse engineering of the firmware in the **F9070W** car head unit —
an Allwinner **F133 / D1s** (RISC-V RV64, XuanTie C906) running **Melis**,
Allwinner's RTOS, not Android. There is no vendor documentation and no source;
everything here was measured out of one stock image.

The toolchain unpacks that image down to individual pixels and puts it back
together again:

```
F9070W.rar → LTTF133.img (IMAGEWTY) → data_udisk.fex (MINFS) → apps/Data/*.data (DATAV1.0) → zlib → pixels
```

A theme built from the untouched stock PNGs reassembles an image that is
byte-identical to the vendor's. That test is the foundation everything else
rests on.

## ⛔ Do not flash this device

**The recovery path has never been verified on hardware.** PhoenixSuit and SD
recovery tooling is present inside the image, but nobody has ever restored a
unit with it — *present* is not *verified*. Until that is done, flashing
anything, stock or modified, risks a permanent brick with no way back.

Building is where this project stops. Read
**[`docs/hardware.md`](docs/hardware.md)** before going anywhere near the
device; it opens with the same warning and explains the gate.

## Quick start

```bash
python3 -m venv .venv && ./.venv/bin/pip install pillow pytest
make                                        # what is available
make unpack SRC=~/Downloads/F9070W.rar      # → stock/
make png                                    # → stock/png/<Screen>/NN.png
make test                                   # fast suite, ~1 s
```

`tools/unpack.py` opens the `.rar` with `bsdtar`, which ships with macOS.

A theme is a directory of PNGs named after the sprite index they replace:

```
themes/vw/Main/10.png        replaces sprite 10 of Main.data
themes/vw/SystemBar/03.png   replaces sprite 3 of SystemBar.data
```

Each PNG must match its stock sprite's exact width and height; the build refuses
anything else. Sprites you do not supply keep their stock bytes, so a
half-finished theme is legal. Start from the stock export (`stock/png/…`) so the
size is right by construction.

```bash
make build THEME=vw          # → out/apps/Data/*.data
make img   THEME=vw          # → out/LTTF133.img
```

`THEME` is a name under `themes/` or a path to a directory, and defaults to
`vw`. `themes/vw/` ships empty, so `make build THEME=vw` fails with `theme is
empty - nothing to build` until you put PNGs in it.

The control that must always hold — an empty theme reproduces the vendor image:

```bash
mkdir -p /tmp/empty-theme
make img THEME=/tmp/empty-theme
cmp out/LTTF133.img stock/LTTF133.img && echo BYTE-IDENTICAL
```

`make test-stock` (~3 min) runs the same checks over the whole stock tree; it
needs `stock/` unpacked. `make test` does not, and is what runs on a fresh
clone.

## Documentation

The format specifications live in `docs/`, written from re-measured data.

| Read | When |
|---|---|
| [`docs/findings.md`](docs/findings.md) | **First.** What has been proven and by which measurement, what was disproven, and what is still open |
| [`docs/hardware.md`](docs/hardware.md) | SoC, the 25 partitions, the recovery machinery in the image, service passwords |
| [`docs/formats/imagewty.md`](docs/formats/imagewty.md) | The `.img` container: item table, padding, V-sum checksum partitions |
| [`docs/formats/minfs.md`](docs/formats/minfs.md) | The read-only ROOTFS: entries, in-place patching, the free tail |
| [`docs/formats/datav1.md`](docs/formats/datav1.md) | A UI screen: sprites, pixel depths, row padding, the undecoded layout section |
| [`docs/formats/melis-lzma.md`](docs/formats/melis-lzma.md) | Why firmware *code* cannot be repacked yet |
| [`docs/config-keys.md`](docs/config-keys.md) | `Config.ini` keys — present in the file vs. defaults that only exist in `init.axf` |
| [`docs/roadmap.md`](docs/roadmap.md) | What is deliberately not done, and where to start on each |

## Procedures

Ready-made procedures, for a human or an AI, in `.claude/skills/`:

| Skill | When |
|---|---|
| [`unpack-firmware`](.claude/skills/unpack-firmware/SKILL.md) | `stock/` is missing or stale, or a stock-marked test skips |
| [`build-theme`](.claude/skills/build-theme/SKILL.md) | PNG → theme → `.img`, and confirming exactly what changed |
| [`verify-roundtrip`](.claude/skills/verify-roundtrip/SKILL.md) | **Mandatory** before any commit under `formats/` |
| [`reverse-format`](.claude/skills/reverse-format/SKILL.md) | Decoding something new without guessing |

## Before you change any code

Read **[`AGENTS.md`](AGENTS.md)**. It is not a style guide: every rule in it
exists because the mistake it forbids was actually made in this repository and
caught by a test. It applies to humans as much as to AI.

## Layout

```
formats/    imagewty · minfs · datav1 · melislzma
tools/      unpack · build · verify · mkfixtures
tests/      pytest; fixtures/ holds the committed golden files
docs/       the specifications
themes/     your PNGs
stock/      unpacked firmware — gitignored, regenerate with `make unpack`
out/        build output — gitignored
```
