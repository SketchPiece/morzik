// Второй ряд: новые миры вне темы Волны (без бакелита и янтаря).
const N = { ink:'#1D1A2F', white:'#FFFFFF' };
const outline = (w = 4) => `stroke="${N.ink}" stroke-width="${w}" stroke-linejoin="round"`;

// Пиксельный: сетка 12×12, клетка 10.
function pixels(rows, pal) {
  let o = '';
  rows.forEach((r, y) => [...r].forEach((ch, x) => { if (pal[ch]) o += `<rect x="${x * 10}" y="${y * 10}" width="10.4" height="10.4" fill="${pal[ch]}"/>`; }));
  return o;
}

Object.assign(CHARS, {
  // Ж. Монстрик-наклейка: зелёный одноглазый, как стикер в Telegram, с обводкой и рожками.
  sticker: s => {
    let o = bg('#F7C6CF');
    o += `<path d="M38 36 L42 22 L50 32 M82 36 L78 22 L70 32" fill="#7BD389" ${outline(3.5)}/>`;
    o += `<path d="M26 122 L26 64 A34 34 0 0 1 94 64 L94 122 Z" fill="#7BD389" ${outline()}/>`;
    if (s === 'write') o += `<path d="M42 58 Q60 44 78 58" fill="none" stroke="${N.ink}" stroke-width="5" stroke-linecap="round"/>`;
    else {
      o += `<circle cx="60" cy="58" r="17" fill="${N.white}" ${outline(3.5)}/>`;
      const [px, py] = { idle: [0, 1], read: [-3, 5], think: [5, -5] }[s];
      o += dot(60 + px, 58 + py, 8, N.ink) + dot(63 + px, 55 + py, 2.6, N.white);
    }
    if (s === 'write') o += `<ellipse cx="60" cy="86" rx="8" ry="6.5" fill="${N.ink}"/><ellipse cx="60" cy="89" rx="4.5" ry="2.6" fill="#F27C8C"/>`;
    else if (s === 'think') o += stroke('M53 87 Q57 84 60 87 Q63 90 67 87', N.ink, 3.5);
    else o += stroke('M50 84 Q60 92 70 84', N.ink, 3.5) + `<path d="M55 86.4 L57 91 L59 87.4 Z" fill="${N.white}" stroke="${N.ink}" stroke-width="1.5" stroke-linejoin="round"/>`;
    return o;
  },
  // З. Сигнальный фонарь: корабельный прожектор, которым мигают азбукой Морзе. Линза — глаз, шторки — веки.
  aldis: s => {
    let o = bg('#1E2A4A');
    [[18, 20], [98, 26], [104, 86], [14, 92], [30, 104]].forEach(([x, y]) => o += dot(x, y, 1.3, '#F2E8D5', 'opacity=".6"'));
    if (s === 'write') o += `<path d="M86 50 L124 34 L124 82 L86 70 Z" fill="#FFD54A" opacity=".35"/>`;
    o += stroke('M40 30 Q60 12 80 30', '#F2E8D5', 6);
    o += dot(60, 62, 34, '#F2E8D5');
    o += dot(60, 60, 25, '#1E2A4A');
    const lit = s !== 'think';
    o += dot(60, 60, 20, lit ? '#FFD54A' : '#6B7390', lit ? `style="filter:drop-shadow(0 0 ${s === 'write' ? 10 : 5}px rgba(255,213,74,.9))"` : '');
    if (s === 'write') [50, 60, 70].forEach(y => o += `<rect x="40" y="${y - 2.5}" width="40" height="5" rx="2" fill="#1E2A4A"/>`);
    else {
      const [px, py, r] = { idle: [0, 0, 8], read: [0, 5, 9], think: [5, -5, 7] }[s];
      o += dot(60 + px, 60 + py, r, '#1E2A4A') + dot(63.5 + px, 56.5 + py, 2.8, '#FFF8DC');
    }
    o += stroke(s === 'think' ? 'M55 89 L65 89' : 'M53 87 Q60 92 67 87', '#1E2A4A', 3.4);
    return o;
  },
  // И. Светлячок: ночное небо, у Морзика светится хвостик. Пишет — мигает им точки и тире.
  firefly: s => {
    let o = bg('#2B1F4D');
    [[16, 22], [96, 16], [108, 54], [20, 70], [100, 104], [40, 108]].forEach(([x, y]) => o += dot(x, y, 1.3, N.white, 'opacity=".55"'));
    const tail = s === 'think' ? '#6F8A4A' : '#C6FF6A', tg = s === 'think' ? '' : `style="filter:drop-shadow(0 0 ${s === 'write' ? 12 : 7}px rgba(198,255,106,.95))"`;
    o += `<ellipse cx="44" cy="54" rx="16" ry="10" fill="${N.white}" opacity=".35" transform="rotate(-25 44 54)"/><ellipse cx="78" cy="50" rx="16" ry="10" fill="${N.white}" opacity=".35" transform="rotate(25 78 50)"/>`;
    o += `<ellipse cx="62" cy="86" rx="15" ry="14" fill="${tail}" ${tg}/>`;
    o += stroke('M52 44 Q46 28 40 24 M68 44 Q74 28 80 24', '#F7E9C4', 3) + dot(40, 24, 3.6, '#F7E9C4') + dot(80, 24, 3.6, '#F7E9C4');
    o += dot(60, 60, 21, '#F7E9C4');
    const [px, py] = { idle: [0, 0], read: [0, 3], think: [3, -4], write: [0, 0] }[s];
    [51, 69].forEach(x => {
      if (s === 'write') o += stroke(`M${x - 5} 59 Q${x} 53 ${x + 5} 59`, N.ink, 3.4);
      else o += dot(x + px, 58 + py, 6, N.ink) + dot(x + px + 2.2, 55.5 + py, 2, N.white);
    });
    o += `<ellipse cx="46" cy="67" rx="4" ry="2.4" fill="#F49AB0" opacity=".8"/><ellipse cx="74" cy="67" rx="4" ry="2.4" fill="#F49AB0" opacity=".8"/>`;
    o += s === 'think' ? stroke('M57 70 L63 70', N.ink, 2.8) : stroke('M56 68 Q60 72 64 68', N.ink, 2.8);
    if (s === 'write') o += morse('.-.', 98, 92, '#C6FF6A', { unit: 5, w: 3.5, r: 2.3, extra: 'style="filter:drop-shadow(0 0 4px rgba(198,255,106,.9))"' });
    return o;
  },
  // К. Пиксельный: 8-бит, тёмный человечек с одним жёлтым глазом-лампой и антенной.
  pixel: s => {
    const eye = { idle: ['yyyy', 'yooy', 'yooy', 'yyyy'], read: ['yyyy', 'yyyy', 'ooyy', 'ooyy'], think: ['yyoo', 'yyoo', 'yyyy', 'yyyy'], write: ['####', '####', 'yyyy', '####'] }[s];
    const mouth = { idle: '##mm##', read: '##mm##', think: '###m##', write: '#mmmm#' }[s];
    const rows = [
      s === 'think' ? '.....y......' : '.....a......',
      '.....#......',
      '...######...',
      '..########..',
      ...eye.map(e => `.###${e}###.`),
      '.##########.',
      `.##${mouth}##.`,
      '.##########.',
      '..#.#..#.#..',
    ];
    let o = bg('#4C6FFF');
    for (let i = 0; i < 12; i++) o += `<line x1="${i * 10}" y1="0" x2="${i * 10}" y2="120" stroke="#fff" stroke-opacity=".07"/><line x1="0" y1="${i * 10}" x2="120" y2="${i * 10}" stroke="#fff" stroke-opacity=".07"/>`;
    o += `<g>${pixels(rows, { '#': '#1B1F3B', o: '#1B1F3B', y: '#FFD54A', m: '#F4F1FF', a: '#FF6B8B' })}</g>`;
    if (s === 'write') o += `<g>${pixels(['............', '..........m.', '.........m.m', '..........m.'], { m: '#FFD54A' })}</g>`;
    return o;
  },
  // Л. Конвертик: письмо с сургучной печатью-лицом. Пишет — клапан открыт и вылетают точки-тире.
  envelope: s => {
    let o = bg('#FF8A66');
    const open = s === 'write';
    if (open) o += `<path d="M20 44 L60 14 L100 44 Z" fill="#F3E3CB" ${outline(3)}/>` + morse('.-.', 60, 30, '#FF8A66', { unit: 5, w: 3.5, r: 2.3 });
    o += `<rect x="20" y="40" width="80" height="54" rx="7" fill="#FFF4E6" ${outline(3.5)}/>`;
    o += `<path d="M22 92 L52 66 M98 92 L68 66" fill="none" stroke="#E2CDB0" stroke-width="3" stroke-linecap="round"/>`;
    if (!open) o += `<path d="M21 42 L60 72 L99 42" fill="#FFF4E6" ${outline(3.5)}/>`;
    o += dot(60, 70, 15, '#D6443A') + `<circle cx="60" cy="70" r="11.5" fill="none" stroke="#B8322A" stroke-width="1.6"/>`;
    const [px, py] = { idle: [0, 0], read: [0, 2], think: [2.5, -3], write: [0, 0] }[s];
    o += dot(55 + px, 68 + py, 2.4, '#FFF4E6') + dot(65 + px, 68 + py, 2.4, '#FFF4E6');
    o += s === 'write' ? `<ellipse cx="60" cy="75" rx="2.6" ry="2.2" fill="#FFF4E6"/>` : s === 'think' ? stroke('M57.5 75 L62.5 75', '#FFF4E6', 2) : stroke('M56.5 74 Q60 77 63.5 74', '#FFF4E6', 2);
    return o;
  },
  // М. Лампочка: Эдисонова лампа, спираль внутри — улыбка. Думает — гаснет, пишет — вспыхивает.
  bulb: s => {
    let o = bg('#2EC4B6');
    const lit = s !== 'think', hot = s === 'write';
    if (lit) o += `<circle cx="60" cy="50" r="${hot ? 46 : 38}" fill="#FFF3B0" opacity="${hot ? .45 : .28}"/>`;
    o += `<path d="M60 18 A30 30 0 0 1 80 70 Q74 76 74 84 L46 84 Q46 76 40 70 A30 30 0 0 1 60 18 Z" fill="${lit ? '#FFF3B0' : '#DDF2EF'}" ${outline(3.5)}/>`;
    [86, 93].forEach(y => o += `<rect x="45" y="${y}" width="30" height="6" rx="3" fill="#8A8F98" ${outline(2.5)}/>`);
    o += `<path d="M53 100 L67 100 L63 106 L57 106 Z" fill="${N.ink}"/>`;
    const [px, py] = { idle: [0, 0], read: [0, 3], think: [3, -3], write: [0, 0] }[s];
    [51, 69].forEach(x => o += hot ? stroke(`M${x - 4} 47 Q${x} 42 ${x + 4} 47`, N.ink, 3.2) : dot(x + px, 46 + py, 4.2, N.ink) + dot(x + px + 1.6, 44.2 + py, 1.4, N.white));
    o += stroke('M52 84 L52 70 M68 84 L68 70', '#B9A77A', 2);
    const fil = s === 'think' ? 'M52 64 L68 64' : 'M52 62 Q55 68 58 62 Q60 59 62 62 Q65 68 68 62';
    o += stroke(fil, lit ? '#FF8C42' : '#8A8F98', 3.2, lit ? `style="filter:drop-shadow(0 0 ${hot ? 5 : 3}px rgba(255,140,66,.95))"` : '');
    return o;
  },
});
