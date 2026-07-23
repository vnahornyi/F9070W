# Hardware

> # ⛔ DO NOT FLASH THIS DEVICE
>
> **The recovery path has not been verified on hardware.** Plan §12 records it as
> an open question, and it is still open. Until someone has actually restored a
> bricked unit — not read about it, not inferred it from the files below —
> flashing anything, stock or modified, risks a permanent brick with no way back.
>
> The gate is QA case 5 in the plan: flash the **unmodified** stock image via
> PhoenixSuit *and* via SD, and confirm the device boots both ways. Nothing else
> touches hardware until that passes.
>
> This page describes the recovery *machinery that exists in the image*. That is
> not the same as a recovery procedure that is known to work.

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

### On-device update — a lead, not a route

`init.axf` carries the default strings `LTTF133.img` / `appUpdateFile` and
`LTTMcu.bin` / `mcuUpdateFile`, and `Config.ini` sets `logoCardName=F:`. This
suggests the running firmware can update itself from a card, but neither the
trigger nor the required file placement has been established.

⚠️ UNVERIFIED: everything in this section. No route above has been executed. In
particular it is unknown whether an F9070W in FEL mode is reachable at all
without opening the case.

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
