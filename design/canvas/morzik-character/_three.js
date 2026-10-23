// Морзик в настоящем 3D (three.js): лампа Н3·1 — прозрачное стекло, свет за лицом, чёрные глаза, спираль-улыбка.
// Доски грузят не этот модуль, а _three.bundle.js (обычный скрипт: draftwall держит доски в песочнице, где ES-модули не грузятся).
// Пересобрать после правок: в папке с three@0.170 и esbuild — entry.js с `import { morzik3d } from '<путь>/_three.js'; window.morzik3d = morzik3d;`, затем
// npx esbuild entry.js --bundle --format=iife --minify --outfile=<путь>/_three.bundle.js --alias:three/addons=node_modules/three/examples/jsm --alias:three=node_modules/three
// Анимация как у Н3·1: свет дышит, взгляд иногда уходит вбок, моргает, спираль изредка вздрагивает вместе со всем светом.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export function morzik3d(canvas, { style = 'glass', size = 480, t: frozen = null } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(2); renderer.setSize(size, size, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  const scene = new THREE.Scene();
  const grad = (stops, w = 256) => { const c = document.createElement('canvas'); c.width = c.height = w; const x = c.getContext('2d'); const g = x.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2); stops.forEach(([o, col]) => g.addColorStop(o, col)); x.fillStyle = g; x.fillRect(0, 0, w, w); const tx = new THREE.CanvasTexture(c); tx.colorSpace = THREE.SRGBColorSpace; return tx; };
  { const c = document.createElement('canvas'); c.width = c.height = 512; const x = c.getContext('2d'); const g = x.createRadialGradient(256, 200, 0, 256, 220, 360); g.addColorStop(0, '#34477C'); g.addColorStop(1, '#10172C'); x.fillStyle = g; x.fillRect(0, 0, 512, 512); const tx = new THREE.CanvasTexture(c); tx.colorSpace = THREE.SRGBColorSpace; scene.background = tx; }
  const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromScene(new RoomEnvironment(), .04).texture; scene.environmentIntensity = .55;
  const camera = new THREE.PerspectiveCamera(28, 1, .1, 50); camera.position.set(0, .45, 8.2); camera.lookAt(0, .3, 0);
  scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x1a2140, .7));
  const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(-3, 4, 4); scene.add(key);
  const rim = new THREE.DirectionalLight(0x8fb0ff, 1.4); rim.position.set(3, 2, -3); scene.add(rim);

  const bulb = new THREE.Group(); scene.add(bulb);
  // Стекло: шар r=1 с центром y=1, горлышко сужается к цоколю.
  const prof = [];
  for (let i = 0; i <= 40; i++) { const a = i / 40 * 2.42; prof.push(new THREE.Vector2(Math.max(.001, Math.sin(a)), 1 + Math.cos(a))); }
  const p0 = prof[prof.length - 1];
  for (let i = 1; i <= 14; i++) { const k = i / 14; prof.push(new THREE.Vector2(p0.x + (.46 - p0.x) * (1 - (1 - k) ** 2), p0.y + (-.42 - p0.y) * k)); }
  const glassOpts = style === 'glass'
    ? { color: 0xdfe8ff, opacity: .16, roughness: .03, clearcoat: 1, clearcoatRoughness: .03, envMapIntensity: 1.3, specularIntensity: 1 }
    : { color: 0xf3efe6, opacity: .5, roughness: .4, clearcoat: .5, envMapIntensity: .9, sheen: .5, sheenColor: new THREE.Color(0xffffff) };
  const glassGeo = new THREE.LatheGeometry(prof, 96);
  [THREE.BackSide, THREE.FrontSide].forEach((side, i) => { const m = new THREE.Mesh(glassGeo, new THREE.MeshPhysicalMaterial({ ...glassOpts, transparent: true, depthWrite: false, side })); m.renderOrder = 2 + i; bulb.add(m); });

  // Свет за лицом и ореол — спрайты, яркость от той же g.
  const back = new THREE.Sprite(new THREE.SpriteMaterial({ map: grad([[0, 'rgba(255,200,110,.75)'], [.45, 'rgba(255,170,70,.32)'], [1, 'rgba(255,160,60,0)']]), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false }));
  back.renderOrder = 4;
  back.position.set(0, .92, .25); back.scale.set(1.7, 1.5, 1); bulb.add(back);
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: grad([[0, 'rgba(255,200,110,.35)'], [1, 'rgba(255,200,110,0)']]), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false }));
  halo.renderOrder = 1; halo.position.set(0, .9, -1.2); halo.scale.set(4.6, 4.6, 1); scene.add(halo);

  // Проволочки и спираль-улыбка «W».
  const wireMat = new THREE.MeshStandardMaterial({ color: 0x9aa6c4, metalness: .9, roughness: .3 });
  const fy = .47, fz = .3, fw = .7;
  [-.36 * fw, .36 * fw].forEach(x => { const w = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(x * 1.05, -.45, fz * .6), new THREE.Vector3(x, .1, fz * .9), new THREE.Vector3(x, fy, fz)]), 24, .022, 8), wireMat); bulb.add(w); });
  const W = [[-.36, .03], [-.25, -.12], [-.1, -.075], [0, -.035], [.1, -.075], [.25, -.12], [.36, .03]].map(([x, y]) => new THREE.Vector3(x * fw, fy + y, fz + .02));
  const filMat = new THREE.MeshBasicMaterial({ color: 0xff9b3d, toneMapped: false, transparent: true });
  const fil = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(W), 80, .04, 12), filMat); fil.renderOrder = 5; bulb.add(fil);
  const filGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: grad([[0, 'rgba(255,120,30,1)'], [.5, 'rgba(255,120,30,.35)'], [1, 'rgba(255,120,30,0)']]), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false }));
  filGlow.renderOrder = 4; filGlow.position.set(0, fy - .02, fz + .05); filGlow.scale.set(.8, .42, 1); bulb.add(filGlow);
  const bulbLight = new THREE.PointLight(0xffb45a, 2, 4, 1.6); bulbLight.position.set(0, fy + .1, .5); bulb.add(bulbLight);

  // Глаза: глянцевые чёрные «пуговки» на поверхности стекла, с двумя бликами.
  const eyeMat = new THREE.MeshPhysicalMaterial({ color: 0x0d0c12, roughness: .18, clearcoat: 1, clearcoatRoughness: .05 });
  const hiMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const eyes = [-1, 1].map(sx => {
    const g = new THREE.Group(); bulb.add(g);
    const e = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 24), eyeMat); e.scale.set(.165, .19, .07); g.add(e);
    const h1 = new THREE.Mesh(new THREE.SphereGeometry(.05, 16, 12), hiMat); h1.position.set(.055, .06, .06); g.add(h1);
    const h2 = new THREE.Mesh(new THREE.SphereGeometry(.022, 12, 8), hiMat); h2.position.set(-.045, -.075, .06); g.add(h2);
    return { g, e, h1, h2, sx };
  });
  const placeEye = (E, look, open) => {
    const dir = new THREE.Vector3(E.sx * .34 + look, .02, .94).normalize();
    E.g.position.copy(dir.clone().multiplyScalar(1.01)).add(new THREE.Vector3(0, 1, 0));
    E.g.lookAt(E.g.position.clone().add(dir));
    E.g.scale.set(1, Math.max(.08, open), 1);
    E.h1.visible = E.h2.visible = open > .6;
  };

  // Цоколь: металлическая резьба, тёмное кольцо, контакт.
  const sp = [];
  for (let i = 0; i <= 60; i++) { const k = i / 60, y = -.42 - k * .66; sp.push(new THREE.Vector2(.47 + .035 * Math.sin(k * Math.PI * 6), y)); }
  sp.push(new THREE.Vector2(.36, -1.14), new THREE.Vector2(.3, -1.2), new THREE.Vector2(.001, -1.2));
  bulb.add(new THREE.Mesh(new THREE.LatheGeometry(sp, 64), new THREE.MeshStandardMaterial({ color: 0xaeb6d2, metalness: 1, roughness: .28 })));
  const tip = new THREE.Mesh(new THREE.CylinderGeometry(.22, .12, .16, 32), new THREE.MeshStandardMaterial({ color: 0x1d1f2a, roughness: .5 })); tip.position.y = -1.27; bulb.add(tip);
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 2.2), new THREE.MeshBasicMaterial({ map: grad([[0, 'rgba(0,0,0,.55)'], [1, 'rgba(0,0,0,0)']]), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = -1.42; shadow.scale.set(1, .5, 1); scene.add(shadow);
  bulb.position.y = .05;

  const CALM = 8, ease = p => (1 - Math.cos(Math.PI * Math.min(1, Math.max(0, p)))) / 2;
  const bump = (t, c, w) => { const p = (t - c) / w; return p > 0 && p < 1 ? Math.sin(Math.PI * p) : 0; };
  const blink = (t, c) => { const p = (t - c) / .28; return p > 0 && p < 1 ? 1 - Math.sin(Math.PI * p) : 1; };
  const dim = new THREE.Color(0x7a3a1e), hot = new THREE.Color(0xff8a2a);
  function frame(t) {
    t = ((t % CALM) + CALM) % CALM;
    const g = (.94 + .06 * Math.sin(t / CALM * Math.PI * 2)) * (1 - .38 * bump(t, 5.1, .14) - .24 * bump(t, 5.34, .18));
    const k = Math.max(0, Math.min(1, (g - .45) / .55));
    const look = -.075 * (ease((t - 2.8) / .6) - ease((t - 4.6) / .6));
    const open = Math.min(blink(t, 1.3), blink(t, 6.4));
    filMat.color.copy(dim).lerp(hot, k);
    filGlow.material.opacity = .25 + .75 * k;
    back.material.opacity = Math.min(1, g ** 1.5) * (style === 'glass' ? .8 : .6);
    halo.material.opacity = .25 + .45 * g;
    bulbLight.intensity = 2.4 * g;
    eyes.forEach(E => placeEye(E, look, open));
    bulb.rotation.y = .1 * Math.sin(t / CALM * Math.PI * 2);
    renderer.render(scene, camera);
  }
  if (frozen != null) { frame(frozen); return; }
  const t0 = performance.now();
  renderer.setAnimationLoop(now => frame((now - t0) / 1000));
}
