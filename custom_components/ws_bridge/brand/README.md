# WebSocket Bridge brand assets

A brand icon combining the geometric WebSocket CI mark (white and sky blue) with
a minimalist golden bridge span underneath, drawn by `scripts/generate_brand.py`
on a dark navy rounded square, with a matching sky blue `WS Bridge` wordmark for
the landscape logo.

| File | Size | Purpose |
| --- | --- | --- |
| `icon.png` | 256 × 256 | Home Assistant and HACS icon |
| `icon@2x.png` | 512 × 512 | High-resolution icon |
| `logo.png` | 1055 × 256 | Landscape integration logo; README artwork |
| `logo@2x.png` | 2110 × 512 | High-resolution landscape logo |

All images are RGBA PNGs with transparent outer corners and backgrounds. These
sizes follow the [HA brand image guidelines](https://contributors.home-assistant.io/core/integrations/brands/).
Home Assistant 2026.3 and later serves these assets from the integration's local
`brand/` directory. The sky blue wordmark works against light and dark
backgrounds, so separate dark variants are not required.

## Source and permission

The icon is drawn from geometric primitives in this repository's
`scripts/generate_brand.py` and is covered by the repository's MIT license
(Copyright (c) 2026 eigger). The wordmark is rendered with Pillow's bundled
Aileron Regular via
[`ImageFont.load_default`](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.load_default).
[Aileron](https://dotcolon.net/font/aileron/) permits commercial use and is
released with no rights reserved. No font file is redistributed or loaded from
the system.

## Reproduce

Use Python 3.10 or newer and Pillow 12.3.0 (also supplied by HA 2026.10.2):

```sh
python -m pip install Pillow==12.3.0
python scripts/generate_brand.py
```

The script needs no network access and produces the same PNG bytes on every
run with that Pillow version.

SHA256 (Pillow 12.3.0):

- `icon@2x.png`: `213d37b017efb8b584a02dec1a597878828028aed4cb31b8067e1ded8fd3cf11`
- `icon.png`: `0b5e82d97c9eac54b001de09319f6ebe13a15b8cbab7d44a55a6846634c1f849`
- `logo@2x.png`: `7d201900aa23556890d4c2f504c0e3aee794fdbe862513996b482d8056fc1ef0`
- `logo.png`: `d3d6d3d2268a10b527ec40684c08eeb3ffcd211e6b13985da1d2fe9553a43988`

The local `brand/icon.png` is used by the
[HACS brands check](https://hacs.xyz/docs/publish/include/#check-brands).
These files do not imply inclusion in the HA brands repository. README pages
use `custom_components/ws_bridge/brand/logo.png`.
