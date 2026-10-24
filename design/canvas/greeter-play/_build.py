"""Builds the boards: every board is one keyboard game played as a loop on the pixel Morzik,
with the keys being pressed, the sound and the steps under him. Run: python3 _build.py"""
import json, math
from pathlib import Path
from _cat import build, SHUT, PALETTE

FPS = 20
HERE = Path(__file__).parent
CAT_X, CAT_Y = 8, 4          # where the head sits on the 56 x 38 stage
JOKE = ("тут живёт морзик", "пароль не скажу, даже за вкусняшку")


def ramp(t, t0, t1, a, b):
    if t <= t0: return a
    if t >= t1: return b
    return a + (b - a) * (t - t0) / (t1 - t0)


def blink(t, at, step=.05):
    seq = [14, 16, 18, SHUT, SHUT, 18, 16, 14]
    for b in at:
        k = int((t - b) / step)
        if 0 <= k < len(seq): return seq[k]
    return 0


def slow_blink(t, t0):
    """The cat's 'I love you': lids down in .6 s, shut .4 s, up in .6 s."""
    if t < t0 or t > t0 + 1.6: return 0
    v = ramp(t, t0, t0 + .6, 12, 19) if t < t0 + 1 else ramp(t, t0 + 1, t0 + 1.6, 19, 12)
    return SHUT if v >= 19 else (0 if v <= 12 else round(v))


def breath(t, period=4.0, lo=0):
    level = .5 + .5 * math.sin(2 * math.pi * t / period)
    return "zyxY"[min(3, lo + int(level * (4 - lo)))]


def twitch(t, at):
    for a in at:
        for k, v in enumerate([.5, 1, .5, 0]):
            if a + k * .05 <= t < a + (k + 1) * .05: return v
    return 0


def at(t, keys, default):
    v = default
    for start, value in keys:
        if t >= start - 1e-9: v = value
    return v


def zs(t, t0, t1=1e9, x0=CAT_X + 36, y0=CAT_Y + 9):
    """Floating z's while asleep: a new one every 1.2 s, each drifts up and grows."""
    out = []
    if t < t0: return out
    k = 0
    while t0 + k * 1.2 <= min(t, t1):
        age = t - (t0 + k * 1.2)
        if age < 2.6:
            out.append([x0 + round(age * 2), y0 - round(age * 4.5), 1 if age > 1.1 else 0])
        k += 1
    return out


# key positions on the board for the eyes that follow them (column in key widths, row)
ROWS = ["1234567890-", "qwertyuiop", "asdfghjkl", "zxcvbnm,."]
OFFS = [0, .5, .75, 1.25]
POS = {k: (OFFS[r] + c, r) for r, row in enumerate(ROWS) for c, k in enumerate(row)}
RU = dict(zip("qwertyuiopasdfghjklzxcvbnm,.", "йцукенгшщзфывапролдячсмитьбю"))
LAT = {v: k for k, v in RU.items()}


def look_at(key):
    x, r = POS[key]
    return max(-2, min(2, round((x - 5) / 2.4))), (-1 if r == 0 else 1 if r == 3 else 0)


def typing(word, t0, dt=.2):
    """[(time, key, char)] for typing a Russian word on the ЙЦУКЕН layout."""
    return [(t0 + i * dt, LAT.get(ch, ch), ch) for i, ch in enumerate(word)]


def held(t, presses, dur=.12):
    return {k for s, k, *_ in presses if s <= t < s + dur}


MORSE = {"S": "...", "O": "---", "М": "--", "Я": ".-.-", "У": "..-"}


def morse(word, t0, dot=.15, dash=.45):
    out, t = [], t0
    for n, ch in enumerate(word):
        for s in MORSE[ch]:
            d = dot if s == "." else dash
            out.append((t, t + d, s, n)); t += d + dot
        t += 2 * dot
    return out, t


# ---------------------------------------------------------------- the games

def now():
    blinks = [1.0, 6.0]
    look = [(2.6, -1), (2.7, -2), (3.3, -1), (3.4, 0), (3.6, 1), (3.7, 2), (4.3, 1), (4.4, 0)]
    tongue = [(2.4, 1), (2.45, 0), (4.85, 1), (4.9, 2)]
    def f(t):
        return dict(lid=blink(t, blinks), look=at(t, look, 0), tongue=at(t, tongue, 2), ear=twitch(t, [7.3, 7.6]), glow=breath(t),
                    keys={"k"} if 5.4 <= t < 5.55 else set(), snd="мяу" if 5.4 <= t < 6.4 else "")
    return dict(file="0-now.html", title="Сейчас · любая клавиша — мявк, кот не меняется", dur=8, f=f,
                steps=[(0, "Кот живёт своей петлёй: моргает, смотрит по сторонам"), (5.4, "Нажал клавишу — звучит мявк, но сам кот на это не реагирует")])


def scratch():
    home = "asdfghjkl"
    def finger(t):
        ph = ((t - .6) / .55) % 2
        i = round(ph * 8) if ph < 1 else round((2 - ph) * 8)
        return home[i]
    def f(t):
        s = dict(glow=breath(t, 4))
        if .6 <= t < 8.2: s["keys"] = {finger(t)}
        if t < 1.2 and t >= .6: s["look"], _ = look_at(finger(t))
        if t < 8.0:
            s["lid"] = round(ramp(t, 1.0, 2.2, 0, 16)) if t < 5 else round(ramp(t, 5, 6, 16, 17))
            if t < 1.0: s["lid"] = blink(t, [.2])
            s["ear"] = twitch(t, [3.3, 5.9])
            if t >= 2.4: s["glow"] = breath(t, 7, 1); s["snd"] = "мур-р-р… (громче, пока чешешь)"
        elif t < 9.6:
            s.update(lid=0, pupil=3, flat=min(1, (t - 8) * 8), mouth=3 if t < 8.9 else 0, snd="ш-ш! кусь" if t < 8.9 else "")
        else:
            s.update(flat=ramp(t, 9.6, 10.4, 1, 0), pupil=2 if t < 10.4 else 1, lid=blink(t, [10.8]))
        return s
    return dict(file="1-scratch.html", title="1 · Почесать: щурится, мурчит, на перебор — кусь", dur=12, f=f,
                steps=[(0, "Ведёшь пальцем по ряду туда-сюда (A…L…A)"), (1.0, "Прищуривается, усы светятся медленнее"),
                       (2.4, "Мурчит; мурчание стихает, если перестать"), (8.0, "Чешешь слишком долго: глаза круглые, уши назад — кусь!"),
                       (9.6, "Через пару секунд успокаивается")])


def gaze():
    presses = [(.4, "a"), (1.4, "l"), (2.6, "5"), (3.6, "b"), (4.4, "m")] + [(5.4 + i * .17, k) for i, k in enumerate("qwertyuiop")]
    def f(t):
        s = dict(glow=breath(t), lid=blink(t, [8.6]))
        s["keys"] = held(t, presses, .15)
        last = [k for st, k in presses if st <= t]
        last_t = max([st for st, k in presses if st <= t], default=-9)
        if last and t - last_t < 1.2:
            s["look"], s["look_y"] = look_at(last[-1])
        return s
    return dict(file="2-gaze.html", title="2 · Взгляд за клавишей", dur=9.5, f=f,
                steps=[(0, "Нажал слева — смотрит влево"), (1.4, "Справа — вправо"), (2.6, "Верхний ряд — глаза вверх, нижний — вниз"),
                       (5.4, "Пробежал по ряду — глаза бегут следом"), (7.6, "Перестал — через секунду снова смотрит прямо")])


def morse_game():
    sos, end = morse("SOS", .6)
    ans, ans_end = morse("МЯУ", end + 1.0, .22, .6)
    def f(t):
        s = dict(glow=breath(t))
        on = [x for x in sos if x[0] <= t < x[1]]
        if .6 <= t < end + .9:
            s["glow"] = "Y" if on else "z"
            s["keys"] = {"space"} if on else set()
            s["ear"] = .5 if on else 0
            s["look_y"] = 1
        elif end + .9 <= t < ans_end:
            s["glow"] = "Y" if any(a <= t < b for a, b, *_ in ans) else "z"
        if t >= ans_end: s["lid"] = blink(t, [ans_end + .4])
        line = "ты:      " + sym_text(sos, t)
        if t >= end + 1.0: line += "\nморзик:  " + sym_text(ans, t) + ("   = МЯУ" if t >= ans_end else "")
        s["line"] = line if t >= .6 else ""
        return s
    return dict(file="3-morse.html", title="3 · Морзянка пробелом, ответ усами", dur=ans_end + 2, f=f,
                steps=[(0, "Стучишь пробелом: коротко — точка, долго — тире"), (.6, "Усы вспыхивают в такт, ухо ловит каждый сигнал"),
                       (end + 1.0, "Отвечает морзянкой усами"), (ans_end, "Это «МЯУ». На SOS, «ПРИВЕТ» и т.п. — свои ответы")])


def sym_text(sigs, t):
    """Dots and dashes sent so far, a space between letters."""
    out, letter = "", 0
    for a, b, s, n in sigs:
        if a > t: break
        out += (" " if n != letter else "") + ("•" if s == "." else "—")
        letter = n
    return out


def words():
    plan = [("кис-кис", .4), ("морзик", 3.6), ("рыба", 7.4), ("мяу", 11.0), ("ж", 14.0)]
    presses = [p for w, t0 in plan for p in typing(w, t0)]
    def f(t):
        s = dict(glow=breath(t), keys=held(t, presses))
        typed = [(st, ch) for st, k, ch in presses if st <= t]
        for w, t0 in plan:
            done = t0 + .2 * len(w)
            if t0 <= t < done + 1.6: s["line"] = "".join(ch for st, ch in typed if st >= t0 - 1e-9)
        if 1.8 <= t < 3.4:
            s.update(ear=twitch(t, [1.8, 2.1]), ear_l=twitch(t, [1.8, 2.1]), pupil=2, dy=-1 if t < 2.6 else 0)
        if 4.9 <= t < 6.6:
            s.update(lid=slow_blink(t, 4.9), ear=twitch(t, [6.2]))
        if 8.3 <= t < 10.0:
            s["tongue"] = at(t, [(8.3, 3), (8.55, 4), (8.8, 3), (9.05, 4), (9.3, 3), (9.55, 2)], 2)
        if 11.7 <= t < 12.5: s.update(mouth=1, snd="мяу!")
        if 14.2 <= t < 14.8: s.update(mouth=1, snd="мяу")
        if t >= 14.8: s["lid"] = blink(t, [15.4])
        return s
    return dict(file="4-words.html", title="4 · Слова: кис-кис, морзик, рыба, мяу", dur=16.5, f=f,
                steps=[(0, "«кис-кис» — уши торчком, зрачки шире, приподнимается"), (3.6, "«морзик» — медленно моргает: по-кошачьи «люблю»"),
                       (7.4, "«рыба», «вкусняшка» — облизывается"), (11.0, "«мяу» — отвечает мявком"),
                       (14.0, "Просто клавиша — короткий мявк, как сейчас")])


def lie():
    palm = set("rtyufghjcvbn")
    def f(t):
        s = dict(glow=breath(t, 6, 1) if t > 3 else breath(t))
        if .5 <= t < 9: s["keys"] = palm
        if .8 <= t < 9.6: s.update(look_y=1, pupil=2 if t < 1.6 else 1)
        if t >= 1.3:
            dy = ramp(t, 1.3, 2.6, 0, 5) if t < 10.3 else ramp(t, 10.3, 11.1, 5, 0)
            s["dy"] = round(dy)
            s["paws"] = max(0, min(4, round(dy) - 1))
        if t < 9.6:
            s["lid"] = round(ramp(t, 2.2, 3.4, 0, 16)) if t < 4.4 else (18 if t < 5.4 else SHUT)
        else:
            s["lid"] = 16 if t < 10.3 else blink(t, [11.4])
        if 3.0 <= t < 9.2: s["snd"] = "мур-р-р (тихо)"
        s["z"] = zs(t, 6.0, 9.0, CAT_X + 36, CAT_Y + 13) if t < 11 else []
        return s
    return dict(file="5-lie.html", title="5 · Ладонь на клавиатуре — ложится рядом", dur=12.5, f=f,
                steps=[(0, "Положил ладонь на клавиатуру: зажато много клавиш"), (.8, "Смотрит вниз, на руку"),
                       (1.3, "Ложится: голова опускается на лапы"), (3.0, "Глаза закрываются, тихо мурчит"),
                       (6.0, "Задремал"), (9.0, "Убрал руку — приоткрывает глаза и поднимает голову")])


def sleep():
    droop = [(2.0, 14), (2.6, 15), (3.1, 14), (3.6, 16), (4.2, 17), (4.8, 18), (5.4, SHUT)]
    def f(t):
        s = dict(glow=breath(t, 6, 0))
        if t < 2: s["lid"] = blink(t, [.8])
        elif t < 9.5: s["lid"] = at(t, droop, 0); s["look_y"] = 1 if t > 3.6 else 0
        if 5.4 <= t < 9.5: s["glow"] = "z" if int(t * 2) % 4 else "y"
        s["z"] = zs(t, 6.0, 9.2) if t < 9.5 else []
        if 9.5 <= t < 9.65: s["keys"] = {"k"}
        if 9.5 <= t < 11.0:
            s.update(lid=0, pupil=3 if t < 10.4 else 2, dy=-2 if t < 9.8 else 0, ear=1 if t < 10.0 else 0, ear_l=1 if t < 10.0 else 0, snd="мр-р?!")
        if t >= 11.0: s["lid"] = blink(t, [11.6])
        return s
    return dict(file="6-sleep.html", title="6 · Засыпает без дела, просыпается от клавиши", dur=13, f=f,
                steps=[(0, "Клавиатуру никто не трогает"), (2.0, "Через пару минут клюёт носом (здесь быстрее)"),
                       (5.6, "Спит: тусклые усы, плывут «z»"), (9.5, "Нажал клавишу — вздрагивает, уши торчком"), (11.0, "Снова на посту")])


def hunt():
    path = [(.8, (48, 7)), (2.8, (6, 7)), (3.8, (6, 31)), (5.8, (48, 31)), (6.5, (40, 18))]
    keys_for = [(.8, "left"), (2.8, "down"), (3.8, "right"), (5.8, "up"), (6.5, None)]
    def dot(t):
        if t < .8 or t >= 8.25: return None
        for (t0, p0), (t1, p1) in zip(path, path[1:]):
            if t0 <= t < t1:
                return [round(ramp(t, t0, t1, p0[0], p1[0])), round(ramp(t, t0, t1, p0[1], p1[1]))]
        return list(path[-1][1]) if t < 7.6 else [40 + (1 if int(t * 10) % 2 else 0), 18]
    def f(t):
        s = dict(glow=breath(t))
        d = dot(t)
        s["dot"] = d
        k = at(t, keys_for, None)
        if k and .8 <= t < 6.5: s["keys"] = {k}
        if 7.6 <= t < 8.0: s["keys"] = {"left", "right"} if int(t * 10) % 2 else set()
        if 8.0 <= t < 8.2: s["keys"] = {"space"}
        if d:
            eye_x, eye_y = CAT_X + 20, CAT_Y + 16
            s.update(look=max(-2, min(2, round((d[0] + 1.5 - eye_x) / 9))), look_y=max(-1, min(1, round((d[1] + 1.5 - eye_y) / 9))),
                     pupil=3 if t > 1.4 else 2, ear=twitch(t, [7.0, 7.4]))
        if 8.0 <= t < 8.6:
            s.update(pupil=3, dy=round(ramp(t, 8.0, 8.15, 0, -3)) if t < 8.3 else round(ramp(t, 8.3, 8.6, -3, 0)), dx=round(ramp(t, 8.0, 8.2, 0, 3)) if t < 8.3 else round(ramp(t, 8.3, 8.6, 3, 0)))
        if 8.6 <= t < 10.4: s.update(happy=True, snd="мрр!" if t < 9.4 else "")
        return s
    return dict(file="7-hunt.html", title="7 · Охота на лазерную точку", dur=11.5, f=f,
                steps=[(0, "Стрелками водишь «лазерную точку»"), (1.2, "Следит за ней круглыми зрачками"),
                       (6.5, "Точка дрожит на месте — он готовится"), (8.0, "Пробел — прыжок!"), (8.6, "Поймал, доволен")])


def enter():
    def f(t):
        s = dict(glow=breath(t), lid=blink(t, [.6]))
        if 1.6 <= t < 1.75: s["keys"] = {"enter"}
        if 1.6 <= t < 3.6: s.update(happy=True, ear=twitch(t, [2.2]), say=("ну ладно, заходи", "раз уж почесал"))
        if 3.6 <= t: s["screen"] = 1
        return s
    return dict(file="8-enter.html", title="8 · Enter, если его сегодня чесали", dur=6, f=f,
                steps=[(0, "Сегодня его уже чесали — он в хорошем настроении"), (1.6, "Enter: довольно щурится, «ну ладно, заходи»"),
                       (3.6, "Дальше обычный вход")])


def night():
    def f(t):
        s = dict(glow=breath(t, 6, 0), lid=15)
        if 1.0 <= t < 3.0:
            s.update(lid=SHUT if 1.4 <= t < 2.6 else 17, mouth=2 if 1.2 <= t < 2.7 else 0, snd="а-а-ам" if 1.2 <= t < 2.7 else "")
        if 5.0 <= t < 5.15: s["keys"] = {"h"}
        if 5.9 <= t < 8.2:
            s.update(lid=14 if t < 7.6 else 15, look=1 if t > 6.2 else 0)
            if 6.6 <= t < 7.2: s.update(mouth=1, snd="мя… (сонно)")
        if 8.2 <= t: s["lid"] = 16
        if 9.6 <= t < 11.4:
            s.update(lid=SHUT if 10.0 <= t < 11.1 else 17, mouth=2 if 9.8 <= t < 11.2 else 0, snd="а-а-ам" if 9.8 <= t < 11.2 else "")
        return s
    return dict(file="9-night.html", title="9 · Ночью: сонный, зевает", dur=12.5, f=f,
                steps=[(0, "Ночью (примерно с 23 до 7) глаза прикрыты, усы тусклее"), (1.0, "Зевает"),
                       (5.0, "Нажал клавишу — реагирует не сразу, лениво"), (9.6, "И снова зевает")])


GAMES = [now, scratch, gaze, morse_game, words, lie, sleep, hunt, enter, night]
CAT_KEYS = ["lid", "look", "tongue", "ear", "glow", "ear_l", "flat", "look_y", "pupil", "mouth", "happy"]


def render(game):
    frames, index, ticks = [], {}, []
    says = [list(JOKE)]
    for i in range(round(game["dur"] * FPS)):
        s = game["f"](i / FPS)
        cat = {k: s[k] for k in CAT_KEYS if k in s}
        key = tuple(sorted(cat.items()))
        if key not in index:
            index[key] = len(frames)
            frames.append("\n".join(build(**cat)[:29]))
        say = list(s.get("say", JOKE))
        if say not in says: says.append(say)
        ticks.append([index[key], s.get("dy", 0), s.get("dx", 0), s.get("paws", 0), s.get("z", []), s.get("dot"),
                      " ".join(sorted(s.get("keys", ()))), s.get("snd", ""), s.get("line", ""), says.index(say), s.get("screen", 0)])
    data = dict(pal=PALETTE, frames=frames, ticks=ticks, says=says, steps=game["steps"], fps=FPS)
    html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="board" content="1280x800">
<title>{game['title']}</title><link rel="stylesheet" href="_shared.css"></head>
<body><section class="screen"><div class="tty"><canvas id="st" width="560" height="380"></canvas>
<div class="txt"><div class="top" id="top"></div><div class="bottom" id="bot"></div><div class="hint"><b>Enter</b> — войти</div></div></div>
<pre class="login" id="login">Ubuntu 26.04 LTS sketch-server tty1

sketch-server login: <span class="cur">_</span></pre></section>
<section class="strip"><div class="kb" id="kb"></div><div class="side"><div class="snd" id="snd"></div>
<pre class="line" id="line"></pre><ol class="steps" id="steps"></ol><div class="bar"><i id="bar"></i></div></div></section>
<script src="_player.js"></script><script>play({json.dumps(data, ensure_ascii=False, separators=(',', ':'))})</script></body></html>
"""
    (HERE / game["file"]).write_text(html)
    return len(frames)


if __name__ == "__main__":
    for g in GAMES:
        game = g()
        print(game["file"], render(game), "frames")
