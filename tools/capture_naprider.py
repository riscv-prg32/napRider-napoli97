#!/usr/bin/env python3
"""Record napRider's real QEMU screen and UART PCM using PRG32's recorder."""

import argparse
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

game_root = Path(__file__).resolve().parents[1]
framework = Path(os.environ.get("PRG32_CAPTURE_ROOT",
                                os.environ.get("PRG32_ROOT", game_root.parent / "PRG32")))
spec = importlib.util.spec_from_file_location(
    "prg32_capture", framework / "tools/capture_cartridge_previews.py"
)
capture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture_module)
capture_module.ROOT = framework.resolve()

parser = argparse.ArgumentParser()
parser.add_argument("--duration", type=float, default=60)
parser.add_argument("--warmup", type=float, default=7)
parser.add_argument("--output", type=Path, default=game_root / "release-artifacts/naprider-napoli97-qemu-demo-60s.mp4")
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
capture_output = framework.resolve() / "build-qemu/naprider-demo-capture.mp4"

events = [(0.5, "k")]
events += [(second, "j") for second in range(2, 28, 3)]
events += [(second, "d") for second in (5, 11, 17, 23)]
events += [(second, "a") for second in (8, 20)]
events += [(30, "k"), (35, "j"), (39, "k")]
events += [(second, "j") for second in range(41, 59, 3)]
capture_module.CARTRIDGES = {
    "naprider": (str(game_root / "build/naprider-napoli97-base.prg32"),
                  str(capture_output), tuple(sorted(events)))
}

# PRG32's stock uploader still assumes a 32 KiB RAM profile. The game wrapper
# reads the actual 64 KiB executable window from the built QEMU firmware ELF.
original_run = subprocess.run
def run_with_extended_upload(command, *positional, **kwargs):
    if command[:5] == ["python3", "-m", "prg32", "qemu", "upload"]:
        command = ["python3", str(game_root / "tools/upload_qemu_extended.py"), *command[5:]]
    return original_run(command, *positional, **kwargs)
capture_module.subprocess.run = run_with_extended_upload

try:
    capture_module.capture("naprider", args.duration, 30, args.warmup,
                           "/opt/homebrew/bin/ffmpeg", verbose_console=True)
    shutil.copy2(capture_output, args.output)
finally:
    capture_output.unlink(missing_ok=True)
