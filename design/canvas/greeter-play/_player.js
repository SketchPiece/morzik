// Plays one keyboard game: the pixel cat on the stage, the keys being pressed, the sound and the steps.
const KB = [["1","2","3","4","5","6","7","8","9","0","-"], ["q","w","e","r","t","y","u","i","o","p"],
            ["a","s","d","f","g","h","j","k","l","enter"], ["z","x","c","v","b","n","m",",","."], ["space","left","up","down","right"]];
const RU = Object.fromEntries([..."qwertyuiopasdfghjklzxcvbnm,."].map((k, i) => [k, "йцукенгшщзфывапролдячсмитьбю"[i]]));
const LBL = { enter: "Enter", space: "", left: "←", up: "↑", down: "↓", right: "→" };
const PAWS = [".FFFFFF.", "FFFFFFFF", "FFfFFfFF", "FFfFFfFF"];
const Z4 = ["hhhh", "..h.", ".h..", "hhhh"], Z5 = ["HHHHH", "...H.", "..H..", ".H...", "HHHHH"];
const DOT = [".NN.", "NTTN", "NTTN", ".NN."];
const SW = 56, SH = 38, S = 10, CX = 8, CY = 4;

function play(D) {
  const $ = id => document.getElementById(id);
  const keys = {};
  KB.forEach(row => {
    const r = document.createElement("div"); r.className = "row";
    row.forEach(k => {
      const e = document.createElement("div"); e.className = "k " + (LBL[k] !== undefined ? k : "");
      e.innerHTML = `<span>${LBL[k] ?? k.toUpperCase()}</span><small>${RU[k] || ""}</small>`;
      r.appendChild(e); keys[k] = e;
    });
    $("kb").appendChild(r);
  });
  const lis = D.steps.map(([, text]) => { const li = document.createElement("li"); li.textContent = text; $("steps").appendChild(li); return li; });
  const ctx = $("st").getContext("2d");
  const px = (x, y, ch) => { if (ch === "." || x < 0 || y < 0 || x >= SW || y >= SH) return; ctx.fillStyle = D.pal[ch]; ctx.fillRect(x * S, y * S, S, S); };
  const pat = (p, x, y) => p.forEach((r, j) => [...r].forEach((c, i) => px(x + i, y + j, c)));
  let i = 0, prev = [];
  function tick() {
    const T = D.ticks[i], [f, dy, dx, paws, z, dot, k, snd, line, say, screen] = T;
    ctx.fillStyle = D.pal["."]; ctx.fillRect(0, 0, SW * S, SH * S);
    D.frames[f].split("\n").forEach((r, y) => [...r].forEach((c, x) => px(CX + x + dx, CY + y + dy, c)));
    if (paws) { pat(PAWS, 16, SH - paws); pat(PAWS, 32, SH - paws); }
    z.forEach(([x, y, big]) => pat(big ? Z5 : Z4, x, y));
    if (dot) pat(DOT, dot[0], dot[1]);
    const on = k ? k.split(" ") : [];
    if (on.join() !== prev.join()) { prev.forEach(x => keys[x]?.classList.remove("on")); on.forEach(x => keys[x]?.classList.add("on")); prev = on; }
    $("snd").textContent = snd || "звук: тихо"; $("snd").className = "snd" + (snd ? " on" : "");
    $("line").textContent = line;
    $("top").textContent = D.says[say][0]; $("bot").textContent = D.says[say][1];
    $("login").style.display = screen ? "block" : "none";
    const t = i / D.fps; let a = 0;
    D.steps.forEach(([s], j) => { if (t >= s) a = j; });
    lis.forEach((li, j) => li.className = j === a ? "on" : j < a ? "done" : "");
    $("bar").style.width = (100 * i / (D.ticks.length - 1)) + "%";
    i = (i + 1) % D.ticks.length;
  }
  const still = location.hash.match(/t=([\d.]+)/);   // #t=8.2 shows one moment, for checking the boards
  if (still) { i = Math.round(+still[1] * D.fps); tick(); return; }
  tick(); setInterval(tick, 1000 / D.fps);
}
