# Publishing

1. Run `./build.sh` (see the README). It regenerates the assets, runs the tests and writes the Store bundle to `dist/`.
2. Run `make capture` to refresh the QEMU demo and Store screenshot, then `./build.sh` again if the screenshot changed.
3. Commit, including `dist/`, and push.
4. Upload `dist/naprider-napoli97-<version>-store.zip` to the Cartridge Store (`python3 -m prg32 store publish-bundle` from the PRG32 checkout); submissions are reviewed before they appear in the catalogue.

There is no CI workflow in this repository: the build needs the ESP-IDF RISC-V toolchain and a PRG32 checkout.
