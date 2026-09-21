# Changelog

## Unreleased

- Fixed the road's left-edge row scrolling at the district (one-quarter) parallax speed instead of full road speed, which drifted it out of sync with the rest of the roadway and with fragment/collision detection.
- Fixed `SELECT+B` (toggle headlights) not registering when `SELECT` is pressed and held before `B`; only the reverse press order worked previously.
- Corrected stale documentation: tile bank is 72 frames (not 66), the game is horizontal-parallax (not isometric), and the asset pipeline has no scikit-learn dependency.

## 1.0.0 — 2026-09-13

- Renamed the saga entry to **napRider-napoli97**.
- Retargeted the project to PRG32 `main` portable ABI build flow.
- Replaced the San Gennaro treasure campaign with a mythological Virgil's Egg storyline.
- Added Napoli Sotterranea as the final dungeon-like stage and a two-choice ending.
- Converted runtime art to 8-bpp indexed sprites and a 72-frame semantic tile bank with byte-coded Naples district maps.
- Preserved the recognizable white 1971 Fiat 500 L as dedicated pseudo-3D directional art.
- Retained manual/self-drive, turbo, handbrake, fuel/battery/lights, scooter gangs and arcade gadgets.
- Added GitHub Actions, Store metadata, reproducible asset tooling and strict source checks.
