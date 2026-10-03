#!/usr/bin/env python3
"""Compose napRider-napoli97's original soundtrack and write audio.json.

The AUDIO block holds ten SID-like procedural instruments and eight tracker
tracks, so it stores no PCM at all. Music uses voices 0-3 (the tracker plays
instrument N on voice N); the game keeps voices 4-7 for the engine and
effects, which it pans by screen position.

Tracker timing: `delta` is the wait *after* an event, in ticks, so events
with delta 0 sound together (PRG32 docs/tools/audio.md). The tunes are
original; none quotes a television theme or a traditional melody.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TRI, SAW, PULSE, NOISE = range(4)


def synth(wave, pulse_width=8, cutoff=15, resonance=0):
    """PRG32_AUDIO_SYNTH_ID: bit 15 marker, resonance, cutoff, pulse width, waveform."""
    return 0x8000 | (resonance & 3) << 10 | (cutoff & 15) << 6 | (pulse_width & 15) << 2 | wave


def inst(sample_id, volume, pan, attack, decay, sustain, release):
    return {"sample_id": sample_id, "default_volume": volume, "default_pan": pan,
            "attack": attack, "decay": decay, "sustain": sustain, "release": release}


INSTRUMENTS = [
    inst(synth(PULSE, 6, 13, 1), 190, -24, 4, 96, 130, 70),    # 0 lead, left of centre
    inst(synth(PULSE, 3, 11, 0), 120, 24, 0, 70, 50, 50),      # 1 mandolin-like counter, right
    inst(synth(TRI, 8, 10, 1), 230, 0, 2, 90, 160, 60),        # 2 bass
    inst(synth(NOISE, 8, 12, 0), 90, 8, 0, 56, 0, 30),         # 3 tambourine / drum
    inst(synth(SAW, 8, 4, 2), 70, 0, 20, 0, 255, 60),          # 4 engine drone
    inst(synth(PULSE, 2, 14, 2), 170, 0, 0, 80, 0, 50),        # 5 turbo / gadget zap
    inst(synth(TRI, 8, 15, 0), 220, 0, 0, 110, 40, 90),        # 6 chime
    inst(synth(NOISE, 8, 7, 1), 220, 0, 0, 120, 0, 80),        # 7 crash
    inst(synth(PULSE, 8, 12, 0), 150, 0, 4, 0, 230, 40),       # 8 horn
    inst(synth(SAW, 8, 8, 3), 90, 0, 6, 40, 150, 50),          # 9 scooter two-stroke
]

NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(name):
    pitch = NOTE[name[0]]
    rest = name[1:]
    while rest[0] in "#b":
        pitch += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + pitch


def part(text, unit=1):
    """'E5 G5:2 r:3' -> [(midi or None, ticks)]"""
    out = []
    for tok in text.replace("|", " ").split():
        name, _, length = tok.partition(":")
        out.append((None if name == "r" else midi(name), int(length or 1) * unit))
    return out


def track(tempo, parts, loop=True):
    """Merge per-voice note lists into one delta-after event stream."""
    timeline = []
    length = 0
    for voice, notes in parts.items():
        tick = 0
        for note, ticks in notes:
            if note is None:
                timeline.append((tick, 0, "NOTE_OFF", voice, 0))
            else:
                timeline.append((tick, 1, "NOTE_ON", voice, note))
            tick += ticks
        length = max(length, tick)
    for voice, notes in parts.items():
        assert sum(t for _, t in notes) == length, f"voice {voice}: {sum(t for _, t in notes)} != {length}"
    timeline.sort()
    events = [{"delta": 0, "command": "SET_TEMPO", "arg0": tempo}]
    for i, (tick, _, command, arg0, arg1) in enumerate(timeline):
        nxt = timeline[i + 1][0] if i + 1 < len(timeline) else length
        assert nxt - tick < 256
        events.append({"delta": nxt - tick, "command": command, "arg0": arg0, "arg1": arg1})
    if loop:
        events.append({"delta": 0, "command": "JUMP", "arg0": 1, "arg1": 0})
    else:
        for voice in parts:
            events.append({"delta": 0, "command": "NOTE_OFF", "arg0": voice})
        events.append({"delta": 0, "command": "END"})
    return {"events": events}


def beat(pattern, bars, unit=1):
    return part(" ".join([pattern] * bars), unit)


TRACKS = [
    # 0 Decumano: title and Centro Storico, A minor 6/8 (one tick per quaver)
    track(100, {
        0: part("A4 C5 E5 A5 E5 C5 | B4 D5 E5 G#5 E5 D5 | A4 C5 E5 A5 B5 C6 | B5:2 G#5 E5:3 |"
                "F5 A5 F5 D5 F5 D5 | E5 G5 E5 C5 E5 C5 | D5 F5 D5 B4 D5 G#4 | A4:3 r:3 |"
                "C5 E5 G5 C6 G5 E5 | D5 G5 B5 D6 B5 G5 | C6 B5 A5 G5 F5 E5 | D5:2 E5 G5:3 |"
                "A5 E5 C5 A4 C5 E5 | G#5 E5 B4 G#4 B4 E5 | A4 B4 C5 D5 E5 G#5 | A5:3 r:3"),
        1: beat("r:2 E4 r:2 C4", 4) + beat("r:2 D4 r:2 A3", 2) + beat("r:2 E4 r:2 B3", 2)
           + beat("r:2 E4 r:2 G4", 4) + beat("r:2 E4 r:2 C4", 4),
        2: part("A2:3 E3:3 | E2:3 B2:3 | A2:3 E3:3 | E2:3 E3:3 | D3:3 A2:3 | C3:3 G2:3 | E2:3 E3:3 | A2:3 A2:3 |"
                "C3:3 G2:3 | G2:3 D3:3 | C3:3 G2:3 | G2:3 G2:3 | A2:3 E3:3 | E2:3 B2:3 | A2:3 E3:3 | A2:3 A2:3"),
        3: beat("C3:3 C6 C6 C6", 16),
    }),
    # 1 Lungomare: Posillipo, C major, easy four
    track(108, {
        0: part("E5:4 G5:2 C6:2 | B5:4 G5:4 | A5:4 C6:2 A5:2 | G5:6 r:2 |"
                "F5:4 A5:2 F5:2 | E5:4 G5:4 | D5:2 E5:2 F5:2 D5:2 | C5:6 r:2", 2),
        1: part("G4 C5 E5 C5 G4 C5 E5 C5 | G4 B4 E5 B4 G4 B4 E5 B4 | A4 C5 F5 C5 A4 C5 F5 C5 | G4 B4 D5 B4 G4 B4 D5 B4 |"
                "A4 C5 F5 C5 A4 C5 F5 C5 | G4 C5 E5 C5 G4 C5 E5 C5 | F4 A4 D5 A4 G4 B4 D5 B4 | G4 C5 E5 C5 G4 C5 E5 r", 2),
        2: part("C3:4 G2:4 | E3:4 B2:4 | F3:4 C3:4 | G2:4 D3:4 | F3:4 C3:4 | C3:4 G2:4 | D3:4 G2:4 | C3:4 C3:4", 2),
        3: beat("C3:2 C6:2 C6:2 C6:2", 8, 2),
    }),
    # 2 Vicoli: Quartieri Spagnoli, D minor, fast
    track(118, {
        0: part("A5 D6 A5 F5 A5 F5 | G5 Bb5 G5 E5 G5 E5 | F5 A5 F5 D5 F5 D5 | E5:2 C#5 A4:3 |"
                "D5 E5 F5 G5 A5 Bb5 | A5:2 F5 D5:3 | G5 F5 E5 D5 C#5 E5 | D5:3 r:3"),
        1: beat("r:2 F4 r:2 D4", 3) + beat("r:2 E4 r:2 C#4", 1) + beat("r:2 F4 r:2 D4", 2)
           + beat("r:2 E4 r:2 C#4", 1) + beat("r:2 F4 r:2 D4", 1),
        2: part("D3:3 A2:3 | C3:3 G2:3 | D3:3 A2:3 | A2:3 E3:3 | D3:3 D3:3 | D3:3 A2:3 | A2:3 E3:3 | D3:3 D3:3"),
        3: beat("C3:2 C6 C3 C6 C6", 8),
    }),
    # 3 Galleria: Vomero by night, E minor
    track(96, {
        0: part("E5:3 G5 B5:4 | A5:3 G5 F#5:4 | G5:3 E5 D5:4 | E5:6 r:2 |"
                "C5:3 E5 G5:4 | B4:3 D5 F#5:4 | A4:2 B4:2 C5:2 D#5:2 | E5:6 r:2", 2),
        1: part("E4:2 B4:2 E4:2 B4:2 | D4:2 A4:2 D4:2 A4:2 | C4:2 G4:2 C4:2 G4:2 | E4:2 B4:2 E4:2 B4:2 |"
                "C4:2 G4:2 C4:2 G4:2 | B3:2 F#4:2 B3:2 F#4:2 | A3:2 E4:2 B3:2 F#4:2 | E4:2 B4:2 E4:2 r:2", 2),
        2: part("E2:4 B2:4 | D3:4 A2:4 | C3:4 G2:4 | E2:4 B2:4 | C3:4 G2:4 | B2:4 F#2:4 | A2:4 B2:4 | E2:8", 2),
        3: beat("C3:4 C6:2 C6:2", 8, 2),
    }),
    # 4 Tramonto: Parco Virgiliano, F major barcarolle
    track(72, {
        0: part("C5:3 F5:3 | A5:2 G5 F5:3 | G5:3 Bb5:3 | A5:6 | D5:3 F5:3 | Bb5:2 A5 G5:3 | F5:2 E5 G5:3 | F5:6"),
        1: beat("r A4 C5 r A4 C5", 2) + beat("r G4 Bb4 r G4 Bb4", 1) + beat("r A4 C5 r A4 C5", 1)
           + beat("r Bb4 D5 r Bb4 D5", 1) + beat("r G4 Bb4 r G4 Bb4", 1) + beat("r G4 C5 r G4 C5", 1)
           + beat("r A4 C5 r A4 C5", 1),
        2: part("F2:3 C3:3 | F2:3 C3:3 | C3:3 G2:3 | F2:3 C3:3 | Bb2:3 F3:3 | G2:3 D3:3 | C3:3 C3:3 | F2:6"),
        3: beat("r:3 C6:3", 8),
    }),
    # 5 Tufo: Napoli Sotterranea, a slow phrygian drone
    track(60, {
        0: part("E5:4 F5:4 | E5:8 | D5:4 Bb4:4 | A4:8 | A5:2 G5:2 F5:2 E5:2 | F5:8 | E5:4 D#5:4 | E5:6 r:2"),
        1: part("r:6 E6:2 | r:3 C6:2 r:3 | r:5 Bb5:3 | r:2 E6:2 r:4 | r:8 | r:4 C6:2 r:2 | r:6 B5:2 | r:8"),
        2: part("A1:8 | A1:8 | Bb1:8 | A1:8 | F2:8 | D2:8 | E2:8 | A1:8"),
        3: beat("C2:8", 8),
    }),
    # 6 Equilibrio: the Egg, A major resolution of the Decumano theme
    track(84, {
        0: part("A4:2 C#5:2 E5:2 A5:6 | G#5:2 E5:2 B4:2 E5:6 | F#5:2 D5:2 A4:2 D5:6 | E5:2 C#5:2 A4:2 A4:6"),
        1: part("r:6 C#5:2 E5:2 C#5:2 | r:6 B4:2 E5:2 B4:2 | r:6 A4:2 D5:2 A4:2 | r:6 E4:2 A4:2 E4:2"),
        2: part("A2:12 | E2:12 | D3:12 | A2:12"),
        3: beat("r:12", 4),
    }),
    # 7 Senza benzina: game-over sting
    track(90, {
        0: part("A4:2 G4:2 F4:2 E4:6"),
        2: part("A2:2 G2:2 F2:2 E2:6"),
    }, loop=False),
]

out = ROOT / "audio.json"
out.write_text(json.dumps({"instruments": INSTRUMENTS, "tracks": TRACKS}, separators=(",", ":")) + "\n")
events = sum(len(t["events"]) for t in TRACKS)
print(f"{out.name}: {len(INSTRUMENTS)} instruments, {len(TRACKS)} tracks, {events} events ({events * 4} bytes)")
