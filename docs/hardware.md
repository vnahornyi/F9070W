# Hardware

> # ⚠️ FLASHING WORKS. RECOVERY STILL DOES NOT.
>
> **Flashing a full image built by this toolchain is proven.** A rebuilt
> `LTTF133.img` — differing from stock only in two JPEG files — was flashed from a
> USB `update/` folder and the device came back up with no regressions. So the
> flasher accepts `imagewty.build()` output, the recomputed V-sums are sufficient,
> and the pipeline is sound end to end.
>
> **What is still unproven is getting back from a *bad* image.** No unbootable
> unit has ever been restored. The recovery button restores the last *flashed*
> settings, and the USB updater lives inside `data_udisk.fex` — the partition a
> theme rewrites. If the app stops booting, both are gone.
>
> So the rule is not "never flash". It is: **only flash an image this toolchain
> has verified**, and verify it before every flash — see
> `.claude/skills/verify-roundtrip/SKILL.md` and the audit below. An image that
> differs from stock anywhere you did not intend is not to be flashed.
>
> Still open: QA case 5 — restoring a unit via PhoenixSuit/USB or SD. Until that
> is done, a bad flash is a one-way door.

## SoC

Allwinner **F133 / D1s**, RISC-V RV64 (XuanTie C906).

Evidence, from `strings stock/partitions/u-boot_nor.fex`:

```
U-Boot 2018.07 (Nov 28 2023 - 17:42:08 +0800) Allwinner Technology
Bad Linux RISCV Image magic!
allwinner,riscv
allwinner,sun20iw1p1-pinctrl
allwinner,sun20iw1-nand
```

`sun20iw1` is Allwinner's internal name for the D1/D1s/F133 family. Storage is
SPI NOR flash (`*_nor.fex` throughout, `sunxi_mbr_nor.fex`, `boot0_nor.fex`).

The application OS is **Melis**, not Linux: a MINFS read-only filesystem
(`docs/formats/minfs.md`) holding `/apps/init.axf`, `/mod/*.mod` drivers and the
`/apps/Data/*.data` UI screens.

Firmware build identifier, `stock/rootfs/apps/Version.txt`:

```
swl-HT100-WF-8070-PQ-20260527-2006F133-20220107
```

## Partitions

25 items in the IMAGEWTY container. The full table with offsets and lengths is in
[`docs/formats/imagewty.md`](formats/imagewty.md). The ones that matter:

| item | what it is |
|---|---|
| `boot0_nor.fex`, `boot0_card.fex` | first-stage loader, NOR and SD variants |
| `boot_pkg_uboot_nor.fex` | u-boot package — **present twice**, subtypes `BOOTPKG-00000000` and `BOOTPKG-NOR00000` |
| `u-boot_nor.fex` | u-boot |
| `melis_pkg_nor.fex` | the Melis kernel package (`sunxi-package` container, 1 589 248 B) |
| `data_udisk.fex` | ROOTFS, MINFS, 14 614 528 B — everything themeable lives here |
| `Vmelis_pkg_nor.fex`, `Vdata_udisk.fex` | 4-byte checksums of the two above |
| `dlinfo.fex` | download descriptor; pairs each partition with its checksum partition |
| `sys_partition_nor.fex` | flash partition table: `ROOTFS size = 28544` sectors |
| `usbtool.fex`, `usbtool_crash.fex` | USB flashing tools |
| `cardtool.fex`, `cardscript.fex` | SD-card flashing tool and its script |
| `arisc.fex` | 15 bytes; contents unexamined |

The flash layout itself, from `stock/partitions/sys_partition_nor.fex`:

```
[mbr]  size = 16 (KB)
[partition] name = bootA   size = 3200   downloadfile = "melis_pkg_nor.fex"
[partition] name = ROOTFS  size = 28544  downloadfile = "data_udisk.fex"
[partition] name = UDISK   ro = 0        (no size, no downloadfile: the rest)
```

## Recovery machinery present in the image

Again: **present** is not **verified**.

### USB — PhoenixSuit

`usbtool.fex` is the flashing agent (maintype `PXTOOLSB`), with
`usbtool_crash.fex` as its crash variant (`PXTOOLCH`). Its strings name the host
tool directly:

```
PhoenixSuit
UsbTool.cfg
efex_verify_transfer_status
efex_verify_uboot_blk
download_packet, check_crc32_form_efex failed
```

The `efex` / FEL references mean the standard Allwinner USB recovery path: put
the SoC into FEL mode, PhoenixSuit uploads `fes1.fex` and then the partitions.
`fes1.fex` is item 11 of the image.

Note the verification strings — the flasher checks what it wrote. That is what
the V-partitions are for: an image whose `Vdata_udisk.fex` does not match its
`data_udisk.fex` will be rejected. `imagewty.build()` recomputes them
automatically; see `docs/formats/imagewty.md`.

### SD card — cardtool + cardscript

`cardtool.fex` plus `cardscript.fex`, which is a `card_script.cfg`:

```
[process]
version=300
mode=product          ; 0 null, 1 product, 2 bromrun, 3 update, 4 test
[boot_0_0]  main=12345678  sub=1234567890BOOT_0     start=16     ; boot0_card.fex
[boot_1_0]  main=12345678  sub=BOOTPKG-NOR00000     start=32800
[card_boot]
```

Note which u-boot subtype the SD path names: `BOOTPKG-NOR00000`, the **second**
of the two identically-named `boot_pkg_uboot_nor.fex` items. That is the concrete
reason `imagewty.build()` refuses to resolve that name by guessing — a wrong
guess there breaks exactly this recovery route.

### On-device update from USB — the one route that has actually been used

This is the only mechanism here that anybody has run. Reported by the developer
from direct use: an `update/` folder on a USB stick is picked up on its own, the
unit flashes and reboots by itself. It accepts **individual files** — `Config.ini`,
the boot logo — not only a full image.

`init.axf` carries the matching defaults `LTTF133.img` / `appUpdateFile`,
`LTTMcu.bin` / `mcuUpdateFile`, and `Config.ini` sets `logoCardName=F:`. The
progress UI is in the same binary: `SetupUpdate`, `SetupOtaUpdate`,
`ViewShowSliderUpdateProgress`, `ViewShowStrUpdateProgress`, `UpdateMcu.bin`.

**And that is exactly the problem.** This updater lives inside `/apps/init.axf`,
which lives inside `data_udisk.fex` — the partition a theme rewrites. If a bad
image stops the app from booting, this updater is gone with it. It is a
convenient update path, not a recovery path.

The recovery button does not cover that gap either: it restores settings to the
**last flashed** state, not to a factory baseline, so it would restore the bad
image's own settings. See `docs/findings.md`.

The u-boot-level path (`usb update probe`, `usb_update_probe_ok`,
`usb_update_efex`, `pburn`, `SUNXI_UPDATE_NEXT_ACTION_REBOOT` in
`u-boot_nor.fex`) is USB-**gadget** flashing over a cable — the PhoenixSuit/FEL
side, not a USB stick — and it runs before the app, so it would survive a broken
app. It has never been exercised.

⚠️ UNVERIFIED: whether the USB-stick updater can repair a unit whose app no
longer boots; whether an F9070W in FEL mode is reachable at all without opening
the case; and what the `update/` folder must contain for a **full image** as
opposed to a single file.

### Risk ladder

Established by what the developer has actually done, cheapest first:

1. a single cosmetic file (boot logo) via `update/` — done, works;
2. `Config.ini` via `update/` — done, works, and revertible the same way;
3. a full `LTTF133.img` via `update/` — **done, works.** A toolchain-built image
   was flashed and the unit booted with no regressions. See `docs/findings.md`.

All three rungs are proven. What is *not* proven is the rung below zero:
recovering a unit that no longer boots. That is why step 3 must always be
preceded by the differential audit — the audit is what stands in for a recovery
path that does not exist yet.

## Passwords

Service-menu passwords. `logoPassword` and `factoryPaswword` (the vendor's
spelling) are set in `stock/rootfs/apps/Config.ini`; `panelKeyPassword` is not in
the file and only exists as a default in `init.axf`, where the string table pairs
each default with its key name:

```
112233  logoPassword
113266  factoryPaswword
260127  panelKeyPassword
```

| key | value | source |
|---|---|---|
| `logoPassword` | `112233` | present in `Config.ini` |
| `factoryPaswword` | `113266` | present in `Config.ini` |
| `panelKeyPassword` | `260127` | default in code only |

⚠️ UNVERIFIED: what each password actually unlocks, and how the menus are
reached. The values are read out of the firmware, not confirmed on a device.

See [`docs/config-keys.md`](config-keys.md) for the rest of `Config.ini`.
