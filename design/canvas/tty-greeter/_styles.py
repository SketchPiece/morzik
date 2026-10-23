"""New style variants of the login-screen Morzik. Run: python3 -I _styles.py"""
import html, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _pixel_head import grid as pixel_grid
from _build import face, CSS as LINE_CSS
from _pixel_v2 import build as avatar_grid, PALETTE as AV

HERE = pathlib.Path(__file__).parent
VGA = {"G": "#555555", "g": "#aaaaaa", "P": "#ff55ff", "W": "#ffffff", "O": "#aa5500", "Y": "#ffff55",
       "C": "#55ffff", "R": "#ff5555", "K": "#000000", "w": "#aaaaaa", "y": "#ffff55", "c": "#55ffff",
       "m": "#ff55ff", "b": "#5555ff", "o": "#aa5500", "r": "#ff5555", "t": "#ffffff"}

def esc(s): return html.escape(s)

def pixels(rows, size=12, pal=None):
    pal = pal or VGA
    cells = "".join(f'<i style="background:{pal[ch]}"></i>' if ch != "." else "<i></i>" for r in rows for ch in r)
    return f'<div class="pix" style="grid-template-columns:repeat({len(rows[0])},{size}px);grid-auto-rows:{size}px">{cells}</div>'

def halfblocks(rows):
    """Two pixel rows per text row, like ▀ with fg/bg colours on the Linux console."""
    if len(rows) % 2: rows = rows + ["." * len(rows[0])]
    out = []
    for top, bot in zip(rows[::2], rows[1::2]):
        line = ""
        for a, b in zip(top, bot):
            if a == "." and b == ".": line += " "
            elif a == b: line += f'<b style="color:{VGA[a]}">█</b>'
            elif b == ".": line += f'<b style="color:{VGA[a]}">▀</b>'
            elif a == ".": line += f'<b style="color:{VGA[b]}">▄</b>'
            else: line += f'<b style="color:{VGA[a]};background:{VGA[b]}">▀</b>'
        out.append(line)
    return "\n".join(out)

def colored(art, mask):
    """Plain art + a same-shaped mask of VGA colour letters."""
    out = []
    for a, m in zip(art.split("\n"), mask.split("\n")):
        m = m.ljust(len(a))
        line = ""
        for ch, k in zip(a, m):
            line += f'<b style="color:{VGA[k]}">{esc(ch)}</b>' if k in VGA and ch != " " else esc(ch)
        out.append(line)
    return "\n".join(out)

def by_rule(art, rule):
    out = []
    for r, line in enumerate(art.split("\n")):
        out.append("".join(f'<b style="color:{VGA[rule(r, ch)]}">{esc(ch)}</b>' if ch != " " else " " for ch in line))
    return "\n".join(out)

def page(title, body, extra_css=""):
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="board" content="1280x800">
<title>{title}</title><link rel="stylesheet" href="_shared.css"><style>{LINE_CSS}{extra_css}</style></head>
<body>{body}</body></html>"""

def joke(top, bottom):
    return f'<pre class="txt"><b class="top">{esc(top)}</b>\n<b class="bottom">{esc(bottom)}</b>\n\n<b class="key">Enter</b> — войти</pre>'

# 0 · the line-art Morzik from before, now looking straight
now = page("Сейчас · линии, смотрит прямо",
    f'<main><pre class="art">{face("round")}</pre>{joke("тут живёт морзик", "пароль не скажу, даже за вкусняшку")}</main>')

# A · pixel art in half blocks
a = page("А · Пиксель-арт",
    f'<main>{pixels(pixel_grid(), 12)}{joke("морзик занят: думает", "иногда о почте, чаще о рыбе")}</main>',
    ".pix{display:grid}")

# B · small cat + status panel, like neofetch
cat_b = r"""     /\_____/\
 .==/  o   o  \==.
[##]|  =  ^  =  |[##]
[##] \   'u'   / [##]
      '-.___.-'==(@)"""
def rule_b(r, ch):
    if ch == "#": return "o"
    if ch == "o": return "y"
    if ch in "^u'" and r in (2, 3): return "m"
    if ch == "=" and r == 2: return "c"
    if ch == "@": return "r"
    if ch in "[].=()" : return "t"
    return "w"
info = [("", "морзик@sketch-server", "c"), ("", "─" * 22, "w"),
        ("дома", "3 дня 4 часа", "t"), ("сейчас", "разбирает почту", "t"),
        ("почта", "тихо, новых нет", "t"), ("дел на сегодня", "2", "t")]
panel = "\n".join((f'<b style="color:{VGA["y"]}">{esc(k.ljust(15))}</b>' if k else "") +
                  f'<b style="color:{VGA[c]}">{esc(v)}</b>' for k, v, c in info)
b = page("Б · Маленький кот и статус",
    f'''<main><div class="row">{pixels(pixel_grid(), 9)}<pre class="panel">{panel}</pre></div>
{joke("тут всё под контролем", "под моим, если что")}</main>''',
    ".row{display:flex;gap:64px;align-items:center}.panel{line-height:1.45}")

# C · rounded lines
cat_c = r"""      /\                       /\
     /  \    ╭───────────╮    /  \
    /    \───╯           ╰───/    \
 ╭─╮                               ╭─╮
 │█│                               │█│
 │█│      ●                 ●      │█│
 │█│                               │█│
 ╰─╯             ╲▁╱               ╰─╯
     ·–··–       ╰┴╯       ·–··–   ╱
     ╲                            ╱
      ╰─╮                     ╭(●)
        ╰─────────────────────╯"""
mask_c = r"""      ww                       ww
     w  w    ttttttttttttt    w  w
    w    wwwwt           twwww    w
 ttt                               ttt
 tot                               tot
 tot      y                 y      tot
 tot                               tot
 ttt             mmm               ttt
     ccccc       www       ccccc   t
     w                            w
      www                     wtrt
        wwwwwwwwwwwwwwwwwwwwwww"""
c = page("В · Скруглённые линии",
    f'<main><pre class="art">{colored(cat_c, mask_c)}</pre>{joke("если ты не хозяин", "я всё видел и уже написал ему")}</main>')

# D · banner
FONT = {
 "М": ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
 "О": [" ███ ", "█   █", "█   █", "█   █", " ███ "],
 "Р": ["████ ", "█   █", "████ ", "█    ", "█    "],
 "З": ["████ ", "    █", " ███ ", "    █", "████ "],
 "И": ["█   █", "█  ██", "█ █ █", "██  █", "█   █"],
 "К": ["█   █", "█  █ ", "███  ", "█  █ ", "█   █"],
}
letter_colors = ["c", "c", "t", "t", "y", "y"]
banner = "\n".join("  ".join(f'<b style="color:{VGA[col]}">{FONT[ch][r]}</b>' for ch, col in zip("МОРЗИК", letter_colors))
                   for r in range(5))
small = r""" /\_/\
( o.o )
 > ^ <"""
small_mask = """ wwwww
wwywyww
 wmmmw"""
d = page("Г · Баннер с именем",
    f'''<main><div class="row">{pixels(pixel_grid(), 6)}<pre class="banner">{banner}</pre></div>
<pre class="morse">·  –  ·  ·  –</pre>{joke("не выключай меня, пожалуйста", "жизней у меня девять, а аптайм один")}</main>''',
    ".row{display:flex;gap:48px;align-items:center}.banner{font-size:26px;line-height:1.0}.morse{color:#55ffff;font-size:22px}")

cat_e = r"""    /\_____/\
 .=/  o   o  \=.
[#]|  =  ^  =  |[#]
[#] \   'u'   / [#]
     '-.___.-'=(@)"""
def rule_e(r, ch):
    if ch == "#": return "o"
    if ch == "o": return "y"
    if ch in "^u'" and r in (2, 3): return "m"
    if ch == "@": return "r"
    return "t"
e = page("Д · Окно в стиле BIOS",
    f'''<div class="dos"><div class="win"><div class="ttl">═══[ sketch-server ]═══</div>
<pre class="art">{by_rule(cat_e, rule_e)}</pre>
<pre class="msg"><b>морзик дежурит у почты</b>
<b class="dim">если увидишь мышь — не трогай, она по делу</b></pre>
<div class="btn">&lt; <u>В</u>ойти &gt;</div></div>
<div class="bar"><b>Enter</b> Войти   <b>F1</b> Что это за компьютер   <b>F10</b> Ничего не делать</div></div>''',
    """.dos{width:1280px;height:800px;background:#0000aa;display:flex;align-items:center;justify-content:center;position:relative}
.win{background:#aaaaaa;color:#000;border:3px double #fff;outline:3px solid #aaaaaa;box-shadow:16px 16px 0 #000;padding:24px 56px 28px;display:flex;flex-direction:column;align-items:center;gap:22px;font-family:"JetBrains Mono",monospace;font-size:20px}
.win .art{background:#000;padding:18px 28px}.ttl{color:#fff;background:#0000aa;padding:0 10px;margin-top:-38px}
.msg{text-align:center;color:#000}.msg b{font-weight:400}.msg .dim{color:#555555}
.btn{background:#00aaaa;color:#000;padding:2px 14px;box-shadow:8px 8px 0 #000}.btn u{color:#fff;text-decoration:none}
.bar{position:absolute;left:0;right:0;bottom:0;background:#aaaaaa;color:#000;font-family:"JetBrains Mono",monospace;font-size:18px;padding:4px 16px;white-space:pre}.bar b{color:#aa0000;font-weight:400}""")

def joke_av(top, bottom):
    return (f'<pre class="txt"><b style="color:#ece8df">{esc(top)}</b>\n<b style="color:#8f8aa6">{esc(bottom)}</b>\n\n'
            f'<b style="color:#ffa21f">Enter</b><b style="color:#8f8aa6"> — войти</b></pre>')
AV_BG = f"html,body{{background:{AV['.']}}}"
a2 = page("А2 · Пиксель-арт в цветах авы",
    f'<main>{pixels(avatar_grid(), 11, AV)}{joke_av("морзик занят: думает", "иногда о почте, чаще о рыбе")}</main>', AV_BG)
a3 = page("А3 · То же, только голова",
    f'<main>{pixels(avatar_grid()[:29], 12, AV)}{joke_av("тут живёт морзик", "пароль не скажу, даже за вкусняшку")}</main>', AV_BG)

for name, doc in [("a2-avatar.html", a2), ("a3-avatar-head.html", a3), ("0-now.html", now), ("a-pixel.html", a), ("b-status.html", b), ("c-rounded.html", c), ("d-banner.html", d), ("e-dos.html", e)]:
    (HERE / name).write_text(doc)
