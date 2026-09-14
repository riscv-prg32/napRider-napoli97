# Release checklist

- [ ] Re-run `make assets` and commit deterministic changes.
- [ ] Run `make check`.
- [ ] Build against a fresh `riscv-prg32/PRG32` `main` checkout in ESP-IDF 5.4.1.
- [ ] Confirm `python3 -m prg32 cartridge summary` reports portable ABI compatibility.
- [ ] Confirm both `.prg32` files are <= 131072 bytes.
- [ ] Test QEMU controls and capture a real 320x200 screenshot/preview.
- [ ] Flash/test an ESP32-C6 running the 128 KiB cartridge-RAM profile.
- [ ] Replace the deterministic software preview screenshot with a real QEMU capture before a binary release, if available.
- [ ] Inspect Store metadata and bundle ZIP.
- [ ] Tag `v1.0.0` only after runtime validation.
