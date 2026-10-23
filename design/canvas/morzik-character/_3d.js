// Третий ряд: объёмные версии фонаря (З) и лампочки (М). Свет всегда сверху слева.
let gidN = 0;
const gid = p => p + (gidN++);
const st = stops => stops.map(([o, c, a = 1]) => `<stop offset="${o}" stop-color="${c}" stop-opacity="${a}"/>`).join('');
const radial = (id, stops, { cx = .5, cy = .5, r = .5, fx, fy } = {}) => `<radialGradient id="${id}" cx="${cx}" cy="${cy}" r="${r}" fx="${fx ?? cx}" fy="${fy ?? cy}">${st(stops)}</radialGradient>`;
const linear = (id, stops, [x1, y1, x2, y2] = [0, 0, 0, 1]) => `<linearGradient id="${id}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}">${st(stops)}</linearGradient>`;
const blur = r => `style="filter:blur(${r}px)"`;
const shine = (cx, cy, rx, ry, rot, op = .6, b = .6) => `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="#fff" opacity="${op}" transform="rotate(${rot} ${cx} ${cy})" ${blur(b)}/>`;
const floorShadow = (cx, cy, rx, op = .35) => `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${rx * .16}" fill="#000" opacity="${op}" ${blur(2.2)}/>`;
const YGLOW = r => `style="filter:drop-shadow(0 0 ${r}px rgba(255,205,70,.95))"`;

// Глаз-линза: радужка-лампа, зрачок со стеклянным бликом. look: idle/read/think.
function lensEye(cx, cy, r, s, { off = false } = {}) {
  const L = gid('lens'), P = gid('pup');
  let o = '<defs>' + radial(L, off ? [[0, '#B7BED4'], [.7, '#7C86A6'], [1, '#4E5776']] : [[0, '#FFF6C2'], [.5, '#FFD54A'], [1, '#E39A17']], { fx: .4, fy: .35 })
    + radial(P, [[0, '#3A4878'], [1, '#090E1F']], { fx: .35, fy: .3 }) + '</defs>';
  o += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#${L})" ${off ? '' : YGLOW(s === 'write' ? 9 : 4)}/>`;
  if (s !== 'write') {
    const [px, py, k] = { idle: [0, 0, .4], read: [0, .25, .46], think: [.25, -.25, .34] }[s];
    o += `<circle cx="${cx + px * r}" cy="${cy + py * r}" r="${r * k}" fill="url(#${P})"/>` + dot(cx + px * r + r * .14, cy + py * r - r * .15, r * .12, '#fff', 'opacity=".95"');
  }
  o += shine(cx - r * .42, cy - r * .45, r * .36, r * .16, -35, .7, .4);
  return o;
}
// Шторки поверх линзы: металлические полоски, как у сигнального фонаря.
function slats(cx, cy, r, n = 3) {
  const M = gid('slat');
  let o = '<defs>' + linear(M, [[0, '#5A6890'], [.5, '#26325A'], [1, '#121A35']]) + '</defs>';
  for (let i = 0; i < n; i++) { const y = cy - r * .62 + i * r * .62; o += `<rect x="${cx - r}" y="${y - r * .14}" width="${r * 2}" height="${r * .28}" rx="${r * .1}" fill="url(#${M})"/>`; }
  return o;
}
const navyBg = () => { const B = gid('bg'); return `<defs>${radial(B, [[0, '#33467A'], [1, '#121A31']], { cy: .4, r: .7 })}</defs><rect width="120" height="120" fill="url(#${B})"/>`; };
const BULB = 'M60 18 A30 30 0 0 1 80 70 Q74 76 74 84 L46 84 Q46 76 40 70 A30 30 0 0 1 60 18 Z';
function screwBase(y = 84, tone = 'metal') {
  const M = gid('metal');
  const stops = tone === 'metal' ? [[0, '#7D838E'], [.3, '#F4F6F9'], [.55, '#AEB4BE'], [1, '#4E545E']] : tone === 'coral' ? [[0, '#D9645A'], [.35, '#FFB2A3'], [1, '#B8463F']] : [[0, '#5B6078'], [.35, '#AEB4D0'], [1, '#3A3F57']];
  let o = '<defs>' + linear(M, stops, [0, 0, 1, 0]) + '</defs>';
  [0, 7, 14].forEach((d, i) => o += `<rect x="${45 + i}" y="${y + 1 + d}" width="${30 - 2 * i}" height="6.4" rx="3.2" fill="url(#${M})"/>`);
  o += `<path d="M54 ${y + 22} L66 ${y + 22} L63 ${y + 26} L57 ${y + 26} Z" fill="#2A2D36"/>`;
  return o;
}

Object.assign(CHARS, {
  // З1. Глянцевый фонарь: тот же прожектор анфас, но эмаль, металлическое кольцо и стеклянная линза.
  aldisGloss: s => {
    const H = gid('hous'), R = gid('rim'), T = gid('tube');
    let o = navyBg();
    o += '<defs>' + radial(H, [[0, '#FFF9EE'], [.6, '#EADBC0'], [1, '#B09C78']], { fx: .32, fy: .28, r: .55 }) + linear(R, [[0, '#53639A'], [1, '#0C1229']]) + linear(T, [[0, '#FFF6E6'], [1, '#B8A47F']]) + '</defs>';
    if (s === 'write') { const B = gid('beam'); o += `<defs>${linear(B, [[0, '#FFE27A', .7], [1, '#FFE27A', 0]], [0, 0, 1, 0])}</defs><path d="M82 44 L124 26 L124 92 L82 76 Z" fill="url(#${B})"/>`; }
    o += floorShadow(60, 101, 28);
    o += stroke('M40 34 Q60 10 80 34', `url(#${T})`, 7.5);
    o += `<circle cx="60" cy="62" r="34" fill="url(#${H})"/>`;
    o += shine(44, 40, 11, 5, -32, .55, 1.2);
    o += `<circle cx="60" cy="60" r="26" fill="url(#${R})"/><circle cx="60" cy="60" r="25" fill="none" stroke="#9FB0DA" stroke-opacity=".45" stroke-width="1"/>`;
    o += lensEye(60, 60, 20.5, s, { off: s === 'think' });
    if (s === 'write') o += slats(60, 60, 20.5);
    o += stroke(s === 'think' ? 'M55 90 L65 90' : 'M53 88 Q60 93 67 88', '#26325A', 3.4);
    return o;
  },
  // З2. Фонарь в три четверти: видно, что это барабан на подставке, линза повёрнута к зрителю.
  aldis34: s => {
    const Bd = gid('body'), F = gid('face'), Y = gid('yoke'), R = gid('rim');
    let o = navyBg();
    o += '<defs>' + linear(Bd, [[0, '#FFF7E8'], [.45, '#E6D5B5'], [1, '#9C8762']]) + radial(F, [[0, '#FFFBF2'], [1, '#D9C7A5']], { fx: .3, fy: .25 }) + linear(Y, [[0, '#4A5786'], [1, '#141B36']], [0, 0, 1, 0]) + linear(R, [[0, '#4C5C92'], [1, '#0B1128']]) + '</defs>';
    if (s === 'write') { const B = gid('beam'); o += `<defs>${linear(B, [[0, '#FFE27A', 0], [1, '#FFE27A', .65]], [1, 0, 0, 0])}</defs><path d="M36 40 L-4 22 L-4 100 L36 84 Z" fill="url(#${B})"/>`; }
    o += floorShadow(62, 106, 30);
    o += `<ellipse cx="62" cy="104" rx="24" ry="5" fill="#0E1430"/><rect x="58" y="88" width="8" height="16" fill="url(#${Y})"/>`;
    o += stroke('M38 62 Q36 92 62 92 Q90 92 88 62', `url(#${Y})`, 5);
    o += `<path d="M50 28 L78 32 A16 30 0 0 1 78 92 L50 96 Z" fill="url(#${Bd})"/><ellipse cx="78" cy="62" rx="16" ry="30" fill="#A8946E"/>`;
    o += stroke('M54 28 Q66 8 80 32', '#E9DCC2', 6) + stroke('M54 28 Q66 8 80 32', '#FFF8EA', 2.2, 'opacity=".7"');
    o += `<ellipse cx="50" cy="62" rx="24" ry="34" fill="url(#${F})"/>`;
    o += `<ellipse cx="50" cy="61" rx="19" ry="27" fill="url(#${R})"/>`;
    o += `<g transform="translate(50 61) scale(.74 1) translate(-50 -61)">${lensEye(50, 61, 22, s, { off: s === 'think' })}${s === 'write' ? slats(50, 61, 22) : ''}</g>`;
    o += shine(38, 36, 7, 3.5, -40, .6, .9);
    o += stroke(s === 'think' ? 'M46 92 L54 92' : 'M45 91 Q50 95 55 91', '#26325A', 3);
    return o;
  },
  // З3. Пластилиновый фонарик: пухлое мягкое тело, ручки-лапки, румянец. Матовый, как игрушка.
  aldisClay: s => {
    const B = gid('bg'), Bd = gid('body'), Rm = gid('rim');
    let o = `<defs>${radial(B, [[0, '#FFD2B3'], [1, '#F29A6E']], { cy: .35, r: .75 })}${radial(Bd, [[0, '#5468A8'], [.7, '#2F3E73'], [1, '#1E2850']], { fx: .3, fy: .25, r: .6 })}${radial(Rm, [[0, '#FFFDF6'], [1, '#E3D4B6']], { fx: .35, fy: .3 })}</defs><rect width="120" height="120" fill="url(#${B})"/>`;
    o += floorShadow(60, 104, 30, .25);
    const arm = s === 'write' ? -10 : 0;
    o += `<ellipse cx="24" cy="${74 + arm}" rx="7" ry="10" fill="url(#${Bd})" transform="rotate(${s === 'write' ? 30 : 15} 24 74)"/><ellipse cx="96" cy="74" rx="7" ry="10" fill="url(#${Bd})" transform="rotate(-15 96 74)"/>`;
    o += stroke('M46 30 Q60 14 74 30', '#2F3E73', 7) + stroke('M47 28 Q60 15 73 28', '#5A6FB0', 2.4, 'opacity=".6"');
    o += `<rect x="26" y="28" width="68" height="74" rx="32" fill="url(#${Bd})"/>`;
    o += shine(42, 40, 12, 6, -30, .22, 2.5);
    o += `<circle cx="60" cy="58" r="22" fill="url(#${Rm})"/>`;
    o += lensEye(60, 58, 16.5, s, { off: s === 'think' });
    if (s === 'write') o += slats(60, 58, 16.5);
    o += `<ellipse cx="38" cy="82" rx="5.5" ry="3" fill="#FF8FA3" opacity=".7" ${blur(1)}/><ellipse cx="82" cy="82" rx="5.5" ry="3" fill="#FF8FA3" opacity=".7" ${blur(1)}/>`;
    o += s === 'write' ? `<ellipse cx="60" cy="88" rx="4" ry="3.4" fill="#141B36"/>` : stroke(s === 'think' ? 'M56 87 L64 87' : 'M54 86 Q60 91 66 86', '#F7EEDC', 3.2);
    return o;
  },
  // М1. Стеклянная лампочка: прозрачное стекло с бликами, металлический цоколь, спираль-улыбка светится.
  bulbGlass: s => {
    const B = gid('bg'), Gl = gid('glass'), Ha = gid('halo');
    const lit = s !== 'think', hot = s === 'write';
    let o = `<defs>${radial(B, [[0, '#5FE0D3'], [1, '#13857C']], { cy: .35, r: .75 })}${radial(Gl, lit ? [[0, '#FFFDF0'], [.55, '#FFF0A8', .97], [1, '#F0CE5C', .95]] : [[0, '#FFFFFF', .75], [.7, '#D7EFEC', .55], [1, '#A9D3CF', .7]], { cy: .6, fx: .5, fy: .62, r: .6 })}${radial(Ha, [[0, '#FFF6B8', .9], [1, '#FFF6B8', 0]])}</defs><rect width="120" height="120" fill="url(#${B})"/>`;
    if (lit) o += `<circle cx="60" cy="52" r="${hot ? 54 : 44}" fill="url(#${Ha})"/>`;
    o += floorShadow(60, 112, 18, .3);
    o += `<path d="${BULB}" fill="url(#${Gl})"/><path d="${BULB}" fill="none" stroke="${lit ? '#D9B443' : '#8FBFBA'}" stroke-width="1.4" opacity=".7"/>`;
    o += stroke('M53 84 L53 68 M67 84 L67 68', lit ? '#B89B5C' : '#8AA6A3', 1.8);
    const fil = s === 'think' ? 'M53 66 L67 66' : 'M53 64 Q56 70 58.5 64 Q60 61 61.5 64 Q64 70 67 64';
    o += stroke(fil, lit ? '#FF7A2E' : '#7D8E8C', 3, lit ? `style="filter:drop-shadow(0 0 ${hot ? 6 : 3.5}px rgba(255,120,40,1))"` : '');
    const [px, py] = { idle: [0, 0], read: [0, 3], think: [3, -3], write: [0, 0] }[s];
    [51, 69].forEach(x => o += hot ? stroke(`M${x - 4.5} 47 Q${x} 41.5 ${x + 4.5} 47`, '#2A2233', 3.2) : dot(x + px, 46 + py, 4.6, '#2A2233') + dot(x + px + 1.7, 44 + py, 1.6, '#fff'));
    o += `<path d="M41 40 Q42 26 55 21" fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round" opacity=".75" ${blur(.6)}/>` + dot(76, 34, 2.4, '#fff', `opacity=".8" ${blur(.4)}`);
    o += screwBase(84);
    return o;
  },
  // М2. Пластилиновая лампочка: матовая игрушка, большие глаза с бликом, румянец, коралловый цоколь, лапки.
  bulbClay: s => {
    const B = gid('bg'), Bd = gid('body');
    const lit = s !== 'think', hot = s === 'write';
    let o = `<defs>${radial(B, [[0, '#CBBDFF'], [1, '#8B74E6']], { cy: .35, r: .75 })}${radial(Bd, lit ? [[0, '#FFF7CC'], [.6, '#FFE27A'], [1, '#E8B83A']] : [[0, '#F3F0FF'], [.6, '#D9D3F0'], [1, '#AFA6D3']], { fx: .32, fy: .25, r: .6 })}</defs><rect width="120" height="120" fill="url(#${B})"/>`;
    if (hot) o += `<circle cx="60" cy="50" r="46" fill="#FFF2A8" opacity=".35" ${blur(4)}/>`;
    o += floorShadow(60, 112, 20, .22);
    const wave = hot ? -12 : 0;
    o += `<ellipse cx="33" cy="${70 + wave}" rx="5.5" ry="8.5" fill="url(#${Bd})" transform="rotate(${hot ? 35 : 20} 33 70)"/><ellipse cx="87" cy="70" rx="5.5" ry="8.5" fill="url(#${Bd})" transform="rotate(-20 87 70)"/>`;
    o += `<path d="${BULB}" fill="url(#${Bd})"/>`;
    o += shine(46, 32, 9, 5, -35, .45, 2);
    const [px, py] = { idle: [0, 0], read: [0, 3], think: [3, -3], write: [0, 0] }[s];
    [50, 70].forEach(x => o += hot ? stroke(`M${x - 5} 50 Q${x} 44 ${x + 5} 50`, '#3B2A4F', 3.4) : `<ellipse cx="${x + px}" cy="${49 + py}" rx="5.8" ry="6.6" fill="#3B2A4F"/>` + dot(x + px + 2, 46.5 + py, 2.1, '#fff') + dot(x + px - 1.6, 52 + py, .9, '#fff', 'opacity=".8"'));
    o += `<ellipse cx="42" cy="60" rx="5" ry="2.8" fill="#FF8FA3" opacity=".75" ${blur(1)}/><ellipse cx="78" cy="60" rx="5" ry="2.8" fill="#FF8FA3" opacity=".75" ${blur(1)}/>`;
    o += hot ? `<ellipse cx="60" cy="63" rx="4.5" ry="4" fill="#3B2A4F"/><ellipse cx="60" cy="65" rx="2.6" ry="1.6" fill="#FF8FA3"/>` : stroke(s === 'think' ? 'M56 62 L64 62' : 'M55 60 Q60 65 65 60', '#3B2A4F', 3);
    o += screwBase(84, 'coral');
    return o;
  },
  // М3. Лампа-циклоп: смесь З и М — стеклянная лампочка, а внутри вместо спирали один глаз-линза фонаря.
  bulbEye: s => {
    const Gl = gid('glass'), Ha = gid('halo');
    const lit = s !== 'think';
    let o = navyBg() + `<defs>${radial(Gl, [[0, '#FFFFFF', .28], [.75, '#CFE0FF', .18], [1, '#9FB6E8', .4]], { fx: .4, fy: .35, r: .6 })}${radial(Ha, [[0, '#FFE27A', .55], [1, '#FFE27A', 0]])}</defs>`;
    if (lit) o += `<circle cx="60" cy="48" r="${s === 'write' ? 50 : 38}" fill="url(#${Ha})"/>`;
    o += floorShadow(60, 112, 18, .4);
    o += stroke('M55 84 L56 66 M65 84 L64 66', '#8E9AB8', 1.8);
    o += lensEye(60, 50, 17, s, { off: !lit });
    if (s === 'write') o += slats(60, 50, 17);
    o += `<path d="${BULB}" fill="url(#${Gl})"/><path d="${BULB}" fill="none" stroke="#C9D6F5" stroke-width="1.6" opacity=".55"/>`;
    o += stroke(s === 'think' ? 'M56 74 L64 74' : 'M54 72 Q60 77 66 72', lit ? '#FFB347' : '#7E89A8', 2.6, lit ? `style="filter:drop-shadow(0 0 3px rgba(255,170,60,.95))"` : '');
    o += `<path d="M41 40 Q42 26 55 21" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" opacity=".6" ${blur(.6)}/>` + dot(76, 33, 2.2, '#fff', 'opacity=".75"');
    o += screwBase(84, 'navy');
    return o;
  },
});
