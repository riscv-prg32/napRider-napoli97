# Asset pipeline

The single artistic source of truth is `assets/source/naprider_visual_sheet.png`.

`tools/extract_visual_sheet.py` performs deterministic crops, builds a 128-color shared palette, converts car/scooter/egg graphics to 8-bpp indices, and clusters the six approved gameplay scenes into 96 representative 16x16 tiles. Each stage stores only 200 tile indices (20x10), so dense isometric scenery costs mostly one shared tile bank rather than six full framebuffers.

The generated C data is `src/assets8.h`. It contains no host pointers, which matters for portable PRG32 cartridges because QEMU and ESP32-C6 can load the cartridge at different executable-RAM bases. `game.c` constructs `prg32_indexed_sprite_t` descriptors at runtime using PC-relative asset addresses.

The generation dependencies are intentionally development-only: Pillow, NumPy and scikit-learn. The cartridge itself has no dependency on them.
