#!/usr/bin/env python3
"""Login screen for the server laptop's console (tty1): the animated pixel Morzik in the
avatar's colours and a random joke, and the keyboard games in play.py (scratching, words,
morse, a laser dot, dozing off). A lone key meows (a random recording, one at a time) through
the laptop speaker; Enter hands the console to agetty for a normal, silent login. When that
session ends systemd starts this screen again.

The Linux console has 16 colours, which can be set to any RGB (ESC ] P n rrggbb, n in ANSI
order), so the palette in pixel.py becomes the console's own. Only the classic SGR colours
read that palette (30-37, bold for 8-15; 38;5;n is mapped to fixed colours instead), and
only 8 of them work as backgrounds, so every pixel is drawn as foreground █ blocks on the
navy background (slot 0). The console font has █ but not ▀/▄, so pixels are whole cells:
SX columns by SY rows; 2×1 is a square 24 px pixel with the 12×24 Terminus font the
server's console uses (sketch-server, setup/50-greeter.sh). All 16 slots are taken, so the
red laser dot borrows the dimmer whisker slot while it is out (the whiskers stay lit then).
"""
import datetime, glob, os, random, select, signal, subprocess, sys, termios, time, tty
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from pixel import FPS, PALETTE, build
from keys import Keys, from_text
import play

SX, SY = 2, 1
JOKES = Path(os.environ.get("MORZIK_GREETER_JOKES", "/usr/local/share/morzik-greeter/jokes.tsv"))
MEOWS = Path(os.environ.get("MORZIK_GREETER_MEOWS", "/usr/local/share/morzik-greeter/meows"))
SOUNDS = Path(os.environ.get("MORZIK_GREETER_SOUNDS", "/usr/local/share/morzik-greeter/sounds"))
STATE = Path(os.environ.get("MORZIK_GREETER_STATE", "/var/lib/morzik-greeter"))
RECENT, SCRATCHED = STATE / "recent", STATE / "scratched"
RED = "#ff2a2a"
AGETTY = ["/usr/sbin/agetty", "--noreset", "--noclear",
          "--issue-file=/etc/issue:/etc/issue.d:/run/issue.d:/usr/lib/issue.d", "-", os.environ.get("TERM", "linux")]
FALLBACK = [("тут живёт морзик", "пароль не скажу, даже за вкусняшку"), ("мур. это мой компьютер", "если ты хозяин, заходи")]

# one console palette slot per art colour; '.' (background) takes slot 0 so the whole screen is navy
SLOT = {ch: i for i, ch in enumerate(["."] + [c for c in PALETTE if c != "."])}
SLOT["R"] = SLOT["y"]                   # the laser dot, see above
TEXT_TOP, TEXT_BOTTOM, TEXT_KEY = SLOT["H"], SLOT["h"], SLOT["O"]


def out(s):
    os.write(sys.stdout.fileno(), s.encode())


def fg(slot):
    return f"\033[{'1' if slot >= 8 else '22'};{30 + slot % 8}m"


BG = "\033[40m"


def set_palette(red=False):
    out("".join(f"\033]P{SLOT[ch]:x}{(RED if red and ch == 'y' else rgb)[1:]}" for ch, rgb in PALETTE.items()))


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


class Sounds:
    """The laptop speaker: a random meow for a lone key (unless one is still playing, so no
    chorus when keys are mashed), a hiss, and a purr looped for as long as he is scratched."""

    def __init__(self):
        self.files, self.proc, self.last, self.purr = sorted(MEOWS.glob("*.wav")), None, None, None

    def play(self, name):
        if name == "purr": return self.purr_on()
        if name == "-purr": return self.purr_off()
        if name == "meow":
            if not self.files or (self.proc and self.proc.poll() is None):
                return
            f = random.choice([f for f in self.files if f != self.last] or self.files)
            self.last = f
        else:
            f = SOUNDS / f"{name}.wav"
            if not f.exists(): return
            self.kill()
        try:
            self.proc = subprocess.Popen(["aplay", "-q", str(f)], stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.files = []                     # no aplay: stay quiet

    def purr_on(self):
        f = SOUNDS / "purr.wav"
        if self.purr or not f.exists(): return
        try:
            self.purr = subprocess.Popen(["sh", "-c", 'while aplay -q "$0"; do :; done', str(f)], start_new_session=True,
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def purr_off(self):
        if self.purr:
            try:
                os.killpg(self.purr.pid, signal.SIGTERM)
            except OSError:
                pass
            self.purr.wait()
            self.purr = None

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        if self.proc:
            self.proc.wait()

    def hush(self):
        self.kill()
        self.purr_off()


def scratched_today():
    try:
        return SCRATCHED.read_text().strip() == datetime.date.today().isoformat()
    except OSError:
        return False


def remember_scratch():
    try:
        SCRATCHED.parent.mkdir(parents=True, exist_ok=True)
        SCRATCHED.write_text(datetime.date.today().isoformat())
    except OSError:
        pass


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


Z_SMALL, Z_BIG = ["hhhh", "..h.", ".h..", "hhhh"], ["HHHHH", "...H.", "..H..", ".H...", "HHHHH"]
DOT = [".RR.", "RRRR", "RRRR", ".RR."]
_heads = {}


def head(pose):
    key = tuple(sorted(pose.items()))
    if key not in _heads:
        if len(_heads) > 500: _heads.clear()
        _heads[key] = build(**pose)[:play.HEAD_ROWS]
    return _heads[key]


def stage(f, height):
    """One frame of the stage as art characters: the head where it stands, then the z's and the dot."""
    g = [["."] * play.STAGE_W for _ in range(height)]
    def put(x, y, ch):
        if ch != "." and 0 <= x < play.STAGE_W and 0 <= y < height: g[y][x] = ch
    for y, row in enumerate(head(f["pose"])):
        for x, ch in enumerate(row):
            put(play.CAT_X + f["dx"] + x, play.CAT_Y + f["dy"] + y, ch)
    for x, y, big in f["z"]:
        for j, row in enumerate(Z_BIG if big else Z_SMALL):
            for i, ch in enumerate(row): put(x + i, y + j, ch)
    if f["dot"]:
        for j, row in enumerate(DOT):
            for i, ch in enumerate(row): put(f["dot"][0] + i, f["dot"][1] + j, ch)
    return ["".join(r) for r in g]


def screen():
    cols, lines = os.get_terminal_size()
    height = max(play.CAT_Y + play.HEAD_ROWS, min(play.STAGE_H, lines - 6))
    art_w = play.STAGE_W * SX
    x0, y0 = max(0, (cols - art_w) // 2), max(0, (lines - height * SY - 6) // 2)
    ty = y0 + height * SY
    joke = pick_joke()

    set_palette()
    out("\033[?25l\033[0m" + BG + "\033[2J")
    NOTHING = object()
    shown = [NOTHING]                   # what the text lines show now; None is the joke
    def text(t):
        """t: None for the joke, ("say", top, bottom) or ("morse", marks, letters)."""
        if t == shown[0]: return
        shown[0] = t
        for y in (ty + 1, ty + 2):
            out(f"\033[{y + 1};1H{BG}\033[2K")
        if t is None:
            centered(ty + 1, cols, [(joke[0], TEXT_TOP)]); centered(ty + 2, cols, [(joke[1], TEXT_BOTTOM)])
        elif t[0] == "morse":
            centered(ty + 1, cols, [(t[1], TEXT_KEY)]); centered(ty + 2, cols, [(t[2], TEXT_TOP)])
        else:
            centered(ty + 1, cols, [(t[1], TEXT_TOP)]); centered(ty + 2, cols, [(t[2], TEXT_BOTTOM)])
        centered(ty + 4, cols, [("Enter", TEXT_KEY), (" — войти", TEXT_BOTTOM)])

    fd = sys.stdin.fileno()
    sounds, keys = Sounds(), Keys()
    cat = play.Cat(time.monotonic())
    cat.scratched = scratched_today()
    remembered = cat.scratched
    prev, red, was_closed, leaving = None, False, False, None
    try:
        while True:
            if lid_closed():
                if not was_closed:
                    sounds.hush()
                was_closed = True
                if select.select([fd], [], [], 1)[0] and os.read(fd, 64):
                    pass
                continue
            if was_closed:                      # lid opened again: new joke, a fresh cat, full redraw
                was_closed, prev, shown[0] = False, None, NOTHING
                joke = pick_joke()
                cat = play.Cat(time.monotonic()); cat.scratched = scratched_today()
                out(BG + "\033[2J")
            now = time.monotonic()
            if leaving is not None and now >= leaving:
                return
            cat.live_keys = keys.live
            f = cat.frame(now)
            if red and not f["red"]:            # back to the whisker colour before it is drawn again
                red = False
                set_palette()
            g = cells("\n".join(stage(f, height)))
            draw(g, prev, x0, y0)
            prev = g
            if f["red"] and not red:            # the whiskers are lit by now, so the slot is free
                red = True
                set_palette(red=True)
            text(f["text"])
            for name in f["sounds"]:
                sounds.play(name)
            if cat.scratched and not remembered:
                remembered = True
                remember_scratch()
            wait = [fd] + keys.files()
            ready = select.select(wait, [], [], 1 / FPS)[0]
            for r in ready:
                if r == fd:
                    data = os.read(fd, 64)
                    if any(b in (10, 13) for b in data) and leaving is None:
                        sounds.hush()
                        if not cat.goodbye(time.monotonic()):
                            return
                        leaving = time.monotonic() + 1.7     # just inside his goodbye scene
                    elif not keys.live and leaving is None:
                        for t, k, down in from_text(data.decode(errors="ignore"), time.monotonic()):
                            cat.key(t, k, down)
                elif leaving is None:
                    for t, k, down in keys.read(r):
                        if k != "enter":
                            cat.key(t, k, down)
    finally:
        sounds.hush()


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
