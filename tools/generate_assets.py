#!/usr/bin/env python3
"""Generate napRider-napoli97's indexed pixel art, palettes and stage maps.

Everything the cartridge draws is authored here, pixel by pixel, and written
to src/assets.h as packed palette-index data:

- a shared 16x16, 4-bpp tile bank whose pixels are *roles* (asphalt, wall,
  roof, water ...); each district supplies its own 16-colour palette;
- six 20x10 byte maps of semantic tile codes;
- the white 1971 Fiat 500 L, the scooter gangs and Virgil's Egg (4 bpp);
- Vesuvius, an island, the headlight beam (2 bpp / 1 bpp);
- eight-band sky gradients, one per district.

PRG32's ESP32-C6 framebuffer is 8-bit indexed. The firmware maps every sprite
colour to the cell of its 6x6x6 system cube, so two colours in the same cell
would be drawn with the same palette entry. This generator therefore keeps at
most one colour per cube cell among everything visible together, and the
cartridge programs that cell with the exact colour: the board and QEMU then
show the same pixels. Colliding colours are nudged into the nearest free cell.

The Store icon is cropped from the approved visual sheet in assets/source.
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "assets/source/naprider_visual_sheet.png"
OUT = ROOT / "assets/generated"
HDR = ROOT / "src/assets.h"
OUT.mkdir(parents=True, exist_ok=True)

T = 16
STAGE_W, STAGE_H = 20, 10
STAGES = ["CENTRO STORICO", "POSILLIPO", "QUARTIERI", "VOMERO", "VIRGILIANO", "SOTTERRANEA"]

# --------------------------------------------------------------------------
# Colour helpers: RGB888 -> RGB565 and the firmware's 6x6x6 cube cells
# --------------------------------------------------------------------------
NAMED = (0x0000, 0xFFFF, 0xF800, 0x07E0, 0x001F, 0xFFE0, 0x07FF, 0xF81F)


def rgb565(c):
    r, g, b = c
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def rgb888(v):
    r, g, b = v >> 11, (v >> 5) & 63, v & 31
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


def cell(v):
    """System palette index the firmware picks for an RGB565 colour."""
    if v in NAMED:
        return NAMED.index(v)
    return 16 + ((v >> 11) * 5 // 31) * 36 + (((v >> 5) & 63) * 5 // 63) * 6 + ((v & 31) * 5 // 31)


def _ranges(maximum):
    out = [[] for _ in range(6)]
    for v in range(maximum + 1):
        out[v * 5 // maximum].append(v)
    return [(r[0], r[-1]) for r in out]


R5, G6 = _ranges(31), _ranges(63)


def place(v, used, shared=()):
    """Return a colour for v whose cube cell is free in `used`.

    A colour landing in the cell of a shared sprite colour takes that colour
    (they are at most one cube step apart); otherwise it moves to the nearest
    free cell, measured in 8-bit RGB so hue is kept."""
    if v in NAMED or used.get(cell(v), v) == v:
        return v
    if cell(v) in shared:
        return shared[cell(v)]
    r, g, b = v >> 11, (v >> 5) & 63, v & 31
    best = None
    for cr in range(6):
        for cg in range(6):
            for cb in range(6):
                if 16 + cr * 36 + cg * 6 + cb in used:
                    continue
                nr = min(max(r, R5[cr][0]), R5[cr][1])
                ng = min(max(g, G6[cg][0]), G6[cg][1])
                nb = min(max(b, R5[cb][0]), R5[cb][1])
                cand = (nr << 11) | (ng << 5) | nb
                if cand in NAMED:
                    continue
                dr, dg, db = (nr - r) * 8.2, (ng - g) * 4.05, (nb - b) * 8.2
                dist = 3 * dr * dr + 4 * dg * dg + 2 * db * db + 6 * (dr - dg) ** 2 + 6 * (dg - db) ** 2
                if best is None or dist < best[0]:
                    best = (dist, cand)
    assert best, "system colour cube exhausted"
    return best[1]


def claim(colours, used, shared=()):
    """Place a list of RGB888 colours; returns their RGB565 values."""
    out = []
    for c in colours:
        v = place(rgb565(c), used, shared)
        if v not in NAMED:
            used[cell(v)] = v
        out.append(v)
    return out


# --------------------------------------------------------------------------
# Tiny pixel canvas working on palette indices
# --------------------------------------------------------------------------
class Canvas:
    def __init__(self, w, h, fill=0):
        self.a = np.full((h, w), fill, dtype=np.uint8)
        self.w, self.h = w, h

    def px(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.a[y, x] = c

    def rect(self, x0, y0, x1, y1, c):
        self.a[max(y0, 0):y1 + 1, max(x0, 0):x1 + 1] = c

    def hline(self, x0, x1, y, c):
        self.rect(x0, y, x1, y, c)

    def vline(self, x, y0, y1, c):
        self.rect(x, y0, x, y1, c)

    def ellipse(self, cx, cy, rx, ry, c):
        for y in range(self.h):
            for x in range(self.w):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                    self.a[y, x] = c

    def poly(self, pts, c):
        """Scanline fill of a simple polygon (pixel centres)."""
        for y in range(self.h):
            xs = []
            for i in range(len(pts)):
                (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                for x in range(int(np.ceil(xs[i])), int(np.floor(xs[i + 1])) + 1):
                    self.px(x, y, c)

    def outline(self, c, inside=None, empty=0):
        """Paint `c` on empty pixels that touch a painted pixel."""
        src = self.a.copy()
        for y in range(self.h):
            for x in range(self.w):
                if src[y, x] != empty:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < self.w and 0 <= yy < self.h and src[yy, xx] != empty:
                        if inside is None or src[yy, xx] in inside:
                            self.a[y, x] = c
                            break


# --------------------------------------------------------------------------
# Tile bank: pixels are palette *roles*, shared by every district
# --------------------------------------------------------------------------
K, AS, W2, YL, WH, PV, PS, WA, WAS, WB, RF, WD, WL, GD, GL, SK = range(16)
ROLE_NAMES = ["outline", "asphalt", "water light", "lane paint", "white paint", "pavement",
              "pavement shade", "wall A", "wall A shade", "wall B", "roof / accent",
              "window dark", "window lit", "green dark", "green light", "water deep / cut-out"]

(C_SKY, C_ROAD, C_DASH, C_CROSS, C_EDGE_T, C_EDGE_B, C_PIECE, C_PIECE2, C_PUMP, C_LAMP,
 C_BUILD_A, C_BUILD_B, C_DOOR, C_SHOP, C_ROOF_A, C_ROOF_B, C_SEA, C_SEAWALL, C_PARK, C_PINE,
 C_PLAZA, C_WALL, C_ARCH, C_TORCH, C_RUBBLE, C_COLUMN) = range(26)
CODE_COUNT = 26
CUTOUT = (C_ROOF_A, C_ROOF_B, C_PINE, C_COLUMN)       # role 15 is transparent in these


def road(c):
    c.rect(0, 0, 15, 15, AS)
    for x, y in ((3, 4), (11, 2), (7, 11), (13, 13), (1, 9)):
        c.px(x, y, K)
    c.px(9, 6, PS)
    c.px(4, 13, PS)


def edge_top(c):
    c.rect(0, 0, 15, 15, PV)
    for x in (0, 8):
        c.vline(x, 0, 9, PS)
    c.hline(0, 15, 5, PS)
    c.hline(0, 15, 10, WH)
    c.hline(0, 15, 11, PS)
    c.hline(0, 15, 12, K)
    c.rect(0, 13, 15, 15, AS)


def wall(c, base, shade):
    c.rect(0, 0, 15, 15, base)
    c.vline(0, 0, 15, shade)
    c.hline(0, 15, 15, shade)


def window(c, x, y, lit=False, shutter=RF):
    c.rect(x, y, x + 3, y + 5, WL if lit else WD)
    c.vline(x - 1, y, y + 5, shutter)
    c.vline(x + 4, y, y + 5, shutter)
    c.hline(x - 1, x + 4, y + 6, K)


def make_tile(code):
    c = Canvas(T, T, AS)
    if code == C_SKY:
        c.rect(0, 0, 15, 15, SK)
    elif code == C_ROAD:
        road(c)
    elif code == C_DASH:
        road(c)
        c.rect(3, 0, 10, 1, YL)
    elif code == C_CROSS:
        road(c)
        for y in (1, 6, 11):
            c.rect(2, y, 13, y + 2, WH)
    elif code == C_EDGE_T:
        edge_top(c)
    elif code == C_EDGE_B:
        c.rect(0, 0, 15, 2, AS)
        c.hline(0, 15, 3, K)
        c.hline(0, 15, 4, WH)
        c.rect(0, 5, 15, 15, PV)
        c.hline(0, 15, 5, PS)
        c.hline(0, 15, 11, PS)
        for x in (4, 12):
            c.vline(x, 6, 15, PS)
    elif code in (C_PIECE, C_PIECE2):
        road(c)
        c.poly([(8, 2), (13, 8), (8, 13), (3, 8)], YL)
        c.poly([(8, 4), (11, 8), (8, 11), (5, 8)], WL if code == C_PIECE else WH)
        c.px(8, 8, RF)
        c.outline(K, inside=(YL,), empty=AS)
        if code == C_PIECE2:
            for x, y in ((2, 2), (13, 3), (3, 13), (13, 13)):
                c.px(x, y, WH)
    elif code == C_PUMP:
        edge_top(c)
        c.rect(5, 1, 10, 9, RF)
        c.rect(6, 2, 9, 4, WH)
        c.hline(5, 10, 0, K)
        c.vline(4, 1, 9, K)
        c.vline(11, 1, 9, K)
        c.vline(12, 3, 7, K)
        c.px(13, 7, K)
        c.rect(6, 6, 9, 8, YL)
    elif code == C_LAMP:
        edge_top(c)
        c.vline(7, 2, 9, K)
        c.rect(5, 0, 9, 1, WL)
        c.px(4, 1, K)
        c.px(10, 1, K)
        c.hline(6, 8, 9, K)
    elif code == C_BUILD_A:
        wall(c, WA, WAS)
        window(c, 3, 2, lit=False)
        window(c, 10, 2, lit=True)
        c.hline(1, 15, 11, WAS)
        c.hline(2, 13, 12, K)                      # balcony rail
        for x in (2, 5, 8, 11, 13):
            c.vline(x, 12, 14, K)
    elif code == C_BUILD_B:
        wall(c, WB, WAS)
        window(c, 3, 7, lit=True, shutter=GD)
        window(c, 10, 7, lit=False, shutter=GD)
        c.hline(0, 15, 2, K)                       # washing line
        c.rect(2, 3, 4, 5, WH)
        c.rect(6, 3, 7, 6, RF)
        c.rect(10, 3, 13, 4, W2)
    elif code == C_DOOR:
        wall(c, WA, WAS)
        c.rect(5, 5, 10, 15, WD)
        c.rect(6, 4, 9, 4, WD)
        c.vline(8, 6, 15, K)
        c.px(7, 10, WL)
        c.rect(1, 1, 3, 3, WL)
        c.rect(12, 1, 14, 3, WD)
    elif code == C_SHOP:
        wall(c, WB, WAS)
        c.rect(1, 0, 14, 3, RF)                    # awning
        for x in (3, 7, 11):
            c.rect(x, 0, x + 1, 3, WH)
        c.hline(1, 14, 4, K)
        c.rect(2, 6, 13, 12, WL)
        c.rect(2, 13, 13, 13, K)
        c.vline(7, 6, 12, K)
        c.rect(3, 9, 5, 12, RF)
        c.rect(9, 8, 12, 12, GD)
    elif code == C_ROOF_A:
        c.rect(0, 0, 15, 15, SK)
        c.rect(0, 9, 15, 15, WA)
        c.vline(0, 9, 15, WAS)
        c.rect(0, 6, 15, 8, RF)
        c.hline(0, 15, 9, WAS)
        c.hline(0, 15, 5, K)
        c.rect(11, 1, 13, 5, WAS)                  # chimney
        c.hline(10, 14, 1, K)
        c.rect(3, 11, 6, 15, WD)
        c.vline(4, 0, 5, K)                        # antenna
        c.hline(2, 6, 1, K)
        c.hline(3, 5, 3, K)
    elif code == C_ROOF_B:
        c.rect(0, 0, 15, 15, SK)
        c.rect(0, 10, 15, 15, WB)
        c.vline(0, 10, 15, WAS)
        c.hline(0, 15, 10, WAS)
        c.ellipse(8, 9, 6, 6, RF)                  # dome
        c.rect(0, 10, 15, 15, WB)
        c.hline(0, 15, 10, K)
        c.vline(8, 0, 3, K)
        c.hline(7, 9, 1, K)
        c.rect(10, 12, 12, 15, WL)
        c.rect(3, 12, 5, 15, WD)
    elif code == C_SEA:
        c.rect(0, 0, 15, 15, SK)
        for y, off in ((2, 0), (7, 5), (12, 10)):
            for x in range(6):
                c.px((off + x) % 16, y - (1 if 1 < x < 4 else 0), W2)
            c.px((off + 2) % 16, y - 2, WH)
    elif code == C_SEAWALL:
        c.rect(0, 0, 15, 4, SK)
        c.hline(2, 7, 2, W2)
        c.rect(0, 5, 15, 15, PV)
        c.hline(0, 15, 5, WH)
        c.hline(0, 15, 10, PS)
        for x in (5, 13):
            c.vline(x, 6, 9, PS)
        for x in (1, 9):
            c.vline(x, 11, 14, PS)
        c.hline(0, 15, 15, WAS)
    elif code == C_PARK:
        c.rect(0, 0, 15, 15, GD)
        c.ellipse(5, 5, 4.5, 4, GL)
        c.ellipse(12, 10, 3.5, 3.5, GL)
        c.px(4, 4, WL)
        c.px(11, 9, WL)
        c.rect(5, 9, 5, 11, WAS)
        for x, y in ((1, 13), (9, 2), (14, 3), (2, 8)):
            c.px(x, y, GL)
    elif code == C_PINE:
        c.rect(0, 0, 15, 15, SK)
        c.ellipse(8, 5, 7.5, 3.6, GD)              # umbrella pine
        c.ellipse(6, 4, 4, 1.8, GL)
        c.vline(8, 8, 15, WAS)
        c.vline(7, 9, 15, K)
        c.px(9, 9, WAS)
        c.px(6, 8, WAS)
    elif code == C_PLAZA:
        c.rect(0, 0, 15, 15, PV)
        for q in (0, 8):
            c.hline(0, 15, q, PS)
            c.vline(q, 0, 15, PS)
        c.px(4, 4, WH)
        c.px(12, 12, WH)
    elif code == C_WALL:
        c.rect(0, 0, 15, 15, WA)
        for y in (3, 7, 11, 15):
            c.hline(0, 15, y, WAS)
        for row, y in enumerate((0, 4, 8, 12)):
            for x in ((2, 10) if row % 2 else (6, 14)):
                c.vline(x, y, y + 2, WAS)
        c.px(4, 1, WB)
        c.px(12, 9, WB)
    elif code == C_ARCH:
        c.rect(0, 0, 15, 15, WA)
        c.ellipse(7.5, 8, 6, 7, K)
        c.rect(2, 8, 13, 15, K)
        c.ellipse(7.5, 9, 4, 5, WD)
        c.rect(4, 9, 11, 15, WD)
        c.hline(0, 15, 0, WAS)
        c.px(7, 1, WB)
        c.px(8, 1, WB)
    elif code == C_TORCH:
        c.rect(0, 0, 15, 15, WA)
        for y in (3, 11, 15):
            c.hline(0, 15, y, WAS)
        c.vline(8, 7, 12, K)
        c.hline(6, 10, 7, K)
        c.rect(7, 3, 9, 6, YL)
        c.rect(8, 1, 8, 5, WL)
        c.px(7, 2, YL)
    elif code == C_RUBBLE:
        road(c)
        c.ellipse(6, 9, 5, 4, WA)
        c.ellipse(11, 6, 3, 3, WB)
        c.ellipse(5, 8, 2, 1.5, WB)
        c.outline(K, inside=(WA, WB), empty=AS)
        c.px(7, 11, WAS)
        c.px(11, 7, WAS)
    elif code == C_COLUMN:
        c.rect(0, 0, 15, 15, SK)
        c.rect(5, 2, 10, 15, PV)
        c.vline(5, 2, 15, PS)
        c.vline(8, 3, 15, PS)
        c.rect(3, 0, 12, 1, PV)
        c.hline(3, 12, 2, PS)
        c.px(10, 2, SK)
        c.px(11, 0, SK)
    return c.a


TILES = [make_tile(code) for code in range(CODE_COUNT)]

# --------------------------------------------------------------------------
# District palettes (one colour per role) and sky gradients (top to bottom)
# --------------------------------------------------------------------------
STAGE_PAL = [
    # 0 Centro Storico: warm tuff and terracotta, late afternoon
    [(0, 0, 0), (58, 60, 68), (96, 150, 190), (232, 190, 70), (236, 232, 214), (176, 160, 138),
     (124, 110, 96), (206, 150, 96), (138, 88, 60), (226, 192, 128), (178, 70, 52),
     (38, 50, 70), (255, 226, 130), (44, 96, 60), (86, 150, 78), (30, 84, 140)],
    # 1 Posillipo: pale stone, deep gulf
    [(0, 0, 0), (66, 70, 80), (90, 176, 206), (236, 196, 84), (244, 240, 226), (214, 198, 164),
     (160, 140, 110), (232, 208, 160), (170, 130, 90), (240, 226, 190), (196, 84, 60),
     (40, 60, 86), (255, 232, 150), (36, 104, 66), (96, 168, 86), (24, 96, 150)],
    # 2 Quartieri Spagnoli: saturated plaster in a narrow street
    [(0, 0, 0), (78, 72, 80), (110, 170, 200), (240, 184, 60), (238, 230, 210), (164, 148, 132),
     (110, 98, 90), (222, 132, 70), (150, 76, 44), (240, 196, 96), (200, 56, 48),
     (30, 34, 84), (255, 214, 110), (40, 90, 70), (90, 156, 96), (40, 80, 130)],
    # 3 Vomero by night: sodium lamps on dark stone
    [(0, 0, 0), (34, 36, 50), (70, 96, 140), (214, 160, 60), (190, 190, 200), (124, 116, 120),
     (84, 76, 84), (110, 96, 112), (70, 60, 80), (134, 120, 124), (140, 60, 70),
     (20, 24, 44), (255, 204, 96), (24, 60, 56), (50, 100, 76), (24, 44, 90)],
    # 4 Parco Virgiliano at sunset
    [(0, 0, 0), (60, 54, 66), (232, 150, 110), (240, 190, 80), (250, 232, 200), (206, 176, 140),
     (150, 116, 100), (190, 150, 120), (126, 90, 80), (220, 190, 150), (200, 90, 60),
     (50, 40, 66), (255, 220, 130), (50, 96, 60), (120, 160, 70), (96, 70, 130)],
    # 5 Napoli Sotterranea: torch-lit yellow tuff
    [(0, 0, 0), (44, 40, 40), (80, 110, 130), (150, 120, 60), (170, 160, 140), (84, 72, 60),
     (56, 48, 42), (136, 108, 68), (84, 64, 44), (168, 138, 84), (150, 70, 40),
     (20, 16, 20), (255, 200, 90), (40, 60, 50), (70, 96, 66), (26, 40, 60)],
]
SKY = [
    [(70, 130, 206), (88, 146, 214), (108, 162, 220), (132, 178, 226), (160, 194, 230), (190, 208, 230), (216, 220, 224), (236, 226, 208)],
    [(52, 120, 210), (70, 138, 218), (92, 156, 224), (118, 174, 230), (148, 192, 234), (180, 208, 236), (208, 222, 236), (232, 232, 226)],
    [(96, 140, 200), (120, 156, 206), (148, 172, 210), (176, 186, 210), (204, 198, 200), (226, 206, 184), (240, 208, 160), (246, 204, 136)],
    [(10, 12, 40), (14, 18, 54), (20, 26, 70), (30, 34, 86), (46, 42, 98), (70, 50, 106), (104, 60, 104), (150, 78, 96)],
    [(60, 40, 110), (92, 50, 124), (130, 62, 130), (170, 76, 126), (206, 96, 112), (232, 124, 96), (246, 160, 86), (252, 198, 100)],
    [(0, 0, 0)] * 8,
]
# Colour the water glints (or the torches flare) through between base and white.
SPARKLE = [(150, 190, 220), (170, 214, 236), (160, 200, 226), (120, 150, 190), (246, 196, 150), (255, 230, 150)]
# Far silhouette colours per district: body, shade, highlight.
FAR_PAL = [
    [(96, 112, 160), (72, 88, 140), (150, 160, 190)],
    [(84, 110, 170), (60, 86, 150), (140, 164, 206)],
    [(130, 130, 160), (104, 104, 140), (176, 170, 180)],
    [(30, 28, 66), (20, 18, 50), (160, 80, 60)],
    [(80, 44, 100), (56, 30, 80), (236, 130, 90)],
    [(0, 0, 0)] * 3,
]

# --------------------------------------------------------------------------
# Stage maps. Rows 0-2 far band, 3-4 district band, 5-9 the roadway.
# --------------------------------------------------------------------------
LEGEND = {
    ".": C_SKY, "=": C_ROAD, "-": C_DASH, "#": C_CROSS, "t": C_EDGE_T, "b": C_EDGE_B,
    "*": C_PIECE, "P": C_PUMP, "l": C_LAMP, "A": C_BUILD_A, "B": C_BUILD_B, "D": C_DOOR,
    "S": C_SHOP, "r": C_ROOF_A, "d": C_ROOF_B, "~": C_SEA, "w": C_SEAWALL, "g": C_PARK,
    "p": C_PINE, "z": C_PLAZA, "W": C_WALL, "a": C_ARCH, "f": C_TORCH, "x": C_RUBBLE,
    "c": C_COLUMN,
}
MAPS_TXT = [
    [   # Centro Storico: decumani between dense blocks, Vesuvius beyond the roofs
        "....................",
        "rdrr.rrdr.rrrd.rdrr.",
        "ABABDABAABABBADBABAB",
        "BABAABBABABAABABBABA",
        "DSDASDDSADSDSADDSDAS",
        "ttlttttlttttlttttltt",
        "==##=======##=======",
        "--##----*--##-------",
        "--##-------##-------",
        "bbbbbbbbbbbbbbbbbbbb",
    ],
    [   # Posillipo: the coast road above the Gulf
        "....................",
        "....................",
        "~~~~~~~~~~~~~~~~~~~~",
        "wwwwwwwwwwwwwwwwwwww",
        "zzgzzzzgzzzzgzzzzzgz",
        "ttttlttttPttttlttttt",
        "==========##========",
        "----------##--------",
        "----*-----##--------",
        "bbbbbbbbbbbbbbbbbbbb",
    ],
    [   # Quartieri Spagnoli: narrow, tall, washing overhead
        ".r.d.rr.d.r.dr.r.d.r",
        "BABBABABBABABBABABBA",
        "ABABBABABABBABABBABA",
        "BBABABBABBABABBABABB",
        "SDSSDSDDSSDSDSSDDSDS",
        "tltttltttltttltttltt",
        "##====##====##====##",
        "##----##----##--*-##",
        "##----##----##----##",
        "bbbbbbbbbbbbbbbbbbbb",
    ],
    [   # Vomero at night: gardens, the hill and the Galleria
        "..p....p......p...p.",
        ".rdr..rr.p.rdr..r.rr",
        "ABAAgBABgggABABgAgBA",
        "WWaWWWgggzzgggWWaWWW",
        "WfaWfWgzgzzgzgWfaWfW",
        "tttltttttPtttttltttt",
        "====##==========##==",
        "----##--*-------##--",
        "----##----------##--",
        "bbbbbbbbbbbbbbbbbbbb",
    ],
    [   # Parco Virgiliano: the headland, ruins and open water at sunset
        "..c.p....c..p...c..p",
        "~~~~~~~~~~~~~~~~~~~~",
        "wwwwwwwwwwwwwwwwwwww",
        "gggzggggggzgggggzggg",
        "gzgggzzgggggzggggzgg",
        "ttttlttttttttlttttPt",
        "==========##========",
        "----------##--------",
        "----------##*-------",
        "bbbbbbbbbbbbbbbbbbbb",
    ],
    [   # Napoli Sotterranea: tuff corridors, arches and rubble
        "WWWWWWWWWWWWWWWWWWWW",
        "WfWWaWWfWWWaWWfWWaWW",
        "WWWWaWWWWWWaWWWWWaWW",
        "WWfWWWWWWfWWWWWWfWWW",
        "aWWWaWfWaWWWaWfWaWWW",
        "tttttttttttttttttttt",
        "=====x========x=====",
        "-----------x--------",
        "--x-------------x---",
        "bbbbbbbbbbbbbbbbbbbb",
    ],
]
maps = np.zeros((len(STAGES), STAGE_H, STAGE_W), dtype=np.uint8)
for s, rows in enumerate(MAPS_TXT):
    assert len(rows) == STAGE_H and all(len(r) == STAGE_W for r in rows), STAGES[s]
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            maps[s, y, x] = LEGEND[ch]

# --------------------------------------------------------------------------
# Sprites
# --------------------------------------------------------------------------
# Car palette: 0 transparent, then the white 500 L.
CAR_COLOURS = [(0, 0, 0), (255, 255, 255), (214, 218, 226), (150, 158, 172), (24, 26, 34),
               (70, 76, 90), (56, 92, 136), (150, 196, 230), (255, 255, 0), (255, 0, 0),
               (184, 190, 200), (112, 20, 24), (20, 20, 20)]
(_, C_WHITE, C_LIGHT, C_SHADE, C_TYRE, C_HUB, C_GLASS, C_GLINT, C_HEAD, C_TAIL, C_CHROME,
 C_SEAT, C_SHADOW) = range(13)
CAR_W, CAR_H = 48, 26


def car_frame(phase):
    """Side view, nose to the right: the 500's two rounded boxes."""
    c = Canvas(CAR_W, CAR_H)
    c.ellipse(21.5, 10.5, 13.5, 10, C_WHITE)                 # cabin dome
    c.ellipse(23.5, 14, 22.5, 6.6, C_WHITE)                  # body
    c.rect(0, 20, 47, 25, 0)
    c.rect(3, 17, 44, 19, C_LIGHT)                           # sill
    c.hline(4, 43, 19, C_SHADE)
    glass = Canvas(CAR_W, CAR_H)
    glass.ellipse(21.5, 10.5, 11, 7.6, 1)
    for y in range(3, 10):
        for x in range(CAR_W):
            if glass.a[y, x] and not 21 <= x <= 22 and x not in (10, 33):
                c.px(x, y, C_GLASS)
    c.hline(24, 29, 5, C_GLINT)
    c.hline(14, 17, 5, C_GLINT)
    c.hline(15, 28, 0, C_TYRE)                               # folded canvas roof
    c.hline(13, 30, 1, C_TYRE)
    c.hline(5, 41, 11, C_LIGHT)                              # waistline
    c.vline(17, 10, 18, C_SHADE)                             # door shut lines
    c.vline(31, 10, 18, C_SHADE)
    c.hline(26, 28, 13, C_SHADE)                             # handle
    for x in (5, 7, 9):                                      # engine-lid louvres
        c.vline(x, 13, 15, C_SHADE)
    c.rect(0, 16, 2, 17, C_CHROME)                           # bumpers
    c.rect(45, 16, 47, 17, C_CHROME)
    c.rect(2, 12, 3, 14, C_TAIL)
    c.rect(43, 12, 44, 14, C_HEAD)
    for cx in (11, 36):                                      # wheels in their arches
        c.ellipse(cx, 19.5, 5.4, 5.4, C_TYRE)
        c.ellipse(cx, 19.5, 2.4, 2.4, C_HUB)
        if phase:
            c.px(cx, 18, C_CHROME)
            c.px(cx, 21, C_CHROME)
        else:
            c.px(cx - 1, 19, C_CHROME)
            c.px(cx + 1, 20, C_CHROME)
    c.outline(C_TYRE, inside=(C_WHITE, C_LIGHT, C_GLASS, C_SHADE), empty=0)
    c.hline(5, 43, CAR_H - 1, C_SHADOW)                      # ground shadow
    return c.a


def tilt(frame, direction):
    """Shear the car so its nose lifts (-1) or dips (+1) while changing lane."""
    out = np.zeros_like(frame)
    h, w = frame.shape
    for x in range(w):
        dy = int(round((x - w / 2) * 0.09 * direction))
        for y in range(h - 1):
            yy = y + dy
            if 0 <= yy < h - 1:
                out[yy, x] = frame[y, x]
    out[h - 1:] = frame[h - 1:]
    return out


CAR = [car_frame(0), car_frame(1)]
CAR += [tilt(CAR[0], -1), tilt(CAR[0], 1)]

# Scooter gang palette: 0 transparent, 1 body, 2 body shade, 3 jacket, 4 helmet, ...
SC_W, SC_H = 24, 24
(_, S_BODY, S_BODY2, S_JACKET, S_HELMET, S_SKIN, S_TYRE, S_HUB, S_SEAT, S_LAMP, S_JEANS,
 S_SHADOW) = range(12)
SCOOT_BASE = {S_SKIN: (236, 180, 140), S_TYRE: (24, 26, 34), S_HUB: (150, 158, 172),
              S_SEAT: (70, 50, 40), S_LAMP: (255, 255, 0), S_JEANS: (60, 80, 140),
              S_SHADOW: (20, 20, 20)}
GANGS = [   # body, body shade, jacket, helmet
    [(214, 40, 40), (140, 20, 30), (30, 30, 40), (240, 240, 240)],      # red Vespa
    [(60, 170, 90), (30, 110, 60), (220, 120, 30), (40, 40, 50)],       # green Vespa
    [(60, 110, 210), (36, 70, 150), (230, 210, 60), (200, 40, 40)],     # blue Vespa
]


def scooter_frame(phase):
    c = Canvas(SC_W, SC_H)
    bob = phase
    c.ellipse(5, 19, 3.2, 3.2, S_TYRE)
    c.ellipse(18, 19, 3.2, 3.2, S_TYRE)
    c.px(5, 19, S_HUB)
    c.px(18, 19, S_HUB)
    c.px(5 + (1 if phase else 0), 18, S_HUB)
    c.px(18 - (1 if phase else 0), 20, S_HUB)
    c.poly([(2, 18), (2, 14), (5, 12), (11, 12), (12, 17), (15, 17), (15, 19), (8, 19)], S_BODY)  # cowl + floor
    c.rect(3, 16, 9, 17, S_BODY2)
    c.rect(15, 9, 17, 18, S_BODY)                             # leg shield
    c.vline(15, 10, 18, S_BODY2)
    c.hline(15, 19, 8, S_TYRE)                                # handlebar
    c.px(18, 10, S_LAMP)
    c.px(19, 10, S_LAMP)
    c.rect(4, 11, 11, 11, S_SEAT)
    c.rect(1, 13, 1, 14, S_LAMP if phase else S_BODY2)        # tail lamp
    # rider
    c.rect(7, 4 + bob, 11, 10, S_JACKET)
    c.poly([(11, 5 + bob), (15, 7), (15, 9), (11, 8 + bob)], S_JACKET)      # arm
    c.px(15, 8, S_SKIN)
    c.poly([(8, 10), (13, 11), (14, 17), (12, 17), (11, 13), (8, 12)], S_JEANS)
    c.rect(12, 17, 15, 17, S_TYRE)                            # shoe
    c.ellipse(9.5, 2 + bob, 2.6, 2.4, S_HELMET)
    c.rect(11, 2 + bob, 12, 3 + bob, S_SKIN)
    c.hline(2, 21, SC_H - 1, S_SHADOW)
    return c.a


SCOOT = [scooter_frame(0), scooter_frame(1)]

# Virgil's Egg on its plinth.
EGG_W, EGG_H = 24, 32
(_, E_GOLD, E_GOLD2, E_GLOW, E_BLUE, E_STAR, E_STONE, E_STONE2, E_DARK, E_GLOW2) = range(10)
EGG_COLOURS = [(0, 0, 0), (236, 180, 50), (160, 104, 30), (255, 240, 170), (30, 50, 130),
               (190, 220, 255), (150, 132, 104), (96, 80, 62), (30, 24, 30), (250, 212, 104)]


def egg_frame():
    c = Canvas(EGG_W, EGG_H)
    c.ellipse(11.5, 11, 8.5, 11, E_GLOW)
    c.ellipse(11.5, 11.5, 6.5, 9, E_GOLD)
    c.ellipse(11.5, 12.5, 4.8, 7, E_BLUE)
    for x, y in ((10, 9), (13, 12), (11, 15), (9, 13), (13, 8)):
        c.px(x, y, E_STAR)
    c.ellipse(8, 7, 1.2, 2.2, E_GLOW)
    for y in range(4, 20):                                   # shaded right rim
        row = c.a[y]
        xs = [x for x in range(EGG_W) if row[x] == E_GOLD]
        if xs:
            c.px(xs[-1], y, E_GOLD2)
    c.rect(4, 23, 19, 25, E_STONE)
    c.rect(6, 26, 17, 29, E_STONE)
    c.rect(3, 30, 20, 31, E_STONE)
    c.hline(4, 19, 25, E_STONE2)
    c.hline(3, 20, 31, E_STONE2)
    c.vline(17, 26, 29, E_STONE2)
    c.rect(9, 21, 14, 22, E_DARK)
    return c.a


EGG = egg_frame()

# Far silhouettes, 2 bpp: 0 transparent, 1 body, 2 shade, 3 highlight.
VES_W, VES_H = 96, 24


def vesuvius():
    c = Canvas(VES_W, VES_H)
    ridge = [(0, 23), (10, 20), (22, 14), (30, 8), (36, 5), (41, 6), (45, 9), (50, 8), (55, 3),
             (60, 2), (64, 4), (72, 11), (82, 17), (95, 23)]
    c.poly(ridge + [(95, 24), (0, 24)], 1)
    c.poly([(55, 3), (60, 2), (64, 4), (72, 11), (82, 17), (95, 23), (95, 24), (62, 24), (58, 10)], 2)
    for x, y in ((57, 3), (58, 3), (59, 2), (36, 6), (37, 5), (33, 8), (56, 5)):
        c.px(x, y, 3)
    return c.a


ISLE_W, ISLE_H = 64, 12


def island():
    c = Canvas(ISLE_W, ISLE_H)
    c.poly([(0, 11), (6, 8), (14, 3), (20, 2), (26, 6), (34, 7), (42, 3), (48, 1), (54, 4),
            (63, 11), (63, 12), (0, 12)], 1)
    c.poly([(42, 3), (48, 1), (54, 4), (63, 11), (63, 12), (46, 12)], 2)
    c.px(48, 2, 3)
    c.px(19, 3, 3)
    return c.a


VES, ISLE = vesuvius(), island()

# Headlight beam, 1 bpp chequer cone.
BEAM_W, BEAM_H = 64, 24
beam = np.zeros((BEAM_H, BEAM_W), dtype=np.uint8)
for x in range(BEAM_W):
    half = 2 + x * 9 // BEAM_W
    for y in range(BEAM_H):
        if abs(y - BEAM_H // 2) <= half and (x + y) % 2 == 0 and (x % 4 < 3 or y % 2):
            if x > 52 and (x + 2 * y) % 3:
                continue
            beam[y, x] = 1

# --------------------------------------------------------------------------
# Place every colour in its own cube cell (sprites first: they are shared)
# --------------------------------------------------------------------------
shared = {}
car_pal = [0] + claim(CAR_COLOURS[1:], shared)
scoot_base = dict(zip(SCOOT_BASE, claim(list(SCOOT_BASE.values()), shared)))
gang_pal = []
for gang in GANGS:
    vals = claim(gang, shared)
    pal = [0] * 16
    pal[S_BODY], pal[S_BODY2], pal[S_JACKET], pal[S_HELMET] = vals
    for idx, v in scoot_base.items():
        pal[idx] = v
    gang_pal.append(pal)
egg_pal = [0] + claim(EGG_COLOURS[1:], shared)
BEAM_COLOUR = claim([(255, 244, 190)], shared)[0]

stage_pal, far_pal, sparkle_pal = [], [], []
for s in range(len(STAGES)):
    used = dict(shared)
    stage_pal.append(claim(STAGE_PAL[s], used, shared))
    far_pal.append([0] + claim(FAR_PAL[s], used, shared))
    sparkle_pal.append(claim([SPARKLE[s]], used, shared)[0])
    by_cell = {}
    for v in stage_pal[s] + far_pal[s][1:] + [sparkle_pal[s]] + list(shared.values()):
        if v not in NAMED:
            assert by_cell.setdefault(cell(v), v) == v, f"cube-cell collision in {STAGES[s]}"
sky_pal = [[rgb565(c) for c in SKY[s]] for s in range(len(STAGES))]


# --------------------------------------------------------------------------
# Packing and C output
# --------------------------------------------------------------------------
def pack(frames, bpp):
    """Pack frames the way prg32_sprite_draw_indexed reads them (MSB first)."""
    out = bytearray()
    for f in frames:
        flat = f.reshape(-1)
        assert flat.max() < (1 << bpp)
        acc = nbits = 0
        for v in flat:
            acc = (acc << bpp) | int(v)
            nbits += bpp
            if nbits == 8:
                out.append(acc)
                acc = nbits = 0
        if nbits:
            out.append(acc << (8 - nbits))
    return bytes(out)


def c_array(name, values, ctype="uint8_t", per=20):
    fmt = (lambda v: f"0x{v:04X}") if ctype == "uint16_t" else str
    vals = [fmt(int(v)) for v in values]
    lines = ["  " + ",".join(vals[i:i + per]) + "," for i in range(0, len(vals), per)]
    return f"static const {ctype} {name}[{len(vals)}] = {{\n" + "\n".join(lines) + "\n};\n"


tile_bytes = pack(TILES, 4)
car_bytes = pack(CAR, 4)
scoot_bytes = pack(SCOOT, 4)
egg_bytes = pack([EGG], 4)
ves_bytes = pack([VES], 2)
isle_bytes = pack([ISLE], 2)
beam_bytes = pack([beam], 1)


def pad16(pal):
    return list(pal) + [0] * (16 - len(pal))


piece_code = C_PIECE
defines = {
    "NR_STAGE_COUNT": len(STAGES), "NR_STAGE_W": STAGE_W, "NR_STAGE_H": STAGE_H,
    "NR_TILE_W": T, "NR_TILE_H": T, "NR_TILE_COUNT": CODE_COUNT,
    "NR_CODE_SKY": C_SKY, "NR_CODE_ROAD": C_ROAD, "NR_CODE_DASH": C_DASH,
    "NR_CODE_PIECE": C_PIECE, "NR_CODE_PIECE2": C_PIECE2, "NR_CODE_PUMP": C_PUMP,
    "NR_CODE_ROOF_A": C_ROOF_A, "NR_CODE_ROOF_B": C_ROOF_B, "NR_CODE_PINE": C_PINE,
    "NR_CODE_COLUMN": C_COLUMN, "NR_CODE_SEA": C_SEA, "NR_CODE_SEAWALL": C_SEAWALL,
    "NR_CODE_TORCH": C_TORCH, "NR_CODE_RUBBLE": C_RUBBLE,
    "NR_ROLE_WATER_LIGHT": W2, "NR_ROLE_WHITE": WH, "NR_ROLE_LIT": WL, "NR_ROLE_LANE": YL,
    "NR_ROLE_WATER": SK,
    "NR_CAR_W": CAR_W, "NR_CAR_H": CAR_H, "NR_CAR_FRAMES": len(CAR),
    "NR_SCOOT_W": SC_W, "NR_SCOOT_H": SC_H, "NR_SCOOT_FRAMES": len(SCOOT), "NR_GANG_COUNT": len(GANGS),
    "NR_EGG_W": EGG_W, "NR_EGG_H": EGG_H, "NR_EGG_GLOW": E_GLOW, "NR_EGG_GLOW2": E_GLOW2, "NR_EGG_GOLD": E_GOLD, "NR_EGG_STAR": E_STAR,
    "NR_VES_W": VES_W, "NR_VES_H": VES_H, "NR_ISLE_W": ISLE_W, "NR_ISLE_H": ISLE_H,
    "NR_BEAM_W": BEAM_W, "NR_BEAM_H": BEAM_H, "NR_BEAM_COLOUR": f"0x{BEAM_COLOUR:04X}",
    "NR_SKY_BANDS": 8,
}
with HDR.open("w") as f:
    f.write("/* Generated by tools/generate_assets.py - do not edit. */\n")
    f.write("#ifndef NAPRIDER_ASSETS_H\n#define NAPRIDER_ASSETS_H\n#include <stdint.h>\n")
    for k, v in defines.items():
        f.write(f"#define {k} {v}\n")
    f.write(c_array("nr_tiles", tile_bytes, per=24))
    f.write(c_array("nr_stage_maps", maps.reshape(-1), per=20))
    f.write(c_array("nr_stage_pal", [v for p in stage_pal for v in p], "uint16_t", 8))
    f.write(c_array("nr_sky_pal", [v for p in sky_pal for v in p], "uint16_t", 8))
    f.write(c_array("nr_far_pal", [v for p in far_pal for v in p], "uint16_t", 4))
    f.write(c_array("nr_sparkle_pal", sparkle_pal, "uint16_t", 8))
    f.write(c_array("nr_car_pal", pad16(car_pal), "uint16_t", 8))
    f.write(c_array("nr_gang_pal", [v for p in gang_pal for v in p], "uint16_t", 8))
    f.write(c_array("nr_egg_pal", pad16(egg_pal), "uint16_t", 8))
    f.write(c_array("nr_car_pixels", car_bytes, per=24))
    f.write(c_array("nr_scoot_pixels", scoot_bytes, per=24))
    f.write(c_array("nr_egg_pixels", egg_bytes, per=24))
    f.write(c_array("nr_ves_pixels", ves_bytes, per=24))
    f.write(c_array("nr_isle_pixels", isle_bytes, per=24))
    f.write(c_array("nr_beam_pixels", beam_bytes, per=24))
    f.write("#endif\n")

# --------------------------------------------------------------------------
# Previews: every district as the cartridge composes it, and a sprite sheet
# --------------------------------------------------------------------------
def to_rgb(indices, pal, transparent=None, backdrop=(255, 0, 255)):
    lut = np.array([rgb888(v) for v in pal] + [(0, 0, 0)] * (256 - len(pal)), dtype=np.uint8)
    img = lut[indices]
    if transparent is not None:
        img[indices == transparent] = backdrop
    return img


def stage_preview(s):
    img = np.zeros((STAGE_H * T, STAGE_W * T, 3), dtype=np.uint8)
    for band in range(8):
        img[band * 6:(band + 1) * 6] = rgb888(sky_pal[s][band])
    if s < 5 and s != 2:
        sil, w, h, x, y = (ISLE, ISLE_W, ISLE_H, 60, 4) if s == 4 else (VES, VES_W, VES_H, 190, 8)
        rgb = to_rgb(sil, far_pal[s])
        for yy in range(h):
            for xx in range(w):
                if sil[yy, xx] and 0 <= y + yy < 48:
                    img[y + yy, x + xx] = rgb[yy, xx]
    for ty in range(STAGE_H):
        for tx in range(STAGE_W):
            code = int(maps[s, ty, tx])
            if code == C_SKY:
                continue
            tile = TILES[code]
            rgb = to_rgb(tile, stage_pal[s])
            block = img[ty * T:(ty + 1) * T, tx * T:(tx + 1) * T]
            if code in CUTOUT:
                mask = tile != SK
                block[mask] = rgb[mask]
            else:
                block[:] = rgb
    return img


previews = [stage_preview(s) for s in range(len(STAGES))]
contact = np.zeros((STAGE_H * T * 3, STAGE_W * T * 2, 3), dtype=np.uint8)
for i, p in enumerate(previews):
    y, x = (i // 2) * STAGE_H * T, (i % 2) * STAGE_W * T
    contact[y:y + STAGE_H * T, x:x + STAGE_W * T] = p
Image.fromarray(contact).save(OUT / "runtime_stages_contact.png", optimize=True)

BACK = (58, 60, 68)
sheet = np.full((40, CAR_W * 4 + 24 * 6 + 24 + 8, 3), BACK, dtype=np.uint8)


def blit(dst, x, y, indices, pal):
    rgb = to_rgb(indices, pal)
    h, w = indices.shape
    region = dst[y:y + h, x:x + w]
    mask = indices != 0
    region[mask] = rgb[mask]


for i, fr in enumerate(CAR):
    blit(sheet, i * CAR_W, 8, fr, car_pal)
for g in range(len(GANGS)):
    for i, fr in enumerate(SCOOT):
        blit(sheet, CAR_W * 4 + (g * 2 + i) * 24, 8, fr, gang_pal[g])
blit(sheet, CAR_W * 4 + 144 + 4, 4, EGG, egg_pal)
Image.fromarray(sheet).resize((sheet.shape[1] * 3, sheet.shape[0] * 3), Image.Resampling.NEAREST).save(
    OUT / "sprites.png", optimize=True)

# Store icon: the logo and the 500 from the approved title panel.
src = Image.open(SHEET).convert("RGB")
icon = src.crop((8, 8, 452, 372)).resize((96, 80), Image.Resampling.LANCZOS)
canvas = Image.new("RGB", (96, 96), (8, 10, 30))
canvas.paste(icon, (0, 8))
canvas.quantize(colors=24, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(
    OUT / "icon.png", optimize=True)

total = sum(map(len, (tile_bytes, car_bytes, scoot_bytes, egg_bytes, ves_bytes, isle_bytes, beam_bytes)))
total += maps.size + 2 * (16 * 6 + 8 * 6 + 4 * 6 + 16 + 48 + 16)
print(f"tiles {len(tile_bytes)} car {len(car_bytes)} scooters {len(scoot_bytes)} egg {len(egg_bytes)} "
      f"far {len(ves_bytes) + len(isle_bytes)} beam {len(beam_bytes)} maps {maps.size}: {total} bytes of art")
print(f"icon {(OUT / 'icon.png').stat().st_size} bytes")
