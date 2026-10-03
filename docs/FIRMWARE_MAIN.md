# PRG32 `main` alignment

The cartridge targets `riscv-prg32/PRG32` branch `main`. Version 2.0.0 was built and run in QEMU at commit `a8669e5`.

## Limits

| | Firmware default | napRider 2.0.0 |
| --- | ---: | ---: |
| Stored `.prg32` package, metadata included | 65536 bytes | about 36 KiB |
| Executable cartridge RAM | 64 KiB (32 KiB classroom profile) | about 24 KiB |

`build.sh` passes `--cart-ram-kib 32` so the builder itself rejects a cartridge that would not fit the smallest profile, and fails if a Store variant exceeds 65536 bytes.

## Calls used

- Graphics: `prg32_sprite_draw_indexed`, `prg32_gfx_rect_indexed`, `prg32_gfx_clear_indexed`, `prg32_palette_set`, `prg32_gfx_text8`, `prg32_gfx_present`. No RGB565 fills: on the ESP32-C6 those are quantised per pixel.
- Audio: `prg32_audio_play_track`, `prg32_audio_stop_track`, `prg32_audio_note_on_pan`, `prg32_audio_note_off`.
- Runtime: `prg32_input_read`, `prg32_ticks_ms`, `prg32_band_set_game_info`, `prg32_score_count`, `prg32_score_get`, `prg32_score_submit_current_player`.

The palette calls arrived with ABI 1.5.

## Firmware behaviour the cartridge relies on

- **Indexed sprites on the ESP32-C6** are mapped colour by colour to the 6x6x6 system cube; QEMU writes the sprite's own RGB565 colours. See [ASSET_PIPELINE.md](ASSET_PIPELINE.md) for how the art gets exact colours on both.
- **`prg32_palette_set`** recolours pixels already on the ESP32-C6 screen; on QEMU it only affects later indexed draws. The playfield is redrawn every frame, so both show palette effects.
- **The framebuffer persists** between frames, so the HUD bands are redrawn only when they change.
- **The palette is not reset** between cartridges, so `naprider_init` restores the eight named colours it uses for text.
- **Frames are paced at 33 ms**; the simulation runs in 33 ms steps from `prg32_ticks_ms`, up to four per frame.
- **Tracker `delta`** is the wait after an event, and a `NOTE_ON` plays instrument N on voice N. Music stays on voices 0-3; the game's effects use 4-7.
- **Portable cartridges cannot carry pointer tables** in static data; strings are returned by functions and descriptors are filled at run time.

## QEMU

`python3 -m prg32 qemu build`, then stage and run the cartridge as in the README. `tools/qemu_capture.py` automates a scripted run and records it. The firmware needs the SDL display: with `-display none` it stalls at the splash screen.
