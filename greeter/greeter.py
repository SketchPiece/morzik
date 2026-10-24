#!/usr/bin/env python3
"""Login screen for the server laptop's console (tty1): the animated pixel Morzik in the
avatar's colours and a random joke. Any other key meows (a random
recording, one at a time) through the laptop speaker; Enter hands the console to agetty for a
normal, silent login. When that session ends systemd starts this screen again.

The Linux console has 16 colours, which can be set to any RGB (ESC ] P n rrggbb, n in ANSI
order), so the palette in pixel.py becomes the console's own. Only the classic SGR colours
read that palette (30-37, bold for 8-15; 38;5;n is mapped to fixed colours instead), and
only 8 of them work as backgrounds, so every pixel is drawn as foreground █ blocks on the
navy background (slot 0). The console font has █ but not ▀/▄, so pixels are whole cells:
SX columns by SY rows; 2×1 is a square 24 px pixel with the 12×24 Terminus font the
server's console uses (sketch-server, setup/50-greeter.sh).
"""
import glob, os, random, select, subprocess, sys, termios, time, tty
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from pixel import FPS, PALETTE, timeline

SX, SY = 2, 1
JOKES = Path(os.environ.get("MORZIK_GREETER_JOKES", "/usr/local/share/morzik-greeter/jokes.tsv"))
MEOWS = Path(os.environ.get("MORZIK_GREETER_MEOWS", "/usr/local/share/morzik-greeter/meows"))
RECENT = Path("/var/lib/morzik-greeter/recent")
AGETTY = ["/usr/sbin/agetty", "--noreset", "--noclear",
          "--issue-file=/etc/issue:/etc/issue.d:/run/issue.d:/usr/lib/issue.d", "-", os.environ.get("TERM", "linux")]
FALLBACK = [("тут живёт морзик", "пароль не скажу, даже за вкусняшку"), ("мур. это мой компьютер", "если ты хозяин, заходи")]

# one console palette slot per art colour; '.' (background) takes slot 0 so the whole screen is navy
SLOT = {ch: i for i, ch in enumerate(["."] + [c for c in PALETTE if c != "."])}
TEXT_TOP, TEXT_BOTTOM, TEXT_KEY = SLOT["H"], SLOT["h"], SLOT["O"]


def out(s):
    os.write(sys.stdout.fileno(), s.encode())


def fg(slot):
    return f"\033[{'1' if slot >= 8 else '22'};{30 + slot % 8}m"


BG = "\033[40m"


def set_palette():
    out("".join(f"\033]P{SLOT[ch]:x}{rgb[1:]}" for ch, rgb in PALETTE.items()))


def pick_joke():
    try:
        jokes = [tuple(l.split("\t", 1)) for l in JOKES.read_text().splitlines() if "\t" in l]
    except OSError:
        jokes = []
    jokes = jokes or FALLBACK
    try:
        recent = [int(x) for x in RECENT.read_text().split()]
    except (OSError, ValueError):
        recent = []
    fresh = [i for i in range(len(jokes)) if i not in recent] or list(range(len(jokes)))
    i = random.choice(fresh)
    try:
        RECENT.parent.mkdir(parents=True, exist_ok=True)
        RECENT.write_text(" ".join(map(str, (recent + [i])[-min(30, len(jokes) // 2):])))
    except OSError:
        pass
    return jokes[i]


class Meower:
    """Plays a random meow for a key press, unless one is still playing (no chorus when keys are mashed)."""

    def __init__(self):
        self.files, self.proc, self.last = sorted(MEOWS.glob("*.wav")), None, None

    def meow(self):
        if not self.files or (self.proc and self.proc.poll() is None):
            return
        f = random.choice([f for f in self.files if f != self.last] or self.files)
        try:
            self.proc = subprocess.Popen(["aplay", "-q", str(f)], stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.last = f
        except OSError:
            self.files = []                     # no aplay: stay quiet

    def hush(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        if self.proc:
            self.proc.wait()


def lid_closed():
    for f in glob.glob("/proc/acpi/button/lid/*/state"):
        try:
            if "closed" in Path(f).read_text():
                return True
        except OSError:
            pass
    return False


def cells(frame):
    """The art colour of every text cell for one frame."""
    rows = frame.split("\n")
    return [[ch for ch in row for _ in range(SX)] for row in rows for _ in range(SY)]


def draw(grid, prev, x0, y0):
    buf = []
    for r, row in enumerate(grid):
        c = 0
        while c < len(row):
            if prev is not None and prev[r][c] == row[c]:
                c += 1
                continue
            start, ch = c, row[c]                    # a run of changed cells of one colour
            while c < len(row) and row[c] == ch and (prev is None or prev[r][c] != ch):
                c += 1
            glyph = " " if ch == "." else "█"
            buf.append(f"\033[{y0 + r + 1};{x0 + start + 1}H{fg(SLOT[ch])}{BG}{glyph * (c - start)}")
    if buf:
        out("".join(buf) + "\033[0m")


def centered(y, cols, parts):
    """parts: [(text, colour slot)] on one line, centred."""
    width = sum(len(t) for t, _ in parts)
    out(f"\033[{y + 1};{max(1, (cols - width) // 2 + 1)}H"
        + "".join(f"{fg(slot)}{BG}{t}" for t, slot in parts) + "\033[0m")


def screen():
    frames, seq = timeline(29)
    grids = [cells(f) for f in frames]
    cols, lines = os.get_terminal_size()
    art_w, art_h = len(grids[0][0]), len(grids[0])
    x0, y0 = max(0, (cols - art_w) // 2), max(0, (lines - art_h - 6) // 2)
    top, bottom = pick_joke()

    set_palette()
    out("\033[?25l\033[0m" + BG + "\033[2J")
    def text():
        centered(y0 + art_h + 2, cols, [(top, TEXT_TOP)])
        centered(y0 + art_h + 3, cols, [(bottom, TEXT_BOTTOM)])
        centered(y0 + art_h + 5, cols, [("Enter", TEXT_KEY), (" — войти", TEXT_BOTTOM)])
    text()

    fd = sys.stdin.fileno()
    meower = Meower()
    i, prev, was_closed = 0, None, False
    while True:
        closed = lid_closed()
        if closed:
            was_closed = True
            if select.select([fd], [], [], 1)[0] and os.read(fd, 64):
                pass
            continue
        if was_closed:                          # lid opened again: new joke, full redraw
            was_closed, prev = False, None
            top, bottom = pick_joke()
            out(BG + "\033[2J"); text()
        g = grids[seq[i]]
        draw(g, prev, x0, y0)
        prev, i = g, (i + 1) % len(seq)
        if select.select([fd], [], [], 1 / FPS)[0]:
            keys = os.read(fd, 64)
            if any(b in (10, 13) for b in keys):
                meower.hush()
                return
            if keys:
                meower.meow()


def main():
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)                       # keys one by one, no echo
        screen()
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, saved)
        out("\033]R\033[0m\033[2J\033[H\033[?25h")   # console's own palette back for the login and the shell
    os.execv(AGETTY[0], AGETTY)


if __name__ == "__main__":
    main()
