"""ASCII Morzik for the laptop's login screen: builds one board per eye variant.
Run: python3 -I _build.py  (writes the .html boards next to this file)."""
import html, json, pathlib

HERE = pathlib.Path(__file__).parent
W = 22  # half width; the face is mirrored around column 22
MIR = str.maketrans("/\\()<>[]{}", "\\/)(><][}{")

# left half of the face, its colour mask and the centre column
FACE = [
 ("       /\\             ", "       oo             ", " ", " "),
 ("      /  \\       .=###", "      o  o       hhccc", "#", "c"),
 ("     / /\\ \\  .=#''    ", "     o pp o  hhchh    ", " ", " "),
 ("    / /  \\ \\='        ", "    o p  p oh         ", " ", " "),
 ("   |  '--'            ", "   o  pppp            ", " ", " "),
 (" .-+                  ", " hhh                  ", " ", " "),
 ("|##|      EEEEEE      ", "hcch      EEEEEE      ", " ", " "),
 ("|##|     EEEEEEEE     ", "hcch     EEEEEEEE     ", " ", " "),
 ("|##|     EEEEEEEE     ", "hcch     EEEEEEEE     ", " ", " "),
 ("|##|      EEEEEE      ", "hcch      EEEEEE      ", " ", " "),
 (" '-+                  ", " hhh                  ", " ", " "),
 ("   |   . _ . . _      ", "   o   wwwwwwwww      ", " ", " "),
 ("    \\                 ", "    o                 ", " ", " "),
 ("     '.               ", "     oo               ", " ", " "),
 ("       '-._           ", "       oooo           ", " ", " "),
 ("           '-.._______", "           ooooooooooo", "_", "o"),
]
EYE_ROWS = [(6, 10), (7, 9), (8, 9), (9, 10)]  # (row, first column) of the left eye

# eye = 4 rows (6, 8, 8, 6 chars) + mask; e = eye outline, y = pupil
EYES = {
 "cross": ([" .-\"\"-."[1:], "/    ()\\", "\\      /", "'-..-'"], ["eeeeee", "e    yye", "e      e", "eeeeee"]),
 "round": ([".-\"\"-.", "/  ()  \\", "\\      /", "'-..-'"], ["eeeeee", "e  yy  e", "e      e", "eeeeee"]),
 "big":   ([".-\"\"-.", "/ .--. \\", "\\ '--' /", "'-..-'"], ["eeeeee", "e yyyy e", "e yyyy e", "eeeeee"]),
 "slit":  ([".-\"\"-.", "/  ||  \\", "\\  ||  /", "'-..-'"], ["eeeeee", "e  yy  e", "e  yy  e", "eeeeee"]),
 "shut":  (["      ", " .____. ", "        ", "      "], ["      ", " eeeeee ", "        ", "      "]),
}

COLORS = {"o": "#aaaaaa", "p": "#aa00aa", "h": "#ffffff", "c": "#aa5500", "e": "#ffff55", "y": "#aa5500",
          "w": "#55ffff", "n": "#ff55ff", "t": "#ff55ff", "m": "#ffffff", "r": "#ff5555"}

def face(eye):
    grid, mask = [], []
    for l, m, c, cm in FACE:
        assert len(l) == W and len(m) == W, l
        grid.append(list(l + c + l[::-1].translate(MIR)))
        mask.append(list(m + cm + m[::-1]))
    def put(r, c, s, k):
        for i, ch in enumerate(s):
            while len(grid[r]) <= c + i:
                grid[r].append(" "); mask[r].append(" ")
            grid[r][c + i] = ch; mask[r][c + i] = k if isinstance(k, str) and len(k) == 1 else k[i]
    rows, masks = EYES[eye]
    for (r, c), s, m in zip(EYE_ROWS, rows, masks):
        put(r, c, s, m)                                       # left eye
        mirrored = s[::-1].translate(MIR) if eye != "cross" else s[::-1].translate(MIR)
        put(r, 44 - c - len(s) + 1, mirrored, m[::-1])        # right eye
    put(9, 21, "\\_/", "n")
    put(10, 19, "'-.^.-'", "o")
    put(11, 22, "u", "t")
    put(11, 29, ". _ . . _", "w")
    put(11, 40, "/", "m")
    put(12, 25, "(@)==========='", "m"); mask[12][26] = "r"
    out = []
    for g, m in zip(grid, mask):
        line, cur, buf = "", None, ""
        for ch, k in zip(g, m):
            k = k if ch != " " else cur
            if k != cur:
                line += (f'<b class="c{cur}">{html.escape(buf)}</b>' if cur in COLORS else html.escape(buf)); buf, cur = "", k
            buf += ch
        line += f'<b class="c{cur}">{html.escape(buf)}</b>' if cur in COLORS else html.escape(buf)
        out.append(line.rstrip())
    return "\n".join(out)

CSS = "".join(f".c{k}{{color:{v}}}" for k, v in COLORS.items())

def board(title, eye, top, bottom, extra=""):
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="board" content="1280x800">
<title>{title}</title><link rel="stylesheet" href="_shared.css"><style>{CSS}</style></head>
<body><main><pre class="art" id="art">{face(eye)}</pre>
<pre class="txt"><b class="top">{top}</b>
<b class="bottom">{bottom}</b>

<b class="key">Enter</b> — войти</pre></main>{extra}</body></html>"""

BLINK = """<template id="shut">{shut}</template><script>
const art = document.getElementById('art'), open = art.innerHTML, shut = document.getElementById('shut').innerHTML;
function blink() {{ art.innerHTML = shut; setTimeout(() => art.innerHTML = open, 160); setTimeout(blink, 2500 + Math.random() * 3000); }}
setTimeout(blink, 1800);
</script>""".format(shut=face("shut"))

BOARDS = [
 ("0-now.html", "Сейчас · глаза косят", "cross", "мур. это мой компьютер", "крышку закрывай нежно, я под ней сплю"),
 ("a-round.html", "А · Круглые зрачки по центру", "round", "тут живёт морзик", "пароль не скажу, даже за вкусняшку"),
 ("b-big.html", "Б · Большие зрачки", "big", "я на работе, почта сама себя не разберёт", "хотя я ей много раз предлагал"),
 ("c-slit.html", "В · Кошачьи зрачки-щёлки", "slit", "привет, я тут главный", "хозяин так не считает, но он и не кот"),
 ("d-blink.html", "Г · Круглые и моргает", "round", "не выключай меня, пожалуйста", "жизней у меня девять, а аптайм один", BLINK),
]

if __name__ == "__main__":
  for name, title, eye, top, bottom, *extra in BOARDS:
    (HERE / name).write_text(board(title, eye, top, bottom, *extra))
