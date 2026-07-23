---
name: build-theme
description: Replace F9070W UI sprites with your own PNGs and assemble out/LTTF133.img. Use when asked to change the firmware's look — a wallpaper, icon, button or splash — to create or edit a theme under themes/, to run tools/build.py, or to confirm that a built image changed exactly what was intended and nothing else.
---

# Build a theme

From the repository root. Requires an unpacked `stock/` tree — if you do not have
one, run `.claude/skills/unpack-firmware/` first. Read `AGENTS.md`.

**You cannot flash the result.** Rule 8: the recovery path is unverified, so
building is where this stops. Say so rather than implying the image is ready.

## 1. Find the sprite you want to replace

Every sprite is already exported at `stock/png/<Screen>/NN.png`. Browse them:

```bash
ls stock/png | head -20
ls stock/png/Main
```

The PNG's file name is the sprite index. To see the sizes and depths of a screen:

```bash
./.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from formats import datav1
screen = 'Main'
d = open(f'stock/rootfs/apps/Data/{screen}.data', 'rb').read()
for s in datav1.sprites(d):
    print(f'{s.idx:02}  {s.width:>4}x{s.height:<4} depth {s.depth}')
"
```

```
00   808x310  depth 4
01   160x160  depth 4
02   160x160  depth 4
03   160x156  depth 4
04   160x156  depth 4
05   274x274  depth 4
```

## 2. Lay the theme out

A theme is a directory of PNGs named after the sprite index they replace:

```
themes/vw/Main/10.png          replaces sprite 10 of Main.data
themes/vw/SystemBar/03.png     replaces sprite 3 of SystemBar.data
```

Screen directory names must match `stock/rootfs/apps/Data/<Screen>.data`
exactly, case included. Anything you do not supply keeps its stock bytes, so a
half-finished theme is legal and still boots.

Start from the stock export so the size is right by construction:

```bash
mkdir -p themes/vw/Main
cp stock/png/Main/10.png themes/vw/Main/10.png
# …edit themes/vw/Main/10.png…
```

### Constraints — the build refuses anything else

* **Width and height must equal the stock sprite's, exactly.** There is no
  scaling and no cropping.
* **Depth is fixed by the stock sprite, not by your PNG.** Depth 4 = BGRA8888
  (alpha preserved), depth 3 = BGR888 (**alpha is discarded**), depth 2 = RGB565
  (banding on gradients is expected). Check the depth before you design.
* **The sprite index must exist** in that screen.
* You may add PNGs for screens or indices you like, but you may not add a sprite,
  remove one, or resize the screen.

Row padding, the layout section, the record headers and every unexplained field
of a replaced sprite are carried over from the sprite it replaces — see rule 4 in
`AGENTS.md` and `docs/formats/datav1.md`. Do not try to build a `.data` by hand.

## 3. Build

```bash
./.venv/bin/python tools/build.py vw --img
```

`vw` is a name under `themes/`; an absolute or relative path to a theme directory
also works. Real output for a theme holding one edited PNG:

```
building theme "themes/vw"
  Main                     1/20 sprites
  1 screens, 1 sprites replaced
screens -> /Users/…/F9070W/tools/../out/apps/Data
  free tail 2663808 -> 2088256 bytes
image   -> /Users/…/F9070W/tools/../out/data_udisk.fex
img     -> /Users/…/F9070W/tools/../out/LTTF133.img
  image size 18252800 bytes
  V-sum Vdata_udisk.fex      a1763c1e -> f17d46a0
```

Roughly 6 seconds. Read every line:

* **`free tail`** — a replaced file that no longer fits in place is relocated
  into the free tail of the MINFS partition. It starts at 2 663 808 bytes and
  never grows back; if it reaches zero, the build fails. The partition size
  itself is fixed at 14 614 528 bytes and may not change (rule 6).
* **`image size 18252800`** — must always be exactly this. A different number
  means something resized and the build should have refused.
* **`V-sum`** — recomputed automatically. If you replaced sprites and see no
  V-sum line, something is wrong.

| flag | effect |
|---|---|
| none | writes the rebuilt `.data` screens to `out/apps/Data/` only |
| `--image` | also patches `out/data_udisk.fex` (the ROOTFS partition) |
| `--img` | also assembles the full `out/LTTF133.img` |
| `--out DIR` | write somewhere other than `out/` |

## 4. Confirm the result — do not skip this

First, the empty-theme control. It must reproduce the vendor image byte for byte:

```bash
mkdir -p /tmp/empty-theme
./.venv/bin/python tools/build.py /tmp/empty-theme --img >/dev/null
cmp out/LTTF133.img stock/LTTF133.img && echo BYTE-IDENTICAL
```

```
BYTE-IDENTICAL
```

If that fails, the toolchain is broken and nothing you build is trustworthy —
stop and go to `.claude/skills/verify-roundtrip/`.

Then rebuild your real theme and check that **exactly** the sprites you meant
changed, by unpacking the built image back down to sprite level:

```bash
./.venv/bin/python tools/build.py vw --img >/dev/null
./.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, '.')
from formats import datav1, imagewty, minfs

def rootfs(img):
    for it in imagewty.parse(img):
        blob = imagewty.extract(img, it)
        if blob[:5] == minfs.MAGIC:
            return blob

a = rootfs(open('stock/LTTF133.img', 'rb').read())
b = rootfs(open('out/LTTF133.img', 'rb').read())
changed = 0
for node in minfs.files(a):
    if not node.path.startswith('/apps/Data/'):
        continue
    x = a[node.offset:node.offset + node.stored]
    n = minfs.find(b, node.path)
    y = b[n.offset:n.offset + n.stored]
    if x == y:
        continue
    for p, q in zip(datav1.sprites(x), datav1.sprites(y)):
        if p.decode() != q.decode():
            print(f'{node.path} sprite {p.idx}  {p.width}x{p.height} depth {p.depth}')
            changed += 1
print(f'{changed} sprite(s) differ')
EOF
```

Real output for the one-PNG theme above:

```
/apps/Data/Main.data sprite 10  150x166 depth 4
1 sprite(s) differ
```

The count must match the number of PNGs in your theme. Anything extra is a bug
in the toolchain, not a quirk of yours.

## When the build fails

A wrong-sized PNG stops the build before anything is written:

```
ValueError: themes/vw/Main/10.png: is 100x100, stock sprite is 150x166
```

Other messages you may hit: `sprite N does not exist (stock has M)`,
`no stock screen named <X>.data`, `no pristine .img in stock/ - run
tools/unpack.py first`.

**A failed build leaves the previous `out/` in place.** `out/LTTF133.img` may be
an older image with a plausible timestamp. After any failure, fix the input and
rebuild before you look at `out/` again.

## Do not

* Do not flash. Rule 8, `docs/hardware.md`.
* Do not edit `stock/` to "fix" a sprite. Themes are the only input.
* Do not touch `formats/` to make a theme work — if a theme needs a code change,
  that change needs `.claude/skills/verify-roundtrip/` and its own tests.
