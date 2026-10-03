# Release checklist

- [x] `make assets` regenerates `src/assets.h` and `audio.json` with no diff.
- [x] `make check` passes (static checks, strict C99, bot playthrough on both display models).
- [x] `./build.sh` against `riscv-prg32/PRG32` `main` (2.0.0: commit `a8669e5`).
- [x] Both `.prg32` files are within 65536 bytes.
- [x] The Cartridge Store intake code accepts the bundle.
- [x] QEMU: boots from the Store cartridge, title, controls, music and effects (`make capture`).
- [x] Store screenshot is a real QEMU capture.
- [ ] ESP32-C6: colours match QEMU, frame rate is acceptable, stereo panning on two MAX98357A boards.
- [ ] Publish `dist/naprider-napoli97-<version>-store.zip` to the Cartridge Store.
- [ ] Tag the version after the hardware run.
