# Asset pipeline

`tools/generate_assets.py` draws every runtime graphic pixel by pixel and writes `src/assets.h`; `tools/generate_audio.py` composes the score and writes `audio.json`. Both are deterministic: running them again produces the same files.

`assets/source/naprider_visual_sheet.png` is the art-direction reference. Only the Store icon is cropped from it; no runtime graphic is.

## Tiles as roles

The 26 tiles are 16x16 at 4 bpp. A pixel value is a *role*, not a colour: outline, asphalt, water light, lane paint, white paint, pavement, pavement shade, wall A, wall A shade, wall B, roof/accent, window dark, window lit, green dark, green light, water deep. Each district has a 16-colour palette that gives the roles its own materials, so one tile bank serves all six districts.

Role 15 doubles as the cut-out key: roofline, pine and column tiles are drawn with it transparent, over the sky.

## One colour per cube cell

The ESP32-C6 firmware maps each sprite colour to the cell of its 6x6x6 colour cube (`16 + r*36 + g*6 + b`, each channel scaled to 0..5) and stores that index in the framebuffer. Two colours in the same cell would be shown as one. The generator therefore places every colour in a free cell:

- sprite colours (car, gangs, Egg, beam) are placed first and are the same in every district;
- a district colour that lands in a sprite colour's cell takes that colour (they are at most one cube step apart);
- a district colour that lands in another district colour's cell moves to the nearest free cell, measured in 8-bit RGB;
- the eight firmware named colours (black, white, red, green, blue, yellow, cyan, magenta) are exact everywhere and need no cell.

At run time `program()` in `src/game.c` writes each colour to its cell with `prg32_palette_set`. Colours that animate (sea glint, torches, Egg glow) step between authored colours, never through arbitrary blends, so they keep their cells. Fades and the unlit tunnel do blend; there, colours that meet in a cell merge on the board, which is what a fade looks like anyway.

## Maps

Six 20x10 byte maps are written as text in the generator, one character per tile. Rows 0-2 are the far layer, 3-4 the district layer, 5-9 the roadway (pavement, three lanes, pavement). See [MAP_REFERENCE.md](MAP_REFERENCE.md).

## Sizes

| Asset | Format | Bytes |
| --- | --- | ---: |
| 26 tiles | 4 bpp | 3328 |
| Fiat 500 L, 4 frames of 48x26 | 4 bpp | 2496 |
| Scooter, 2 frames of 24x24, 3 palettes | 4 bpp | 576 |
| Egg 24x32 | 4 bpp | 384 |
| Vesuvius 96x24, island 64x12 | 2 bpp | 768 |
| Headlight beam 64x24 | 1 bpp | 192 |
| Maps | bytes | 1200 |
| Palettes | RGB565 | about 500 |

The generated header holds no pointers: portable cartridges are loaded at different addresses on QEMU and on the board, and `game.c` fills its sprite descriptors at run time.

Development dependencies are Pillow and NumPy; the cartridge depends on neither.
