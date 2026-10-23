// Морзик — текстовый помощник в Telegram (Hermes). Сетка viewBox 120, аватарка всегда круг.
const C = { ivory:'#E7E0D2', bakelite:'#26211D', signal:'#B8321F', lamp:'#E8A33D', off:'#CFC6B6', ether:'#1F1B18' };
const glow = (c = 'rgba(232,163,61,.9)', r = 3) => `style="filter:drop-shadow(0 0 ${r}px ${c})"`;
const G = () => glow('rgba(232,163,61,.95)', 3.5);
const STATES = [['idle', 'покой'], ['read', 'читает'], ['think', 'думает'], ['write', 'пишет']];
const STATUS = { idle: 'в сети', read: 'читает…', think: 'думает…', write: 'печатает…' };

function wave(cx, cy, w, amp, periods = 3, bell = true, smile = 0) {
  const pts = [];
  for (let i = 0; i <= 60; i++) {
    const t = i / 60, x = cx - w / 2 + w * t;
    const env = bell ? Math.exp(-Math.pow((t - .5) / .26, 2)) * .75 + .25 : 1;
    pts.push(`${x.toFixed(2)} ${(cy - Math.sin(t * Math.PI * 2 * periods) * amp * env + smile * (1 - 4 * (t - .5) ** 2)).toFixed(2)}`);
  }
  return 'M' + pts.join(' L');
}
const stroke = (d, color, w, extra = '') => `<path d="${d}" fill="none" stroke="${color}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" ${extra}/>`;
const dot = (x, y, r, color, extra = '') => `<circle cx="${x}" cy="${y}" r="${r}" fill="${color}" ${extra}/>`;
const bg = c => `<rect width="120" height="120" fill="${c}"/>`;
function screen() {
  let o = bg(C.ether);
  [30, 45, 60, 75, 90].forEach(v => o += `<line x1="${v}" y1="0" x2="${v}" y2="120" stroke="${C.ivory}" stroke-opacity=".045" stroke-width="1.2"/><line x1="0" y1="${v}" x2="120" y2="${v}" stroke="${C.ivory}" stroke-opacity=".045" stroke-width="1.2"/>`);
  return o;
}
// Строка морзянки: '.-.' → точки и тире слева направо, по дуге smile.
function morse(code, cx, cy, color, { unit = 6, w = 4.5, r = 2.8, arc = 0, extra = '' } = {}) {
  const seg = [...code].map(ch => ch === '.' ? unit * .5 : unit * 1.8), gap = unit * .9;
  const total = seg.reduce((a, b) => a + b, 0) + gap * (seg.length - 1);
  let x = cx - total / 2, o = '';
  const yAt = px => cy + arc * (1 - 4 * ((px - cx) / total) ** 2);
  [...code].forEach((ch, i) => {
    const L = seg[i], mid = x + L / 2;
    o += ch === '.' ? dot(mid, yAt(mid), r, color, extra) : stroke(`M${x + w / 2} ${yAt(x)} L${x + L - w / 2} ${yAt(x + L)}`, color, w, extra);
    x += L + gap;
  });
  return o;
}

const CHARS = {
  // Сейчас: аватарка Волны Д6·2 стоит и у бота.
  now: s => {
    let o = screen();
    const dx = s === 'think' ? 4 : 0, dy = s === 'think' ? -4 : 0, r = s === 'read' ? 6.8 : 5.5;
    o += dot(45 + dx, 54 + dy, r, C.lamp, G()) + dot(75 + dx, 54 + dy, r, C.lamp, G());
    if (s === 'think') o += stroke('M38 75 L82 75', C.lamp, 2.5, 'opacity=".35"') + dot(70, 75, 4, C.lamp, G());
    else if (s === 'read') o += stroke('M41 74 Q60 78 79 74', C.lamp, 4.5, G());
    else o += stroke(wave(60, 73, 46, s === 'write' ? 10 : 3.5, 2, true, s === 'write' ? 0 : 4), C.lamp, 4.5, G());
    return o;
  },
  // А. Брат Волны: тот же экран осциллографа, но рот — морзянка «·–·» дугой-улыбкой.
  screen: s => {
    let o = screen();
    const dx = s === 'think' ? 4 : 0, dy = s === 'think' ? -4 : s === 'read' ? 3 : 0, r = s === 'read' ? 6.5 : 5.5;
    o += dot(45 + dx, 53 + dy, r, C.lamp, G()) + dot(75 + dx, 53 + dy, r, C.lamp, G());
    if (s === 'think') o += [50, 60, 70].map((x, i) => dot(x, 76, 2.8, C.lamp, `opacity="${[.3, .6, 1][i]}" ${G()}`)).join('');
    else if (s === 'write') o += morse('-.--.', 60, 75, C.lamp, { unit: 6.5, extra: G() });
    else if (s === 'read') o += morse('-', 60, 75, C.lamp, { unit: 7, extra: G() });
    else o += morse('.-.', 60, 72, C.lamp, { unit: 8, w: 5, r: 3.2, arc: 4, extra: G() });
    return o;
  },
  // Б. Красный: та же морзянка-улыбка, но на сигнальном красном — сразу отличим от Волны в списке чатов.
  red: s => {
    let o = bg(C.signal);
    const dx = s === 'think' ? 4 : 0, dy = s === 'think' ? -5 : s === 'read' ? 3 : 0, r = s === 'read' ? 7 : 6;
    o += dot(46 + dx, 52 + dy, r, C.ivory) + dot(74 + dx, 52 + dy, r, C.ivory);
    if (s === 'think') o += [50, 60, 70].map((x, i) => dot(x, 76, 3, C.ivory, `opacity="${[.35, .65, 1][i]}"`)).join('');
    else if (s === 'write') o += morse('-.--.', 60, 75, C.ivory, { unit: 6.5, w: 5 });
    else if (s === 'read') o += morse('-', 60, 75, C.ivory, { unit: 7, w: 5 });
    else o += morse('.-.', 60, 72, C.ivory, { unit: 8, w: 5.5, r: 3.4, arc: 4 });
    return o;
  },
  // В. Точка и тире: сам Морзик — янтарная точка, а тире парит над ней как бровь или шапочка.
  dotdash: s => {
    let o = screen();
    const sq = s === 'write' ? 2 : 0;
    o += `<ellipse cx="60" cy="${70 + sq}" rx="${27 + sq}" ry="${27 - sq}" fill="${C.lamp}" ${G()}/>`;
    const dash = { idle: 'M48 33 L72 33', read: 'M47 38 L73 38', think: 'M49 30 L73 24', write: 'M44 30 L64 30' }[s];
    o += stroke(dash, C.lamp, 7, G());
    if (s === 'write') o += dot(76, 30, 3.8, C.lamp, G());
    const ex = s === 'think' ? 3 : 0, ey = s === 'think' ? 63 : s === 'read' ? 69 : 66, er = s === 'read' ? 4.2 : 3.6;
    o += dot(51 + ex, ey, er, C.ether) + dot(69 + ex, ey, er, C.ether);
    if (s === 'think') o += stroke('M57 79 L65 79', C.ether, 3);
    else if (s === 'write') o += `<ellipse cx="60" cy="79" rx="3.6" ry="3" fill="${C.ether}"/>`;
    else o += stroke('M54 77 Q60 82 66 77', C.ether, 3);
    return o;
  },
  // Г. Телеграфный ключ: голова — красная кнопка ключа на бакелитовой базе; пишет — жмёт ключ, под ним искра.
  key: s => {
    let o = bg(C.ivory);
    const down = s === 'write' ? 5 : 0;
    o += `<rect x="22" y="88" width="76" height="12" rx="6" fill="${C.bakelite}"/>`;
    o += stroke('M82 88 L82 74', C.bakelite, 5) + dot(82, 72, 4.5, C.bakelite);
    o += stroke(`M82 72 L44 ${70 + down}`, C.bakelite, 5.5);
    o += dot(92, 82, 3, s === 'think' ? C.lamp : '#5E554B', s === 'think' ? glow('rgba(232,163,61,1)', 5) : '');
    if (s === 'write') o += dot(44, 85, 3.2, C.lamp, glow('rgba(232,163,61,1)', 5)) + stroke('M36 84 L32 82 M52 84 L56 82', C.lamp, 2, glow());
    const cy = 50 + down;
    o += dot(44, cy, 22, C.signal);
    const px = s === 'think' ? 2.5 : 0, py = s === 'think' ? -3 : s === 'read' ? 2.5 : 0, er = s === 'read' ? 4.6 : 4;
    o += dot(36 + px, cy - 2 + py, er, C.ivory) + dot(52 + px, cy - 2 + py, er, C.ivory);
    if (s === 'write') o += `<ellipse cx="44" cy="${cy + 9}" rx="3.4" ry="2.8" fill="${C.ivory}"/>`;
    else if (s !== 'think') o += stroke(`M39 ${cy + 8} Q44 ${cy + 12} 49 ${cy + 8}`, C.ivory, 3);
    return o;
  },
  // Д. Птичка на проводе: бакелитовый воробей, янтарные глаза, клюв — тире, хохолок — «·–».
  bird: s => {
    let o = bg(C.ivory);
    o += stroke('M0 98 L120 94', C.bakelite, 2.2, 'opacity=".55"');
    o += stroke('M53 88 L52 96 M67 88 L68 96', C.bakelite, 3);
    const hop = s === 'write' ? -3 : 0;
    o += `<g transform="translate(0 ${hop})">`;
    o += dot(58, 24, 3.2, C.bakelite) + stroke('M64 23 L72 18', C.bakelite, 3.6);
    o += `<ellipse cx="60" cy="60" rx="31" ry="31" fill="${C.bakelite}"/>`;
    o += `<ellipse cx="60" cy="74" rx="19" ry="15" fill="${C.ivory}" opacity=".9"/>`;
    const px = s === 'think' ? 3 : 0, py = s === 'think' ? -3 : s === 'read' ? 2 : 0, er = s === 'read' ? 5 : 4.4;
    o += dot(49 + px, 52 + py, er, C.lamp, glow()) + dot(71 + px, 52 + py, er, C.lamp, glow());
    o += s === 'write' ? stroke('M55 62 L65 61 M55 65 L64 67', C.signal, 3.6) : stroke('M55 63 L65 63', C.signal, 4.5);
    o += '</g>';
    if (s === 'write') o += morse('.-', 98, 40, C.lamp, { unit: 5, w: 3.5, r: 2.2, extra: glow() });
    if (s === 'think') o += dot(96, 34, 3, C.lamp, glow('rgba(232,163,61,1)', 4));
    return o;
  },
  // Е. Одна лампа: циклоп-индикатор. Большой янтарный глаз мигает морзянкой, когда пишет.
  lamp: s => {
    let o = bg(C.bakelite);
    o += dot(60, 54, 25, C.ivory) + dot(60, 54, 20, C.ether);
    if (s === 'write') o += stroke('M48 54 L72 54', C.lamp, 11, glow('rgba(232,163,61,1)', 6));
    else if (s === 'think') o += dot(60, 54, 13, '#6B5233') + dot(64, 50, 5, C.lamp, G());
    else o += dot(60, s === 'read' ? 56 : 54, s === 'read' ? 15 : 13, C.lamp, glow('rgba(232,163,61,1)', s === 'read' ? 7 : 4)) + dot(65, 49, 3.4, '#FFF6E2', 'opacity=".9"');
    if (s === 'write') o += morse('.-.', 60, 92, C.ivory, { unit: 6, w: 4, r: 2.6 });
    else o += stroke(s === 'think' ? 'M54 90 L66 90' : 'M50 88 Q60 95 70 88', C.ivory, 4);
    return o;
  },
};

let uid = 0;
function avatar(key, size, s = 'idle') {
  const id = 'c' + (uid++);
  return `<svg width="${size}" height="${size}" viewBox="0 0 120 120"><clipPath id="${id}"><circle cx="60" cy="60" r="60"/></clipPath><g clip-path="url(#${id})">${CHARS[key](s)}</g></svg>`;
}

function board(key, title, line, name = 'Морзик') {
  document.body.innerHTML = `
  <main>
    <div class="big">${avatar(key, 360)}</div>
    <div class="side">
      <h1>${title}</h1>
      <p>${line}</p>
      <div class="states">${STATES.map(([s, l]) => `<figure>${avatar(key, 76, s)}<figcaption>${l}</figcaption></figure>`).join('')}</div>
      <div class="tg">
        <div class="contact">${avatar(key, 44, 'write')}<div><b>${name}</b><span>${STATUS.write}</span></div></div>
        <div class="msg">${avatar(key, 30)}<div class="bubble">Готово, письмо Лене в черновиках. Отправить?</div></div>
      </div>
      <div class="sizes">${[64, 40, 28, 20].map(z => `<figure>${avatar(key, z)}<figcaption>${z}</figcaption></figure>`).join('')}</div>
    </div>
  </main>`;
}
