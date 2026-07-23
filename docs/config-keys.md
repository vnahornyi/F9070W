# `Config.ini` keys

`stock/rootfs/apps/Config.ini`, 5761 bytes, CRLF line endings, 29 sections,
**311 key/value lines**. Read by `/apps/init.axf`.

Re-measured on the stock partition: the MINFS entry for `/apps/Config.ini` is at
offset 4 962 108, `stored = 5761`, `compressed = False`, and those bytes are
identical to both `stock/rootfs/apps/Config.ini` and the golden fixture
`tests/fixtures/Config.ini`. The file is pure CRLF — 402 `\r\n` and no bare `\n`
— splitting into 29 section lines, 311 key/value lines and 63 blank lines;
`configparser` agrees at 29 sections and 311 keys.

`themes/config/Config.ini` is the working copy. It changes eleven values, adds four keys
and adds one section, which makes it 6067 bytes; `tests/test_config_ini.py`
declares that list and fails if anything else moves. Five of the changes are
confirmed on hardware (`backLightMode`, `startUpDefVolume`, `wallPaper`,
`bLoudness`, and the fact that `[EUROPE]` is read at all); the rest are
experiments. Nothing on this page comes from that copy — every value quoted below
is the stock one unless it says otherwise.

| Change | Why | Status |
|---|---|---|
| `backLightMode` 0→2 | parking lights stop forcing the night theme | confirmed |
| `startUpDefVolume` 10→5 | start at volume 5 | confirmed |
| `carType` 22→19, `carModel=0` added | plain reverse guide lines instead of the parking-sensor scale | ⚠️ UNVERIFIED |
| `colorLampMode` 0→6 | red button backlight | ⚠️ UNVERIFIED |
| `bBackMute` 1→0, `bBackToMain` 0→1, `bBackToSource` 1→0, `bBackStopSource` 0→1 | reverse-gear behaviour the developer had before | ⚠️ UNVERIFIED |
| `bRadioSoundAtCarPlay` 0→1 + `bAudioOutputAutoCtrl=0` added to `[AUDIO]` | radio audio while CarPlay is on screen, attempt 3 | ⚠️ UNVERIFIED |
| `backLightNight` 40→50 | the value the developer's earlier config carried | ⚠️ UNVERIFIED |
| `wallPaper=12.JPG` added to `[SETUP]` | that wallpaper instead of the built-in default | confirmed |
| `bLoudness=1` added to `[AUDIO]` | Loudness on by default | confirmed |
| `carplayVolGain` 88→100 | CarPlay is ~6 dB quieter than radio at the same setting | ⚠️ UNVERIFIED |
| `[EUROPE]` section added, `FM1` fields 2–7 | the six wanted presets; the section is read and field 2 is measured | partly confirmed |

The experiments come from `docs/roadmap.md` items 2a/2b and from the earlier
`Config.ini` diffed in `docs/findings.md`. The table carries the status key by key
rather than once at the top, because these are the rows most likely to be read in
isolation.

Two categories are distinguished throughout:

* **present in the file** — the key literally appears in `Config.ini`, with the
  value shown;
* **default in code only** — the key name appears in `init.axf`'s key-name string
  table, in the same contiguous run as keys that *are* in the file, but the file
  does not set it. Adding it is untested.

Everything below was extracted from the real file and the real binary. No key on
this page was invented.

> ⚠️ Changing `Config.ini` is **not** on a verified path. The file is stored raw
> in MINFS so `minfs.replace()` can rewrite it — `tools/patchfile.py` is the
> front end for that — but see "Checksum" at the bottom, and see
> `docs/hardware.md`: flashing is currently forbidden.

## Present in the file

### `[SETUP]` (22)

`b12Hour=0` · `bBeepOn=0` · `bBrakeWarn=0` · `bScreenSave=1` · `bVideoOutput=1` ·
`bDateShow=1` · `bAnyKeyPowerUp=1` · `bBackOff=0` · `bEnableFrontCamera=0` ·
`bright=20` · `contrast=50` · `hue=20` · `saturation=50` · `language=0` ·
`animationType=0` · `idleReturnTime=1000` · `vcomVoltage=25` · `bBackMute=1` ·
`colorLampMode=0` · `wheelType=0` · `dateFormat=1` · `bBackLine=1`

### `[CONFIG]` (31)

`bArmBeep=0` · `bBackToMain=0` · `bBackToSource=1` · `bBackStopSource=0` ·
`bCapacitiveScreen=0` · `bFontBold=0` · `bEnableAddFont=0` · `bEnableCapture=0` ·
`bToastAsTip=1` · `mainID=0` · `maxVolume=33` · `uiType=2` · `uiBpp=24` ·
`photoConvertMode=1` · `usb0Speed=2` · `usb1Speed=2` · `screenResolution=1` ·
`supportLanguage=34052091` · `sourceValid=7287021` · `saleArea=0` ·
`arrowKeyMode=-1` · `maxVideoValue=100` · `saveMethod=0` · `brakeDetectGpio=-1` ·
`illDetectGpio=-1` · `usb0PowerGpio=321` · `defaultSource=Radio` ·
`defaultInterface=` · `logoPassword=112233` · `factoryPaswword=113266` ·
`logoCardName=F:`

`uiType=2` is what selects the UI set; `bUseUi1Config` (code-only, below) is the
neighbouring switch. `factoryPaswword` is the vendor's spelling — do not
"correct" it.

### `[DEBUG]` (4)

`bPrintLog=1` · `bPrintTouch=0` · `bPrintThreadCpuLoad=0` · `bUseLogBuffer=0`

`bPrintLog=1` is already on, which is why a debug UART would be cheap to exploit
if one is reachable.

### `[MCU]` (2)

`mcuChip=2` · `mcuSerialName=/dev/uart1`

### `[CAN]` (3)

`bArmCan=1` · `carType=22` · `canSerialName=/dev/uart5`

### `[ARM]` (3)

`armVolGain=88` · `armChannelA=0` · `armOutputVolume=38`

### `[AUDIO]` (4)

`audioChip=3` · `subwoof=0` · `minVolDB=-39` · `audioI2cName=`

### `[STARTUP]` (6)

`startUpDefVolume=10` · `startUpMinVolume=5` · `startUpMaxVolume=20` ·
`startUpDelayTime=1000` · `startUpResume=0` · `startUpVideoPath=`

`startUpDefVolume` is the volume the unit comes up at. `themes/config/Config.ini`
sets it to `5`, which the file's own neighbours bracket: `startUpMinVolume=5` ≤ 5
≤ `startUpMaxVolume=20`, asserted by
`test_the_new_default_volume_stays_inside_the_files_own_limits`.

**Confirmed on hardware by the developer:** with `themes/config/Config.ini`
delivered through `update/`, the unit comes up at volume 5. See
`docs/findings.md`.

⚠️ UNVERIFIED whether `startUpResume=0` is what makes that hold — the volume was
read after a start, not after deliberately setting a different one, powering the
unit down and starting it again (QA case 6). The two keys have not been
separated.

`bMaxVolumeAsDefVolume` is **not** in the stock file; it exists only as a string
in `init.axf`. Setting it to `1` here made the unit start at 20 instead of 5,
which is how the meta-test in `docs/findings.md` proved that keys absent from the
stock file are read at all. It is not in `themes/config/Config.ini` — it was a
probe, and it was reverted. ⚠️ UNVERIFIED that the `20` is `startUpMaxVolume`
being used as the default rather than a ceiling that happens to equal it.

⚠️ Do not read a start-up volume after an ordinary ACC cycle and treat it as this
section's answer: the same file gave 20, then 5, then 20 depending on how the
unit came up. `docs/findings.md` explains what that costs an experiment.

### `[RADIO]` (24)

`bArmRadio=1` · `radioChannelA=0` · `radioVolGain=88` · `radioMaxDac=799072` ·
`radioModule=11` · `radioArea=6` · `fmStopValue=15` · `amStopValue=35` ·
`stOpenValue=20` · `fmAdjChannel=58` · `fmMultipath=10` · `fmDetuning=5` ·
`amDetuning=10` · `bAmEnable=1` · `bAmLocEnable=0` · `bHaveRds=1` ·
`bRdsEnDefault=1` · `radioButtonType=0` · `bRadioBackgroundRun=1` ·
**`bRadioSoundAtCarPlay=0`** · `radioResetGpio=107` · `rdsInterruptGpio=-1` ·
`radioI2cName=/dev/twi1` · `radioPowerGpio=403`

`bRadioSoundAtCarPlay=1` was tested on hardware and **does not work**. See
`docs/findings.md` — the cause is a guard in `init.axf`, not the config.

#### `radioArea=6` and the zone names in `init.axf`

`init.axf` carries a contiguous run of eleven NUL-terminated zone names in
8-byte slots, starting at offset `0x1f3569` of `stock/rootfs/apps/init.axf`
(2 501 564 B on disk). Each name occurs exactly once in the binary except
`EUROPE`, whose second occurrence is the tail of `EASTEUROPE`. Measured slot by
slot:

```
idx  offset     slot  name
  0  0x1f3569     8  CHINA
  1  0x1f3571    16  AMERICA1
  2  0x1f3581     8  JAPAN
  3  0x1f3589    16  AMERICA2
  4  0x1f3599     8  RUSSIA
  5  0x1f35a1     8  MIDEAST
  6  0x1f35a9     8  EUROPE
  7  0x1f35b1     8  BRAZIL
  8  0x1f35b9    16  AUSTRALIA
  9  0x1f35c9    16  EASTEUROPE
 10  0x1f35d9     8  KOREA
```

The run is bracketed by `fmSoftMute` before it and `RadioSave.bin` after it.

**`radioArea=6` is EUROPE, confirmed on hardware.** With `radioArea` left at `6`,
an added `[EUROPE]` section changed what the FM page shows (`docs/findings.md`).
The unit therefore looks for the zone at position 6 of this run, which is the
first behavioural evidence that the run is an indexed table and not merely a pile
of strings. ⚠️ UNVERIFIED for every other position — one index was exercised, not
eleven — and no code was disassembled.

### `[AMERICA2]` and `[Brazil]` (5 each) — per-zone band plans

The only two sections in the file named after a zone. Identical in both:

```
FM1 = FM2 = FM3 = 7600,7600,9010,9810,10610,10800,7600,10,10
AM1 = AM2 = 520,520,600,1000,1400,1620,520,10,10
```

There is **no `[EUROPE]` section** in the stock file. `themes/config/Config.ini`
adds one.

**A section named after the active zone is read — confirmed on hardware.** An
added `[EUROPE]` with one changed field moved the first preset cell on the FM
page (`docs/findings.md`). The name match `[AMERICA2]` ↔ `AMERICA2` was only ever
suggestive; the behaviour is now measured.

**Field 2 of the nine is the first preset — confirmed on hardware.** Setting it
to `10260` put 102.6 in the first cell. Not a band floor, not a step.

⚠️ UNVERIFIED: **the remaining eight fields.** The reading that fits is field 1 =
band lower limit, fields 2–7 = the six preset cells, fields 8–9 = tuning steps —
one of its nine parts is measured and the rest ride on it. The delivery that
fills all six cells is what tests fields 3–7. Field 1 is left at the stock `7600`
in the working copy, because nothing has measured it: the procedure step that
would have was never reached.

⚠️ UNVERIFIED: what `AM1`/`AM2` mean in the same layout. `[EUROPE]` carries them
copied verbatim from `[AMERICA2]`, untouched.

⚠️ UNVERIFIED: how `saleArea` (`0`) and `radioArea` (`6`) select between the two
sections, and what happens when neither names the active zone.

### `[DVD]` (8)

`bArmDvd=1` · `bEnableDvd=1` · `bDvdInterlace=0` · `dvdVolGain=88` ·
`dvdChannelA=0` · `dvdChannelV=0` · `dvdVideoOffsetX=0` · `dvdVideoOffsetY=0`

### `[BT]` (10)

`btModule=1` · `btmChannelA=0` · `btVolume=18` · `btVolGain=90` ·
`btmVolGain=90` · `bBtMusicNeedConnect=0` · `btSerialName=` ·
`btCmdMicGain=AT#VN030606` · `btLocalName=SWL-BT` · `bBtLocalNameUnique=1`

### `[MEDIA]` (15)

`bEnableLicenseMedia=0` · `bMediaBackgroundPlay=0` · `bMediaSoftDecode=1` ·
`bDecodeHDPhoto=0` · `mediaMaxVol=100` · `mediaVolGain=100` · `mediaChannelA=0` ·
`mediaBright=46` · `mdiaConstast=47` · `mediaHue=50` · `mediaSaturation=91` ·
`usbDiskName=` · `usbDisk2Name=` · `sdCardName=` · `sdCard2Name=`

`mdiaConstast` and `tvConstast` / `videoConstast` are the vendor's spellings.

### `[TV]` (10)

`tvType=0` · `tvChannelA=0` · `tvChannelV=0` · `tvBright=46` · `tvConstast=47` ·
`tvHue=50` · `tvSaturation=91` · `tvVideoOffsetX=0` · `tvVideoOffsetY=0` ·
`tvSerialName=`

### `[VIDEO]` (17)

`auxVolGain=88` · `auxChannelA=1` · `aux2ChannelA=1` · `aux3ChannelA=11` ·
`auxChannelV=1` · `aux2ChannelV=-1` · `aux3ChannelV=4` · `backChannelV=0` ·
`frontChannelV=0` · `videoBright=10` · `videoConstast=50` · `videoHue=20` ·
`videoSaturation=50` · `auxDetectGpio=-1` · `cameraSwitch1Gpio=-1` ·
`cameraSwitch2Gpio=-1` · `frontAuxSwitchGpio=-1`

`backChannelV=0` is the reversing-camera video channel.

### `[LINK]` (21) — CarPlay / Android Auto

`bEchoCancel=1` · `echoDelayTime=200` · `echoCancelMode=4` · `bNoiseCancel=1` ·
`noiseCancelMode=3` · `bAutoGainCtrl=0` · `minAgcGain=0` · `maxAgcGain=15` ·
`noiseThreshold=150` · `micGain=70` · `usbIphoneLink=1` · `usbAndroidLink=2` ·
`carplayVolGain=88` · `carplayVolume=10` · `carplayIconLabel=` ·
`carplayI2cName=/dev/twi2` · `androidWifiMode=2` · `linkVolGain=88` ·
`wifiChannel=36` · `linkVideoWidth=1280` · `linkVideoHeight=720`

### `[BACKLIGHT]` (8)

`backLightGain=100` · `bBackLightReverse=0` · `bBackLightPowerCtrl=1` ·
`backLightMinValue=5` · `backLightMode=0` · `backLightDay=100` ·
`backLightNight=40` · `backLight=100`

`backLightMode` is not a boolean. Measured over the whole file: all **49** keys
whose name starts with `b` + a capital take only `0` or `1`, while the 14
`*Mode` / `*Type` keys range far wider (`echoCancelMode=4`, `carType=22`,
`arrowKeyMode=-1`), so a value above 1 here is in keeping with the file's own
convention rather than an anomaly.

**`backLightMode=2` was confirmed on hardware by the developer**:
with it set, switching the parking lights on no longer forces the unit into the
night theme, and they observed no side effect. That is a report from direct
observation on the device, not a measurement made here; it is what
`themes/config/Config.ini` sets. Re-confirmed by them after this repository's
own working copy was delivered through `update/`.

⚠️ UNVERIFIED: what any other value of `backLightMode` does, and whether `2`
changes how `backLightDay=100` / `backLightNight=40` are applied after dark. Only
the daylight case was observed. The experiment is to switch the parking lights on
in darkness and compare the panel brightness against stock.

### `[TOUCH]` (4)

`bTouchXYSwap=0` · `bTouchXReverse=1` · `bTouchYReverse=0` · `touchCalibData=`

### `[MIC]` (4)

`micCtrlType=0` · `micDetectGpio=-1` · `micSwitchGpio=-1` · `micSerialName=`

### `[MAINKEY]` (6)

`key0=45` · `key1=27` · `key2=28` · `key3=39` · `key4=59` · `key5=33`

### `[SCREENKEY]` (18)

Six on-screen buttons, `buttonNX` / `buttonNY` / `buttonNKey`. All six sit at
`X=860`:

| button | Y | Key |
|---|---:|---:|
| 1 | 219 | 17 |
| 2 | 329 | 71 |
| 3 | 5 | 16401 |
| 4 | 144 | 134 |
| 5 | 270 | 39 |
| 6 | 90 | 138 |

### `[PANELKEY1]` (14) / `[PANELKEY2]` (10)

Resistor-ladder panel keys, `buttonNVolt` / `buttonNKey`.

PANELKEY1: `8→224`, `54→33`, `76→1`, `137→2`, `149→3`, `196→63`, `241→91`.
PANELKEY2: `31→8`, `101→12`, `118→4`, `175→100`, `221→160`.

`panelKeyPassword` (code-only, default `260127`) presumably gates the calibration
screen for these — ⚠️ UNVERIFIED.

### `[SCREEN]` (2)

`rotateAngle=180` · `refreshRate=30`

### `[DAB]` (5)

`dabModule=1` · `dabChannelA=2` · `dabSerialName=/dev/uart4` · `dabBaudRate=9600`
· `bSyncDabTime=0`

### `[IRKEY]` (47)

`userCode=65280`, then 23 pairs `buttonNCode` / `buttonNKey`.

### `[CAR]` (2)

`seatRowNumber=0` · `seatColumnNumber=0`

### `[GPS]` (1)

`gpsVolGain=80`

## Default in code only

These key names appear in `init.axf`'s key-name string table, inside the same
contiguous runs as the keys that *are* in `Config.ini`, but the file never sets
them. The four the plan called out are marked.

From the `[SETUP]` run (between `b12Hour` and `bArmBeep`):

`TirePressureUnit` · `bIllCtrlScreen` · `bIllCtrlPanel` · `bBackEnable` ·
`bFixWheel` · `bColorLamp` · `bWheelHighResistor` · `screenSaveType` ·
`screenSaveTime` · `videoOutputFormat` · `avddVoltage` · `colorLampTime` ·
`backDump` · `fixWheelType` · `frontCameraTime` · `wallPaper`

From the `[CONFIG]` run (between `bArmBeep` and `logoCardName`):

**`bSavePowerOff`** · **`bUseUi1Config`** · `bUseSoftReset` · `bGpioPullUp` ·
`supportLanguage2` · `lvdsBits` · `brakeActiveLevel` · `illActiveLevel` ·
`bSyncPhoneTime` · `colorLampModeNum` · **`bNewWheelKey`** · **`sourceSave`** ·
`usb1PowerGpio` · `lvdsBitsGpio` · `antPowerGpio` · `colorLampGpioR` ·
`colorLampGpioG` · `colorLampGpioB` · `LampPowerGpio` · `panelKeyPassword`

The three password defaults sit in this run as value/name pairs
(`112233 logoPassword`, `113266 factoryPaswword`, `260127 panelKeyPassword`), so
`panelKeyPassword`'s default is `260127`. `bUseUi1Config` is also referenced by a
log format string: `CSystemSetup_SetUiID %d,save %d,bUseUi1Config %d`.

**One of them has now been set on hardware and it worked.**
`bMaxVolumeAsDefVolume=1`, added to `[STARTUP]`, changed the start-up volume —
see `docs/findings.md`. So a key that the stock file never contained is read and
acted on, and the inference "string in the key-name run ⇒ readable config key"
has one confirming case instead of none.

⚠️ UNVERIFIED that it generalises to the rest of the run, and ⚠️ UNVERIFIED what
any individual key here does — one key being read says nothing about what the
other 331 mean. Treat the list as candidates worth an experiment, not as
documented settings.

## Checksum

⚠️ UNVERIFIED: whether `Config.ini` is checksummed, and by what algorithm. Plan
§1 lists "`Config.ini` checksum" as out of scope and unsolved, and §2 lists the
algorithm as unknown. Until that is settled, assume a hand-edited `Config.ini`
may be rejected or may brick the boot. Nothing in this toolchain writes it.
