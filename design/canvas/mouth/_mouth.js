// Морзик говорит (фразы-макеты) с ртом из <body data-mouth="volume|letters|fangs">.
(() => {
  const d = document.body.dataset, q = new URLSearchParams(location.search).get('t');
  const c = document.createElement('canvas'); document.body.append(c);
  morzikCat2(c, { size: 840, headOnly: true, transparent: true, call: 'speaking', callStyle: 'both', soul: { focus: true, lids: true }, mouth: d.mouth, t: q == null ? null : +q });
})();
