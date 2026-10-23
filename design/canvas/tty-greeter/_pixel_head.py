# pixel-art Morzik head, left half mirrored; '.' = empty
HALF = [
 "....G.........",
 "....GG........",
 "....GPG.......",
 "....GPPG...WWW",
 "....GPPGGWWGGG",
 "....GGGGWGGGGG",
 "...GGGGWGGGGGG",
 "...GGGWGGGGGGG",
 "..WWWWGGGGGGGG",
 ".WOOOWGGGGGGGG",
 ".WOOOWGYYYYGGG",
 ".WOOOWYYYYYYGG",
 ".WOOOWYYOOYYGG",
 ".WOOOWYYOOYYGG",
 ".WOOOWYYYYYYGG",
 "..WWWWGYYYYGGG",
 "...GGGGGGGGGGP",
 "CCCC.GGGGGGGGg",
 "...GGGGGGGGGgG",
 "..CCCCGGGGGGGG",
 "....GGGGGGGGGG",
 ".....GGGGGGGGG",
 ".......GGGGGGG",
 "..........GGGG",
]
def grid():
    g = [list(r + r[::-1]) for r in HALF]
    # tongue, mic boom from the right cup to the mouth, red light
    g[19][13] = g[19][14] = "P"
    for r, c in [(16, 24), (17, 23), (18, 22), (19, 21), (20, 20), (20, 19)]:
        g[r][c] = "W"
    g[20][18] = "R"
    return ["".join(r) for r in g]
if __name__ == "__main__":
    for r in grid(): print(r)
