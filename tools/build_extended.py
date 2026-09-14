#!/usr/bin/env python3
"""Build for PRG32's 64 KiB QEMU / 128 KiB ESP32-C6 RAM profiles.

PRG32's portable builder currently checks against its 32 KiB fallback even
when a larger firmware profile is selected. Override only that build-time
limit; the firmware still checks the cartridge's actual memory requirement.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from prg32.cartridge import build_cartridge
from prg32.prg32 import main

assert build_cartridge.FALLBACK_CART_RAM_SIZE == 32 * 1024
build_cartridge.FALLBACK_CART_RAM_SIZE = 64 * 1024
sys.exit(main(sys.argv[1:]))
