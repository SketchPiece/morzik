// Морзик-кот (Мурзик + Морзе) в мультяшном 3D, four variants from a pet to a robot. Собирается в _cats.bundle.js, как _three.js.
// Анимация спокойная, цикл 8 с: дышит, моргает, иногда смотрит вбок, дёргает ухом, хвост медленно качается.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const V = (x, y, z) => new THREE.Vector3(x, y, z);
const VARIANTS = {
  home:  { fur: 0xE8893A, light: 0xFFF1E0, ear: 0xF4A3A0, nose: 0xE46F7C, eyes: 'button', whisk: 'white', stripes: 0xB65A1F },
  black: { fur: 0x24222C, light: 0x24222C, ear: 0x4A3A55, nose: 0x3A2B3B, eyes: 'slit', whisk: 'morse', sheen: 0x6170A0 },
  radio: { fur: 0x9EA4B3, light: 0xF1F2F6, ear: 0xF2A9B2, nose: 0xD9707E, eyes: 'button', whisk: 'white', phones: true },
  robot: { fur: 0xF3F4F7, light: 0xF3F4F7, ear: 0xFFB43A, nose: null, eyes: 'screen', whisk: 'none', robot: true },
};

export function morzikCat(canvas, { variant = 'home', size = 420, t: frozen = null, mirrors = [] } = {}) {
  const P = VARIANTS[variant];
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(2); renderer.setSize(size, size, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  const scene = new THREE.Scene();
  const grad = stops => { const c = document.createElement('canvas'); c.width = c.height = 256; const x = c.getContext('2d'); const g = x.createRadialGradient(128, 128, 0, 128, 128, 128); stops.forEach(([o, col]) => g.addColorStop(o, col)); x.fillStyle = g; x.fillRect(0, 0, 256, 256); const tx = new THREE.CanvasTexture(c); tx.colorSpace = THREE.SRGBColorSpace; return tx; };
  { const c = document.createElement('canvas'); c.width = c.height = 512; const x = c.getContext('2d'); const g = x.createRadialGradient(256, 200, 0, 256, 220, 360); g.addColorStop(0, '#34477C'); g.addColorStop(1, '#10172C'); x.fillStyle = g; x.fillRect(0, 0, 512, 512); const tx = new THREE.CanvasTexture(c); tx.colorSpace = THREE.SRGBColorSpace; scene.background = tx; }
  const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromScene(new RoomEnvironment(), .04).texture; scene.environmentIntensity = .5;
  const camera = new THREE.PerspectiveCamera(30, 1, .1, 50); camera.position.set(0, .2, 6.7); camera.lookAt(0, -.08, 0);
  scene.add(new THREE.HemisphereLight(0xe6ecff, 0x1a2140, .9));
  const key = new THREE.DirectionalLight(0xfff4e8, 2.0); key.position.set(-3, 4, 5); scene.add(key);
  const rim = new THREE.DirectionalLight(0x8fb0ff, 2.2); rim.position.set(3, 2.5, -3); scene.add(rim);

  const fur = c => P.robot
    ? new THREE.MeshPhysicalMaterial({ color: c, roughness: .25, clearcoat: 1, clearcoatRoughness: .08 })
    : new THREE.MeshPhysicalMaterial({ color: c, roughness: .85, sheen: 1, sheenRoughness: .5, sheenColor: new THREE.Color(P.sheen ?? 0xffffff) });
  const glow = (c, op = 1) => new THREE.MeshBasicMaterial({ color: c, toneMapped: false, transparent: op < 1, opacity: op });
  const sph = (r, m, p, s = [1, 1, 1], parent) => { const o = new THREE.Mesh(new THREE.SphereGeometry(r, 48, 32), m); o.position.copy(p); o.scale.set(...s); parent.add(o); return o; };
  const tube = (pts, r, m, parent) => { const o = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 48, r, 10), m); parent.add(o); return o; };
  const sprite = (col, scale, pos, parent) => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: grad([[0, col], [1, 'rgba(0,0,0,0)']]), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false })); s.scale.set(scale, scale, 1); s.position.copy(pos); parent.add(s); return s; };

  const furM = fur(P.fur), lightM = fur(P.light);
  const cat = new THREE.Group(); scene.add(cat);
  // Тело и лапки.
  const body = sph(.95, furM, V(0, -1.45, -.15), [1.05, .9, .85], cat);
  if (!P.robot && P.light !== P.fur) sph(.6, lightM, V(0, -1.3, .5), [1, 1, .55], cat);
  [-1, 1].forEach(sx => sph(.27, lightM, V(sx * .4, -2.1, .55), [1, .7, 1.15], cat));
  // Хвост: группа с опорой у основания, качается.
  const tail = new THREE.Group(); tail.position.set(.75, -1.75, -.35); cat.add(tail);
  tube([V(0, 0, 0), V(.5, .2, .05), V(.7, .8, .2), V(.55, 1.3, .35)], .13, furM, tail);
  if (P.robot) sph(.15, glow(0xFFB43A), V(.55, 1.32, .35), [1, 1, 1], tail);

  // Голова.
  const head = new THREE.Group(); head.position.set(0, .3, 0); cat.add(head);
  sph(1, furM, V(0, 0, 0), [1.1, .93, .95], head);
  if (!P.robot) [-1, 1].forEach(sx => sph(.42, furM, V(sx * .72, -.28, .22), [1.05, .78, .8], head));
  const ears = [-1, 1].map(sx => {
    const g = new THREE.Group(); g.position.set(sx * .58, .72, -.05); g.rotation.z = -sx * .36; head.add(g);
    const outer = new THREE.Mesh(new THREE.ConeGeometry(.36, .7, 32), furM); outer.position.y = .2; g.add(outer);
    const inner = new THREE.Mesh(new THREE.ConeGeometry(.22, .46, 32), P.robot ? glow(P.ear) : new THREE.MeshStandardMaterial({ color: P.ear, roughness: .7 })); inner.position.set(0, .14, .14); inner.scale.z = .5; g.add(inner);
    return g;
  });
  if (P.stripes) [-.22, 0, .22].forEach((x, i) => tube([V(x - .04, .78 - (i === 1 ? 0 : .05), .52), V(x, .6, .74), V(x + .02, .44, .84)], .045, new THREE.MeshStandardMaterial({ color: P.stripes, roughness: .8 }), head));

  // Морда: у живых котов — щёчки-подушечки, нос и рот «ω»; у робокота — тёмный экран.
  const eyeParts = [];
  let screenGlow = [];
  if (P.robot) {
    sph(.86, new THREE.MeshPhysicalMaterial({ color: 0x0b0e1c, roughness: .1, clearcoat: 1 }), V(0, -.02, .38), [1.05, .7, .7], head);
    const amber = glow(0xFFB43A);
    [-1, 1].forEach(sx => { const g = new THREE.Group(); g.position.set(sx * .34, .08, .99); head.add(g); const e = new THREE.Mesh(new THREE.CapsuleGeometry(.07, .14, 8, 16), amber); g.add(e); eyeParts.push({ g, sx, base: g.position.clone() }); });
    tube([V(-.2, -.26, .97), V(-.1, -.33, .99), V(0, -.25, 1), V(.1, -.33, .99), V(.2, -.26, .97)], .028, amber, head);
    screenGlow.push(sprite('rgba(255,180,60,.35)', 1.6, V(0, -.05, 1.05), head));
  } else {
    [-1, 1].forEach(sx => sph(.25, lightM, V(sx * .18, -.3, .8), [1, .85, .8], head));
    if (P.light !== P.fur) sph(.2, lightM, V(0, -.42, .78), [1.2, .7, .7], head);
    sph(.1, new THREE.MeshPhysicalMaterial({ color: P.nose, roughness: .35, clearcoat: .6 }), V(0, -.13, 1.02), [1.35, .85, .8], head);
    tube([V(-.21, -.33, .98), V(-.11, -.4, 1.0), V(0, -.29, 1.03), V(.11, -.4, 1.0), V(.21, -.33, .98)], .022, new THREE.MeshStandardMaterial({ color: variant === 'black' ? 0x0d0c12 : 0x4a2a2a, roughness: .6 }), head);
    // Глаза.
    [-1, 1].forEach(sx => {
      const g = new THREE.Group(); const base = V(sx * .4, .14, .82); g.position.copy(base); g.lookAt(base.clone().multiplyScalar(2)); head.add(g);
      if (P.eyes === 'slit') {
        const iris = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 24), glow(0xFFB43A)); iris.scale.set(.2, .23, .09); g.add(iris);
        const pupil = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), new THREE.MeshBasicMaterial({ color: 0x0b0a10 })); pupil.scale.set(.045, .18, .04); pupil.position.z = .07; g.add(pupil);
        screenGlow.push(sprite('rgba(255,170,50,.5)', .7, V(0, 0, .02), g));
      } else {
        const e = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 24), new THREE.MeshPhysicalMaterial({ color: 0x0d0c12, roughness: .15, clearcoat: 1, clearcoatRoughness: .04 })); e.scale.set(.19, .22, .09); g.add(e);
      }
      const hi = new THREE.MeshBasicMaterial({ color: 0xffffff });
      const h1 = new THREE.Mesh(new THREE.SphereGeometry(.055, 16, 12), hi); h1.position.set(.06, .08, .08); g.add(h1);
      const h2 = new THREE.Mesh(new THREE.SphereGeometry(.024, 12, 8), hi); h2.position.set(-.05, -.09, .08); g.add(h2);
      eyeParts.push({ g, sx, base, hl: [h1, h2] });
    });
    // Усы: белые проволочки или морзянка из точек и тире.
    const whiskers = [];
    [-1, 1].forEach(sx => [[.02, .07], [-.06, -.02], [-.14, -.12]].forEach(([y0, y1]) => {
      const a = V(sx * .36, -.2 + y0, .95), b = V(sx * 1.32, -.2 + y1 * 2.2, .62), m = a.clone().lerp(b, .5).add(V(0, .04, .08));
      if (P.whisk === 'white') tube([a, m, b], .012, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: .4 }), head);
      if (P.whisk === 'morse') {
        const curve = new THREE.QuadraticBezierCurve3(a, m, b), mat = glow(0xFFB43A, .95); whiskers.push(mat);
        const code = '.-..-', unit = 1 / 11; let u = .02;
        [...code].forEach(ch => { const len = ch === '.' ? unit * .6 : unit * 1.9; const pts = [0, .5, 1].map(k => curve.getPoint(u + len * k)); if (ch === '.') sph(.028, mat, pts[1], [1, 1, 1], head); else tube(pts, .024, mat, head); u += len + unit * .7; });
      }
    }));
    if (whiskers.length) screenGlow.push(...whiskers.map(() => null).slice(0, 0));
    head.userData.whiskers = whiskers;
  }
  // Радионаушники с антенной, на кончике — лампочка Морзика.
  let antennaBulb = null, antennaGlow = null, antennaLight = null;
  if (P.phones) {
    const metal = new THREE.MeshPhysicalMaterial({ color: 0x2C3A66, roughness: .3, metalness: .4, clearcoat: 1 });
    const band = new THREE.Mesh(new THREE.TorusGeometry(1.12, .07, 16, 64, Math.PI), metal); band.position.set(0, .05, -.05); head.add(band);
    [-1, 1].forEach(sx => { const cup = new THREE.Mesh(new THREE.CylinderGeometry(.33, .33, .22, 40), metal); cup.rotation.z = Math.PI / 2; cup.position.set(sx * 1.1, .02, -.02); head.add(cup); const pad = new THREE.Mesh(new THREE.TorusGeometry(.26, .07, 12, 32), new THREE.MeshStandardMaterial({ color: 0x151a2e, roughness: .8 })); pad.rotation.y = Math.PI / 2; pad.position.set(sx * .98, .02, -.02); head.add(pad); });
    tube([V(1.16, .2, .05), V(1.16, .45, .1), V(1.08, .66, .14)], .022, new THREE.MeshStandardMaterial({ color: 0xaeb6d2, metalness: 1, roughness: .3 }), head);
    antennaBulb = sph(.1, glow(0xFFC45A), V(1.06, .72, .15), [1, 1, 1], head);
    antennaGlow = sprite('rgba(255,190,80,.8)', .8, V(1.06, .72, .2), head);
    antennaLight = new THREE.PointLight(0xffb45a, 1.5, 3, 1.5); antennaLight.position.set(1.06, .72, .5); head.add(antennaLight);
  }

  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(3, 3), new THREE.MeshBasicMaterial({ map: grad([[0, 'rgba(0,0,0,.5)'], [1, 'rgba(0,0,0,0)']]), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = -2.3; scene.add(shadow);

  const CALM = 8, ease = p => (1 - Math.cos(Math.PI * Math.min(1, Math.max(0, p)))) / 2;
  const bump = (t, c, w) => { const p = (t - c) / w; return p > 0 && p < 1 ? Math.sin(Math.PI * p) : 0; };
  const blink = (t, c) => { const p = (t - c) / .26; return p > 0 && p < 1 ? 1 - Math.sin(Math.PI * p) : 1; };
  const ctxs = mirrors.map(c => c.getContext('2d'));
  function frame(t) {
    t = ((t % CALM) + CALM) % CALM;
    const w = t / CALM * Math.PI * 2;
    const g = (.94 + .06 * Math.sin(w)) * (1 - .3 * bump(t, 5.1, .16));
    const look = -.09 * (ease((t - 2.8) / .6) - ease((t - 4.6) / .6));
    const open = Math.min(blink(t, 1.3), blink(t, 6.4));
    eyeParts.forEach(E => { E.g.position.x = E.base.x + look; E.g.scale.y = Math.max(.08, open); E.hl?.forEach(h => h.visible = open > .6); });
    ears[1].rotation.z = .36 * -1 + .22 * bump(t, 3.7, .35) - .12 * bump(t, 4.05, .3);
    body.scale.y = .9 * (1 + .012 * Math.sin(t / 4 * Math.PI * 2));
    head.rotation.z = .035 * Math.sin(w); head.position.y = .3 + .015 * Math.sin(t / 4 * Math.PI * 2);
    tail.rotation.z = .14 * Math.sin(w + 1);
    cat.rotation.y = .12 * Math.sin(w);
    (head.userData.whiskers || []).forEach(m => m.opacity = .55 + .4 * g);
    screenGlow.forEach(s => s && (s.material.opacity = .6 + .4 * g));
    if (antennaBulb) { antennaGlow.material.opacity = g; antennaLight.intensity = 1.6 * g; antennaBulb.material.color.setRGB(1, .55 + .25 * g, .2 + .15 * g); }
    renderer.render(scene, camera);
    ctxs.forEach((x, i) => { const s = mirrors[i].width; x.clearRect(0, 0, s, s); x.save(); x.beginPath(); x.arc(s / 2, s / 2, s / 2, 0, Math.PI * 2); x.clip(); x.drawImage(canvas, 0, 0, s, s); x.restore(); });
  }
  if (frozen != null) { frame(frozen); return; }
  const t0 = performance.now();
  renderer.setAnimationLoop(now => frame((now - t0) / 1000));
}
