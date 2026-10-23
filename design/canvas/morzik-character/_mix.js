// Четвёртый ряд: лицо из М2 (без щёк и лапок), цвета М3, рот — спираль на проволочках из М1.
// Большая аватарка анимирована: дышит светом, моргает, раз в цикл мигает спиралью «·–·».
const LOOP = 6;
function anim(t) {
  t = ((t % LOOP) + LOOP) % LOOP;
  let glow = .78 + .18 * Math.sin(t / 3 * Math.PI * 2), open = 1, look = 0, morseOn = null;
  if (t > 2 && t < 2.22) open = Math.abs(Math.cos((t - 2) / .22 * Math.PI));
  if (t > .5 && t < 1.7) look = Math.sin((t - .5) / 1.2 * Math.PI) * 2.2;
  const u = .2, seq = [1, 0, 1, 1, 1, 0, 1], m0 = 3.4;
  if (t > m0 && t < m0 + seq.length * u) morseOn = seq[Math.floor((t - m0) / u)] === 1;
  if (t >= m0 + seq.length * u && t < m0 + seq.length * u + .6) morseOn = false;
  if (morseOn !== null) glow = morseOn ? 1.35 : .3;
  return { glow, open, look };
}
// Спокойная анимация для доработанных Н3: только медленное дыхание света и плавный взгляд, без морганий и вспышек.
const CALM = 8;
const ease = p => (1 - Math.cos(Math.PI * Math.min(1, Math.max(0, p)))) / 2;
// Взгляд: смотрит прямо, плавно уводит глаза вбок, держит, возвращает. Моргает дважды за цикл.
function animCalm(t) {
  t = ((t % CALM) + CALM) % CALM;
  // Яркость спирали — единственный источник: от неё же ореол вокруг лампы и тёплое пятно за лицом.
  // На 5-й секунде спираль дважды слегка вздрагивает, как старая лампа.
  const bump = (c, w) => { const p = (t - c) / w; return p > 0 && p < 1 ? Math.sin(Math.PI * p) : 0; };
  const glow = (.94 + .06 * Math.sin(t / CALM * Math.PI * 2)) * (1 - .38 * bump(5.1, .14) - .24 * bump(5.34, .18));
  const look = -2.6 * (ease((t - 2.8) / .6) - ease((t - 4.6) / .6));
  const blink = c => { const p = (t - c) / .28; return p > 0 && p < 1 ? 1 - Math.sin(Math.PI * p) : 1; };
  return { glow, open: Math.min(blink(1.3), blink(6.4)), look };
}
const mixBulb = ({ glass, eye, back = 0, rim = false, calm = false }) => Object.assign((s, t) => {
  const A = t == null ? { glow: s === 'write' ? 1.3 : 1, open: 1, look: 0 } : calm ? animCalm(t) : anim(t);
  const lit = s !== 'think', g = lit ? A.glow : 0;
  const Gl = gid('glass'), Ha = gid('halo');
  const GLASS = {
    warm:  [[0, '#FFFAE6', .98], [.55, '#FFE596', .9], [1, '#E2B456', .85]],
    frost: [[0, '#F6F8FF', .96], [.7, '#DDE5F7', .9], [1, '#A9B7DA', .92]],
    clear: [[0, '#FFFFFF', .2], [.75, '#CFE0FF', .14], [1, '#9FB6E8', .38]],
  }[glass];
  const cold = { warm: [[0, '#E9EEFA', .75], [.7, '#C3CEE8', .55], [1, '#8E9CC4', .6]], frost: GLASS, clear: GLASS }[glass];
  let o = navyBg() + `<defs>${radial(Gl, lit ? GLASS : cold, { cy: .62, fx: .5, fy: .6, r: .62 })}${radial(Ha, [[0, '#FFE08A', .6], [1, '#FFE08A', 0]])}</defs>`;
  if (g > 0) o += `<circle cx="60" cy="54" r="${36 + 14 * g}" fill="url(#${Ha})" opacity="${Math.min(1, .35 + .5 * g)}"/>`;
  o += floorShadow(60, 112, 18, .4);
  // Стекло, на нём проволочки, спираль-улыбка (из М1) и лицо.
  o += `<path d="${BULB}" fill="url(#${Gl})"/><path d="${BULB}" fill="none" stroke="#C9D6F5" stroke-width="1.5" opacity=".55"/>`;
  if (back && lit) { const Bk = gid('back'); o += `<defs>${radial(Bk, [[0, '#FFF1C4', .95], [.55, '#FFE08A', .55], [1, '#FFE08A', 0]])}</defs><ellipse cx="60" cy="52" rx="${26 * back + 6}" ry="${22 * back + 5}" fill="url(#${Bk})" opacity="${Math.min(1, g ** 1.5)}"/>`; }
  const wire = glass === 'frost' ? 'opacity=".5"' : '';
  o += stroke('M53 84 L53 66 M67 84 L67 66', '#9AA6C4', 1.8, wire);
  const fil = s === 'think' ? 'M53 65 L67 65' : 'M53 64 Q56 70 58.5 64 Q60 61 61.5 64 Q64 70 67 64';
  // Спираль светится той же яркостью g, что ореол и пятно за лицом: тускнеет — темнеет и теряет свечение.
  const mixC = (a, b, k) => '#' + [0, 2, 4].map(i => Math.round(parseInt(a.substr(i + 1, 2), 16) * (1 - k) + parseInt(b.substr(i + 1, 2), 16) * k).toString(16).padStart(2, '0')).join('');
  const k = Math.max(0, Math.min(1, (g - .45) / .55));
  o += lit ? stroke(fil, g > 1 ? '#FFD27A' : mixC('#8A4A2A', '#FF9B3D', k), 3, `style="filter:drop-shadow(0 0 ${1 + 5 * k}px rgba(255,150,50,${(.3 + .7 * k).toFixed(2)}))"`) : stroke(fil, '#7E89A8', 3);
  const [px, py] = { idle: [A.look, 0], read: [0, 3], think: [3, -3], write: [0, 0] }[s];
  const R = rim ? `stroke="#F3E9CF" stroke-width="1.6" stroke-opacity=".9"` : '';
  const E = eye === 'black' ? '#14131A' : eye === 'amber' ? (lit ? '#FFC34D' : '#8E98B8') : '#1B1F3B', eg = eye === 'amber' && lit ? `style="filter:drop-shadow(0 0 3px rgba(255,190,70,.9))"` : '';
  [50, 70].forEach(x => {
    const cx = x + px, cy = 47 + py;
    if (s === 'write') o += stroke(`M${x - 5} 48 Q${x} 42 ${x + 5} 48`, E, 3.4, eg);
    else if (A.open < .2) o += stroke(`M${cx - 5} ${cy} L${cx + 5} ${cy}`, E, 3, eg);
    else o += `<ellipse cx="${cx}" cy="${cy}" rx="5.8" ry="${6.6 * A.open}" fill="${E}" ${eg} ${R}/>` + (A.open > .6 ? dot(cx + 2, cy - 2.5, 2.1, '#fff') + dot(cx - 1.6, cy + 3, .9, '#fff', 'opacity=".85"') : '');
  });
  o += `<path d="M41 40 Q42 26 55 21" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" opacity="${glass === 'clear' ? .6 : .7}" ${blur(.6)}/>` + dot(76, 33, 2.2, '#fff', 'opacity=".8"');
  o += screwBase(84, 'navy');
  return o;
}, { calm });
Object.assign(CHARS, {
  mixWarm: mixBulb({ glass: 'warm', eye: 'dark' }),
  mixFrost: mixBulb({ glass: 'frost', eye: 'dark' }),
  mixClear: mixBulb({ glass: 'clear', eye: 'amber' }),
  clearGlow: mixBulb({ glass: 'clear', eye: 'black', back: 1, calm: true }),
  clearRim: mixBulb({ glass: 'clear', eye: 'black', rim: true, calm: true }),
  clearBoth: mixBulb({ glass: 'clear', eye: 'black', back: .6, rim: true, calm: true }),
});

avatar = function (key, size, s = 'idle', t) {
  const id = 'c' + (uid++);
  return `<svg width="${size}" height="${size}" viewBox="0 0 120 120"><clipPath id="${id}"><circle cx="60" cy="60" r="60"/></clipPath><g clip-path="url(#${id})">${CHARS[key](s, t)}</g></svg>`;
};
// Доска как обычно, но большая аватарка живёт по таймлайну (?t=1.5 — замереть на кадре).
function animBoard(key, title, line) {
  board(key, title, line + (CHARS[key].calm ? ' Анимация: свет дышит, взгляд иногда уходит вбок, моргает; спираль изредка вздрагивает вместе со всем светом.' : ' Большая аватарка анимирована: так она будет выглядеть в профиле бота.'));
  const big = document.querySelector('.big'), q = new URLSearchParams(location.search).get('t');
  if (q != null) { big.innerHTML = avatar(key, 360, 'idle', +q); return; }
  const t0 = performance.now();
  const tick = now => { big.innerHTML = avatar(key, 360, 'idle', (now - t0) / 1000); requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
}
