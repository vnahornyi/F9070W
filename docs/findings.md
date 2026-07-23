# Findings

The journal. Every entry says what was measured and what proves it. Where the
original plan (`F9070W-1`) said something different, the plan's claim is quoted
next to the measurement — the code and the tests win.

Nothing here is a belief. Anything believed but not demonstrated is marked
`⚠️ UNVERIFIED` with the experiment that would settle it.

---

## Disproven on hardware

### `bRadioSoundAtCarPlay=1` does not work

Setting `bRadioSoundAtCarPlay=1` in `[RADIO]` was tested on the device. Radio
audio still does not play while CarPlay is connected.

The cause is a guard in `/apps/init.axf`, not the config. Both strings are
present in the decompressed binary:

```
无效，CarPlay连接中
Priority is low,SourceApp:%s,uiID:%d[%d<%d]
Priority is low,TopApp:%s,uiID:%d[%d<%d]
Priority is important,SourceApp:%s,uiID:%d[%d<%d]
```

(The first is at byte 1 741 017 of `stock/rootfs/apps/init.axf`; the rest come
out of `strings -a`.)

So the audio-source arbitration refuses the request by priority before the config
flag is ever consulted. Making this work means patching `init.axf`, which means
melis-lzma has to become exact — see `docs/formats/melis-lzma.md`. Do not
re-litigate this by flipping the config again.

---

## Confirmed on hardware

Reported by the developer from direct observation on the device. Observation on
real hardware outranks anything read out of the binary — but it establishes only
what was actually seen, and the limits are recorded with each entry.

### `stalogo1.jpg` is the boot logo

Seen on screen during startup. Two byte-identical copies exist:

```
/res/stalogo1.jpg            44133 B  uncompressed  800x480 RGB JPEG
/apps/Logo/stalogo1.jpg      44133 B  uncompressed  same sha256
```

⚠️ **UNVERIFIED which copy is read.** The two are byte-identical, so seeing the
image on screen cannot distinguish them. Replace **both**. Settling it means
writing two *different* images and seeing which one appears.

It is a plain JPEG in the MINFS tree, not a DATAV1.0 sprite, so `tools/build.py`
does not touch it — patch it with `minfs.replace` directly.

### The recovery button is not a rollback

The button restores settings to the last state that was **flashed**, not to a
factory state baked into the SoC. Flash a modified `Config.ini` from USB and the
button afterwards restores *that* config.

This matters more than it looks: **the recovery button is not a safety net.**
A bad image cannot be undone with it, because it would restore the bad image's
own settings. Nothing in `docs/hardware.md`'s recovery section is replaced by it.

### A toolchain-built full image flashes and boots

The headline result of the project. A `LTTF133.img` produced by
`imagewty.build()` was flashed from a USB `update/` folder; the device came back
up with no regressions.

The image differed from stock only in `/res/stalogo1.jpg` and
`/apps/Logo/stalogo1.jpg` (a replaced 800x480 JPEG), plus the recomputed
`Vdata_udisk.fex`. It was audited before flashing, and the audit is the reason
this was a reasonable thing to do:

```
відмінних діапазонів: 367, всього 87276 B
  data_udisk.fex     366 ranges, 87272 B
  Vdata_udisk.fex      1 range,      4 B
header 0x00..0x400 identical, item table identical, other 23 partitions identical
files 257 -> 257, none moved, only the two JPEGs changed
sprites 1128 -> 1128, 0 changed
69 compressed files: 0 changed, init.axf byte-identical
free tail 2663808 -> 2663808, V-sum recomputed and correct
```

What this establishes:

- the flasher **accepts `imagewty.build()` output** — the two-region padding, the
  recomputed `offset`/`stored_len`/`length`/`image_size`, and the V-sum algorithm
  are all sufficient, not merely self-consistent;
- `vsum` is the **only** checksum that matters for `data_udisk.fex`. Had there
  been another integrity field anywhere in the header, table or partition, this
  image would have been rejected;
- the whole chain — `minfs.replace` → `imagewty.build` → flash → boot — is real.

What it does **not** establish: that a *bad* image can be undone, that sprite
edits specifically are safe (this image changed no sprite — see below), or that
the unit survives repeated cold starts (plan §8 case 8 is still unrun).

The one remaining difference between this and a sprite theme is
`datav1.rebuild()`, which is covered by round-trip tests over all 1128 stock
sprites and by the byte-identical whole-image test.

### The device updates itself from a USB stick

An `update/` folder on a USB stick is picked up on its own and the unit reboots
by itself. Both granularities are confirmed: **individual files** (`Config.ini`,
the boot logo) and a **full `LTTF133.img`**. That gives a graduated risk ladder —
a single cosmetic file is a far smaller step than rewriting `data_udisk.fex`
whole — but all three rungs now work.

⚠️ **UNVERIFIED: whether this survives a broken image.** The updater with the
progress UI lives in `/apps/init.axf` — the very partition a theme rewrites —
and its screens are in the binary (`SetupUpdate`, `SetupOtaUpdate`,
`ViewShowSliderUpdateProgress`, `UpdateMcu.bin`). If the app does not boot, that
updater is gone with it. The separate u-boot-level path (`usb update probe`,
`usb_update_efex`, `pburn` in `u-boot_nor.fex`) is USB-gadget flashing over a
cable and does not depend on the app — but it has never been exercised.

---

## `Config.ini`: measured, patched, delivered

### The file itself

Re-measured on the stock partition rather than taken from the plan:

```
minfs entry /apps/Config.ini   offset 4962108  stored 5761  compressed False
partition bytes == stock/rootfs/apps/Config.ini == tests/fixtures/Config.ini : True
5761 bytes, 402 CRLF, 0 bare LF
29 section lines, 311 key/value lines, 63 blank lines
configparser: 29 sections, 311 keys
[BACKLIGHT] backLightMode = 0
[STARTUP]   startUpDefVolume = 10, startUpMinVolume = 5, startUpMaxVolume = 20
[RADIO]     radioArea = 6, bRadioSoundAtCarPlay = 0, bRadioBackgroundRun = 1
zone-named sections present: ['AMERICA2', 'Brazil']   'EUROPE' in sections: False
```

Every one of those agrees with what the plan claimed, which is worth saying only
because the rule is to re-run it rather than repeat it.

`init.axf` carries eleven zone names in a contiguous run of 8-byte NUL-terminated
slots at `0x1f3569`, `CHINA … KOREA`, listed slot by slot in
`docs/config-keys.md`. When this was written it was ⚠️ UNVERIFIED that a name's
position in that run is the value `radioArea` takes — a run of strings is not an
indexed array. Position 6 has since been exercised on the device and holds; see
"A section named after the zone IS read" below. The other ten positions are still
unexercised.

### A golden fixture for it, and why rule 11 has nothing to say

`tests/fixtures/Config.ini` now pins the stock file so a clone without `stock/`
can still assert against it. Rule 11 governs *regenerating* a fixture — an
expected value that moved is either a regression or a finding, and either needs a
paragraph. This fixture is new: no existing expected value changed, and the bytes
were measured identical to both the partition slice and the unpacked tree before
being committed. There is nothing to explain, which is the point of writing it
down.

### What `tools/patchfile.py` proves

Feeding the stock file back in unchanged reproduces the vendor image exactly:

```
/apps/Config.ini  5761 -> 5761 bytes, in place;  free tail 2663808 -> 2663808
cmp out/LTTF133.img stock/LTTF133.img  ->  BYTE-IDENTICAL
```

Feeding in `themes/config/Config.ini` — the two-line change — moves exactly what
it should and nothing else. Full differential audit, re-run for this entry:

```
payloads changed: 2 of 25 -> data_udisk.fex (DATA_UDISK_FEX00),
                              Vdata_udisk.fex (VDATA_UDISK_FEX0)
partition size   14614528 -> 14614528
rootfs files     257 -> 257,  changed 1 -> ['/apps/Config.ini'],  moved 0
compressed blobs 69,   changed 0,   init.axf identical: True
screens 75, sprites 1128 -> 1128, changed 0
free tail 2663808 -> 2663808
vsum(new partition) = 0x39249d4f  ==  Vdata_udisk.fex in the new image
```

The two-key edit makes the file 5761 → 5760 bytes, so it stays in its stock slot
and no other entry moves. The V-sum is recomputed and matches, as rule 7 requires.

This is the same shape of audit that preceded the flash recorded above under
"Confirmed on hardware", one layer narrower: that image changed two JPEGs, this
one changes one text file.

### The two-key change, confirmed on hardware

`themes/config/Config.ini` — the whole file, not an image — was delivered
through `update/` by the developer and applied. Both keys do what they were
changed for:

* **`startUpDefVolume=5`** — the unit comes up at volume 5.
* **`backLightMode=2`** — switching the parking lights on no longer forces the
  night theme, and the daylight brightness is unaffected.

That is a report from direct observation on the device, not a measurement made
in this repository. It also confirms the delivery route end to end for a file
this toolchain produced: a text file, alone, through `update/`, revertible by
putting `tests/fixtures/Config.ini` back the same way.

Not separated by this observation: ⚠️ UNVERIFIED whether `startUpResume=0` is
what makes the volume hold. The reading was taken after a start, not after
deliberately setting a different volume, powering down and starting again. Nor
was the backlight watched after dark — only the daylight case was seen.

### The parser reads keys the stock file never had — and the file is not read at every start

The meta-test, run by the developer. `bMaxVolumeAsDefVolume=1` — a key that
exists as a string in `init.axf` and **nowhere in the stock `Config.ini`** — was
added to `[STARTUP]` and delivered through `update/`. Observed, in order:

| Event | Volume at start |
|---|---|
| straight after the config was applied | **20** |
| after an ordinary ACC power cycle | **5** |
| after Reset Factory | **20** |

Two independent things fall out of that.

**1. A key absent from the stock file is read and acted on.** This was the gate
on everything else in this area, and it is now open: code-only keys are not
decorative. `bAirPlayBackground`, `bAudioOutputAutoCtrl`, `bLinkVol` and the rest
of the `init.axf`-only inventory in `docs/config-keys.md` are worth trying, and a
`[EUROPE]` section is worth trying. ⚠️ UNVERIFIED that a *section* the stock file
lacks is read — a key and a section are read by different code, and only the key
case was observed.

**2. `Config.ini` is not consulted on every start.** The same file produced 20,
then 5, then 20 again without changing. The reading that fits: the file is
consumed into persistent settings when it is applied and again on Reset Factory,
and an ordinary start reads those stored settings, not the file. That is
consistent with what the recovery button already does — see "The recovery button
is not a rollback" above, which found it restores the last *flashed* state.
⚠️ UNVERIFIED as a mechanism; no store was located and no code was read.

**This changes how every later experiment must be run.** An ACC cycle alone can
show a stored value and hand you a false negative — the experiment looks like it
failed when the file was simply never re-read. Read the result immediately after
applying the config, or force a Reset Factory, before writing anything down. Any
future negative result obtained by ACC cycle alone is not a result.

⚠️ UNVERIFIED that the `20` is `startUpMaxVolume=20` being used as the default
rather than an absolute ceiling that happens to be 20. Changing `startUpMaxVolume`
to something else and repeating would separate them.

### An earlier `Config.ini` from the same device, diffed against stock

The developer kept the `Config.ini` that was on the unit before the current
firmware. It is not derived from this stock file — it comes from another build —
but it ran on this hardware, which makes it evidence rather than a suggestion.
Diffed key by key against `tests/fixtures/Config.ini`:

```
size 5465 B vs 5761;  CRLF 0, bare LF 409;  one stray tab;  pure ASCII
sections 29 vs 29, same order;  keys 318 vs 311
```

**It has no CRLF at all and it worked.** The stock file is pure CRLF and this
repository's working copy keeps that, but the parser evidently accepts bare LF.
Worth knowing before anyone treats a line-ending change as the cause of a
failure.

**Eight keys that the stock file does not contain**, accepted the same way:
`videoOutputFormat` · `avddVoltage` · `backDump` (in `[SETUP]`), `lvdsBits`
(`[CONFIG]`), `carModel` (`[CAN]`), `startUpMaxTalkVolume` (`[STARTUP]`),
`btMicGain` · `btHeadsetMicGain` (`[BT]`). That is an independent confirmation of
the meta-test above, from a file nobody wrote for the purpose.

Eleven values differ:

| Key | stock | earlier file |
|---|---|---|
| `[SETUP] bBackMute` | 1 | 0 |
| `[SETUP] colorLampMode` | 0 | **6** |
| `[CONFIG] bBackToMain` / `bBackToSource` / `bBackStopSource` | 0 / 1 / 0 | 1 / 0 / 1 (tried, then put back to stock) |
| `[CAN] carType` | 22 | **19** |
| `[RADIO] bRadioSoundAtCarPlay` | 0 | **1** |
| `[LINK] micGain` | 70 | 65 |
| `[LINK] wifiChannel` | 36 | 161 |
| `[BACKLIGHT] backLightMode` | 0 | **2** |
| `[BACKLIGHT] backLightNight` | 40 | 50 |

Three of those are worth more than the rest:

* **`carType=19`.** With the earlier file the reverse-camera screen drew plain
  guide lines; on stock it draws the parking-sensor scale. The firmware has two
  screens for this — `Back.data` (7 sprites) and `Back2.data` (66, of which 64
  are identical 22×108 bars, the same bars `CarRadar.data` is built from). ⚠️
  UNVERIFIED that `carType` is what selects between them; it is the strongest
  candidate in the diff and the developer has no parking sensors and no CAN bus.
* **`colorLampMode=6`.** The developer reports the button backlight was red under
  that file. Reported from their own use of the device, not measured here.
  `init.axf` also carries `bColorLamp`, `colorLampModeNum`, `colorLampTime` and
  `colorLampGpioR/G/B`, none of them in `Config.ini`, so the lamp is an RGB
  device driven per-mode. ⚠️ UNVERIFIED that `6` means red rather than a cycle
  that happens to sit on red.
* **`bRadioSoundAtCarPlay=1` was already set in that file.** So the negative
  result recorded under "Disproven on hardware" came from this exact
  configuration. Worth re-running as the control experiment now that we know an
  ACC cycle may not re-read the file at all.

⛔ **Do not deliver that file as-is**, and this repository does not. It carries
`avddVoltage=50` and `lvdsBits=8` — panel supply voltage and LVDS bit depth for a
different build. Wrong display electrical parameters are the one change in this
whole area that a config reflash does not undo. Individual keys are cherry-picked
onto the stock-derived working copy instead.

### The floating button over CarPlay is a window with a switch, not a drawn control

Removing a control was assumed to need the undecoded `DATAV1.0` layout section
(`docs/roadmap.md` item 3). For this particular control it does not. `init.axf`
carries, as separate strings, a config key and the view that reads it:

```
0x1ce469  bLinkDot            (key-name table; NOT a key in Config.ini)
0x1a89e1  ViewShowWndLinkDot
0x1a8c71  ViewShowButtonDot
0x1b9951  ViewShowStrSwLinkDot
```

So it is a window the firmware shows or hides, and there is a settable flag
behind it. ⚠️ UNVERIFIED that `bLinkDot=0` hides it — the reading rests on the
naming convention (all 49 `b`-prefixed keys in the stock file take only 0 or 1)
and on `Wnd`/`Button`/`Sw` sitting next to the key name. Nothing was
disassembled and nothing was tried on the device.

**The neighbours of that last string are the more useful find.** They are a
contiguous run of settings-screen field names:

```
ViewShowStrLvdsBits · ViewShowStrRadioModule · ViewShowStrCarType
ViewShowStrCarModel · ViewShowStrSwLinkDot · ViewShowStrColorLampMode
ViewShowStrColorLampTime
```

`carType`, `carModel`, `colorLampMode` and the link-dot switch are fields on one
screen — an engineering menu, whose password the config itself carries
(`factoryPaswword=113266`; see `docs/hardware.md`). ⚠️ UNVERIFIED which screen and
whether every field is editable there. If it is, three of the changes carried in
`themes/config/Config.ini` can be tried from the menu with no flash and no
revert step at all, which is strictly cheaper than an experiment through
`update/`. Worth checking before the next delivery, not after.

### Wallpaper, Loudness, and the EQ preset that has no key

Three more defaults were asked for. Two have a key; one does not, and saying so
is the finding.

**Wallpaper.** `wallPaper` is in the key-name table and not in `Config.ini`. The
string immediately before it in the table is `0.jpg` — the table stores a default
next to its key here, as it does for the three passwords — so the built-in
default is `/apps/WallPaper/0.jpg`. The rootfs ships six:

```
/apps/WallPaper/0.jpg   178936 B      /apps/WallPaper/5.JPG    86982 B
/apps/WallPaper/2.jpg    89326 B      /apps/WallPaper/9.jpg    88004 B
/apps/WallPaper/4.JPG     9983 B      /apps/WallPaper/12.JPG   85058 B
```

Note the mixed case: `12.JPG` is upper-case in the image, and the working copy
spells it that way. `tests/test_config_ini.py` asserts the named file is really
in the rootfs, because a misspelt name would leave the setting quietly doing
nothing. ⚠️ UNVERIFIED that the key takes a bare file name rather than a path.

**Loudness — not "lossless".** The bottom-left control on the audio screen is
Loudness: `ViewShowButtonLoudness`, `ViewShowStrLoudnessSw`, and `TipBox`
carries `LOUDNESS ON` / `LOUDNESS OFF` (`等响度`, the equal-loudness contour).
Two keys back it, both code-only: `bLoudness` (the switch) and `loudness` (a
level). The working copy sets `bLoudness=1` and leaves the level alone, since its
scale is unknown. ⚠️ UNVERIFIED.

**The EQ preset has no key, as far as the binary shows.** The nine presets exist
as views — `ViewShowButtonEqUser` · `EqRock` · `EqPop` · `EqLive` · `EqDance` ·
`EqClassic` · `EqSoft` · `EqJazz` · `EqFlat` — and the audio run of the key table
is:

```
audioChip · audioMode · maxEqNum · eqSegNum · subwoof · subwoofGain ·
bLoudness · loudness · minVolDB · initVolGain · audioI2cName
```

`maxEqNum` is a count of presets and `eqSegNum` a count of bands; `eq%d` and
`bassTab` further down are per-preset curve tables. **Nothing in that run selects
which preset is active.** `audioMode` sits next to `audioChip` and is far more
likely a codec/routing mode. Guessing a value for it would be a change to audio
routing made on a hunch, so nothing was added.

So "Pop by default" is not settable from `Config.ini` on present evidence. Pop
chosen in the menu persists in the settings store; it is only a Reset Factory
that would drop it. ⚠️ UNVERIFIED whether the default preset is compiled in or
lives in a key not in this table.

### Per-source volume trim exists, as keys and as sliders

Sources come out at different loudness — CarPlay quieter than radio, so switching
between them means reaching for the knob. The firmware already has a per-source
gain, and every one of them is in the stock `Config.ini`:

```
[RADIO] radioVolGain 88   [LINK]  carplayVolGain 88   [MEDIA] mediaVolGain 100
[LINK]  linkVolGain  88   [BT]    btVolGain      90   [BT]    btmVolGain    90
[VIDEO] auxVolGain   88   [DVD]   dvdVolGain     88   [ARM]   armVolGain    88
[GPS]   gpsVolGain   80
```

Each has a slider view and a label in `init.axf` — `ViewShowSliderRadioVolGain`,
`ViewShowSliderCarplayVolGain`, `ViewShowSliderMediaVolGain`,
`ViewShowSliderBtVolGain`, `…IpodVolGain`, `…AuxVolGain`, `…ArmVolGain`,
`…GpsVolGain`, `…DvdVolGain`, `…BtmVolGain`, `…LinkVolGain`.

**The sliders are not reachable.** The developer looked for them and they are not
in any menu on this unit. A view existing in the binary is not a view the user
can get to — the screen may belong to a build variant, or sit behind an entry
point nobody has found. So the file is the only handle, and "there is a slider
for it" is not an answer to "how do I change it".

Worth noting: **radio and CarPlay already carry the same 88** and are still
unequal by ear. So the imbalance is in the CarPlay path rather than in these
numbers, and matching them is a calibration, not an arithmetic correction.

**How far apart, measured by ear:** volume 10 on radio matches volume 15 on
CarPlay. The file gives `maxVolume=33` and `minVolDB=-39`, so if the steps are
uniform each is about 1.2 dB and the gap is roughly **6 dB**.

⚠️ UNVERIFIED what scale `*VolGain` is on, and that is what decides whether this
is fixable at all from here. If it is a linear percentage, moving CarPlay from 88
to 100 buys about **+1.1 dB** — a sixth of the gap. If it is closer to a dB trim,
12 units would overshoot. `mediaVolGain=100` is the highest value the vendor
ships and `gpsVolGain=80` the lowest; nothing establishes whether values above
100 are accepted, clamped, or clip.

The working copy therefore goes to `carplayVolGain=100` — the ceiling the vendor
itself attests — and `tests/test_config_ini.py` refuses to push any source gain
past it. If the gap only narrows slightly, the scale is linear and the next step
is an explicit probe above 100, which is untested ground and belongs in its own
delivery.

### A section named after the zone IS read, and field 2 of `FM1` is the first preset

The probe of `docs/roadmap.md` item 2b, step 1, run by the developer. A `[EUROPE]`
section was added as a copy of `[AMERICA2]` with a single field of `FM1` changed
to `10260`, and **the first preset cell on the FM page became 102.6**.

Two things are settled by that one observation:

* **The parser looks for a section named after the active zone.** With
  `radioArea=6` the unit read `[EUROPE]`, a section the stock file does not
  contain. The name match `[AMERICA2]` ↔ `AMERICA2` was only ever suggestive;
  now it is measured.
* **Field 2 of the nine is the first preset.** Not the band floor, not a step.

That also settles, by implication, that `radioArea=6` selects EUROPE — the value
`6` and the name `EUROPE` at position 6 of the `init.axf` run now agree with an
observed behaviour rather than with each other alone.

Still ⚠️ UNVERIFIED: fields 3–7 as presets 2–6, field 1 as the band floor, and
fields 8–9 as tuning steps. The whole reading hangs together and one of its nine
parts is measured; the delivery that sets all six cells is what tests the rest.
Field 1 was deliberately left at the stock `7600` — nothing has measured it, and
step 2 of the procedure, which would have, was never needed.

### Confirmed and disproved by the same delivery

Four more results from the same round. Reported by the developer from the
device.

**Confirmed:**

* **`wallPaper=12.JPG`** — the wallpaper changed. So the key is read, and it
  takes a bare file name, not a path.
* **`bLoudness=1`** — Loudness comes up on.

Both were code-only keys, which makes them the second and third independent
confirmations that keys absent from the stock file are honoured.

**Disproved:**

* **`bAirPlayBackground=1` does not give radio audio under CarPlay.** This was
  B1 attempt 2 and the most promising of the four. The behaviour is worth
  recording precisely: the source switches the moment CarPlay is opened, whether
  by the on-screen button or by the MODE key, **even when nothing is playing in
  CarPlay**. So it is not audio arbitration losing to an active stream — opening
  the screen alone takes the source. That fits the guard in `init.axf` refusing
  by priority, and it narrows what a future patch would have to change: the
  handover happens at screen entry, not at first audio.
* **`bLinkDot=0` does not hide the floating button over CarPlay.** The key is
  read from the file — that much is established by the two confirmations above —
  so either `0` is not the value that hides it, or `bLinkDot` is not what draws
  it. The button remains, and with it the layout route (`docs/roadmap.md` item 3)
  as the only other idea. ⚠️ UNVERIFIED which of the two.

Both disproved keys were taken back out of `themes/config/Config.ini`. A key with
no observed effect left in a config is noise that the next reader has to
re-disprove.

### The six presets land, and `bBackTo*` is about reverse gear, not the back button

Round three on the device.

**Fields 3–7 of `FM1` are presets 2–6 — confirmed.** All six cells came up as
asked: 102.6, 99.8, 90.9, 91.3, 90.5, 92.0. With field 2 already measured, eight
of the nine fields now have a meaning that has been observed rather than
inferred. Field 1 remains ⚠️ UNVERIFIED — it was never changed — and so do
fields 8–9.

**`colorLampMode=6` is red — confirmed.**

**B1 attempt 3 is negative.** `bAudioOutputAutoCtrl=0` with
`bRadioSoundAtCarPlay=1`: radio audio still stops the moment CarPlay is entered.
Three of the four cheap combinations are now spent. Removed from the working
copy.

**`carplayVolGain=100` changed nothing perceptible.** The gap stayed at about
five volume steps. So either the key is not the lever, or the range 88→100 is
too small to matter, or values are clamped somewhere before the output. Put back
to the stock 88, and the other CarPlay volume key — `carplayVolume`, `10` in
stock against `btVolume=18` for Bluetooth — is tried instead. One lever at a
time; `15` is chosen because five steps is exactly the measured gap.

### `bBackToMain` / `bBackToSource` / `bBackStopSource` are reverse-gear keys

Worth writing down because the names invite exactly one wrong reading. These
three are not about the back **button**; the `Back` in them is the reverse gear,
the same `Back` as in `bBackMute`, `bBackOff`, `bBackLine`, `backDetectGpio`,
`backChannelV` and `Back.data`. The key-name table places them in that company:

```
… colorLampMode · colorLampTime · wheelType · dateFormat · backDump ·
fixWheelType · frontCameraTime · wallPaper · bArmBeep ·
bBackToMain · bBackToSource · bBackStopSource · bCapacitiveScreen …
```

So they say what the unit does when reverse is **disengaged** — return to the
main screen, return to the previous source, or leave the source stopped.
⚠️ UNVERIFIED in the sense that no code was traced, but the developer's own use
fits: `bBackStopSource=1` was being used as a way to stop the radio, by engaging
reverse.

The back button always landing on the main screen is therefore not something
these keys govern, and no key in the table obviously does. The hardware buttons
are mapped by code in `[MAINKEY]`, `[SCREENKEY]`, `[PANELKEY1/2]` and `[IRKEY]`,
so changing what a button does means knowing the key-code table — which is not
decoded. ⚠️ UNVERIFIED whether "return to previous source" exists as a code at
all.

### The radio starts itself because the config tells it to

`defaultSource=Radio` in `[CONFIG]`, and there is no stop control on the radio
screen — so the radio comes up at every start and cannot be turned off, only
switched away from. That is the root cause of the workaround above.

`defaultSource` and `defaultInterface` sit together in the key-name table, and
the stock file leaves `defaultInterface` empty. So **empty is an attested value
for this pair**, as it is for `startUpVideoPath=` and `audioI2cName=`. The
working copy empties `defaultSource` rather than naming another source, because
naming one means guessing a token.

The tokens are not a mystery, for the record: `init.axf` carries a run of source
names at `0x1a8029` — `Radio · Dab · Aux · Aux2 · AndroidAuto · CarPlayWireless ·
AutoWireless · AirPlay · AndroidWireless · EclinkWireless · PaceWireless ·
Miracast · YouTube` — and a separate run of screen names at `0x1a93e0` including
`Main`. ⚠️ UNVERIFIED that either run is what these two keys are matched against.

⚠️ **`defaultInterface` was deliberately left alone.** It is the one key in this
area where a wrong value could plausibly stop the unit reaching a usable screen,
and the `update/` recovery route runs inside the app it would break — see "The
device updates itself from a USB stick" above. An empty `defaultSource` cannot do
that; a made-up screen name might.

### Still open: the experiments nobody has run

* **Fields 3–7 of `FM1` as presets 2–6, field 1 as the band floor, 8–9 as
  steps.** ⚠️ UNVERIFIED. Field 2 is measured; the rest of the reading is what
  the next delivery tests.
* **Radio audio while CarPlay is connected.** Two of the four cheap combinations
  are now spent — `bRadioSoundAtCarPlay=1` long ago, `bAirPlayBackground=1`
  above — both negative, and the second showed the source is taken at screen
  entry rather than at first audio. Attempts 3 and 4 remain, in
  `docs/roadmap.md`.
* **What hides the floating button over CarPlay.** `bLinkDot=0` did not.
* **The EQ preset default**, and the scale `*VolGain` is on. Both above.
* **Whether `carType=19` restores the plain reverse guide lines, and whether
  `colorLampMode=6` gives a red backlight.** Both shipped in the same delivery as
  the results above and neither was looked at yet.

---

## Corrections to the plan's §2

### 1. IMAGEWTY padding is two regions, not one

**Plan said:** "IMAGEWTY: 25 partitions, alignment 1024, padding is the byte
`0xCD`", proved by "rebuild with `0xCD` → BYTE-IDENTICAL REBUILD: True".

**Measured:** there are two fill regions per item — zeroes from `offset+length`
to `offset+stored_len` (where `stored_len == align(length, 16)`), then `0xCD` up
to the next 1024 boundary. Whole-image filler histogram over all 25 items:

```
{0x00: 70, 0xCD: 8128}
```

Filling both regions with `0xCD` does not reproduce the image.

Pinned by `test_filler_is_zeroes_up_to_stored_len_then_cd_up_to_the_boundary` and
`test_whole_image_filler_histogram_is_seventy_zeroes_and_8128_cd`.

⚠️ UNVERIFIED (carried over from the plan): whether `0xCD` is a stable vendor
convention or an artefact of this one build. Needs a second vendor image.

### 2. Sprite record headers come in two sizes

**Plan said:** "bytes `+0x18..0x20` of the sprite header are non-zero in 14
screens, purpose unknown".

**Measured:** the distinction is the **header size**, and the tail never varies.

```
header sizes {24: 788, 32: 340}
screens per header size {24: 55, 32: 14}, overlap 0
32-byte tails seen: {b'\x01\x00\x00\x00\x00\x00\x00\x00'}
```

788 sprites across 55 screens have a 24-byte header and therefore no
`+0x18..0x20` bytes at all. 340 sprites across 14 screens have a 32-byte header
whose `+0x18..0x20` is *always* `01 00 00 00 00 00 00 00`. No screen mixes the
two. Pinned by `test_stock_header_sizes_split_55_and_14_screens`.

⚠️ UNVERIFIED: what the 32-byte variant signals. A constant value carries no
information; a second firmware image with a different value would.

### 3. `datav1.Sprite.pack()` used to zero the row padding — a real bug

**Plan said:** nothing; it assumed the existing `datav1` was "proven".

**Measured:** 543 of the 1128 stock sprites store **non-zero** row padding,
carrying 1020 distinct padding values, and the old `pack()` replaced all of it
with zeroes. Re-running the pre-fix behaviour as a simulation over the stock tree:

```
zeroed padding: 21/69 screens survive, 543/1128 sprites corrupted
```

A "change nothing" round-trip silently altered 48 of the 69 themeable screens.

Fixed in `abd3cd3`: `pack()` lifts the padding out of the sprite's own stored
buffer instead of synthesising it. `pack(pixels()) == decode()` now holds for all
1128 sprites (`test_no_stock_sprite_loses_its_row_padding`, 0 lossy).

This is what made the end-to-end "stock PNGs through the whole chain change zero
bytes" test achievable at all.

> Note on numbers: the implementation notes reported this as "11 of 36 screens
> reproduced before the fix, 36 of 36 after". That does not reproduce here. The
> measurement re-run for this document is **21 of 69** themeable screens
> surviving before the fix (75 screens exist, 69 carry at least one sprite, 6 are
> pure layout). The 543/1128 sprite figure does reproduce exactly.

### 4. `build()` was keyed by partition name, and two items share a name

**Plan said (§4 T08):** `build(image, replace: dict[str, bytes])` — a name-keyed
dict, silently assuming names are unique.

**Measured:** `boot_pkg_uboot_nor.fex` appears **twice** in the item table, under
subtypes `BOOTPKG-00000000` (offset 334 848) and `BOOTPKG-NOR00000` (offset
662 528). The payloads are identical today; the table entries are not.

Fixed in `ba46963`: payloads are indexed by item position, and replacing an
ambiguous name raises `ValueError` naming both subtypes rather than guessing.
This matters concretely — `cardscript.fex` (the SD recovery script) names
`BOOTPKG-NOR00000` specifically, so a wrong guess breaks a recovery route.

Pinned by `test_exactly_one_item_name_is_used_twice`,
`test_the_two_uboot_package_items_are_distinct_partitions` and
`test_replacing_an_ambiguous_name_raises_and_names_both_subtypes`.

### 5. The MINFS entry of a compressed file carries the real chunk table

**Plan said:** MINFS entry `+0x10` is `u32 name_len`; melis-lzma chunk boundaries
are recovered by scanning for the `5d 00 80 00 00` signature.

**Measured:** `+0x10`'s low 16 bits are the name length in all 257 entries, but
in exactly **69** entries the value exceeds `0x100` — and 69 is exactly the number
of compressed files. Those entries are oversized (`entry_size` 188..348 instead of
`20 + align4(namelen)`), and the surplus is always a multiple of 32 bytes: 5, 6 or
10 records.

The first u32 of each 32-byte record is an offset into the compressed blob. For
**66 of 69** files those offsets are exactly what the signature scan finds; the 3
that disagree are precisely the files the scan gets wrong:

| file | table | signature scan |
|---|---|---|
| `/mod/cedar/arec.plg` | `0, 2648, 2976, 3112, 0, 3144` | `0, 2976` |
| `/mod/charset.mod` | `0, 32, 936, 120740, 120740, 120740` | `32, 936` |
| `/mod/slib.mod` | `0, 216, 6996, 7564, 7564, 7564` | `216` |

`/apps/init.axf`'s entry literally contains `904944` and `1075560` — exactly the
boundaries `melislzma._chunk_bounds` rediscovers by scanning.

This is a **lead, not a decoded format.** ⚠️ UNVERIFIED: the meaning of every
column after the first. Columns 2 and 3 look like compressed/uncompressed chunk
sizes, but for `init.axf` they sum to 2 501 048 rather than the declared
2 501 564, so that reading is wrong or incomplete. Settling it needs the loader's
reader disassembled out of `init.axf`, or a second firmware image to diff.

Pinned by `test_compressed_entries_carry_an_oversized_record`.

### 6. `minfs._read_entry` is accidentally quadratic

**Plan said:** nothing; `minfs` was listed as "proven, tests only".

**Measured:** because `_read_entry` takes the whole `+0x10` u32 as a name length,
it slices up to `0x0140_0000` (20 MB) out of the partition before `split(b'\0')`
cuts it back. The parse is *correct* — names come out right — but one
`minfs.files()` call on the stock partition costs **1.38 s**, and `replace()`
calls it twice. That is why the stock suite runs for minutes.

Masking the field to its low 16 bits fixes finding 5's layout question and this
performance problem in one change. Not done yet — it belongs with the melis-lzma
work.

### 7. Pillow has a `BGR;16` decoder but no encoder

**Plan said:** nothing; PNG export/import was assumed symmetric.

**Measured:** `Image.new('RGB',(1,1)).tobytes('raw','BGR;16')` raises
`ValueError`, so `tools/build.py` packs RGB565 by hand (`rgb_to_565`, plus the
`_R5` / `_G6` quantisation tables). The packing is asserted to be the exact
inverse of Pillow's decoder over **all 65 536 code points**
(`test_rgb565_packing_inverts_the_decoder_for_every_code_point`) and over **all
65 depth-2 sprites** in the firmware
(`test_every_depth_two_sprite_survives_the_png_detour_with_zero_loss`).

The quantisation is lossy in principle — an 8-bit value the decoder never emits
would not survive — but every value in a stock-exported PNG does come out of the
decoder, so the **measured loss on stock content is zero**.
`test_pillow_still_has_no_bgr16_encoder` exists so the hand-rolled packer can be
deleted the day Pillow grows an encoder.

### 8. `vsum` rejects a short tail instead of ignoring it

**Plan said (§4 T07):** "a tail shorter than 4 bytes is ignored (stock partitions
have none — pin it with an assert)".

**Landed:** `vsum()` raises `ValueError('partition length is not a multiple of
4')`. Deliberate divergence: no stock partition has such a tail, so the branch
would never run on real data, and silently dropping bytes from a checksum is
exactly how a corrupted partition passes verification. Failing loudly costs
nothing and catches a caller who sliced a partition wrong.

Pinned by `test_vsum_rejects_a_length_that_is_not_a_multiple_of_four`.

### 9. V-partition pairing is derived, not hardcoded

**Plan said:** listed the two pairs as facts
(`DATA_UDISK_FEX00↔VDATA_UDISK_FEX0`, `MELIS_PKG_NOR_FE↔VMELIS_PKG_NOR_F`).

**Landed:** `imagewty._v_pairs()` reads them out of `dlinfo.fex` at build time, so
an image that pairs differently is handled without a code change. The two
expected pairs are asserted as a *fact about this image*, not baked into the
builder (`test_dlinfo_pairs_the_two_checksummed_partitions`).

`dlinfo` also independently corroborates the ROOTFS size: the `ROOTFS` record
declares 28 544 sectors, x 512 = **14 614 528** = exactly the `length` of
`data_udisk.fex`, which is also what `sys_partition_nor.fex` (`size = 28544`
sectors) and `rootfs_ini.tmp` (`size=14272` KB) say. Three independent
declarations, one number.

Note that `dlinfo`'s `size_sectors` is a *slot* size, not a payload length: the
`bootA` record declares 3200 sectors = 1 638 400 bytes for a
`melis_pkg_nor.fex` payload of 1 589 248. The ROOTFS match is exact only because
that partition fills its slot.

---

## Smaller corrections

### `free_offset` is not monotonic

**Plan said (§6):** "`free_offset` monotonic".

**Measured:** it is `align16(max(offset + stored))`, so shrinking whichever file
currently sits highest lowers it again. Pinned as-is by
`test_free_offset_grows_with_the_relocated_block_but_is_not_monotonic`, because
relocation depends on the actual behaviour, not the described one.

### The V-partitions are 4 bytes, not 16

**Plan said:** "`data_udisk.fex` is the second-to-last partition, followed only by
`Vdata_udisk` (16 B)".

**Measured:** `length = 4`, `stored_len = 16`. The 16 is the `align(4, 16)` slot,
zero-filled — see correction 1.

### 75 screens, but only 69 are themeable

Six of the 75 `/apps/Data/*.data` screens contain no sprite at all (pure layout),
so a theme can never reach them and `build_screens` never rewrites them. The
plan's "75/75" round-trip figure counts screens that rebuild identically, which
is a different measurement from screens a theme can touch.

---

## Confirmed as stated in the plan

Re-measured for this document; the plan was right about these.

| Claim | Measurement |
|---|---|
| SoC is Allwinner F133/D1s, RISC-V | `u-boot_nor.fex` strings: `U-Boot 2018.07 ... Allwinner Technology`, `Bad Linux RISCV Image magic!`, `allwinner,riscv`, `allwinner,sun20iw1p1-pinctrl` |
| 25 partitions, 1024-byte alignment | `imagewty.parse` on the stock image; every offset ≡ 0 mod 1024 |
| No checksum in the header or item table | `build(img, {})` is byte-identical without computing any CRC |
| V-sum = sum of LE u32 words mod 2^32 | `Vdata_udisk = 0x1e3c76a1`, `Vmelis_pkg_nor = 0x814cb3db`, both match |
| `data_udisk.fex` at offset `0x378000` | 3 637 248 = `0x378000`, and it is the second-to-last item |
| ROOTFS size fixed at 28544 sectors / 14272 KB | `sys_partition_nor.fex` and `rootfs_ini.tmp`, both = 14 614 528 B |
| MINFS: 257 files, 188 uncompressed | `minfs.files()`: 257 total, 188 raw, 69 compressed |
| All 75 `.data` screens stored uncompressed | `test_every_data_screen_is_stored_uncompressed` |
| Free tail = 2 663 808 bytes | `free_offset = 11 950 720`, partition 14 614 528 |
| 1128 sprites, 31.6 Mpx, depths 4/3/2 | `{4: 132, 3: 931, 2: 65}`, `stride = align4(w * depth)` for all |
| Stock PNGs back through the pipeline gives 0 changed bytes | `test_stock_pngs_through_the_whole_chain_change_zero_bytes` |
| melis-lzma overshoots init.axf by 30 bytes | 2 501 594 vs a declared 2 501 564; bounds `0, 904944, 1075560` |
| The compressed extensions are drv/mod/plg/axf | `rootfs_ini.tmp` `[COMPRESS_EXT] count=4` |
| 27 languages in `apps/Language/*.txt` | UTF-16LE TSV with a BOM, 29 columns: `//`, 原始, then 27 languages; 13 files |

---

## Open, unverified

* **The recovery path.** Not verified on hardware. Flashing is forbidden until it
  is. See `docs/hardware.md`. This is the single blocking item.
* **`0xCD` stability** across vendor builds — needs a second image.
* **Whether the loader accepts a formerly-compressed file stored raw.** `init.axf`
  would fit raw with ~1.3 MB of the free tail to spare, but nothing proves the
  loader tolerates it. Needs a device with a confirmed recovery path.
* **`Config.ini` checksum algorithm** — unknown; assume a hand-edited file may be
  rejected.
* **Whether `Config.ini`'s parser reads a section or a key that the stock file
  does not contain** — one meta-test settles both; see the `Config.ini` section
  above and `docs/roadmap.md`.
* **The nine fields of the per-zone `FM1`/`AM1` band plans**, and whether a
  zone's position in `init.axf`'s name run is the value of `radioArea`.
* **The 32-byte chunk-table record fields** — see correction 5.
* **The 32-byte sprite header's meaning** — see correction 2.
* **The DATAV1.0 layout section** — not decoded at all; copied verbatim.

## Rules that came out of this

* Never zero or "normalise" a byte you cannot explain. Corrections 1, 2 and 3 are
  all the same mistake in three places.
* A name is not an address (correction 4).
* When the plan and the measurement disagree, write the measurement down here
  before changing the code.
* Golden fixtures are never regenerated silently — a `tools/mkfixtures.py
  --update` needs an entry on this page explaining why the expected value moved.
