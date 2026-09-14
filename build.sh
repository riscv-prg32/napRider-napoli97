#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${PRG32_ROOT:-}"
if [[ -z "$ROOT" ]]; then
  CANDIDATE="$(cd "$HERE/../PRG32" 2>/dev/null && pwd || true)"
  if [[ -f "$CANDIDATE/prg32/__main__.py" || -d "$CANDIDATE/prg32" ]]; then ROOT="$CANDIDATE"; fi
fi
if [[ -z "$ROOT" || ! -d "$ROOT/prg32" ]]; then
  echo "Set PRG32_ROOT to a checkout of https://github.com/riscv-prg32/PRG32/tree/main" >&2
  exit 2
fi
BUILD="$HERE/build"; DIST="$HERE/dist"; STORE="$DIST/store"
rm -rf "$BUILD" "$STORE"; mkdir -p "$BUILD" "$STORE"
cd "$ROOT"
python3 tools/prg32audio_pack.py "$HERE/audio.json" --out "$BUILD/naprider-audio.block"
python3 "$HERE/tools/build_extended.py" cartridge build "$HERE/src/game.c" \
  --portable --entry-prefix naprider --name naprider-napoli97 \
  --audio-block "$BUILD/naprider-audio.block" \
  --out "$BUILD/naprider-napoli97-base.prg32"
for arch in esp32c6 qemu; do
  python3 -m prg32 store attach-metadata "$BUILD/naprider-napoli97-base.prg32" \
    --metadata "$HERE/metadata/metadata.json" --icon "$HERE/assets/generated/icon.png" \
    --screenshot "$HERE/assets/generated/screenshot.png" --colophon "$HERE/metadata/colophon.json" \
    --architecture "$arch" --out "$STORE/naprider-napoli97-$arch.prg32"
done
cp "$HERE/metadata/manifest.json" "$HERE/assets/generated/icon.png" "$HERE/assets/generated/screenshot.png" "$HERE/metadata/colophon.json" "$STORE/"
python3 -m prg32 cartridge summary "$STORE/naprider-napoli97-esp32c6.prg32"
python3 -m prg32 store inspect-metadata "$STORE/naprider-napoli97-esp32c6.prg32"
python3 -m prg32 store pack-bundle --manifest "$STORE/manifest.json" --out "$DIST/naprider-napoli97-1.0.0-store.zip"
python3 "$HERE/tests/source_checks.py"
for f in "$STORE"/*.prg32; do
  size=$(wc -c < "$f")
  if (( size > 131072 )); then echo "ERROR: $f exceeds PRG32 128 KiB package limit" >&2; exit 3; fi
done
( cd "$DIST" && sha256sum store/*.prg32 naprider-napoli97-1.0.0-store.zip > SHA256SUMS )
echo "Built PRG32 main portable variants and Store bundle in $DIST"
