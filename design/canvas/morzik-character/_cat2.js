// Кот·2, доработка: чёрный Морзик с янтарными глазами, усы — по одному знаку морзянки, матовые кремовые наушники.
// Голова — одна гладкая форма вращения, расширенная книзу (щёки без отдельных шаров). Собирается в _cat2.bundle.js.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const V = (x, y, z) => new THREE.Vector3(x, y, z);
export function morzikCat2(canvas, { size = 420, t: frozen = null, mirrors = [], manual = false, shiftY = 0, tailSide = 1, twitchEar = 1 } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(2); renderer.setSize(size, size, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  const scene = new THREE.Scene();
  const tex = (w, h, paint) => { const c = document.createElement('canvas'); c.width = w; c.height = h; paint(c.getContext('2d'), w, h); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; };
  const radialTex = stops => tex(256, 256, (x, w) => { const g = x.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2); stops.forEach(([o, c]) => g.addColorStop(o, c)); x.fillStyle = g; x.fillRect(0, 0, w, w); });
  scene.background = tex(512, 512, (x) => { const g = x.createRadialGradient(256, 200, 0, 256, 220, 360); g.addColorStop(0, '#34477C'); g.addColorStop(1, '#10172C'); x.fillStyle = g; x.fillRect(0, 0, 512, 512); });
  const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromScene(new RoomEnvironment(), .04).texture; scene.environmentIntensity = .45;
  const camera = new THREE.PerspectiveCamera(30, 1, .1, 50); camera.position.set(0, .2 + shiftY, 6.7); camera.lookAt(0, -.08 + shiftY, 0); // shiftY > 0 опускает кота в кадре (для авы)
  scene.add(new THREE.HemisphereLight(0xe6ecff, 0x1a2140, .8));
  const key = new THREE.DirectionalLight(0xfff2e6, 1.8); key.position.set(-3, 4, 5); scene.add(key);
  const rimR = new THREE.DirectionalLight(0x9fb8ff, 1.8); rimR.position.set(3.5, 2, -3); scene.add(rimR);
  const rimL = new THREE.DirectionalLight(0xb7c6ff, 1.1); rimL.position.set(-3.5, 1.5, -3); scene.add(rimL);

  const furM = new THREE.MeshStandardMaterial({ color: 0x2F2C3A, roughness: .92, metalness: 0 }); // плотная матовая шерсть, без отлива
  const matte = c => new THREE.MeshStandardMaterial({ color: c, roughness: .95, metalness: 0 });
  const glow = (c, op = 1) => new THREE.MeshBasicMaterial({ color: c, toneMapped: false, transparent: true, opacity: op });
  const sprite = (col, sx, sy, pos, parent) => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: radialTex([[0, col], [1, 'rgba(0,0,0,0)']]), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false })); s.scale.set(sx, sy, 1); s.position.copy(pos); parent.add(s); return s; };
  const sph = (r, m, p, s, parent) => { const o = new THREE.Mesh(new THREE.SphereGeometry(r, 48, 32), m); o.position.copy(p); o.scale.set(...s); parent.add(o); return o; };
  const tube = (pts, r, m, parent) => { const o = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 48, r, 10), m); parent.add(o); return o; };

  const cat = new THREE.Group(); scene.add(cat);
  // Тело, лапки, хвост.
  const body = sph(.95, furM, V(0, -1.55, -.2), [1, .88, .82], cat);
  [-1, 1].forEach(sx => sph(.24, furM, V(sx * .36, -2.18, .5), [1, .7, 1.2], cat));
  // tailSide = -1 сажает хвост с другой стороны (ава отзеркалена при сборке, а хвост должен остаться справа).
  const tail = new THREE.Group(); tail.position.set(.7 * tailSide, -1.85, -.4); cat.add(tail);
  // Хвост с круглым кончиком, загнутым внутрь.
  const tailPts = [V(-.2, -.05, -.05), V(.5, .15, .05), V(.74, .72, .2), V(.62, 1.18, .34), V(.42, 1.32, .4)].map(p => p.setX(p.x * tailSide));
  tube(tailPts, .12, furM, tail);
  tailPts.slice(-1).forEach(p => sph(.12, furM, p, [1, 1, 1], tail));

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
  { const z = surf(0, -.3) + .06; tube([V(-.17, -.32, z - .03), V(-.085, -.38, z), V(0, -.3, z + .01), V(.085, -.38, z), V(.17, -.32, z - .03)], .016, new THREE.MeshStandardMaterial({ color: 0x0c0b10, roughness: .6 }), head); }

  // Язычок: пока Морзик косит, рот чуть приоткрыт (тёмная щёлочка под «ω») и оттуда свисает кончик языка.
  const mouthZ = surf(0, -.36);
  const gap = sph(1, new THREE.MeshBasicMaterial({ color: 0x1a0d14 }), V(0, -.355, mouthZ + .012), [.07, .022, .02], head);
  const tongue = sph(1, new THREE.MeshPhysicalMaterial({ color: 0xE2607A, roughness: .35, clearcoat: .4 }), V(0, -.4, mouthZ + .03), [.06, .07, .03], head);
  const tongueY = -.36;

  // Глаза: миндалевидная радужка с градиентом, ровная щёлка, блики.
  const irisTex = radialTex([[0, '#FFE6A0'], [.45, '#FFBE45'], [.85, '#EA8A1C'], [1, '#8E430E']]);
  const eyes = [-1, 1].map(sx => {
    const x = sx * .4, y = .1, z = surf(x, y) + .035;
    const g = new THREE.Group(); g.position.set(x, y, z); g.lookAt(x + sx * .3, y + .06, z + 1); head.add(g);
    const lid = new THREE.Group(); g.add(lid);
    const iris = new THREE.Mesh(new THREE.CircleGeometry(1, 64), new THREE.MeshBasicMaterial({ map: irisTex, toneMapped: false })); iris.scale.set(.2, .235, 1); lid.add(iris);
    const pupil = new THREE.Mesh(new THREE.CircleGeometry(1, 48), new THREE.MeshBasicMaterial({ color: 0x07060b })); pupil.scale.set(.04, .175, 1); pupil.position.z = .004; lid.add(pupil);
    const hi = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const h1 = new THREE.Mesh(new THREE.CircleGeometry(.05, 24), hi); h1.position.set(.07, .09, .008); lid.add(h1);
    const h2 = new THREE.Mesh(new THREE.CircleGeometry(.022, 16), hi); h2.position.set(-.06, -.1, .008); lid.add(h2);
    const halo = sprite('rgba(255,170,50,.45)', .62, .7, V(0, 0, -.01), g);
    pupil.userData.base = sx * .048;
    return { lid, pupil, halo, sx };
  });

  // Усы-морзянка как у первого чёрного кота: по три с каждой стороны, каждый целиком из точек и тире «·–··–».
  const whiskerMats = [];
  [-1, 1].forEach(sx => [[.02, .07], [-.06, -.02], [-.14, -.12]].forEach(([y0, y1]) => {
    const a = V(sx * .34, -.24 + y0, surf(.34, -.24 + y0) + .02), b = V(sx * 1.4, -.24 + y1 * 2.2, .66), m = a.clone().lerp(b, .5).add(V(0, .04, .1));
    const curve = new THREE.QuadraticBezierCurve3(a, m, b), mat = glow(0xFFB43A, .95); whiskerMats.push(mat);
    const unit = 1 / 11; let u = .02;
    [...'.-..-'].forEach(ch => {
      const len = ch === '.' ? unit * .6 : unit * 1.9;
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

  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(3, 3), new THREE.MeshBasicMaterial({ map: radialTex([[0, 'rgba(0,0,0,.5)'], [1, 'rgba(0,0,0,0)']]), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = -2.4; scene.add(shadow);

  const CALM = 8, ease = p => (1 - Math.cos(Math.PI * Math.min(1, Math.max(0, p)))) / 2;
  const bump = (t, c, w) => { const p = (t - c) / w; return p > 0 && p < 1 ? Math.sin(Math.PI * p) : 0; };
  const blink = (t, c) => { const p = (t - c) / .26; return p > 0 && p < 1 ? 1 - Math.sin(Math.PI * p) : 1; };
  const ctxs = mirrors.map(c => c.getContext('2d'));
  function frame(t) {
    t = ((t % CALM) + CALM) % CALM;
    const w = t / CALM * Math.PI * 2;
    const g = (.94 + .06 * Math.sin(w)) * (1 - .3 * bump(t, 5.1, .16));
    // Сценка: косит → собирает зрачки к центру → смотрит влево, вправо → в центр → глаза снова разъезжаются.
    const squint = 1 - ease((t - 2.4) / .4) + ease((t - 4.9) / .5);
    const look = -.055 * ease((t - 2.85) / .4) + .11 * ease((t - 3.55) / .5) - .055 * ease((t - 4.3) / .4);
    const open = Math.min(blink(t, 1.3), blink(t, 6.4));
    const tk = Math.max(0, Math.min(1, squint)); tongue.visible = gap.visible = tk > .03; gap.scale.x = .07 * tk; tongue.scale.y = .07 * tk; tongue.position.y = tongueY - .06 * tk;
    eyes.forEach(E => { E.lid.scale.y = Math.max(.06, open); E.pupil.position.x = E.pupil.userData.base * squint + look; E.halo.material.opacity = .5 + .5 * g; });
    // twitchEar: какое ухо дёргается (1 — правое в сцене, -1 — левое; для отзеркаленной авы -1).
    { const k = twitchEar > 0 ? 1 : -1; ears[k > 0 ? 1 : 0].rotation.z = k * (-.4 + .2 * bump(t, 6.9, .35) - .1 * bump(t, 7.25, .3)); }
    body.scale.y = .88 * (1 + .012 * Math.sin(t / 4 * Math.PI * 2));
    head.rotation.z = .03 * Math.sin(w); head.rotation.y = look * 1.6; head.position.y = .3 + .015 * Math.sin(t / 4 * Math.PI * 2);
    tail.rotation.z = .14 * Math.sin(w + 1);
    cat.rotation.y = .12 * Math.sin(w);
    whiskerMats.forEach(m => m.opacity = .6 + .4 * g);
    leds.forEach(l => l.material.opacity = .5 + .5 * g);
    renderer.render(scene, camera);
    ctxs.forEach((x, i) => { const s = mirrors[i].width; x.clearRect(0, 0, s, s); x.save(); x.beginPath(); x.arc(s / 2, s / 2, s / 2, 0, Math.PI * 2); x.clip(); x.drawImage(canvas, 0, 0, s, s); x.restore(); });
  }
  // manual: кадры по запросу (для экспорта аватарки), без цикла анимации.
  if (manual) return { frame, loop: CALM };
  if (frozen != null) { frame(frozen); return; }
  const t0 = performance.now();
  renderer.setAnimationLoop(now => frame((now - t0) / 1000));
}
