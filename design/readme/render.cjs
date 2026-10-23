// README banner: frames of banner.html → morzik-banner.gif (one 8 s loop).
// Needs puppeteer-core (NODE_PATH to the folder with it), Google Chrome and ffmpeg:
//   NODE_PATH=<folder>/node_modules node render.cjs [fps=15]
const puppeteer = require('puppeteer-core');
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
const fps = +(process.argv[2] || 15);
const here = __dirname, frames = fs.mkdtempSync('/tmp/morzik-banner-');
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 960, height: 320 });
  await page.goto('file://' + path.join(here, 'banner.html?manual'), { waitUntil: 'networkidle0' });
  await page.evaluate('document.fonts.ready');
  const loop = await page.evaluate('window.loop'), n = Math.round(loop * fps);
  const banner = await page.$('.banner');
  for (let i = 0; i < n; i++) {
    await page.evaluate(t => window.frameAt(t), i / fps);
    await banner.screenshot({ path: path.join(frames, String(i).padStart(4, '0') + '.png') });
  }
  await browser.close();
  const out = path.join(here, 'morzik-banner.gif');
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(fps), '-i', path.join(frames, '%04d.png'),
    '-vf', 'split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a', '-loop', '0', out]);
  fs.rmSync(frames, { recursive: true, force: true });
  console.log(`done: ${out}, ${n} frames @ ${fps}fps`);
})().catch(e => { console.error(e); process.exit(1); });
