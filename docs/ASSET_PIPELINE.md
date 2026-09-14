# Asset pipeline

The single artistic source of truth is `assets/source/naprider_visual_sheet.png`.

`tools/extract_visual_sheet.py` performs deterministic crops, builds a 128-color shared palette, and converts car, scooter, Egg and map graphics to 8-bpp indices. The six maps are authored as byte-coded semantic cells: buildings, roads, road edges, crossings, sea, seawall, park, plaza and underground walls. A stage-specific lookup gives those cells a district palette while retaining a small 66-tile bank. This prevents unrelated image fragments from being assembled into impossible streets.

Runtime scrolling derives tile selection and sub-tile offset from the same pixel coordinates. This keeps every tile boundary continuous during diagonal motion.

The geographic reasoning behind each authored layout is documented in [MAP_REFERENCE.md](MAP_REFERENCE.md).

The generated C data is `src/assets8.h`. It contains no host pointers, which matters for portable PRG32 cartridges because QEMU and ESP32-C6 can load the cartridge at different executable-RAM bases. `game.c` constructs `prg32_indexed_sprite_t` descriptors at runtime using PC-relative asset addresses.

The generation dependencies are intentionally development-only: Pillow, NumPy and scikit-learn. The cartridge itself has no dependency on them.
