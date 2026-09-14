#!/usr/bin/env python3
"""Stage a cartridge against the RAM size in the built QEMU firmware."""

import os
import sys
from pathlib import Path

framework = Path(os.environ.get("PRG32_ROOT", Path(__file__).resolve().parents[2] / "PRG32"))
sys.path.insert(0, str(framework))

from prg32.prg32 import main
from prg32.utilities import runtime_handler

elf = framework / "build-qemu" / "PRG32.elf"
runtime = runtime_handler.runtime_from_elf(elf, "riscv32-esp-elf-")
runtime_handler.FALLBACK_CART_RAM_SIZE = runtime["cart_ram_size"]
sys.exit(main(["qemu", "upload", *sys.argv[1:]]))
