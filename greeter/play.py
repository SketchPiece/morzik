"""The keyboard games of the login screen (design: design/canvas/greeter-play).

Cat.key() takes key presses and releases, Cat.frame() says what to draw at a moment: the
pose of the head, where it stands, the overlays (z's, the laser dot), the text in place of
the joke, and which sounds to start or stop. Times are time.monotonic() seconds.

- a lone key: a short meow, as before;
- scratching (a finger run back and forth along a row): he squints and purrs; scratched too
  long without a break, he hisses and bites, then calms down;
- words: «кис кис», «морзик», «рыба» / «вкусняшка», «мяу» (Russian or Latin letters);
- morse on the space bar, shown on the screen; he answers with his whiskers; a pause of
  RESET seconds clears it all;
- arrows move a red laser dot that he follows; space pounces on it;
- left alone he dozes off, a key wakes him with a start; at night he is sleepy and yawns.
"""
import math, random, time
from pixel import SHUT, at, blink, breath, idle
from keys import RU

STAGE_W, STAGE_H = 56, 36               # in art pixels; the head stands at CAT_X, CAT_Y
CAT_X, CAT_Y, HEAD_ROWS = 8, 4, 29

ROWS = ["1234567890-", "qwertyuiop[]", "asdfghjkl;'", "zxcvbnm,."]
POS = {k: (off + c, r) for r, (row, off) in enumerate(zip(ROWS, [0, .5, .75, 1.25])) for c, k in enumerate(row)}

LONE = .35                  # a key with no other key this close before or after it is a lone one
STEP = .35                  # scratching: the next key along the row comes within this
SCRATCH_STEPS = 4           # this many such steps in a row start it
SCRATCH_PAUSE = .6          # and it ends after this long without one
BITE_AFTER = (15, 30)       # seconds of non-stop scratching before he has had enough
WORD_PAUSE = 1.5            # a pause this long starts a new word
DOT_MAX, LETTER_GAP, WORD_GAP, RESET = .25, .7, 1.5, 3.0   # morse timing, seconds
LASER_SPEED, LASER_IDLE = 16, 8.0       # art pixels a second; the dot goes after this long untouched
SLEEP_AFTER, SLEEP_AFTER_NIGHT = 180, 60
NIGHT = (23, 7)

WORDS = {"кискис": "kis", "kiskis": "kis", "морзик": "name", "morzik": "name",
         "рыба": "fish", "рыбка": "fish", "вкусняшка": "fish", "fish": "fish", "мяу": "meow", "meow": "meow", "myau": "meow"}
MORSE = {"А": ".-", "Б": "-...", "В": ".--", "Г": "--.", "Д": "-..", "Е": ".", "Ж": "...-", "З": "--..", "И": "..", "Й": ".---",
         "К": "-.-", "Л": ".-..", "М": "--", "Н": "-.", "О": "---", "П": ".--.", "Р": ".-.", "С": "...", "Т": "-", "У": "..-",
         "Ф": "..-.", "Х": "....", "Ц": "-.-.", "Ч": "---.", "Ш": "----", "Щ": "--.-", "Ы": "-.--", "Ь": "-..-", "Э": "..-..",
         "Ю": "..--", "Я": ".-.-", "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....", "6": "-....",
         "7": "--...", "8": "---..", "9": "----.", "0": "-----"}
DECODE = {v: k for k, v in MORSE.items()}
ANSWERS = {"СОС": "МЯУ", "ПРИВЕТ": "МУР", "МЯУ": "МЯУ", "МОРЗИК": "Я", "КИС": "МЯУ", "КТО": "Я"}
GOODBYE = ("ну ладно, заходи", "раз уж почесал")


def ramp(t, t0, t1, a, b):
    if t <= t0: return a
    if t >= t1: return b
    return a + (b - a) * (t - t0) / (t1 - t0)


def twitch(t, starts):
    for s in starts:
        for k, v in enumerate((.5, 1, .5)):
            if s + k * .05 <= t < s + (k + 1) * .05: return v
    return 0


def slow_blink(t):
    """The cat's 'I love you': lids down in .6 s, shut .4 s, up in .6 s (t from its start)."""
    v = ramp(t, 0, .6, 12, 19) if t < 1 else ramp(t, 1, 1.6, 19, 12)
    return SHUT if v >= 19 else (0 if v <= 12 else round(v))


def signals(code, t0, dot=.22, dash=.6):
    """His answer as whisker flashes: [(start, end, symbol, letter n)]."""
    out, t = [], t0
    for n, letter in enumerate(code):
        for s in MORSE[letter]:
            d = dot if s == "." else dash
            out.append((t, t + d, s, n)); t += d + dot
        t += 2 * dot
    return out


def marks(sigs):
    out, n0 = [], None
    for _, _, s, n in sigs:
        if n0 is not None and n != n0: out.append(" ")
        out.append("•" if s == "." else "—"); n0 = n
    return " ".join(out)


class Cat:
    def __init__(self, now, night=None):
        self.t0 = now
        self.night = night or (lambda: time.localtime().tm_hour >= NIGHT[0] or time.localtime().tm_hour < NIGHT[1])
        self.last_key = self.last_input = now
        self.act = None                 # (name, start, length, info): a short scene that overrides the pose
        self.pending_meow = None
        self.prev_letter = None         # (time, key) of the previous letter key, for scratching
        self.chain = 0
        self.scr_start = self.scr_last = None
        self.bite_after = random.uniform(*BITE_AFTER)
        self.no_scratch_until = 0       # after a bite he won't be scratched for a while
        self.scratched = False          # long enough today to earn the nice goodbye
        self.word = []                  # [(time, ru, latin)]
        self.mo_down = None
        self.mo = []                    # your signals: (start, end, symbol, letter n)
        self.answer = None              # (signals, word)
        self.dot, self.dot_moved, self.arrows = None, 0, {}
        self.yawn_at = now + random.uniform(20, 40)
        self.sounds = []                # sounds to start this frame: "meow", "hiss", "purr", "-purr"
        self.purring = False

    # ---------------------------------------------------------------- input

    def key(self, t, k, down):
        if not down:
            self.arrows.pop(k, None)
            if k == "space" and self.mo_down is not None:
                self.morse_signal(self.mo_down, t)
            return
        asleep = self.asleep(t)
        self.last_input = t
        if asleep:
            self.start("startle", t, 1.5)
            return
        lone_before = t - self.last_key >= LONE
        self.last_key = t
        self.pending_meow = None
        if k in ("up", "down", "left", "right"):
            self.laser_key(t, k)
        elif k == "space":
            if self.dot is not None:
                self.pounce(t)
            elif self.word and t - self.word[-1][0] < WORD_PAUSE:
                self.word.append((t, " ", " "))
            else:
                if self.answer: self.answer = None; self.mo = []
                self.mo_down = t
        elif k in POS:
            self.letter(t, k, lone_before)

    def letter(self, t, k, lone_before):
        # scratching: each key a step along the row from the one before
        prev = self.prev_letter
        step = False
        if prev and t - prev[0] < STEP and prev[1] in POS:
            (x0, r0), (x1, r1) = POS[prev[1]], POS[k]
            step = abs(r1 - r0) <= 1 and 0 < abs(x1 - x0) <= 2.5
        self.chain = self.chain + 1 if step else 0
        self.prev_letter = (t, k)
        if self.chain >= SCRATCH_STEPS and t >= self.no_scratch_until:
            if not self.scratching(t):
                self.scr_start = t
                self.bite_after = random.uniform(*BITE_AFTER)
            self.scr_last = t
            self.word = []
            return
        if self.scratching(t):
            return
        # words
        if self.word and t - self.word[-1][0] >= WORD_PAUSE:
            self.word = []
        self.word.append((t, RU.get(k, k), k))
        for spelling in ("".join(ru for _, ru, _ in self.word), "".join(lat for _, _, lat in self.word)):
            plain = spelling.replace(" ", "").replace("-", "")
            for w, what in WORDS.items():
                if plain.endswith(w):
                    self.word = []
                    self.react(t, what)
                    return
        if lone_before:
            self.pending_meow = t

    def react(self, t, what):
        if what == "kis": self.start("kis", t, 1.6)
        elif what == "name": self.start("name", t, 1.7)
        elif what == "fish": self.start("fish", t, 1.6)
        elif what == "meow": self.start("meow", t, .8)

    def morse_signal(self, down, up):
        self.mo_down = None
        sym = "." if up - down <= DOT_MAX else "-"
        n = 0
        if self.mo:
            n = self.mo[-1][3] + (1 if down - self.mo[-1][1] >= LETTER_GAP else 0)
        self.mo.append((down, up, sym, n))

    def laser_key(self, t, k):
        if self.dot is None:
            self.dot = [44.0, 24.0]
            self.dot_since = t
        self.arrows[k] = t
        self.dot_moved = t
        if not self.live_keys:          # console characters: no releases, so each one is a hop
            dx, dy = {"left": (-2, 0), "right": (2, 0), "up": (0, -2), "down": (0, 2)}[k]
            self.move_dot(dx, dy)
            self.arrows.pop(k, None)

    live_keys = True

    def move_dot(self, dx, dy):
        self.dot[0] = min(STAGE_W - 4, max(0, self.dot[0] + dx))
        self.dot[1] = min(STAGE_H - 4, max(0, self.dot[1] + dy))

    def pounce(self, t):
        x = self.dot[0] + 2 - (CAT_X + 20)
        self.start("pounce", t, 2.4, info=(1 if x > 0 else -1) * min(3, abs(round(x / 6))))
        self.dot = None
        self.arrows = {}

    SOUND = {"meow": "meow", "bite": "hiss", "pounce": "meow"}

    def start(self, name, t, length, info=None):
        """A scene from t (which may be a moment ahead); its sound plays when it begins."""
        self.act = (name, t, length, info)
        self.act_heard = False

    # ---------------------------------------------------------------- state

    def scratching(self, t):
        return self.scr_last is not None and t - self.scr_last < SCRATCH_PAUSE

    def sleep_start(self, t):
        return self.last_input + (SLEEP_AFTER_NIGHT if self.night() else SLEEP_AFTER)

    def asleep(self, t):
        return t >= self.sleep_start(t) + 3.5 and self.act is None

    def goodbye(self, t):
        """Enter: True if he wants to see you off first (you scratched him today)."""
        if not self.scratched: return False
        self.stop_purr()
        self.start("goodbye", t, 1.8)
        return True

    def stop_purr(self):
        if self.purring:
            self.purring = False
            self.sounds.append("-purr")

    # ---------------------------------------------------------------- frame

    def frame(self, t):
        night = self.night()
        p = idle(t - self.t0)
        if night:
            p.update(lid=max(p["lid"], 15), glow="zyxx"[min(3, "zyxY".index(breath(t - self.t0, 6)))])     # sleepy, dimmer whiskers
        out = dict(dy=0, dx=0, z=[], dot=None, text=None, red=False)

        # a lone key meows once nobody follows it
        if self.pending_meow and t - self.pending_meow >= LONE:
            self.pending_meow = None
            if self.last_key <= t - LONE:
                self.start("meow", t + (.8 if night else 0), .7)     # at night he answers lazily

        # scratching
        if self.scratching(t):
            s = t - self.scr_start
            p.update(lid=round(ramp(s, .4, 1.6, 0, 16)) if s < 5 else 17,
                     glow=breath(t, 7, 1), ear=twitch(s % 3.2, [2.6]), look=0, tongue=2)
            if s >= 1.5 and not self.purring:
                self.purring = True
                self.sounds.append("purr")
            if s >= 2:
                self.scratched = True
            if s >= self.bite_after:
                self.scr_last = None
                self.chain = 0
                self.stop_purr()
                self.no_scratch_until = t + 5
                self.start("bite", t, 2.4)
        else:
            if self.purring: self.stop_purr()
            if self.scr_last is not None and t - self.scr_last - SCRATCH_PAUSE < .5:     # eyes open again slowly
                p["lid"] = max(p["lid"], round(ramp(t - self.scr_last - SCRATCH_PAUSE, 0, .5, 16, 0)))

        # morse: yours on the screen, then his answer on the whiskers
        if self.mo_down is not None or self.mo:
            held = self.mo_down is not None
            p.update(glow="Y" if held else "z", ear=.5 if held else 0, look_y=1, look=0)
            last = max(self.mo[-1][1] if self.mo else 0, self.mo_down or 0)
            sigs = self.mo + ([(self.mo_down, t, "." if t - self.mo_down <= DOT_MAX else "-",
                                (self.mo[-1][3] + (1 if self.mo_down - self.mo[-1][1] >= LETTER_GAP else 0)) if self.mo else 0)] if held else [])
            letters, cur = [], ""
            for i, (_, _, s, n) in enumerate(sigs):
                if i and n != sigs[i - 1][3]:
                    letters.append(DECODE.get(cur, "?")); cur = ""
                cur += s
            open_letter = held or t - last < LETTER_GAP
            word = "".join(letters) + ("" if open_letter else DECODE.get(cur, "?"))
            shown = " ".join(letters) + ((" [" + DECODE.get(cur, "?") + "…]") if open_letter else (" " + DECODE.get(cur, "?")))
            idle_for = t - last
            if not held and idle_for >= WORD_GAP and "?" not in word and not self.answer:
                reply = ANSWERS.get(word, "МУР")
                self.answer = (signals(reply, t + .3), reply, word)
            if self.answer:
                sigs_a, reply, word = self.answer
                p["glow"] = "Y" if any(a <= t < b for a, b, _, _ in sigs_a) else "z"
                sent = [x for x in sigs_a if x[0] <= t]
                done = sigs_a[-1][1]
                heard = "".join(reply[n] for n in sorted({x[3] for x in sent}))
                out["text"] = ("morse", marks(sent) or marks(self.mo), f"{' '.join(word)}  →  морзик: {' '.join(heard)}" if sent else " ".join(word))
                if t >= done + 2.5:
                    self.mo, self.answer = [], None
                    out["text"] = None
            elif not held and idle_for >= RESET:
                self.mo = []
            else:
                bottom = shown.strip()
                if not held and idle_for >= LETTER_GAP and "?" in word:
                    bottom = "? нет такой буквы"
                    if idle_for >= 1: bottom += f" · сброс через {max(1, math.ceil(RESET - idle_for))}"
                out["text"] = ("morse", marks(sigs), bottom)

        # the laser dot
        if self.dot is not None:
            for k in list(self.arrows):
                dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}[k]
                self.move_dot(dx * LASER_SPEED / 20, dy * LASER_SPEED / 20)
                self.dot_moved = t
            if t - self.dot_moved >= LASER_IDLE:
                self.dot = None
            else:
                d = [round(self.dot[0]), round(self.dot[1])]
                out["dot"], out["red"] = d, True
                ex, ey = CAT_X + 20, CAT_Y + 16
                p.update(look=max(-2, min(2, round((d[0] + 1.5 - ex) / 9))), look_y=max(-1, min(1, round((d[1] + 1.5 - ey) / 9))),
                         pupil=3 if t - self.dot_since > .6 else 2, glow="Y", lid=0 if not night else 14)
                if t - self.dot_moved > 1: p["ear"] = twitch((t - self.dot_moved) % .8, [.3])

        # dozing off and sleeping
        if self.act is None and not self.scratching(t) and self.dot is None and not self.mo and self.mo_down is None:
            s0 = self.sleep_start(t)
            if t >= s0:
                p.update(lid=at(t - s0, [(0, 14), (.6, 15), (1.1, 14), (1.6, 16), (2.2, 17), (2.8, 18), (3.5, SHUT)], 0),
                         look_y=1 if t - s0 > 1.6 else 0, look=0, ear=0, tongue=2)
                if t >= s0 + 3.5:
                    p["glow"] = "z" if int(t * 2) % 4 else "y"
                    out["z"] = zs(t - s0 - 4)
            elif night and t >= self.yawn_at:
                self.yawn_at = t + random.uniform(25, 50)
                self.start("yawn", t, 1.7)

        # a scene on top of it all
        if self.act:
            name, a0, length, info = self.act
            s = t - a0
            if s >= length:
                self.act = None
            elif s >= 0:
                if not self.act_heard:
                    self.act_heard = True
                    if name in self.SOUND: self.sounds.append(self.SOUND[name])
                self.scene(name, s, info, p, out, night)
        out.update(pose=p, sounds=self.sounds)
        self.sounds = []
        return out

    def scene(self, name, s, info, p, out, night):
        if name == "meow":
            p.update(mouth=1 if s < .6 else 0, lid=min(p["lid"], 14) if night else 0)
        elif name == "kis":
            p.update(ear=twitch(s, [0, .3]), ear_l=twitch(s, [0, .3]), pupil=2, lid=0, look=0)
            out["dy"] = -1 if s < .8 else 0
        elif name == "name":
            p.update(lid=slow_blink(s) if s < 1.6 else 0, ear=twitch(s, [1.3]))
        elif name == "fish":
            p["tongue"] = at(s, [(0, 3), (.25, 4), (.5, 3), (.75, 4), (1.0, 3), (1.25, 2)], 2)
        elif name == "bite":
            p.update(lid=0, pupil=3 if s < 1.6 else 2, flat=min(1, s * 8) if s < 1.6 else ramp(s, 1.6, 2.4, 1, 0),
                     mouth=3 if s < .9 else 0, look=0, look_y=0)
        elif name == "startle":
            p.update(lid=0, pupil=3 if s < .9 else 2, ear=1 if s < .5 else 0, ear_l=1 if s < .5 else 0, look_y=0)
            out["dy"] = -2 if s < .3 else 0
        elif name == "pounce":
            if s < .6:
                p.update(pupil=3, lid=0)
                out["dy"] = round(ramp(s, 0, .15, 0, -3)) if s < .3 else round(ramp(s, .3, .6, -3, 0))
                out["dx"] = round(ramp(s, 0, .2, 0, info)) if s < .3 else round(ramp(s, .3, .6, info, 0))
            else:
                p.update(happy=True)
        elif name == "goodbye":
            p.update(happy=True, ear=twitch(s, [.6]))
            out["text"] = ("say",) + GOODBYE
        elif name == "yawn":
            p.update(lid=SHUT if .4 <= s < 1.5 else 17, mouth=2 if .2 <= s < 1.6 else 0)


def zs(age0):
    """Floating z's while asleep: a new one every 1.2 s, each drifts up and grows."""
    out = []
    if age0 < 0: return out
    k = int(age0 / 1.2)
    for j in range(max(0, k - 2), k + 1):
        age = age0 - j * 1.2
        if 0 <= age < 2.6:
            out.append((CAT_X + 36 + round(age * 2), CAT_Y + 9 - round(age * 4.5), age > 1.1))
    return out
