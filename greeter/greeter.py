#!/usr/bin/env python3
"""Login screen for the server laptop's console (tty1): the animated pixel Morzik in the
avatar's colours and a random joke. Enter hands the console to agetty for a normal login;
when that session ends systemd starts this screen again.

The Linux console has 16 colours, which can be set to any RGB (ESC ] P), so the palette
in pixel.py becomes the console's own. Each art pixel is SCALE columns wide and SCALE
half-rows tall, drawn with ▀ (top half in the foreground colour, bottom in the background).
"""
import glob, os, random, select, sys, termios, time, tty
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from pixel import FPS, PALETTE, timeline

SCALE = 3
JOKES = Path(os.environ.get("MORZIK_GREETER_JOKES", "/usr/local/share/morzik-greeter/jokes.tsv"))
RECENT = Path("/var/lib/morzik-greeter/recent")
AGETTY = ["/usr/sbin/agetty", "--noreset", "--noclear",
          "--issue-file=/etc/issue:/etc/issue.d:/run/issue.d:/usr/lib/issue.d", "-", os.environ.get("TERM", "linux")]
FALLBACK = [("тут живёт морзик", "пароль не скажу, даже за вкусняшку"), ("мур. это мой компьютер", "если ты хозяин, заходи")]

# one console palette slot per art colour; '.' (background) takes slot 0 so the whole screen is navy
SLOT = {ch: i for i, ch in enumerate(["."] + [c for c in PALETTE if c != "."])}
TEXT_TOP, TEXT_BOTTOM, TEXT_KEY = SLOT["H"], SLOT["h"], SLOT["O"]


def out(s):
    os.write(sys.stdout.fileno(), s.encode())


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


def lid_closed():
    for f in glob.glob("/proc/acpi/button/lid/*/state"):
        try:
            if "closed" in Path(f).read_text():
                return True
        except OSError:
            pass
    return False


def cells(frame):
    """Text cells (top colour, bottom colour) for one frame at SCALE."""
    rows = frame.split("\n")
    w, h2 = len(rows[0]) * SCALE, len(rows) * SCALE
    def px(y, x):
        return rows[y // SCALE][x // SCALE] if y < h2 else "."
    return [[(px(2 * r, x), px(2 * r + 1, x)) for x in range(w)] for r in range((h2 + 1) // 2)]


def draw(grid, prev, x0, y0):
    buf = []
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if prev is not None and prev[r][c] == cell:
                continue
            top, bot = cell
            buf.append(f"\033[{y0 + r + 1};{x0 + c + 1}H\033[38;5;{SLOT[top]};48;5;{SLOT[bot]}m"
                       + ("▀" if top != bot else " "))
    if buf:
        out("".join(buf) + "\033[0m")


def centered(y, cols, parts):
    """parts: [(text, colour slot)] on one line, centred."""
    width = sum(len(t) for t, _ in parts)
    out(f"\033[{y + 1};{max(1, (cols - width) // 2 + 1)}H"
        + "".join(f"\033[38;5;{slot};48;5;0m{t}" for t, slot in parts) + "\033[0m")


def screen():
    frames, seq = timeline(29)
    grids = [cells(f) for f in frames]
    cols, lines = os.get_terminal_size()
    art_w, art_h = len(grids[0][0]), len(grids[0])
    x0, y0 = max(0, (cols - art_w) // 2), max(0, (lines - art_h - 6) // 2)
    top, bottom = pick_joke()

    set_palette()
    out("\033[?25l\033[0m\033[48;5;0m\033[2J")
    def text():
        centered(y0 + art_h + 2, cols, [(top, TEXT_TOP)])
        centered(y0 + art_h + 3, cols, [(bottom, TEXT_BOTTOM)])
        centered(y0 + art_h + 5, cols, [("Enter", TEXT_KEY), (" — войти", TEXT_BOTTOM)])
    text()

    fd = sys.stdin.fileno()
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
            out("\033[48;5;0m\033[2J"); text()
        g = grids[seq[i]]
        draw(g, prev, x0, y0)
        prev, i = g, (i + 1) % len(seq)
        if select.select([fd], [], [], 1 / FPS)[0]:
            if any(b in (10, 13) for b in os.read(fd, 64)):
                return


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
