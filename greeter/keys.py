"""Keys for the login screen games, read straight from the keyboards (/dev/input/event*):
presses and releases with their times, several keys at once, whatever the console layout.
Key names are the US labels of the physical keys ("a", "space", "left"…). The greeter runs
as root under getty, so it may read them; it only listens, the keys still reach the console.
Without access (or in a test run) the console's characters stand in: each one is a press and
a release at once, mapped back to its key on the US or the Russian layout."""
import glob, os, re, struct, time

EVENT = struct.Struct("llHHi")          # struct input_event on 64-bit: time, type, code, value
EV_KEY = 1
CODES = {**{2 + i: k for i, k in enumerate("1234567890")}, 12: "-",
         **{16 + i: k for i, k in enumerate("qwertyuiop")}, 26: "[", 27: "]",
         **{30 + i: k for i, k in enumerate("asdfghjkl")}, 39: ";", 40: "'",
         **{44 + i: k for i, k in enumerate("zxcvbnm")}, 51: ",", 52: ".",
         57: "space", 28: "enter", 103: "up", 105: "left", 106: "right", 108: "down"}
RU = dict(zip("qwertyuiop[]asdfghjkl;'zxcvbnm,.", "йцукенгшщзхъфывапролджэячсмитьбю"))
FROM_CHAR = {**{k: k for k in CODES.values() if len(k) == 1}, **{v: k for k, v in RU.items()}, " ": "space",
             "\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left"}


def keyboards():
    """Event devices that have letter keys (KEY_A is bit 30 of the KEY capability bitmap)."""
    found = []
    try:
        text = open("/proc/bus/input/devices").read()
    except OSError:
        return found
    for block in text.split("\n\n"):
        handlers = re.search(r"H: Handlers=(.*)", block)
        bits = re.search(r"B: KEY=([0-9a-f ]+)", block)
        if not handlers or not bits:
            continue
        words = bits.group(1).split()
        if words and int(words[-1], 16) >> 30 & 1:
            found += ["/dev/input/" + h for h in handlers.group(1).split() if h.startswith("event")]
    return found


class Keys:
    """Opens the keyboards (again every few seconds, so a USB one plugged in later counts)
    and turns their events into (time, key, down) tuples."""

    def __init__(self):
        self.fds, self.scanned = {}, 0

    def scan(self):
        if time.monotonic() - self.scanned < 3:
            return
        self.scanned = time.monotonic()
        for path in keyboards():
            if path not in self.fds:
                try:
                    self.fds[path] = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                except OSError:
                    pass

    @property
    def live(self):
        return bool(self.fds)

    def files(self):
        self.scan()
        return list(self.fds.values())

    def read(self, fd):
        """Events waiting on one device fd."""
        out = []
        try:
            data = os.read(fd, EVENT.size * 64)
        except BlockingIOError:
            return out
        except OSError:                         # unplugged
            for path, f in list(self.fds.items()):
                if f == fd:
                    os.close(fd); del self.fds[path]
            return out
        now = time.monotonic()
        for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _, _, typ, code, value = EVENT.unpack_from(data, i)
            if typ == EV_KEY and value in (0, 1) and code in CODES:
                out.append((now, CODES[code], value == 1))
        return out


def from_text(text, now):
    """Console characters as instant presses, for when the devices can't be read."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "\x1b" and text[i:i + 3] in FROM_CHAR:
            key, i = FROM_CHAR[text[i:i + 3]], i + 3
        else:
            key, i = FROM_CHAR.get(text[i].lower()), i + 1
        if key:
            out += [(now, key, True), (now, key, False)]
    return out
