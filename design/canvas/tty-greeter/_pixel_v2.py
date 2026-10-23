"""Pixel Morzik closer to the 3D avatar. The Linux console palette can be redefined to any
16 RGB colours, so these are the avatar's own colours (one console palette slot each)."""
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
 "W": "#ffffff",  # eye shine
 "N": "#8c5a7c",  # nose
 "T": "#f2809e",  # tongue
 "Y": "#ffb43a",  # whiskers (morse)
 "B": "#3c5096",  # mic tip
 "y": "#d98e2b",  # whiskers, dimmer (breathing light)
 "z": "#a86b22",  # whiskers, dimmest
}
W, H = 40, 38

def build(blink=0, look=0, tongue=True, ear=False, glow="Y"):
    """blink: 0 open, 1 half shut, 2 shut; look: pupils -1 left, 0, +1 right;
    ear: right ear twitched; glow: whisker colour Y / y / z."""
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
                                 (((33.5, 11), (34.5, 3) if ear else (32, 1), (24, 8)), ((31.5, 9.5), (33, 5.5) if ear else (31, 4), (26, 8.5)))]:
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
        px = int(cx) + (1 if cx < 20 else 0) + look
        for y in range(14, 20): g[y][px] = "K"
        g[13][int(cx) - 1 + look] = g[14][int(cx) - 1 + look] = "W"
        g[18][int(cx) + 2 + look] = "W"
        if blink:
            top = 17 if blink == 1 else 99          # the lid comes down to row 17, or all the way
            for x, y in cells:
                if y < top: g[y][x] = "F"
            if blink == 2:
                for x, y in cells:
                    if y == 17 and abs(x + .5 - cx) < 3: g[y][x] = "o"
                g[16][int(cx) - 3] = g[16][int(cx) + 3] = "o"
    # nose, wavy mouth, tongue
    for x in range(18, 22): g[22][x] = "N"
    g[23][19] = g[23][20] = "N"
    for x in (16, 19, 20, 23): g[24][x] = "K"
    for x in (17, 18, 21, 22): g[25][x] = "K"
    for y in (26, 27): g[y][19] = g[y][20] = "T" if tongue else "f"
    # whiskers in morse: dash dot dot dash dot, three rows each side
    for y, off in ((21, 1), (23, 2), (25, 1)):
        for x in [off, off + 1, off + 2, off + 4, off + 6, off + 8, off + 9, off + 10]:
            g[y][x] = glow; g[y][W - 1 - x] = glow
    # mic boom from the right cup down to the mouth
    for x, y in [(37, 26), (36, 27), (35, 28), (34, 28), (33, 28), (32, 28), (31, 28)]:
        g[y][x] = "H"
    g[28][28] = g[28][29] = g[28][30] = "B"; g[27][28] = g[27][29] = "B"
    return ["".join(r) for r in g]

FPS = 10

def timeline(head_rows=29):
    """The 8-second loop of the avatar: blinks at 1 s and 6 s, looks left and right
    with the tongue hidden (2.4–4.9 s), twitches an ear at the end; whiskers breathe."""
    import math
    frames, seq = [], []
    for i in range(8 * FPS):
        t = i / FPS
        blink = 0
        for b in (1.0, 6.0):
            if b <= t < b + .1 or b + .3 <= t < b + .4: blink = 1
            elif b + .1 <= t < b + .3: blink = 2
        look = -1 if 2.6 <= t < 3.4 else 1 if 3.6 <= t < 4.4 else 0
        tongue = not (2.4 <= t < 4.9)
        ear = 7.3 <= t < 7.5 or 7.6 <= t < 7.7
        level = .5 + .5 * math.sin(2 * math.pi * t / 4)
        glow = "Y" if level > .66 else "y" if level > .33 else "z"
        f = "\n".join(build(blink, look, tongue, ear, glow)[:head_rows])
        if f not in frames: frames.append(f)
        seq.append(frames.index(f))
    return frames, seq

if __name__ == "__main__":
    for r in build(): print(r)
