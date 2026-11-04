"""Generate Home Assistant brand images for WebSocket Bridge.

The artwork combines the geometric WebSocket CI mark (white and sky blue) with
a minimalist golden bridge span underneath on a dark navy rounded square. It is
drawn from geometric primitives at 4x scale and downsampled, so no source
image, external font file or network access is needed. Run with Pillow 12.3.0
for reproducible PNGs.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BRAND = Path(__file__).resolve().parents[1] / "custom_components/ws_bridge/brand"
SIZE = 512
SCALE = 4
NAVY = "#1b2a41"
WHITE = "#ffffff"
CYAN = "#38bdf8"
YELLOW = "#ffd23f"
GOLD = "#f2a900"
WORDMARK = "#0ea5e9"

# Official WebSocket CI mark polygons (256 x 192.105 coordinate space).
WS_UPPER_LEFT: list[tuple[float, float]] = [
    (86.954, 134.08),
    (98.191, 122.844),
    (120.076, 144.729),
    (165.104, 144.729),
    (120.747, 100.288),
    (132.067, 88.968),
    (176.424, 133.326),
    (176.424, 88.296),
    (154.623, 66.495),
    (165.775, 55.342),
    (110.685, 0.0),
    (0.0, 0.0),
    (31.696, 31.696),
    (31.696, 31.78),
    (97.436, 31.78),
    (120.663, 55.007),
    (86.703, 88.967),
    (63.476, 65.74),
    (63.476, 47.712),
    (31.696, 47.712),
    (31.696, 78.905),
    (86.703, 133.912),
]

WS_TR_BRACKET: list[tuple[float, float]] = [
    (192.44, 144.645),
    (224.22, 144.645),
    (224.22, 68.339),
    (188.415, 32.535),
    (165.943, 55.007),
    (192.44, 81.504),
]

WS_BR_HOOK: list[tuple[float, float]] = [
    (224.304, 160.576),
    (113.452, 160.576),
    (86.954, 134.08),
    (64.314, 156.3),
    (100.119, 192.105),
    (256.0, 192.105),
]


def draw_icon() -> Image.Image:
    """Draw the 512px RGBA app icon."""
    s = SCALE
    image = Image.new("RGBA", (SIZE * s, SIZE * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)

    def box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
        return [x0 * s, y0 * s, x1 * s, y1 * s]

    def poly(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * s, y * s) for x, y in points]

    d.rounded_rectangle(box(0, 0, SIZE - 1, SIZE - 1), radius=104 * s, fill=NAVY)

    # 1. Official WebSocket CI mark (white upper-left terminal, sky-blue lower-right terminal).
    scale_ws = 1.34
    ox = (SIZE - 256.0 * scale_ws) / 2.0
    oy = 72.0

    def tx(
        pts: list[tuple[float, float]], dx: float = 0.0, dy: float = 0.0
    ) -> list[tuple[float, float]]:
        return [
            (((px + dx) * scale_ws + ox) * s, ((py + dy) * scale_ws + oy) * s)
            for px, py in pts
        ]

    d.polygon(tx(WS_UPPER_LEFT), fill=WHITE)
    d.polygon(tx(WS_TR_BRACKET), fill=CYAN)
    d.polygon(tx(WS_BR_HOOK), fill=CYAN)

    # 2. Minimalist geometric bridge span underneath (matching 45-degree chamfers + flat-footed arch).
    bridge_layer = Image.new("RGBA", (SIZE * s, SIZE * s), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bridge_layer)

    # Arch curves upward to meet the deck; clipped cleanly at y=372..436 so feet sit flat.
    def outer_arch(x: float) -> float:
        t = (x - 256.0) / 160.0
        return 374.0 + 62.0 * (t * t)

    def inner_arch(x: float) -> float:
        t = (x - 256.0) / 132.0
        return 396.0 + 40.0 * (t * t)

    arch_pts = [(float(x), outer_arch(x)) for x in range(96, 417, 2)] + [
        (float(x), inner_arch(x)) for x in range(388, 123, -2)
    ]
    bd.polygon(poly(arch_pts), fill=GOLD)

    # Horizontal bridge deck with 45-degree chamfered ends matching the WS mark.
    deck_pts = [
        (82.0, 368.0),
        (430.0, 368.0),
        (452.0, 390.0),
        (60.0, 390.0),
    ]
    bd.polygon(poly(deck_pts), fill=YELLOW)

    image.alpha_composite(bridge_layer)

    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    """Write icon.png, icon@2x.png, logo.png and logo@2x.png."""
    BRAND.mkdir(parents=True, exist_ok=True)
    icon = draw_icon()
    icon.save(BRAND / "icon@2x.png", optimize=True)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(
        BRAND / "icon.png", optimize=True
    )

    # Pillow bundles Aileron Regular, so regeneration needs no system fonts.
    font = ImageFont.load_default(size=320)
    bounds = font.getbbox("WS Bridge")
    wordmark = Image.new("RGBA", (bounds[2] - bounds[0], bounds[3] - bounds[1]))
    ImageDraw.Draw(wordmark).text(
        (-bounds[0], -bounds[1]), "WS Bridge", font=font, fill=WORDMARK
    )
    gap = 96
    logo = Image.new("RGBA", (SIZE + gap + wordmark.width, SIZE))
    logo.alpha_composite(icon, (0, 0))
    logo.alpha_composite(wordmark, (SIZE + gap, (SIZE - wordmark.height) // 2))
    logo = logo.crop(logo.getbbox())
    logo.save(BRAND / "logo@2x.png", optimize=True)
    logo.resize((logo.width // 2, logo.height // 2), Image.Resampling.LANCZOS).save(
        BRAND / "logo.png", optimize=True
    )


if __name__ == "__main__":
    main()
