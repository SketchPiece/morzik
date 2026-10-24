// Кот·2, доработка: чёрный Морзик с янтарными глазами, усы — по одному знаку морзянки, матовые кремовые наушники.
// Голова — одна гладкая форма вращения, расширенная книзу (щёки без отдельных шаров). Собирается в _cat2.bundle.js.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const V = (x, y, z) => new THREE.Vector3(x, y, z);
export function morzikCat2(canvas, { size = 420, t: frozen = null, mirrors = [], manual = false, shiftY = 0, tailSide = 1, twitchEar = 1, paws = 'none', headOnly = false, dizzy = false, transparent = false, stars = false, zoom = 1, cross = 1, call = null, callStyle = 'cat', level = null, onFrame = null, soul = {} } = {}) {
  // headOnly — только голова крупным планом (без тела, лапок и хвоста); dizzy — глаза-спиральки крутятся,
  // голова покачивается по кругу; stars — над головой кружат янтарные звёздочки; transparent — без фона.
  // call — состояние звонка вместо надписи: 'idle' (до звонка), 'ringing', 'listening', 'thinking', 'speaking'.
  // callStyle — чем оно показано: 'cat' — мимикой (уши, взгляд, наклон головы), 'whiskers' — бегущим светом по усам, 'both' — и тем и другим,
  // 'waves' — кольцами вокруг головы (их рисует страница в onFrame(t, level), модель только жива). Рот говорит во всех.
  // level(T) — голос: число 0…1 или { v, wide } (wide 0…1: «о» → «и»); в звонке из анализатора звука, без неё — фразы-макеты.
  // T — время с начала в секундах, не зацикленное: в звонке анимация не повторяется.
  // soul — живость глаз в звонке: focus (смотрит на тебя: зрачки сведены, глаза ведут голову, моргает на переводе взгляда),
  // lids (веки: обрезают радужку сверху и снизу, расслабленный взгляд, улыбка глазами, прищур), iris (радужка с волокнами и ободком).
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true, alpha: transparent });
  renderer.setPixelRatio(2); renderer.setSize(size, size, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  const scene = new THREE.Scene();
  const tex = (w, h, paint) => { const c = document.createElement('canvas'); c.width = w; c.height = h; paint(c.getContext('2d'), w, h); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; };
  const radialTex = stops => tex(256, 256, (x, w) => { const g = x.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2); stops.forEach(([o, c]) => g.addColorStop(o, c)); x.fillStyle = g; x.fillRect(0, 0, w, w); });
  if (!transparent) scene.background = tex(512, 512, (x) => { const g = x.createRadialGradient(256, 200, 0, 256, 220, 360); g.addColorStop(0, '#34477C'); g.addColorStop(1, '#10172C'); x.fillStyle = g; x.fillRect(0, 0, 512, 512); });
  const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromScene(new RoomEnvironment(), .04).texture; scene.environmentIntensity = .45;
  const camera = new THREE.PerspectiveCamera(30, 1, .1, 50); camera.position.set(0, .2 + shiftY, 6.7 / zoom); camera.lookAt(0, -.08 + shiftY, 0); // shiftY > 0 опускает кота в кадре (для авы), zoom < 1 отодвигает камеру; cross — насколько косят глаза (1 — как на аве)
  if (headOnly) { camera.position.set(0, .45, 6.2); camera.lookAt(0, .26, 0); }
  scene.add(new THREE.HemisphereLight(0xe6ecff, 0x1a2140, .8));
  const key = new THREE.DirectionalLight(0xfff2e6, 1.8); key.position.set(-3, 4, 5); scene.add(key);
  const rimR = new THREE.DirectionalLight(0x9fb8ff, 1.8); rimR.position.set(3.5, 2, -3); scene.add(rimR);
  const rimL = new THREE.DirectionalLight(0xb7c6ff, 1.1); rimL.position.set(-3.5, 1.5, -3); scene.add(rimL);

  const furM = new THREE.MeshStandardMaterial({ color: 0x2F2C3A, roughness: .92, metalness: 0 }); // плотная матовая шерсть, без отлива
  const matte = c => new THREE.MeshStandardMaterial({ color: c, roughness: .95, metalness: 0 });
  // На прозрачном фоне полупрозрачное свечение не попадает в альфу кадра (усы пропадали бы в видео): там оно непрозрачное,
  // а пульсирует яркостью цвета, а не прозрачностью (pulse ниже).
  const glow = (c, op = 1) => new THREE.MeshBasicMaterial({ color: c, toneMapped: false, transparent: !transparent, opacity: transparent ? 1 : op });
  const pulse = (m, k) => { if (!transparent) { m.opacity = k; return; } (m.userData.base ??= m.color.clone()); m.color.copy(m.userData.base).multiplyScalar(.75 + .25 * k); };
  const sprite = (col, sx, sy, pos, parent) => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: radialTex([[0, col], [1, 'rgba(0,0,0,0)']]), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false })); s.scale.set(sx, sy, 1); s.position.copy(pos); parent.add(s); return s; };
  const sph = (r, m, p, s, parent) => { const o = new THREE.Mesh(new THREE.SphereGeometry(r, 48, 32), m); o.position.copy(p); o.scale.set(...s); parent.add(o); return o; };
  const tube = (pts, r, m, parent) => { const o = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 48, r, 10), m); parent.add(o); return o; };

  const cat = new THREE.Group(); scene.add(cat);
  // Тело, лапки, хвост.
  const body = sph(.95, furM, V(0, -1.55, -.2), [1, .88, .82], cat);
  [-1, 1].forEach(sx => sph(.24, furM, V(sx * .36, -2.18, .5), [1, .7, 1.2], cat));
  // tailSide = -1 сажает хвост с другой стороны (ава отзеркалена при сборке, а хвост должен остаться справа), 0 — без хвоста.
  const tail = new THREE.Group(); tail.position.set(.7 * tailSide, -1.85, -.4); cat.add(tail); tail.visible = tailSide !== 0;
  // Хвост с круглым кончиком, загнутым внутрь.
  const tailPts = [V(-.2, -.05, -.05), V(.5, .15, .05), V(.74, .72, .2), V(.62, 1.18, .34), V(.42, 1.32, .4)].map(p => p.setX(p.x * tailSide));
  tube(tailPts, .12, furM, tail);
  tailPts.slice(-1).forEach(p => sph(.12, furM, p, [1, 1, 1], tail));
  if (headOnly) cat.children.slice().forEach(o => cat.remove(o));

  // Голова: профиль вращения — округлый лоб и широкие щёки внизу; по глубине сплюснута.
  const head = new THREE.Group(); head.position.set(0, .3, 0); cat.add(head);
  const spline = new THREE.SplineCurve([[.001, .92], [.55, .85], [.92, .6], [1.12, .22], [1.2, -.13], [1.12, -.44], [.84, -.67], [.44, -.79], [.001, -.81]].map(([x, y]) => new THREE.Vector2(x, y)));
  const prof = spline.getPoints(60);
  const DEPTH = .86;
  // Голову видно изнутри (BackSide): свет на внутренней стенке даёт мягкое свечение в центре и тёмные края.
  // Сразу за ней — невидимая внешняя оболочка, пишет только глубину: всё, что внутри головы (низ ушей), отсекается.
  const skullGeo = new THREE.LatheGeometry([...prof].reverse(), 96);
  const skull = new THREE.Mesh(skullGeo, furM.clone()); skull.material.side = THREE.BackSide; skull.scale.z = DEPTH; skull.renderOrder = -2; head.add(skull);
  const skullMask = new THREE.Mesh(skullGeo, new THREE.MeshBasicMaterial({ colorWrite: false })); skullMask.scale.z = DEPTH; skullMask.renderOrder = -1; head.add(skullMask);
  const rAt = y => { for (let i = 1; i < prof.length; i++) { const a = prof[i - 1], b = prof[i]; if ((a.y - y) * (b.y - y) <= 0) return a.x + (b.x - a.x) * ((y - a.y) / (b.y - a.y || 1)); } return 0; };
  const surf = (x, y) => DEPTH * Math.sqrt(Math.max(0, rAt(y) ** 2 - x * x));

  // Уши: объёмный сплюснутый конус со скруглённой верхушкой, расширяется только книзу;
  // основание глубоко в голове, поэтому видна только часть, вырастающая из неё, без кромок.
  const lathe = pts => new THREE.LatheGeometry(new THREE.SplineCurve(pts.map(([x, y]) => new THREE.Vector2(x, y))).getPoints(40).reverse(), 64);
  const earGeo = lathe([[.001, .66], [.05, .64], [.1, .57], [.2, .36], [.3, .1], [.38, -.18], [.42, -.45], [.001, -.5]]);
  const innerGeo = lathe([[.001, .5], [.04, .48], [.08, .41], [.15, .22], [.21, 0], [.25, -.3], [.001, -.34]]);
  const ears = [-1, 1].map(sx => {
    const g = new THREE.Group(); g.position.set(sx * .52, .66, -.04); g.rotation.set(-.12, 0, -sx * .36); g.scale.setScalar(1.18); head.add(g);
    const o = new THREE.Mesh(earGeo, furM); o.scale.z = .5; g.add(o);
    const i = new THREE.Mesh(innerGeo, new THREE.MeshStandardMaterial({ color: 0x4A3656, roughness: .85 })); i.scale.z = .3; i.position.set(0, .04, .1); g.add(i);
    return g;
  });

  // Мордочка: нос и рот «ω».
  sph(.085, new THREE.MeshPhysicalMaterial({ color: 0x6A4862, roughness: .4, clearcoat: .5 }), V(0, -.18, surf(0, -.18) + .015), [1.35, .85, .75], head);
  const omega = (z => [V(-.17, -.32, z - .03), V(-.085, -.38, z), V(0, -.3, z + .01), V(.085, -.38, z), V(.17, -.32, z - .03)])(surf(0, -.3) + .06);
  tube(omega, .016, new THREE.MeshStandardMaterial({ color: 0x0c0b10, roughness: .6 }), head);

  // Открытый рот (звонок): вырез прямо под «ω» — верхний край идёт по линии «ω» (прячется за ней), нижний — дугой вниз,
  // уголки сомкнуты; на дне язык. Лежит на поверхности морды, форма пересчитывается каждый кадр (mouthShape).
  const omegaPts = new THREE.CatmullRomCurve3(omega).getPoints(160);
  const omegaY = x => { for (let i = 1; i < omegaPts.length; i++) { const a = omegaPts[i - 1], b = omegaPts[i]; if ((a.x - x) * (b.x - x) <= 0) return a.y + (b.y - a.y) * ((x - a.x) / (b.x - a.x || 1)); } return -.32; };
  // Сетка MN × MR: вершины лежат на поверхности морды и посередине, иначе высокий рот режется выпуклой мордой.
  const MN = 32, MR = 8;
  const flap = mat => {
    const g = new THREE.BufferGeometry(), idx = [];
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array((MN + 1) * (MR + 1) * 3), 3));
    for (let i = 0; i < MN; i++) for (let j = 0; j < MR; j++) { const a = i * (MR + 1) + j, b = a + MR + 1; idx.push(a, a + 1, b, a + 1, b + 1, b); }
    g.setIndex(idx); mat.side = THREE.DoubleSide;
    const o = new THREE.Mesh(g, mat); o.visible = false; o.frustumCulled = false; head.add(o); return o;
  };
  const mouthIn = flap(new THREE.MeshBasicMaterial({ color: 0x1a0d14 })), mouthTongue = flap(new THREE.MeshBasicMaterial({ color: 0xC9566F }));
  const strip = (o, W, top, bottom, dz) => {
    const p = o.geometry.attributes.position;
    for (let i = 0; i <= MN; i++) { const x = -W + 2 * W * i / MN, yt = top(x), yb = bottom(x);
      for (let j = 0; j <= MR; j++) { const y = yt + (yb - yt) * j / MR; p.setXYZ(i * (MR + 1) + j, x, y, surf(x, y) + dz); } }
    p.needsUpdate = true; o.visible = true;
  };
  // m — насколько открыт (0…1), wd — гласная: 0 «о/у» (уже и глубже), 1 «и/е» (шире и площе).
  const mouthShape = (m, wd) => {
    mouthIn.visible = mouthTongue.visible = m > .03; if (!mouthIn.visible) return;
    // Низ — ровная дуга от уголка до уголка (не повторяет зигзаг «ω»), иначе язык выходит галочкой.
    const W = .085 + .05 * wd, H = .03 + .16 * m * (1 - .35 * wd), arc = x => Math.sqrt(Math.max(0, 1 - (x / W) ** 2)) ** .8;
    const corner = omegaY(W), low = x => Math.min(omegaY(x) - .01, corner - H * arc(x));
    strip(mouthIn, W, x => omegaY(x) + .012, low, .016);
    const Wt = W * .68, kt = x => Math.sqrt(Math.max(0, 1 - (x / Wt) ** 2));
    strip(mouthTongue, Wt, x => low(x) + .006 + H * .38 * kt(x), x => low(x) + .006 * (1 - kt(x)), .02);
  };

  // Язычок: пока Морзик косит, рот чуть приоткрыт (тёмная щёлочка под «ω») и оттуда свисает кончик языка.
  const mouthZ = surf(0, -.36);
  const gap = sph(1, new THREE.MeshBasicMaterial({ color: 0x1a0d14 }), V(0, -.355, mouthZ + .012), [.07, .022, .02], head);
  const tongue = sph(1, new THREE.MeshPhysicalMaterial({ color: 0xE2607A, roughness: .35, clearcoat: .4 }), V(0, -.4, mouthZ + .03), [.06, .07, .03], head);
  const tongueY = -.36;

  // Глаза: миндалевидная радужка с градиентом, ровная щёлка, блики.
  const irisTex = soul.iris ? tex(256, 256, (x, w) => {
    // Живая радузка: тёплый градиент, светлый венчик у зрачка, волокна лучами, тёмный ободок по краю.
    const c = w / 2, g = x.createRadialGradient(c, c, 0, c, c, c);
    [[0, '#FFF0B8'], [.3, '#FFD060'], [.6, '#F5A230'], [.86, '#D9741A'], [.93, '#7A3608'], [1, '#3A1804']].forEach(([o, col]) => g.addColorStop(o, col));
    x.fillStyle = g; x.fillRect(0, 0, w, w);
    let r = 5; const rnd = () => (r = (r * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < 220; i++) {
      const a = rnd() * Math.PI * 2, r0 = c * (.2 + rnd() * .15), r1 = c * (.6 + rnd() * .3);
      x.strokeStyle = rnd() < .5 ? `rgba(255,240,190,${.12 + rnd() * .2})` : `rgba(140,60,10,${.1 + rnd() * .2})`; x.lineWidth = 1 + rnd() * 1.5;
      x.beginPath(); x.moveTo(c + r0 * Math.cos(a), c + r0 * Math.sin(a)); x.lineTo(c + r1 * Math.cos(a + (rnd() - .5) * .08), c + r1 * Math.sin(a + (rnd() - .5) * .08)); x.stroke();
    }
    const ring = x.createRadialGradient(c, c, c * .2, c, c, c * .42); ring.addColorStop(0, 'rgba(255,250,220,.55)'); ring.addColorStop(1, 'rgba(255,250,220,0)');
    x.fillStyle = ring; x.fillRect(0, 0, w, w);
    // Тень от верхнего века: верх радужки темнее.
    const top = x.createLinearGradient(0, 0, 0, w * .45); top.addColorStop(0, 'rgba(60,20,0,.55)'); top.addColorStop(1, 'rgba(60,20,0,0)');
    x.fillStyle = top; x.fillRect(0, 0, w, w);
  }) : radialTex([[0, '#FFE6A0'], [.45, '#FFBE45'], [.85, '#EA8A1C'], [1, '#8E430E']]);
  // Веки (soul.lids): радужку, зрачок и блики шейдер обрезает по двум дугам в координатах глаза; у края — тёмная кромка.
  const lidShader = u => m => m.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, u);
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nuniform mat4 uLidInv; varying vec2 vLid;')
      .replace('#include <project_vertex>', '#include <project_vertex>\nvLid = (uLidInv * modelMatrix * vec4(transformed, 1.)).xy;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nuniform vec4 uLids; varying vec2 vLid;')
      .replace('#include <dithering_fragment>', `#include <dithering_fragment>
        float up = uLids.x - uLids.y * vLid.x * vLid.x, lo = uLids.z - uLids.w * vLid.x * vLid.x;
        if (vLid.y > up || vLid.y < lo) discard;
        float edge = min(up - vLid.y, vLid.y - lo);
        gl_FragColor.rgb *= mix(.25, 1., smoothstep(0., .022, edge));`);
  };
  // Глаза-спиральки (dizzy): янтарная радужка с тёмной спиралью из двух витков, крутится вокруг центра.
  const spiralTex = tex(256, 256, (x, w) => {
    const g = x.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2); [[0, '#FFE6A0'], [.5, '#FFBE45'], [.9, '#EA8A1C'], [1, '#8E430E']].forEach(([o, c]) => g.addColorStop(o, c));
    x.fillStyle = g; x.fillRect(0, 0, w, w);
    x.strokeStyle = '#1a0f12'; x.lineWidth = 15; x.lineCap = 'round'; x.beginPath();
    for (let a = 0; a <= Math.PI * 2 * 2.6; a += .05) { const r = 6 + a / (Math.PI * 2 * 2.6) * (w / 2 - 22); x.lineTo(w / 2 + r * Math.cos(a), w / 2 + r * Math.sin(a)); }
    x.stroke();
  });
  const eyes = [-1, 1].map(sx => {
    const x = sx * .4, y = .1, z = surf(x, y) + .035;
    const g = new THREE.Group(); g.position.set(x, y, z); g.lookAt(x + sx * .3, y + .06, z + 1); head.add(g);
    const lid = new THREE.Group(); g.add(lid);
    const lu = { uLidInv: { value: new THREE.Matrix4() }, uLids: { value: new THREE.Vector4(1, 0, -1, 0) } }, clip = soul.lids ? lidShader(lu) : () => {};
    const iris = new THREE.Mesh(new THREE.CircleGeometry(1, 64), new THREE.MeshBasicMaterial({ map: irisTex, toneMapped: false })); iris.scale.set(.2, .235, 1); lid.add(iris);
    const pupil = new THREE.Mesh(new THREE.CircleGeometry(1, 48), new THREE.MeshBasicMaterial({ color: 0x07060b })); pupil.scale.set(.04, .175, 1); pupil.position.z = .004; lid.add(pupil);
    clip(iris.material); clip(pupil.material);
    const hi = new THREE.MeshBasicMaterial({ color: 0xffffff }); clip(hi);
    const h1 = new THREE.Mesh(new THREE.CircleGeometry(.05, 24), hi); h1.position.set(.07, .09, .008); lid.add(h1);
    const h2 = new THREE.Mesh(new THREE.CircleGeometry(.022, 16), hi); h2.position.set(-.06, -.1, .008); lid.add(h2);
    // Живая радужка: блик крупнее.
    if (soul.iris) h1.scale.setScalar(1.25);
    const halo = sprite('rgba(255,170,50,.45)', .62, .7, V(0, 0, -.01), g);
    // Свечение — плоская картинка, а морда выпуклая: с проверкой глубины середину съедала голова (видно при закрытых глазах).
    halo.material.depthTest = false; halo.renderOrder = 1;
    pupil.userData.base = sx * .048;
    // Спиральки и обычная радужка — две материи одного круга: состояние меняется на лету (set ниже).
    const amber = iris.material, spiral = new THREE.MeshBasicMaterial({ map: spiralTex, toneMapped: false });
    // Закрытый глаз (до звонка): тонкая янтарная дужка «‿» вместо радужки, как будто спит.
    const shut = new THREE.Mesh(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(V(-.17, .01, .01), V(0, -.11, .01), V(.17, .01, .01)), 24, .018, 8), glow(0xFFB43A));
    shut.visible = false; g.add(shut);
    // Смеётся: глаза-дужки «∩», как у довольного кота.
    const joy = new THREE.Mesh(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(V(-.17, -.05, .01), V(0, .11, .01), V(.17, -.05, .01)), 24, .02, 8), glow(0xFFB43A));
    joy.visible = false; g.add(joy);
    // Глаз рисуется после свечения (оно без проверки глубины), иначе свечение ложится на зрачок.
    spiral.transparent = true;
    [...lid.children, shut, joy].forEach(o => { o.renderOrder = 2; o.material.transparent = true; });
    return { lid, pupil, halo, sx, iris, shut, joy, amber, spiral, lu };
  });

  // Усы-морзянка как у первого чёрного кота: по три с каждой стороны, каждый целиком из точек и тире «·–··–».
  const whiskerMats = [];
  [-1, 1].forEach(sx => [[.02, .07], [-.06, -.02], [-.14, -.12]].forEach(([y0, y1]) => {
    const a = V(sx * .34, -.24 + y0, surf(.34, -.24 + y0) + .02), b = V(sx * 1.4, -.24 + y1 * 2.2, .66), m = a.clone().lerp(b, .5).add(V(0, .04, .1));
    const curve = new THREE.QuadraticBezierCurve3(a, m, b);
    const unit = 1 / 11; let u = .02;
    [...'.-..-'].forEach(ch => {
      const len = ch === '.' ? unit * .6 : unit * 1.9;
      // Своё свечение у каждого знака: по усам бежит свет (callStyle 'whiskers'); u — место на усе, 0 у мордочки.
      const mat = glow(0xFFB43A, .95); mat.userData.u = u + len / 2; mat.userData.row = y0; whiskerMats.push(mat);
      if (ch === '.') sph(.028, mat, curve.getPoint(u + len / 2), [1, 1, 1], head);
      else tube([0, .5, 1].map(k => curve.getPoint(u + len * k)), .024, mat, head);
      u += len + unit * .7;
    });
  }));

  // Матовые кремовые наушники: дуга за ушами, чашки по бокам, тёмные амбушюры, на чашке янтарная точка.
  const cream = matte(0xE9E1D1), cushion = matte(0x1C2240);
  // Дуга наклонена назад от линии чашек, чтобы проходить за ушами, а не сквозь них.
  const bandG = new THREE.Group(); bandG.position.set(0, -.1, -.12); bandG.rotation.x = -.3; head.add(bandG);
  bandG.add(new THREE.Mesh(new THREE.TorusGeometry(1.27, .085, 20, 80, Math.PI), cream));
  const leds = [];
  [-1, 1].forEach(sx => {
    const cup = new THREE.Mesh(new THREE.CylinderGeometry(.34, .34, .24, 48), cream); cup.rotation.z = Math.PI / 2; cup.position.set(sx * 1.24, -.1, -.12); head.add(cup);
    const rimC = new THREE.Mesh(new THREE.TorusGeometry(.34, .04, 12, 48), cream); rimC.rotation.y = Math.PI / 2; rimC.position.set(sx * 1.36, -.1, -.12); head.add(rimC);
    const pad = new THREE.Mesh(new THREE.TorusGeometry(.25, .085, 16, 40), cushion); pad.rotation.y = Math.PI / 2; pad.position.set(sx * 1.1, -.1, -.12); head.add(pad);
    const yoke = new THREE.Mesh(new THREE.TorusGeometry(.38, .035, 10, 32, Math.PI), cream); yoke.rotation.set(0, Math.PI / 2, 0); yoke.position.set(sx * 1.24, -.1, -.12); head.add(yoke);
    const led = sph(.045, glow(0xFFB43A), V(sx * 1.37, -.1, .02), [1, 1, .6], head); leds.push(led);
  });

  // Микрофон гарнитуры, как у саппорта: штанга из левой чашки идёт под усами к уголку рта.
  { const tip = V(-.44, -.55, surf(-.44, -.55) + .13);
    const boom = new THREE.CatmullRomCurve3([V(-1.3, -.3, -.02), V(-1.22, -.56, .3), V(-.92, -.66, .66), tip.clone().add(V(-.12, -.02, 0))]);
    head.add(new THREE.Mesh(new THREE.TubeGeometry(boom, 48, .028, 10), cream));
    sph(.04, cream, V(-1.3, -.3, -.02), [1, 1, 1], head);
    // Капсула продолжает штангу: стоит по её направлению на конце, штанга входит в торец.
    const end = boom.getPoint(1), dir = boom.getTangent(1).normalize();
    const mic = new THREE.Mesh(new THREE.CapsuleGeometry(.062, .12, 8, 24), cushion);
    mic.position.copy(end).addScaledVector(dir, .1); mic.quaternion.setFromUnitVectors(V(0, 1, 0), dir); head.add(mic); }

  // Лапки (вариант для холста): 'rest' — лежат на нижнем краю, 'wave' — машет, 'mic' — держит микрофон.
  const beanM = new THREE.MeshStandardMaterial({ color: 0x6A4862, roughness: .6 });
  const paw = (parent, pos, beans) => {
    sph(.2, furM, pos, [1, 1.05, .8], parent);
    if (!beans) return;
    const z = pos.z + .15;
    sph(.075, beanM, V(pos.x, pos.y - .05, z), [1.1, .9, .35], parent);
    [[-.09, .07], [0, .11], [.09, .07]].forEach(([dx, dy]) => sph(.034, beanM, V(pos.x + dx, pos.y + dy, z - .01), [1, 1, .35], parent));
  };
  // Парящие лапки (paws: 'float'): без рук, как голова над телом. Каждая лапка — группа (подушечки внутри),
  // поза — { p: [x, y, z], r: [rx, ry, rz] } в координатах кота; анимация смешивает позы (POSES и floatPose ниже).
  const floatPaws = [];
  if (paws === 'float') [-1, 1].forEach(sx => {
    const g = new THREE.Group(); cat.add(g);
    sph(.22, furM, V(0, 0, 0), [1, 1.1, .78], g);
    sph(.08, beanM, V(0, -.05, .16), [1.1, .9, .35], g);
    [[-.095, .075], [0, .12], [.095, .075]].forEach(([dx, dy]) => sph(.036, beanM, V(dx, dy, .15), [1, 1, .35], g));
    floatPaws.push({ g, sx });
  });
  const POSES = {
    float: sx => ({ p: [sx * .38, -1.6, .78], r: [1.15, 0, 0] }),          // лежит внизу, как в «Лапки 1», подушечками вниз
    wave: sx => ({ p: [sx * .86, -.38, .92], r: [.05, -sx * .2, 0] }),     // поднята у щеки, ладошкой к нам (верх дуги маханья)
  };
  const WAVE_PIVOT = sx => [sx * .86, -1.02, .92], WAVE_R = .64;          // маханье — по дуге вокруг точки ниже лапки, как дворник
  const lerpPose = (a, b, k) => ({ p: a.p.map((v, i) => v + (b.p[i] - v) * k), r: a.r.map((v, i) => v + (b.r[i] - v) * k) });
  const applyPose = (g, q) => { g.position.set(...q.p); g.rotation.set(...q.r); };
  let arm = null;
  if (paws === 'rest' || paws === 'wave' || paws === 'mic') {
    if (paws === 'rest') [-1, 1].forEach(sx => paw(cat, V(sx * .38, -1.6, .78), false));
    else {
      paw(cat, V(.38, -1.6, .78), false);
      arm = new THREE.Group(); paws === 'wave' ? arm.position.set(-.55, -1.25, .25) : arm.position.set(-.5, -1.3, .45); cat.add(arm);
      const end = paws === 'wave' ? V(-.62, .62, .4) : V(.02, .92, .42);
      const elbow = paws === 'wave' ? [V(end.x * .6, end.y * .3, end.z * .5)] : [V(-.32, .38, .22), V(-.14, .72, .36)];
      tube([V(0, 0, 0), ...elbow, V(end.x * .95, end.y * .85, end.z * .95)], paws === 'wave' ? .15 : .17, furM, arm);
      paw(arm, end, paws === 'wave');
    }
  }

  // Звёздочки над головой (stars): пять янтарных четырёхлучевых искорок кружат по наклонённому кольцу.
  const starRing = new THREE.Group(); starRing.position.set(0, 1.05, 0); starRing.rotation.x = .38; head.add(starRing);
  if (stars) {
    const shape = new THREE.Shape(); for (let i = 0; i < 8; i++) { const a = i / 8 * Math.PI * 2 + Math.PI / 2, r = i % 2 ? .045 : .13; i ? shape.lineTo(r * Math.cos(a), r * Math.sin(a)) : shape.moveTo(r * Math.cos(a), r * Math.sin(a)); }
    const geo = new THREE.ExtrudeGeometry(shape, { depth: .04, bevelEnabled: true, bevelSize: .015, bevelThickness: .015, bevelSegments: 2 });
    for (let i = 0; i < 5; i++) { const st = new THREE.Mesh(geo, glow(0xFFC24A)); const a = i / 5 * Math.PI * 2; st.position.set(Math.cos(a) * 1.05, 0, Math.sin(a) * 1.05); starRing.add(st); }
  }

  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(3, 3), new THREE.MeshBasicMaterial({ map: radialTex([[0, 'rgba(0,0,0,.5)'], [1, 'rgba(0,0,0,0)']]), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = -2.4; if (!headOnly) scene.add(shadow);

  const CALM = 8, ease = p => (1 - Math.cos(Math.PI * Math.min(1, Math.max(0, p)))) / 2;
  const bump = (t, c, w) => { const p = (t - c) / w; return p > 0 && p < 1 ? Math.sin(Math.PI * p) : 0; };
  const blink = (t, c) => { const p = (t - c) / .26; return p > 0 && p < 1 ? 1 - Math.sin(Math.PI * p) : 1; };
  const ctxs = mirrors.map(c => c.getContext('2d'));

  // Речь для макетов (без level): настоящие фразы, разобранные на слоги. Ударный слог громче и длиннее,
  // между слогами голос проседает на согласных, у каждого слога своя гласная: и/е/э/ы — рот шире, о/у/ё/ю — круглее.
  // В звонке вместо этого — громкость и спектр настоящего голоса (level возвращает число или { v, wide }).
  const speech = (phrases, seed) => {
    let r = seed; const rnd = () => (r = (r * 16807) % 2147483647) / 2147483647;
    const syl = []; let at = .3;
    phrases.forEach(ph => {
      ph.split(' ').forEach(word => {
        const vs = [...word.matchAll(/[аеёиоуыэюяАЕЁИОУЫЭЮЯ]́?/g)].map(m => m[0]);
        vs.forEach(v => {
          const stress = v.length > 1 || vs.length === 1 && word.length > 3, dur = (stress ? .25 : .14) + rnd() * .05;
          syl.push({ at, dur, amp: stress ? .95 : .55 + rnd() * .2, wide: /[иеэы]/i.test(v) ? 1 : /[оуёю]/i.test(v) ? 0 : .5 });
          at += dur + .03;
        });
        at += /[,—]$/.test(word) ? .3 : /[.!?]$/.test(word) ? .65 : .04;
      });
      at += .5;
    });
    return T => {
      T %= at; let v = 0, wide = .5;
      for (const s of syl) {
        if (T < s.at - .05) break;
        const p = (T - s.at) / s.dur; if (p < -.3 || p > 1.3) continue;
        const k = s.amp * Math.min(ease((p + .3) / .5), 1 - ease((p - .8) / .5));
        if (k > v) { v = k; wide = s.wide; }
      }
      return { v, wide };
    };
  };
  const morzikSays = speech(['Приве́т! Я тут поду́мал про твой календа́рь.', 'Во вто́рник у тебя́ три встре́чи подря́д, дава́й одну́ перенесём?',
    'Мо́жно на четве́рг, там свобо́дно по́сле обе́да.'], 7);
  const userSays = speech(['Слу́шай, а что у меня́ за́втра?', 'Мне ну́жно успе́ть в спортза́л ве́чером, и ещё забра́ть посы́лку.'], 3);
  // Звонок гудит: два гудка и пауза каждые 2 с.
  const ring = t => { const p = t % 2; return bump(p, 0, .32) + bump(p, .42, .32); };
  const glowTo = (m, k) => { (m.userData.base ??= m.color.clone()); m.color.copy(m.userData.base).multiplyScalar(k); if (!transparent) m.opacity = 1; };

  // Живость: всё, что движется, — пружины (догоняют цель с лёгким перелётом), а моргания, взгляды и подёргивания ушей
  // случаются в случайные моменты, поэтому анимация не повторяется. Голова плавает по медленному шуму.
  const S = {}; let lastT = null, seed = 11;
  const rand = (a, b) => a + (b - a) * ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const spring = (dt, key, target, f, z) => {
    const s = S[key] ??= { x: target, v: 0 };
    if (dt == null) { s.x = target; s.v = 0; return s.x; }
    const w0 = Math.PI * 2 * f, n = Math.ceil(dt * 240), h = dt / n;
    for (let i = 0; i < n; i++) { s.v += (w0 * w0 * (target - s.x) - 2 * z * w0 * s.v) * h; s.x += s.v * h; }
    return s.x;
  };
  const kick = (key, dv) => { if (S[key]) S[key].v += dv; };
  const noise = (T, a, b, c) => .5 * Math.sin(T * a + c) + .3 * Math.sin(T * b + c * 2.3) + .2 * Math.sin(T * (a + b) * .7 + c * .5);
  const emo = { name: null, at: -9, dur: 0 };
  const ev = { blink: 1.5, blinkAt: -9, dbl: false, saccade: 0, gx: 0, gy: 0, flick: 3, flickAt: -9, flickEar: 1, nodAt: -9, pose: 0, tx: 0, ty: 0, tz: 0, fast: 0, slow: 0, talk: 0, quiet: 0 };
  function callFrame(t, w, T) {
    let dt = lastT == null ? null : T - lastT; lastT = T;
    if (dt != null && (dt <= 0 || dt > .25 || frozen != null)) dt = null;
    const R = call === 'ringing' ? ring(T) : 0, mime = callStyle === 'cat' || callStyle === 'both', idle = call === 'idle';
    const src = call === 'speaking' ? (level || morzikSays) : call === 'listening' ? (level || userSays) : null;
    const got = src ? src(T) : 0, raw = typeof got === 'number' ? got : got.v, wide = typeof got === 'number' ? .5 : got.wide;
    const L = Math.max(0, spring(dt, 'L', raw, 14, .85));

    // События. Моргает раз в 2–6 с, иногда дважды; взгляд перескакивает раз в 0,6–2,5 с; ухо дёргается раз в 4–10 с.
    if (dt != null) {
      if (T > ev.blink) { ev.blinkAt = T; ev.dbl = rand(0, 1) < .15; ev.blink = T + rand(2, call === 'thinking' ? 3.5 : 6); }
      if (T > ev.saccade) {
        const th = call === 'thinking', sp = call === 'speaking', gx0 = ev.gx, gy0 = ev.gy;
        ev.gx = (th ? .04 : 0) + rand(-1, 1) * (th ? .025 : sp ? .026 : .012); ev.gy = (th ? .055 : 0) + rand(-1, 1) * (th ? .015 : sp ? .016 : .008);
        // Говоря, иногда отводит взгляд вбок-вверх, как будто подбирает слово, и возвращается.
        if (sp && rand(0, 1) < .25) { ev.gx = rand(0, 1) < .5 ? -.05 : .05; ev.gy = rand(.015, .035); }
        ev.saccade = T + (sp ? rand(.35, 1.4) : rand(.6, th ? 1.4 : 2.5));
        // soul.focus: на большом переводе взгляда часто моргает, как живые.
        if (soul.focus && Math.hypot(ev.gx - gx0, ev.gy - gy0) > .025 && rand(0, 1) < .5 && T - ev.blinkAt > .8) { ev.blinkAt = T; ev.dbl = false; }
      }
      // Говоря и слушая, раз в 1–3 с чуть меняет позу: наклон, поворот, кивок вверх-вниз.
      if (T > ev.pose) { const a = call === 'speaking' ? 1 : call === 'listening' ? .45 : 0;
        ev.tz = rand(-1, 1) * .055 * a; ev.ty = rand(-1, 1) * .06 * a; ev.tx = rand(-1, 1) * .025 * a; ev.pose = T + rand(1, 3); }
      if (T > ev.flick) { ev.flickAt = T; ev.flickEar = rand(0, 1) < .5 ? 0 : 1; ev.flick = T + rand(4, call === 'thinking' ? 6 : 10); }
      // Кивки на ударениях: громкость резко выросла над средней (говорит он) — короткий кивок; ты договорил фразу — «угу».
      const a1 = 1 - Math.exp(-dt / .04), a2 = 1 - Math.exp(-dt / .45);
      ev.fast += (raw - ev.fast) * a1; ev.slow += (raw - ev.slow) * a2;
      if (call === 'speaking' && ev.fast - ev.slow > .22 && ev.fast > .7 && T - ev.nodAt > .5) { ev.nodAt = T; kick('hx', 1.1 * (ev.fast - ev.slow)); kick('hp', .25 * (ev.fast - ev.slow)); }
      if (raw > .1) { ev.talk += dt; ev.quiet = 0; } else ev.quiet += dt;
      if (call === 'listening' && ev.quiet > .45 && ev.talk > 1.2) { ev.talk = 0; if (rand(0, 1) < .7) { kick('hx', .45); ev.blink = Math.min(ev.blink, T + .15); } }
      if (call !== 'listening') ev.talk = 0;
    }
    const bl = p => p < 0 || p > 1 ? 1 : p < .35 ? 1 - ease(p / .35) : ease((p - .35) / .65);
    // На ударном слоге глаза чуть прищуриваются, как при улыбке.
    const open = Math.min(bl((T - ev.blinkAt) / .2), ev.dbl ? bl((T - ev.blinkAt - .28) / .2) : 1) * (1 - .14 * bump(T - ev.nodAt, 0, .6));
    const flick = bump(T - ev.flickAt, 0, .22) - .5 * bump(T - ev.flickAt, .22, .2);

    // Цели позы для состояния; дыхание и медленный шум поверх.
    const P = { px: ev.gx, py: ev.gy, dil: 1, earF: 0, earT: 0,
      hx: ev.tx + .012 * noise(T, .7, 1.9, 1) + (idle ? .025 * Math.sin(T * Math.PI / 2) : 0), hy: ev.ty + .025 * noise(T, .5, 1.3, 2), hz: ev.tz + .02 * noise(T, .6, 1.7, 3), hp: .012 * Math.sin(T * Math.PI / 2) };
    if (idle) Object.assign(P, { px: 0, py: 0 });
    if (mime && call === 'ringing') Object.assign(P, { earF: .5 + .5 * R, dil: 1.3, hp: P.hp + .02 * R });
    // Слушает: уши вперёд и вздрагивают на голос, голова склонена набок.
    if (mime && call === 'listening') Object.assign(P, { earF: 1, earT: .08 * L, dil: 1.5, hz: P.hz + .11, hx: P.hx + .02 + .03 * L });
    // Думает: смотрит вверх-вбок (взгляд скачет по точкам там), голова чуть отвёрнута.
    if (mime && call === 'thinking') Object.assign(P, { hy: P.hy + .07, hx: P.hx - .07, hz: P.hz - .04 });
    if (mime && call === 'speaking') Object.assign(P, { earF: .3, hx: P.hx + .02 * L, hp: P.hp + .008 * L });
    // Эмоция (emote): плавно входит за 0,18 с, держится dur, уходит за 0,35 с; добавляется к позе состояния.
    const ek = !idle && emo.name ? Math.min(ease((T - emo.at) / .18), 1 - ease((T - emo.at - emo.dur) / .35)) : 0, en = ek > 0 ? emo.name : null;
    if (en === 'laugh') Object.assign(P, { hx: P.hx + .025 * ek * Math.sin(T * Math.PI * 2 * 5), earF: P.earF - .3 * ek, hp: P.hp + .01 * ek });
    if (en === 'smug') Object.assign(P, { px: P.px + .03 * ek, hz: P.hz + .07 * ek, hy: P.hy + .05 * ek, earT: P.earT + .25 * ek });
    if (en === 'excited') Object.assign(P, { earF: Math.max(P.earF, ek), dil: P.dil + .5 * ek });
    if (en === 'purr') Object.assign(P, { hz: P.hz + .08 * ek * Math.sin(T * 1.6), earF: P.earF - .2 * ek });
    if (en === 'meow') Object.assign(P, { earF: P.earF + .6 * ek, hz: P.hz + .09 * ek, hx: P.hx - .03 * ek });
    if (en === 'ask') Object.assign(P, { hz: P.hz + .12 * ek, hy: P.hy + .04 * ek, earF: P.earF + .6 * ek });
    // soul.focus: глаза ведут, голова догоняет взгляд; soul.iris: зрачок чуть «дышит».
    if (soul.focus && !idle) { P.hy += ev.gx * 1.1; P.hx -= ev.gy * .9; }
    if (soul.iris) P.dil += .05 * noise(T, .9, 1.7, 4);
    const hx = spring(dt, 'hx', P.hx, 1.4, .5), hy = spring(dt, 'hy', P.hy, 1.2, .55), hz = spring(dt, 'hz', P.hz, 1.3, .5), hp = spring(dt, 'hp', P.hp, 2, .5);
    const px = spring(dt, 'px', P.px, 7, .85), py = spring(dt, 'py', P.py, 7, .85), dil = spring(dt, 'dil', P.dil, 1, 1);
    const earF = spring(dt, 'earF', P.earF, 2.5, .4), earT = spring(dt, 'earT', P.earT, 4, .4);
    head.rotation.set(hx, hy, hz); head.position.y = .3 + hp;
    cat.rotation.y = 0;
    // soul.lids: верхнее и нижнее веко (в координатах глаза, радужка ±0,2 × ±0,235). Расслабленный взгляд — верхнее
    // чуть прикрыто; говорит — нижнее приподнято (улыбка глазами); думает — прищур; хитрит — тяжёлые веки; восторг — распахнуты.
    let lu = .17, ll = -.3;
    if (call === 'listening') lu = .2;
    if (call === 'speaking') { lu = .165; ll = -.2; }
    if (call === 'thinking') lu = .12;
    if (call === 'ringing') lu = .3;
    if (en === 'smug') { lu += (.04 - lu) * ek; ll += (-.17 - ll) * ek; }
    if (en === 'excited') { lu += (.3 - lu) * ek; ll += (-.3 - ll) * ek; }
    if (en === 'ask' || en === 'meow') lu += (.24 - lu) * ek;
    lu = spring(dt, 'lidU', lu + .7 * py, 3, .8); ll = spring(dt, 'lidL', ll + .5 * py, 3, .8);
    const tremor = soul.focus ? .0025 : 0;
    eyes.forEach(E => {
      if (soul.lids) { E.lid.updateWorldMatrix(true, false); E.lu.uLidInv.value.copy(E.lid.matrixWorld).invert(); E.lu.uLids.value.set(lu, 2.2, ll, 2.8); }
      // Смех — глаза-дужки «∩», мурлычет — закрытые «‿», хитрит — полуприкрытые.
      const joy = en === 'laugh' && ek > .45, purr = en === 'purr' && ek > .45;
      E.lid.visible = !idle && !joy && !purr; E.shut.visible = idle || purr; E.joy.visible = joy; E.halo.material.opacity = idle ? .25 : E.halo.material.opacity;
      const lidK = en === 'laugh' || en === 'purr' ? 1 - .94 * Math.min(1, ek * 2.2) : en === 'smug' ? 1 - .45 * ek : 1;
      E.lid.scale.y = Math.max(.06, (en === 'excited' ? 1 : open) * lidK);
      // soul.focus: зрачки чуть сведены к носу — взгляд сходится на тебе, а не уходит в бесконечность; мелкая дрожь.
      E.pupil.position.set(px + (soul.focus ? -E.sx * .014 : 0) + tremor * Math.sin(T * 37 + E.sx), py + tremor * Math.sin(T * 29 + 1), .004);
      E.pupil.scale.set(.04 * dil, .175 - .02 * (dil - 1), 1);
    });
    // Уши запаздывают за головой (качнулась голова — уши догоняют) и иногда дёргаются сами.
    const lag = S.hz ? S.hz.v * .12 : 0, lagX = S.hx ? S.hx.v * .2 : 0;
    ears.forEach((e, i) => { const sx = i ? 1 : -1;
      e.rotation.x = -.12 + .3 * earF - lagX;
      e.rotation.z = -sx * (.36 - .1 * earF - earT * (i ? 1 : .4) - (i === ev.flickEar ? .25 * flick : 0)) - lag; });
    // Рот: открывается по громкости, форма — по гласной: шире на «и», круглее на «о».
    const m = call === 'speaking' ? Math.min(1, L * 1.1) : 0, wd = spring(dt, 'wide', wide, 6, .9);
    gap.visible = tongue.visible = false; mouthShape(m, wd);
    // Наушники: на линии огонёк горит ровно, на гудках вспыхивает, до звонка почти погас.
    leds.forEach(l => glowTo(l.material, idle ? .15 : call === 'ringing' ? .35 + .8 * R : .9 + .25 * L));
    // До звонка не подключён: глаза закрыты, усы еле тлеют и медленно дышат.
    if (idle) whiskerMats.forEach(mat => glowTo(mat, .4 + .12 * Math.sin(T * Math.PI / 2)));
    if (callStyle === 'whiskers' || callStyle === 'both') whiskerMats.forEach(mat => {
      const u = mat.userData.u, front = (pos, wd = .14) => Math.exp(-(((u - pos) / wd) ** 2));
      let k = .55;
      if (call === 'ringing') k = .35 + 1.3 * Math.max(front((T % 2) / .3 - .05), front(((T % 2) - .42) / .3 - .05));
      // Слушает — свет бежит по усам к мордочке, говорит — от мордочки; яркость по громкости.
      if (call === 'listening') k = .35 + 1.3 * L * (.5 + .5 * Math.cos(Math.PI * 2 * (2 * u + 1.5 * T))) ** 3;
      if (call === 'speaking') k = .35 + 1.3 * L * (.5 + .5 * Math.cos(Math.PI * 2 * (2 * u - 1.5 * T))) ** 3;
      if (call === 'thinking') k = .35 + 1.3 * front(.5 - .5 * Math.cos(Math.PI * (T + mat.userData.row * 3)), .09);
      glowTo(mat, k);
    });
    onFrame?.(T, L, R);
  }
  function frame(t) {
    const T = t; t = ((t % CALM) + CALM) % CALM;
    const w = t / CALM * Math.PI * 2;
    const g = (.94 + .06 * Math.sin(w)) * (1 - .3 * bump(t, 5.1, .16));
    // Сценка: косит → собирает зрачки к центру → смотрит влево, вправо → в центр → глаза снова разъезжаются.
    const squint = 1 - ease((t - 2.4) / .4) + ease((t - 4.9) / .5);
    const look = -.055 * ease((t - 2.85) / .4) + .11 * ease((t - 3.55) / .5) - .055 * ease((t - 4.3) / .4);
    const open = Math.min(blink(t, 1.3), blink(t, 6.4));
    const tk = Math.max(0, Math.min(1, squint)); tongue.visible = gap.visible = tk > .03; gap.scale.x = .07 * tk; tongue.scale.y = .07 * tk; tongue.position.y = tongueY - .06 * tk;
    eyes.forEach(E => { E.lid.scale.y = Math.max(.06, open); E.pupil.position.x = E.pupil.userData.base * cross * squint + look; E.halo.material.opacity = .5 + .5 * g; });
    // twitchEar: какое ухо дёргается (1 — правое в сцене, -1 — левое; для отзеркаленной авы -1).
    { const k = twitchEar > 0 ? 1 : -1; ears[k > 0 ? 1 : 0].rotation.z = k * (-.4 + .2 * bump(t, 6.9, .35) - .1 * bump(t, 7.25, .3)); }
    body.scale.y = .88 * (1 + .012 * Math.sin(t / 4 * Math.PI * 2));
    head.rotation.z = .03 * Math.sin(w); head.rotation.y = look * 1.6; head.position.y = .3 + .015 * Math.sin(t / 4 * Math.PI * 2);
    tail.rotation.z = .14 * Math.sin(w + 1);
    // Парящие лапки: лежат внизу и чуть покачиваются не в такт; на 5,3–6,9 с правая (в сцене) поднимается,
    // дважды проходит туда-сюда по дуге и опускается обратно.
    floatPaws.forEach(({ g, sx }, i) => {
      let q = POSES.float(sx);
      q.p[1] += .03 * Math.sin(t / 4 * Math.PI * 2 + i * 1.7);
      if (sx > 0) {
        const up = ease((t - 5.3) / .45) - ease((t - 6.45) / .45);
        const swing = t > 5.6 && t < 6.44 ? .42 * Math.sin((t - 5.6) / .42 * Math.PI * 2) : 0;
        const [cx, cy, cz] = WAVE_PIVOT(sx), raised = { p: [cx + Math.sin(swing) * WAVE_R, cy + Math.cos(swing) * WAVE_R, cz], r: [.05, -sx * .2, -swing * .5] };
        q = lerpPose(q, raised, up);
      }
      applyPose(g, q);
    });
    if (arm) arm.rotation.z = paws === 'wave' ? -.08 + .22 * Math.sin(t * Math.PI * 2) : .02 * Math.sin(t / 4 * Math.PI * 2);
    cat.rotation.y = .12 * Math.sin(w);
    eyes.forEach(E => { E.iris.material = dizzy ? E.spiral : E.amber; E.pupil.visible = !dizzy; if (!dizzy) E.iris.rotation.z = 0;
      if (!call) { E.lid.visible = true; E.shut.visible = E.joy.visible = false; } });
    if (!call) { mouthIn.visible = mouthTongue.visible = false; eyes.forEach(E => E.lu.uLids.value.set(1, 0, -1, 0)); }
    if (dizzy) {
      // Цикл CALM = 8 с: спиральки делают целое число оборотов в разные стороны, голова плывёт по кругу.
      eyes.forEach(E => { E.iris.rotation.z = -E.sx * w * 6; E.lid.scale.y = 1; });
      tongue.visible = gap.visible = true; gap.scale.x = .07; tongue.scale.y = .07; tongue.position.y = tongueY - .06;
      head.rotation.z = .09 * Math.sin(w * 2); head.rotation.x = .05 * Math.cos(w * 2); head.rotation.y = .1 * Math.sin(w * 2 + .6);
      ears.forEach((e, i) => e.rotation.z = (i ? -1 : 1) * (.36 + .12 * Math.sin(w * 4 + i * 1.5)));
    }
    starRing.rotation.y = -w * 2; scene.updateMatrixWorld();
    // Искорки всегда смотрят в камеру (иначе на боках кольца видны ребром) и крутятся вокруг своей оси.
    starRing.children.forEach((st, i) => { st.lookAt(camera.position); st.rotateZ(w * 4 + i); st.scale.setScalar(.8 + .25 * Math.sin(w * 6 + i * 1.3)); });
    whiskerMats.forEach(m => pulse(m, .6 + .4 * g));
    leds.forEach(l => pulse(l.material, .5 + .5 * g));
    if (call) callFrame(t, w, T);
    renderer.render(scene, camera);
    ctxs.forEach((x, i) => { const s = mirrors[i].width; x.clearRect(0, 0, s, s); x.save(); x.beginPath(); x.arc(s / 2, s / 2, s / 2, 0, Math.PI * 2); x.clip(); x.drawImage(canvas, 0, 0, s, s); x.restore(); });
  }
  // Управление живой головой (приложение): set('idle' | 'ringing' | 'listening' | 'thinking' | 'speaking' | 'dizzy'),
  // setLevel(T => число или { v, wide }) — голос из звонка (null — фразы-макеты).
  const api = {
    set(state) { dizzy = state === 'dizzy'; call = dizzy ? null : state; },
    setLevel(fn) { level = fn; },
    // Эмоция по смыслу реплики: 'laugh', 'smug', 'excited', 'purr', 'meow', 'ask' (вопрос — голова набок), 'exclaim' (кивок).
    emote(name, dur = 1.5) {
      const T = lastT ?? 0;
      if (name === 'exclaim') { kick('hx', .6); kick('hp', .1); ev.nodAt = T; return; }
      Object.assign(emo, { name, at: T, dur }); if (name === 'excited') kick('hp', .2);
    },
  };
  // manual: кадры по запросу (для экспорта аватарки), без цикла анимации.
  if (manual) return { frame, loop: CALM, ...api };
  if (frozen != null) { frame(frozen); return; }
  const t0 = performance.now();
  renderer.setAnimationLoop(now => frame((now - t0) / 1000));
  return api;
}
