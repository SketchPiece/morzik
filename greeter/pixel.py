"""Pixel Morzik, the same art and 8-second loop as design/canvas/tty-greeter/_pixel_v2.py
(the canvas boards are drawn from that copy; keep the two in step)."""
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

def build(lid=0, look=0, tongue=2, ear=0.0, glow="Y"):
    """lid: 0 open, else the eyelid covers rows above it (SHUT = closed, drawn as an arc);
    look: pupils -2..2 pixels; tongue: rows shown 0..2; ear: right ear twitch 0..1;
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
    # ears (drawn before the head so the head's top edge covers their base)
    def tri(p, x, y):
        (x1, y1), (x2, y2), (x3, y3) = p
        def s(ax, ay, bx, by): return (x - bx) * (ay - by) - (ax - bx) * (y - by)
        d1, d2, d3 = s(x1, y1, x2, y2), s(x2, y2, x3, y3), s(x3, y3, x1, y1)
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))
    for y in range(H):
        for x in range(W):
            for outer, inner in [(((6.5, 11), (8, 1), (16, 8)), ((8.5, 9.5), (9, 4), (14, 8.5))),
                                 (((33.5, 11), (32 + 2.5 * ear, 1 + 2 * ear), (24, 8)), ((31.5, 9.5), (31 + 2 * ear, 4 + 1.5 * ear), (26, 8.5)))]:
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
    # eyes: big amber ovals, vertical slit pupils, shine at the top left
    for cx in (12.5, 27.5):
        cells = [(x, y) for y in range(H) for x in range(W) if inside_ellipse(x + .5, y + .5, cx, 16.5, 3.6, 4.4)]
        for x, y in cells:
            edge = not inside_ellipse(x + .5, y + .5, cx, 16.5, 2.6, 3.6)
            g[y][x] = "o" if edge and y >= 17 else "O"
        px = int(cx) + look                     # both pupils start in the middle of the eye
        for y in range(14, 20):
            if (px, y) in cells: g[y][px] = "K"
        g[13][int(cx) - 1] = g[14][int(cx) - 1] = "H"   # the shine stays put while the pupils move
        g[18][int(cx) + 2] = "H"
        if lid:
            for x, y in cells:
                if y < lid: g[y][x] = "F"
            if lid >= SHUT:
                for x, y in cells:
                    if y == 17 and abs(x + .5 - cx) < 3: g[y][x] = "o"
                g[16][int(cx) - 3] = g[16][int(cx) + 3] = "o"
    # nose, wavy mouth, tongue
    for x in range(18, 22): g[22][x] = "N"
    g[23][19] = g[23][20] = "N"
    for x in (16, 19, 20, 23): g[24][x] = "K"
    for x in (17, 18, 21, 22): g[25][x] = "K"
    for y in (26, 27): g[y][19] = g[y][20] = "T" if y < 26 + tongue else "f"
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

def timeline(head_rows=29):
    """The 8-second loop of the avatar: blinks at 1 s and 6 s, hides the tongue and looks
    left and right (2.4–4.9 s), twitches an ear at the end; whiskers breathe all the time.
    Every move goes through in-between frames so it reads smooth at 20 fps."""
    import math
    def at(t, keys, default):
        """Value of a step track: keys = [(start, value), ...] sorted by time."""
        v = default
        for start, value in keys:
            if t >= start - 1e-9: v = value
        return v
    blink = []
    for b in (1.0, 6.0):
        blink += [(b + i * .05, lid) for i, lid in enumerate([14, 16, 18, SHUT, SHUT, 18, 16, 14, 0])]
    look = [(2.6, -1), (2.7, -2), (3.3, -1), (3.4, 0), (3.6, 1), (3.7, 2), (4.3, 1), (4.4, 0)]
    tongue = [(2.4, 1), (2.45, 0), (4.85, 1), (4.9, 2)]
    ear = [(7.3, .5), (7.35, 1), (7.45, .5), (7.5, 0), (7.6, .5), (7.65, 1), (7.75, .5), (7.8, 0)]
    frames, seq = [], []
    for i in range(8 * FPS):
        t = i / FPS
        level = .5 + .5 * math.sin(2 * math.pi * t / 4)
        glow = "zyxY"[min(3, int(level * 4))]
        f = "\n".join(build(at(t, blink, 0), at(t, look, 0), at(t, tongue, 2), at(t, ear, 0), glow)[:head_rows])
        if f not in frames: frames.append(f)
        seq.append(frames.index(f))
    return frames, seq

