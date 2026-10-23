// Экспорт аватарки Морзика: кадры цикла → MP4 для Telegram и PNG/JPG статичного кадра.
// Картинка отзеркалена по горизонтали (hflip): в кадре авы Морзик смотрит и наклонён влево. Сцена при этом та же, что на холсте.
// Нужны puppeteer-core (NODE_PATH на папку с ним), Google Chrome и ffmpeg:
//   NODE_PATH=<папка>/node_modules node render.cjs [fps=30] [still=1.0]
const puppeteer = require('puppeteer-core');
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
const fps = +(process.argv[2] || 30), still = +(process.argv[3] || 1.0);
const here = __dirname, frames = fs.mkdtempSync('/tmp/morzik-frames-');
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 400, height: 400 });
  await page.goto('file://' + path.join(here, 'render.html?size=400'), { waitUntil: 'load' });
  await page.waitForFunction('window.renderAt');
  const loop = await page.evaluate('window.loop'), n = Math.round(loop * fps);
  const save = async (t, file) => fs.writeFileSync(file, Buffer.from((await page.evaluate(t => window.renderAt(t), t)).split(',')[1], 'base64'));
  for (let i = 0; i < n; i++) { await save(i / fps, path.join(frames, String(i).padStart(4, '0') + '.png')); if (i % 30 === 0) console.log(`frame ${i}/${n}`); }
  await save(still, path.join(frames, 'still.png'));
  await browser.close();
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(fps), '-i', path.join(frames, '%04d.png'), '-vf', 'hflip', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-crf', '18', '-movflags', '+faststart', '-an', path.join(here, 'morzik-800.mp4')]);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', path.join(frames, 'still.png'), '-vf', 'hflip', path.join(here, 'morzik-800.png')]);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', path.join(here, 'morzik-800.png'), '-q:v', '2', path.join(here, 'morzik-800.jpg')]);
  fs.rmSync(frames, { recursive: true, force: true });
  console.log(`done: ${n} frames, ${loop}s @ ${fps}fps`);
})().catch(e => { console.error(e); process.exit(1); });
