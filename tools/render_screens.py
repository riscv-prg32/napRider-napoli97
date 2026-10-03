#!/usr/bin/env python3
"""Render real game frames through the host harness.

Builds tests/harness/run_harness.c, runs it with NAPRIDER_SHOTS pointing at a
temporary directory and converts the dumped frames - the exact 320x200 output
of src/game.c as the ESP32-C6 palette shows it - into:

    release-artifacts/screens/*.png                  2x previews
    release-artifacts/naprider-napoli97-contact-sheet.png

The Store screenshot itself is a QEMU capture: see tools/qemu_capture.py.
"""
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release-artifacts"
SHEET = ["01-title", "03-centro-storico", "04-posillipo", "05-quartieri", "06-vomero", "12-vomero-unlit",
         "07-virgiliano", "08-sotterranea", "09-egg"]

with tempfile.TemporaryDirectory(prefix="naprider-shots-") as temp:
    binary = Path(temp) / "harness"
    subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-O1", f"-I{ROOT / 'tests/stub'}", f"-I{ROOT / 'src'}",
                    str(ROOT / "tests/harness/run_harness.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, env={**os.environ, "NAPRIDER_SHOTS": temp}, stdout=subprocess.DEVNULL)
    frames = {p.stem: Image.open(p).convert("RGB") for p in sorted(Path(temp).glob("*.ppm"))}

(OUT / "screens").mkdir(parents=True, exist_ok=True)
for old in (OUT / "screens").glob("*.png"):
    old.unlink()
for name, frame in frames.items():
    frame.resize((640, 400), Image.Resampling.NEAREST).quantize(colors=128, dither=Image.Dither.NONE).save(
        OUT / "screens" / f"{name}.png", optimize=True)
sheet = Image.new("RGB", (3 * 320 + 4 * 4, 3 * 200 + 4 * 4), (8, 10, 30))
for i, name in enumerate(SHEET):
    sheet.paste(frames[name], (4 + (i % 3) * 324, 4 + (i // 3) * 204))
sheet.quantize(colors=200, dither=Image.Dither.NONE).save(OUT / "naprider-napoli97-contact-sheet.png", optimize=True)
print(f"wrote {len(frames)} screens and the contact sheet to {OUT}")
