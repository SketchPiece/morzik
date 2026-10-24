"""Pixel Morzik for the login screen: the art, every pose the keyboard games need, and the
8-second idle loop of the avatar. The design boards in design/canvas/tty-greeter and
design/canvas/greeter-play draw from their own copies."""
PALETTE = {
 ".": "#1f2b52",  # background, navy like the avatar
 "F": "#17151d",  # fur
 "f": "#2a2633",  # fur, lighter lower face and body
 "E": "#5f4872",  # inner ear
 "H": "#ece8df",  # headset, cream
 "h": "#bdb7ab",  # headset shadow
 "O": "#ffa21f",  # eye
 "o": "#e07800",  # eye edge
 "K": "#000000",  # pupils, mouth
 "N": "#8c5a7c",  # nose
 "T": "#f2809e",  # tongue
 "Y": "#ffb43a",  # whiskers (morse)
 "B": "#3c5096",  # mic tip
 "x": "#eca233",  # whiskers, a step dimmer (breathing light)
 "y": "#d38c2b",  # whiskers, dimmer
 "z": "#ad6f23",  # whiskers, dimmest
}
W, H = 40, 38
SHUT = 99

def build(lid=0, look=0, tongue=2, ear=0.0, glow="Y", ear_l=0.0, flat=0.0, look_y=0, pupil=1, mouth=0, happy=False):
    """lid: 0 open, else the eyelid covers rows above it (SHUT = closed, drawn as an arc);
    look: pupils -2..2 pixels, look_y: -1..1 rows; pupil: 1 slit with a darker rim, 2 narrow
    oval, 3 round; tongue: rows shown 0..2, 3 licking out, 4 licking to the side;
    ear / ear_l: right / left ear twitch 0..1; flat: both ears pinned back 0..1;
    mouth: 0 shut, 1 meow, 2 yawn, 3 hiss; happy: eyes shut in ^ ^ arcs;
    glow: whisker colour Y / x / y / z."""
    g = [["."] * W for _ in range(H)]
    def inside_ellipse(x, y, cx, cy, rx, ry): return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1
    # body and tail behind the head
    for y in range(H):
        for x in range(W):
            if inside_ellipse(x, y, 19.5, 41, 12, 11.5): g[y][x] = "f"
    for x, y in [(30, 37), (31, 37), (32, 37), (32, 36), (33, 36), (33, 35), (34, 35), (34, 34), (35, 34), (35, 33), (36, 33), (35, 32), (36, 32),
                 (35, 31), (36, 31), (35, 30), (36, 30), (34, 29), (35, 29), (33, 29), (33, 30)]:
        g[y][x] = "F"
    # headband: an elliptic ring over the head, down to the cups
    for y in range(H):
        for x in range(W):
            outer = ((x + .5 - 20) / 19.4) ** 2 + ((y + .5 - 20) / 16.4) ** 2
            inner = ((x + .5 - 20) / 17.0) ** 2 + ((y + .5 - 20) / 13.8) ** 2
            if outer <= 1 < inner and y <= 19:
                g[y][x] = "H" if ((x + .5 - 20) / 18.6) ** 2 + ((y + .5 - 20) / 15.5) ** 2 <= 1 else "h"
    # ears (drawn before the head so the head's top edge covers their base); the left one mirrors the right
    def tri(p, x, y):
        (x1, y1), (x2, y2), (x3, y3) = p
        def s(ax, ay, bx, by): return (x - bx) * (ay - by) - (ax - bx) * (y - by)
        d1, d2, d3 = s(x1, y1, x2, y2), s(x2, y2, x3, y3), s(x3, y3, x1, y1)
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))
    def right_ear(e, fl):
        outer = ((33.5 + 1.5 * fl, 11), (32 + 2.5 * e + 5 * fl, 1 + 2 * e + 6 * fl), (24 + fl, 8 + fl))
        inner = ((31.5 + 1.5 * fl, 9.5), (31 + 2 * e + 4 * fl, 4 + 1.5 * e + 4.5 * fl), (26 + fl, 8.5 + fl))
        return outer, inner
    def mirror(t): return tuple((W - x, y) for x, y in t)
    ears = [tuple(map(mirror, right_ear(ear_l, flat))), right_ear(ear, flat)]
    for y in range(H):
        for x in range(W):
            for outer, inner in ears:
                if tri(outer, x + .5, y + .5): g[y][x] = "E" if tri(inner, x + .5, y + .5) else "F"
    # head
    for y in range(H):
        for x in range(W):
            if inside_ellipse(x + .5, y + .5, 20, 18.6, 16.6, 11.6):
                g[y][x] = "f" if y >= 25 or (y >= 23 and 8 <= x <= 31) else "F"
    # no gap between the headband and the top of the head
    for y in range(11):
        for x in range(W):
            if g[y][x] == "." and ((x + .5 - 20) / 17.0) ** 2 + ((y + .5 - 20) / 13.8) ** 2 < 1:
                g[y][x] = "F"
    # ear cups in front of the head
    for side in (0, 1):
        for y in range(13, 26):
            for x in range(0, 5):
                if (y in (13, 25)) and x == 0: continue
                xx = x if side == 0 else W - 1 - x
                g[y][xx] = "h" if x == 4 else "H"
    # eyes: amber ovals five pixels wide, vertical slit pupils, shine at the top left
    for cx in (12.5, 27.5):
        c = int(cx)
        cells = [(x, y) for y in range(H) for x in range(W) if inside_ellipse(x + .5, y + .5, cx, 16.5, 2.8, 4.4)]
        if happy:
            for x, y in cells: g[y][x] = "F"
            for x, y in [(c - 3, 18), (c - 2, 17), (c - 1, 16), (c, 16), (c + 1, 16), (c + 2, 17), (c + 3, 18)]:
                g[y][x] = "O"
            continue
        for x, y in cells:
            edge = not inside_ellipse(x + .5, y + .5, cx, 16.5, 1.8, 3.6)
            g[y][x] = "o" if edge and y >= 17 else "O"
        px, ly = c + look, look_y           # both pupils start in the middle of the eye
        sides = [(px + s, y) for s in (-1, 1) for y in range(15 + ly, 19 + ly)]
        dots = [(px, y) for y in range(14 + ly, 20 + ly)]
        if pupil >= 2: dots += sides
        if pupil >= 3: dots += [(px + s, y) for s in (-1, 1) for y in (14 + ly, 19 + ly)] + [(px + s, y) for s in (-2, 2) for y in (16 + ly, 17 + ly)]
        for x, y in (sides if pupil == 1 else []):
            if (x, y) in cells: g[y][x] = "o"         # a darker rim makes the slit read a touch wider
        for x, y in dots:
            if (x, y) in cells: g[y][x] = "K"
        g[13][c - 1] = g[14][c - 1] = "H"           # the shine stays put while the pupils move
        g[18][c + 2] = "H"
        if lid:
            for x, y in cells:
                if y < lid: g[y][x] = "F"
            if lid >= SHUT:
                for x, y in cells:
                    if y == 17 and abs(x + .5 - cx) < 3: g[y][x] = "o"
                g[16][c - 3] = g[16][c + 3] = "o"
    # nose, wavy mouth, tongue
    for x in range(18, 22): g[22][x] = "N"
    g[23][19] = g[23][20] = "N"
    for x in (16, 19, 20, 23): g[24][x] = "K"
    for x in (17, 18, 21, 22): g[25][x] = "K"
    for y in (26, 27): g[y][19] = g[y][20] = "T" if y < 26 + min(tongue, 2) else "f"
    if tongue == 3: g[28][19] = g[28][20] = "T"
    if tongue == 4: g[25][23] = g[26][22] = g[26][23] = "T"
    if mouth:                                   # open mouth: meow, yawn (with fangs), hiss (with fangs)
        for y in range(24, 29):
            for x in range(15, 25):
                if g[y][x] in "KT": g[y][x] = "f"
        shape = {1: {24: (17, 22), 25: (17, 22), 26: (18, 21), 27: (19, 20)},
                 2: {24: (16, 23), 25: (16, 23), 26: (16, 23), 27: (17, 22), 28: (18, 21)},
                 3: {24: (16, 23), 25: (16, 23), 26: (17, 22), 27: (18, 21)}}[mouth]
        for y, (a, b) in shape.items():
            for x in range(a, b + 1): g[y][x] = "K"
        for x, y in {1: [(19, 26), (20, 26)], 2: [(18, 27), (19, 27), (20, 27), (21, 27), (19, 26), (20, 26)], 3: [(19, 26), (20, 26)]}[mouth]:
            g[y][x] = "T"
        if mouth >= 2: g[25][17] = g[25][22] = "H"
    # whiskers in morse: dash dot dot dash dot, three rows each side
    for y, off in ((21, 1), (23, 2), (25, 1)):
        for x in [off, off + 1, off + 2, off + 4, off + 6, off + 8, off + 9, off + 10]:
            g[y][x] = glow; g[y][W - 1 - x] = glow
    # mic boom from the right cup down to the mouth
    for x, y in [(37, 26), (36, 27), (35, 28), (34, 28), (33, 28), (32, 28), (31, 28)]:
        g[y][x] = "H"
    g[28][28] = g[28][29] = g[28][30] = "B"; g[27][28] = g[27][29] = "B"
    return ["".join(r) for r in g]

FPS = 20

def at(t, keys, default):
    """Value of a step track: keys = [(start, value), ...] sorted by time."""
    v = default
    for start, value in keys:
        if t >= start - 1e-9: v = value
    return v


BLINK = [14, 16, 18, SHUT, SHUT, 18, 16, 14]
_LOOK = [(2.6, -1), (2.7, -2), (3.3, -1), (3.4, 0), (3.6, 1), (3.7, 2), (4.3, 1), (4.4, 0)]
_TONGUE = [(2.4, 1), (2.45, 0), (4.85, 1), (4.9, 2)]
_EAR = [(7.3, .5), (7.35, 1), (7.45, .5), (7.5, 0), (7.6, .5), (7.65, 1), (7.75, .5), (7.8, 0)]


def blink(t, starts, step=.05):
    """Eyelid for a blink starting at each of starts (0 when not blinking)."""
    for b in starts:
        k = int((t - b) / step)
        if 0 <= k < len(BLINK): return BLINK[k]
    return 0


def breath(t, period=4.0, low=0):
    """Whisker colour breathing on a sine; low > 0 keeps it from the dimmest steps."""
    import math
    level = .5 + .5 * math.sin(2 * math.pi * t / period)
    return "zyxY"[min(3, low + int(level * (4 - low)))]


def idle(t):
    """The 8-second loop of the avatar: blinks at 1 s and 6 s, hides the tongue and looks
    left and right (2.4–4.9 s), twitches an ear at the end; whiskers breathe all the time."""
    t %= 8
    return dict(lid=blink(t, (1.0, 6.0)), look=at(t, _LOOK, 0), tongue=at(t, _TONGUE, 2), ear=at(t, _EAR, 0), glow=breath(t))
