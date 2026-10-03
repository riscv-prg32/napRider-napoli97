#!/usr/bin/env python3
"""Static checks on the cartridge source, the generated art and the score."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
game = (ROOT / "src/game.c").read_text()
assets = (ROOT / "src/assets.h").read_text()
audio = json.loads((ROOT / "audio.json").read_text())
meta = json.loads((ROOT / "metadata/metadata.json").read_text())
colophon = json.loads((ROOT / "metadata/colophon.json").read_text())


def fail(message):
    sys.exit(f"source_checks: {message}")


def array(name):
    match = re.search(rf"{name}\[\d+\] = \{{(.*?)\}};", assets, re.S)
    if not match:
        fail(f"{name} missing from src/assets.h")
    return [int(v, 0) for v in re.findall(r"0x[0-9A-Fa-f]+|\d+", match.group(1))]


def define(name):
    return int(re.search(rf"#define {name} (\w+)", assets).group(1), 0)


# Entry points, the saga's four phrases and the story scope.
for token in ("naprider_init", "naprider_update", "naprider_draw", "prg32_sprite_draw_indexed",
              "prg32_palette_set", "prg32_gfx_rect_indexed", "prg32_audio_note_on_pan",
              "L'UOVO DI VIRGILIO", "SOTTERRANEA", "vai cuonc cuonc", "ho sete",
              "hai lasciato le luci accese", "ah il freno a mano"):
    if token not in game:
        fail(f"missing: {token}")
for banned in ("TESORO RECUPERATO", "San Gennaro", "vesuvio_init", "development-c6"):
    if banned in game:
        fail(f"obsolete token: {banned}")
# Portable cartridges are loaded at different addresses: no pointer tables in data.
if re.search(r"static\s+const\s+char\s*\*\s*(const\s+)?\w+\s*\[", game):
    fail("static pointer table found; portable cartridges cannot relocate it")
# RGB565 fills would be quantised on the board; the game draws by palette index.
for call in ("prg32_gfx_rect(", "prg32_gfx_clear(", "prg32_gfx_pixel("):
    if call in game:
        fail(f"{call[:-1]} bypasses the indexed palette")

# Maps: one fragment per surface district, none underground.
stages, width, height = define("NR_STAGE_COUNT"), define("NR_STAGE_W"), define("NR_STAGE_H")
maps = array("nr_stage_maps")
piece = define("NR_CODE_PIECE")
if len(maps) != stages * width * height:
    fail("stage map size")
for stage in range(stages):
    cells = maps[stage * width * height:(stage + 1) * width * height]
    if cells.count(piece) != (1 if stage < stages - 1 else 0):
        fail(f"stage {stage}: wrong number of fragments")
    if piece in cells and cells.index(piece) // width not in (6, 7, 8):
        fail(f"stage {stage}: fragment is off the road")
    if any(code >= define("NR_TILE_COUNT") for code in cells):
        fail(f"stage {stage}: unknown tile code")

# Colours: everything shown together owns its own 6x6x6 cube cell, so the
# ESP32-C6 indexed framebuffer shows the authored colours exactly.
NAMED = (0x0000, 0xFFFF, 0xF800, 0x07E0, 0x001F, 0xFFE0, 0x07FF, 0xF81F)


def cell(v):
    return 16 + ((v >> 11) * 5 // 31) * 36 + (((v >> 5) & 63) * 5 // 63) * 6 + ((v & 31) * 5 // 31)


shared = set(array("nr_car_pal")[1:]) | set(array("nr_egg_pal")[1:]) | {define("NR_BEAM_COLOUR")}
gangs = array("nr_gang_pal")
for g in range(define("NR_GANG_COUNT")):
    shared |= set(gangs[g * 16 + 1:(g + 1) * 16])
stage_pal, far_pal, sparkle = array("nr_stage_pal"), array("nr_far_pal"), array("nr_sparkle_pal")
for stage in range(stages):
    colours = shared | set(stage_pal[stage * 16:(stage + 1) * 16]) | set(far_pal[stage * 4 + 1:(stage + 1) * 4])
    colours |= {sparkle[stage]}
    colours = {c for c in colours if c not in NAMED}
    if len({cell(c) for c in colours}) != len(colours):
        fail(f"stage {stage}: two colours share a system-palette cell")

art = sum(len(array(n)) for n in ("nr_tiles", "nr_car_pixels", "nr_scoot_pixels", "nr_egg_pixels",
                                  "nr_ves_pixels", "nr_isle_pixels", "nr_beam_pixels"))
if art > 16384:
    fail(f"indexed art grew to {art} bytes")

# Audio: procedural instruments only, music on voices 0-3, every looping track jumps back.
if audio.get("samples"):
    fail("the soundtrack must stay PCM-free")
for instrument in audio["instruments"]:
    if not instrument["sample_id"] & 0x8000:
        fail("instrument is not a procedural synth")
for number, track in enumerate(audio["tracks"]):
    events = track["events"]
    for event in events:
        if event["command"] in ("NOTE_ON", "NOTE_OFF") and event["arg0"] > 3:
            fail(f"track {number} uses a voice reserved for effects")
    if events[-1]["command"] not in ("JUMP", "END"):
        fail(f"track {number} does not end")
if len(audio["tracks"]) != 8 or len(audio["instruments"]) != 10:
    fail("audio.json does not match the voices game.c uses")

if colophon["version"] != meta["version"] or colophon["title"] != meta["title"]:
    fail("metadata and colophon disagree")
if f"## {meta['version']}" not in (ROOT / "CHANGELOG.md").read_text():
    fail("CHANGELOG.md has no entry for this version")
if not (ROOT / "assets/source/naprider_visual_sheet.png").exists():
    fail("source visual sheet missing")
print(f"OK: {art} bytes of indexed art, {stages} districts, {len(audio['tracks'])} tracks, version {meta['version']}")
