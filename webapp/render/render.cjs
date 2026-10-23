// Морзик для экрана «Скоро»: цикл кадров с прозрачным фоном → видео с альфа-каналом в двух форматах:
// HEVC (.mov, hvc1) для Safari и Telegram на iPhone/Mac, VP9 (.webm) для Chrome и Telegram на Android; плюс PNG-постер.
// Нужны puppeteer-core (NODE_PATH на папку с ним), Google Chrome и ffmpeg с hevc_videotoolbox (macOS):
//   NODE_PATH=<папка>/node_modules node render.cjs [fps=30]
const puppeteer = require('puppeteer-core');
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
const fps = +(process.argv[2] || 30), size = 360;
const here = __dirname, out = path.join(here, '..', 'public'), frames = fs.mkdtempSync('/tmp/morzik-dizzy-');
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--allow-file-access-from-files'] });
  const page = await browser.newPage();
  await page.setViewport({ width: size, height: size });
  await page.goto('file://' + path.join(here, 'render.html') + '?size=' + size, { waitUntil: 'load' });
  await page.waitForFunction('window.renderAt');
  const loop = await page.evaluate('window.loop'), n = Math.round(loop * fps);
  const save = async (t, file) => fs.writeFileSync(file, Buffer.from((await page.evaluate(t => window.renderAt(t), t)).split(',')[1], 'base64'));
  for (let i = 0; i < n; i++) { await save(i / fps, path.join(frames, String(i).padStart(4, '0') + '.png')); if (i % 60 === 0) console.log(`frame ${i}/${n}`); }
  await browser.close();
  const input = ['-y', '-loglevel', 'error', '-framerate', String(fps), '-i', path.join(frames, '%04d.png')];
  execFileSync('ffmpeg', [...input, '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '32', '-row-mt', '1', '-an', path.join(out, 'morzik-dizzy.webm')]);
  execFileSync('ffmpeg', [...input, '-c:v', 'hevc_videotoolbox', '-pix_fmt', 'bgra', '-alpha_quality', '0.8', '-q:v', '60', '-tag:v', 'hvc1', '-an', path.join(out, 'morzik-dizzy.mov')]);
  fs.copyFileSync(path.join(frames, '0000.png'), path.join(out, 'morzik-dizzy.png'));
  fs.rmSync(frames, { recursive: true, force: true });
  console.log(`done: ${n} frames, ${loop}s @ ${fps}fps`);
})().catch(e => { console.error(e); process.exit(1); });
