#!/usr/bin/env python3
"""Run the cartridge in PRG32's QEMU firmware and record what it really does.

The cartridge is staged into a private copy of the firmware's flash image and
booted in Espressif QEMU. The tool then:

- plays a scripted demo through the UART keyboard mapper;
- copies the firmware's 320x240 frame buffer out of guest memory with the
  QEMU monitor's `pmemsave` (no screen-recording permission needed) and keeps
  the 320x200 playfield;
- feeds the firmware's credit-paced UART audio and records the 22050 Hz PCM;
- writes PNG screenshots and, with ffmpeg, an MP4 with the real soundtrack.

Usage (after `python3 -m prg32 qemu build` in the PRG32 checkout and ./build.sh):

    PRG32_ROOT=/path/to/PRG32 python3 tools/qemu_capture.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image

GAME = Path(__file__).resolve().parents[1]
RATE = 22050
CONSOLE_PORT, AUDIO_PORT, MONITOR_PORT = 5551, 4321, 5552

# Demo script, in seconds after the title screen is up: (start, end, keys).
# Keys are held by resending them faster than the firmware's 120 ms key hold.
RIGHT, LEFT, UP, DOWN, A, B, SELECT = "d", "a", "w", "s", "j", "k", " "
DEMO = [
    (2.0, 2.1, A),                 # start
    (5.0, 60.0, RIGHT),            # accelerate for the whole run
    (7.0, 7.5, DOWN), (10.0, 10.4, UP), (12.0, 12.1, A),      # lanes, then turbo
    (15.0, 15.6, UP), (18.0, 18.8, DOWN), (21.0, 21.1, A),
    (24.0, 24.5, UP), (27.0, 27.1, B),                        # self-drive on
    (28.5, 28.6, A), (30.0, 30.1, RIGHT), (31.0, 31.1, A),    # gadgets
    (33.0, 33.1, B), (36.0, 36.6, DOWN), (40.0, 40.5, UP),
    (44.0, 44.1, A), (48.0, 48.6, DOWN), (53.0, 53.5, UP),
]
SHOTS = {"title": 1.0, "intro": 3.2, "drive": 9.0, "turbo": 12.4, "gangs": 22.0, "self-drive": 29.0}


def connect(port: int, process: subprocess.Popen, timeout: float = 20.0) -> socket.socket:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"QEMU exited early with status {process.returncode}")
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=1)
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"timed out connecting to QEMU port {port}")


def audio_worker(process: subprocess.Popen, samples: bytearray, recording: threading.Event,
                 stopping: threading.Event) -> None:
    """Grant one 20 ms credit at a time, as the host audio player does."""
    sock = connect(AUDIO_PORT, process)
    chunk = 441 * 2
    try:
        sock.sendall(b"K")
        next_credit = time.monotonic() + 0.02
        while not stopping.is_set() and process.poll() is None:
            data = bytearray()
            while len(data) < chunk:
                part = sock.recv(chunk - len(data))
                if not part:
                    return
                data.extend(part)
            if recording.is_set():
                samples.extend(data)
            delay = next_credit - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            next_credit += 0.02
            sock.sendall(b"K")
    except OSError:
        return
    finally:
        sock.close()


def drain(sock: socket.socket, sink: bytearray, stopping: threading.Event) -> None:
    sock.settimeout(0.2)
    while not stopping.is_set():
        try:
            data = sock.recv(4096)
        except (TimeoutError, socket.timeout):
            continue
        except OSError:
            return
        if not data:
            return
        sink.extend(data)


PANEL_W, PANEL_H = 320, 240


def framebuffer_address(elf: Path) -> int:
    """Address of the firmware's RGB565 frame buffer (`g_fb`) in the QEMU build."""
    tools = sorted(Path.home().glob(".espressif/tools/riscv32-esp-elf/*/riscv32-esp-elf/bin"))
    nm = shutil.which("riscv32-esp-elf-nm", path=os.pathsep.join([str(t) for t in tools] + [os.environ["PATH"]]))
    if not nm:
        raise SystemExit("riscv32-esp-elf-nm not found; source the ESP-IDF environment")
    for line in subprocess.run([nm, str(elf)], check=True, capture_output=True, text=True).stdout.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] == "g_fb":
            return int(fields[0], 16)
    raise SystemExit(f"g_fb not found in {elf}")


def grab(monitor: socket.socket, address: int, path: Path) -> Image.Image | None:
    """Copy the firmware frame buffer out of guest memory; keep the 320x200 playfield."""
    size = PANEL_W * PANEL_H * 2
    path.unlink(missing_ok=True)
    monitor.sendall(f"pmemsave {address:#x} {size} \"{path}\"\n".encode())
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size == size:
            raw = np.frombuffer(path.read_bytes(), dtype="<u2").reshape(PANEL_H, PANEL_W)[20:220]
            rgb = np.dstack(((raw >> 11) * 255 // 31, ((raw >> 5) & 63) * 255 // 63, (raw & 31) * 255 // 31))
            return Image.fromarray(rgb.astype(np.uint8), "RGB")
        time.sleep(0.004)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prg32-root", type=Path, default=Path(os.environ.get("PRG32_ROOT", GAME.parent / "PRG32")))
    parser.add_argument("--cartridge", type=Path, default=GAME / "build/naprider-napoli97-base.prg32")
    parser.add_argument("--out", type=Path, default=GAME / "release-artifacts")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--warmup", type=float, default=7.0, help="seconds from reset to the title screen")
    parser.add_argument("--store-shot", default="drive", help="shot copied to assets/generated/screenshot.png")
    parser.add_argument("--display", default="sdl", help="QEMU display back end; the firmware stalls with `none`")
    args = parser.parse_args()

    root = args.prg32_root.resolve()
    for required in (root / "build-qemu/qemu_flash.bin", root / "build-qemu/qemu_efuse.bin", args.cartridge):
        if not required.exists():
            raise SystemExit(f"missing {required}")
    qemu = shutil.which("qemu-system-riscv32", path=os.pathsep.join(
        [str(p) for p in sorted(Path.home().glob(".espressif/tools/qemu-riscv32/*/qemu/bin"))] + [os.environ["PATH"]]))
    if not qemu:
        raise SystemExit("qemu-system-riscv32 (Espressif build) not found")
    ffmpeg = shutil.which("ffmpeg")
    fb_address = framebuffer_address(root / "build-qemu/PRG32.elf")
    shots_dir = args.out / "qemu"
    shots_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="naprider-qemu-") as temp_name:
        temp = Path(temp_name)
        flash, efuse = temp / "flash.bin", temp / "efuse.bin"
        shutil.copy2(root / "build-qemu/qemu_flash.bin", flash)
        shutil.copy2(root / "build-qemu/qemu_efuse.bin", efuse)
        subprocess.run([sys.executable, "-m", "prg32", "qemu", "upload", str(args.cartridge.resolve()),
                        "--flash", str(flash), "--cart-ram-kib", "64"], cwd=root, check=True)
        command = [
            qemu, "-M", "esp32c3", "-m", "4M",
            "-drive", f"file={flash},if=mtd,format=raw",
            "-drive", f"file={efuse},if=none,format=raw,id=efuse",
            "-global", "driver=nvram.esp32c3.efuse,property=drive,value=efuse",
            "-global", "driver=timer.esp32c3.timg,property=wdt_disable,value=true",
            "-nic", "user,model=open_eth", "-display", args.display,
            "-monitor", f"tcp:127.0.0.1:{MONITOR_PORT},server=on,wait=off",
            "-serial", f"tcp:127.0.0.1:{CONSOLE_PORT},server=on,wait=off,nodelay=on",
            "-serial", f"tcp:127.0.0.1:{AUDIO_PORT},server=on,wait=on,nodelay=on",
        ]
        samples, transcript, monitor_log = bytearray(), bytearray(), bytearray()
        recording, stopping = threading.Event(), threading.Event()
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threads = [threading.Thread(target=audio_worker, args=(process, samples, recording, stopping), daemon=True)]
        threads[0].start()
        console = connect(CONSOLE_PORT, process)
        monitor = connect(MONITOR_PORT, process)
        threads.append(threading.Thread(target=drain, args=(console, transcript, stopping), daemon=True))
        threads.append(threading.Thread(target=drain, args=(monitor, monitor_log, stopping), daemon=True))
        for thread in threads[1:]:
            thread.start()
        frames: list[tuple[float, Path]] = []
        try:
            time.sleep(args.warmup)
            recording.set()
            start = time.monotonic()
            pending = dict(SHOTS)
            last_key: dict[str, float] = {}
            index = 0
            while (now := time.monotonic() - start) < args.duration:
                for begin, end, key in DEMO:
                    if begin <= now < end and now - last_key.get(key, -1.0) >= 0.06:
                        console.sendall(key.encode())
                        last_key[key] = now
                image = grab(monitor, fb_address, temp / "panel.bin")
                if image is None:
                    continue
                time.sleep(max(0.0, 1 / 30 - (time.monotonic() - start - now)))
                frame = temp / f"frame-{index:05d}.png"
                image.save(frame)
                frames.append((now, frame))
                index += 1
                for name, when in list(pending.items()):
                    if now >= when:
                        image.save(shots_dir / f"{name}.png", optimize=True)
                        del pending[name]
            if process.poll() is not None:
                raise RuntimeError("QEMU stopped during the capture")
        finally:
            stopping.set()
            process.terminate()
            process.wait(timeout=10)
            for sock in (console, monitor):
                sock.close()
            log = [line for line in bytes(transcript).decode(errors="replace").splitlines()
                   if not line.startswith("TRACKER ")]          # drop the firmware's per-note trace
            (shots_dir / "boot-log.txt").write_text("\n".join(log) + "\n")
            if not frames:
                print(monitor_log.decode(errors="replace")[-600:])

        shot = shots_dir / f"{args.store_shot}.png"
        if args.out.resolve() == (GAME / "release-artifacts").resolve() and shot.exists():
            Image.open(shot).quantize(colors=64, dither=Image.Dither.NONE).save(
                GAME / "assets/generated/screenshot.png", optimize=True)
        if len(frames) < 10:
            raise SystemExit("QEMU produced no frames; see release-artifacts/qemu/boot-log.txt")
        distinct = len({Image.open(path).tobytes() for _, path in frames[:: max(1, len(frames) // 40)]})
        print(f"{len(frames)} frames in {args.duration:g} s ({len(frames) / args.duration:.1f} fps), "
              f"{distinct} distinct in a sample of 40, {len(samples) // 2} audio samples")
        with wave.open(str(temp / "audio.wav"), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(bytes(samples[: int(args.duration * RATE) * 2]))
        if ffmpeg:
            listing = temp / "frames.txt"
            lines = []
            for i, (when, path) in enumerate(frames):
                nxt = frames[i + 1][0] if i + 1 < len(frames) else args.duration
                lines += [f"file '{path}'", f"duration {max(nxt - when, 0.001):.4f}"]
            lines.append(f"file '{frames[-1][1]}'")
            listing.write_text("\n".join(lines) + "\n")
            video = args.out / "naprider-napoli97-qemu-demo.mp4"
            subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                            "-i", str(temp / "audio.wav"), "-vf", "scale=640:400:flags=neighbor,fps=30",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-b:a", "96k",
                            "-t", f"{args.duration:g}", "-movflags", "+faststart", str(video)], check=True)
            print(f"wrote {video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
