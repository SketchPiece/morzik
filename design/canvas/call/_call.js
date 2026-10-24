// Экран звонка для досок: <body data-call="listening" data-style="cat" data-text="…" data-live>.
// data-call — состояние модели (или dizzy), data-style — чем оно показано (cat, whiskers, waves).
(() => {
  const d = document.body.dataset, q = new URLSearchParams(location.search).get('t');
  const phone = '<svg viewBox="0 0 24 24"><path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z"/></svg>';
  document.body.insertAdjacentHTML('afterbegin', `<div class="app">
    <div class="status"><span>10:42</span><span class="r">●●● <i></i></span></div>
    <div class="app-head"><div class="pill">✕ Закрыть</div><div class="pill">⋯</div></div>
    <canvas class="waves" id="w" width="780" height="860"></canvas>
    <canvas id="c" class="cat" style="top:150px;width:330px;height:330px"></canvas>
    <div class="txt"><h1>Морзик</h1><p class="${d.mono != null ? 'mono' : ''}">${d.text || ''}</p></div>
    <div class="callbtn${d.live != null ? ' live' : ''}">${phone}</div><div class="home"></div></div>`);

  // Кольца вокруг головы (callStyle 'waves'): гудки расходятся, голос пользователя сходится к голове, голос Морзика расходится;
  // думает — вокруг медленно плывёт кольцо из точек и тире.
  const x = document.getElementById('w').getContext('2d'), CX = 390, CY = 2 * (150 + 165 - 100), R0 = 300;
  const ring = (r, a, lw = 4) => { if (a <= .01) return; x.strokeStyle = `rgba(255,180,58,${a})`; x.lineWidth = lw; x.beginPath(); x.arc(CX, CY, r, 0, Math.PI * 2); x.stroke(); };
  const frac = v => v - Math.floor(v);
  function waves(t, L) {
    x.clearRect(0, 0, 780, 860); x.shadowColor = 'rgba(255,170,50,.8)'; x.shadowBlur = 18;
    const s = d.call;
    if (s === 'ringing') [0, .42].forEach(o => { const p = ((t % 2) - o) / 1.3; if (p > 0 && p < 1) ring(R0 + p * 120, .8 * (1 - p), 6); });
    if (s === 'listening' || s === 'speaking') for (let n = 0; n < 3; n++) {
      const p = frac(n / 3 + (s === 'speaking' ? 1 : -1) * t * .55);
      ring(R0 + 8 + p * 120, Math.min(1, L * 1.1) * Math.sin(Math.PI * p), 4 + 6 * L);
    }
    if (s === 'thinking') {
      x.save(); x.translate(CX, CY); x.rotate(t * Math.PI / 4); x.lineCap = 'round'; x.strokeStyle = 'rgba(255,180,58,.85)'; x.lineWidth = 9;
      const code = '.-..-   .-..-   .-..-   '; let a = 0; const step = Math.PI * 2 / 48;
      [...code].forEach(ch => { const len = ch === '.' ? .01 : ch === '-' ? 2.2 : 0;
        if (ch !== ' ') { x.beginPath(); x.arc(0, 0, R0 + 24, a, a + step * len); x.stroke(); }
        a += step * (len + 1.4); });
      x.restore();
    }
  }
  const call = d.call === 'dizzy' ? null : d.call;
  morzikCat2(document.getElementById('c'), { size: 330, headOnly: true, transparent: true, dizzy: !call, call, callStyle: d.style || 'cat',
    onFrame: d.style === 'waves' ? waves : null, t: q == null ? null : +q });
})();
