# PRG32 `main` alignment

This game targets `riscv-prg32/PRG32` branch `main`.

Design assumptions taken from current `main` documentation:

- new cartridges are portable ABI-table packages (`--portable`);
- executable ABI is 1.1 at the time this package was prepared;
- Store metadata is appended as `PRG32META` and does not consume executable cartridge RAM;
- `.prg32` package size is limited to 128 KiB;
- the optional ESP32-C6 128 KiB profile reserves 128 KiB executable cartridge RAM and provides a 320x200 persistent game viewport;
- QEMU uses a 64 KiB executable profile by default, so this project keeps executable code/data compact and relies on the indexed asset/tile budget; if a particular QEMU build rejects the package for RAM rather than flash/package size, use the matching expanded profile or reduce `NR_TILE_COUNT` in the asset generator.

Before release, always build against the exact PRG32 `main` commit being targeted and run `python3 -m prg32 cartridge summary` on both architecture variants.
