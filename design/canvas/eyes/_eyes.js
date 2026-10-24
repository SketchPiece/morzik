// Крупный план головы в звонке: <body data-call="speaking" data-soul="focus,lids,iris">.
// На «говорит» раз в 5 с проигрывается эмоция из реплики (хитро, вопрос, смех, восторг), чтобы видеть глаза в них.
(() => {
  const d = document.body.dataset, q = new URLSearchParams(location.search).get('t');
  const soul = Object.fromEntries((d.soul || '').split(',').filter(Boolean).map(k => [k, true]));
  const c = document.createElement('canvas'); document.body.append(c);
  const head = morzikCat2(c, { size: 600, headOnly: true, transparent: true, call: d.call, callStyle: 'both', soul, t: q == null ? null : +q });
  if (head && d.call === 'speaking') { const moods = ['smug', 'ask', 'laugh', 'excited']; let i = 0; setInterval(() => head.emote(moods[i++ % 4], 1.8), 5000); }
})();
