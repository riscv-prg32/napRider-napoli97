# Publishing on GitHub

1. Create an empty repository named `napRider-napoli97`.
2. Copy this directory to the repository root.
3. Run `make check` and commit.
4. Push to GitHub; `.github/workflows/ci.yml` checks out PRG32 `main`, builds the portable cartridge in Espressif's IDF 5.4.1 container, and uploads the Store bundle and both architecture variants as Actions artifacts.
5. Download the CI artifact, test QEMU and ESP32-C6 128 KiB profile, then attach the validated Store ZIP and `.prg32` files to release `v1.0.0`.

Do not publish binaries that have not been QEMU/hardware validated. The included PNG screenshot is a deterministic renderer preview from the actual indexed assets, not a claimed emulator capture.
