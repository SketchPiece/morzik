#!/usr/bin/env python3
"""Cuts CC0 / public-domain cat recordings (SOURCES.md) into single meows for the greeter:
finds the loud stretches, pads and fades them, evens out the loudness and writes 44.1 kHz
mono WAVs that aplay plays as is. Needs ffmpeg.

    python3 cut.py <source files…>     # writes meow-NN.wav next to this script
"""
import array, math, os, subprocess, sys

RATE, HOP = 44100, 441                     # 10 ms frames
FLOOR_DB, GAP, MIN_LEN, MAX_LEN, PAD = -28, 0.15, 0.3, 2.2, 0.04
HERE = os.path.dirname(os.path.realpath(__file__))


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return array.array("f", raw)


def segments(x):
    env = [math.sqrt(sum(v * v for v in x[i:i + HOP]) / HOP) for i in range(0, len(x) - HOP, HOP)]
    peak = max(env) or 1
    loud = [e > peak * 10 ** (FLOOR_DB / 20) for e in env]
    segs, start = [], None
    for i, on in enumerate(loud + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if segs and (start - segs[-1][1]) * HOP / RATE < GAP:
                segs[-1][1] = i
            else:
                segs.append([start, i])
            start = None
    return [(a * HOP / RATE, b * HOP / RATE) for a, b in segs if MIN_LEN <= (b - a) * HOP / RATE <= MAX_LEN]


def main(paths):
    n = 0
    for path in paths:
        x = decode(path)
        for a, b in segments(x):
            a, b = max(0, a - PAD), min(len(x) / RATE, b + PAD)
            n += 1
            out = os.path.join(HERE, f"meow-{n:02d}.wav")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", path,
                            "-af", f"afade=t=in:d=0.02,afade=t=out:st={b - a - 0.05:.3f}:d=0.05,"
                                   "highpass=f=200,loudnorm=I=-16:TP=-1.5:LRA=11",
                            "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", out], check=True)
            print(f"{os.path.basename(out)}  {os.path.basename(path)}  {a:.2f}–{b:.2f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
