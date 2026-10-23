# Морзик

Морзик (Мурзик + Морзе) — личный помощник пользователя в Telegram, бот [@WaveWorkerBot](https://t.me/WaveWorkerBot) на [Hermes Agent](https://github.com/NousResearch/hermes-agent). Раньше бот звался Волной, как голосовое приложение; 22.10.2026 он стал отдельным персонажем и отдельным проектом.

## Персонаж

Чёрный мультяшный 3D-кот на дежурстве, в матовой кремовой гарнитуре с микрофоном, как саппорт на линии. Янтарные глаза чуть косят в разные стороны, и в это время высунут кончик языка: с виду простачок, на деле собранный и внимательный. Усы — светящаяся морзянка «·–··–».

- Холст со всеми вариантами и выбранным — доска «Кот·2·2»: `design/canvas/morzik-character/` (hosted: https://draftwall.pieces.run/c/morzik-character-2d81).
- Модель — three.js, `design/canvas/morzik-character/_cat2.js`. Голова нарочно видна изнутри (`BackSide`) — отсюда мягкое свечение морды; невидимая внешняя оболочка пишет только глубину, чтобы низ ушей и наушников не просвечивал. Профили `LatheGeometry` — снизу вверх, иначе поверхность вывернута.
- Анимация — цикл 8 с: свет дышит, моргает (1-я и 6-я с), собирает зрачки к центру и оглядывается влево-вправо (2,4–4,9 с, язык в это время спрятан), снова косит, на 5-й с чуть вздрагивает свет, в конце дёргает ухом.
- Доски грузят не модули, а собранные бандлы (`_cat2.bundle.js` и др.): draftwall держит доски в песочнице, где ES-модули не грузятся. Команда пересборки — в начале `_three.js`.
- Отвергнутые и промежуточные варианты (лампочки, фонари, другие коты) — на том же холсте.

## Аватарка

`design/avatar/`: `morzik-800.mp4` (анимированная, 800×800, 8 с, H.264 без звука), `morzik-800.png` / `.jpg` (статичный кадр на 1,0 с). Кот опущен в кадре на `shiftY: .35`, чтобы уши и наушники не срезала шапка профиля Telegram. Ава отзеркалена по горизонтали при сборке (`hflip` в `render.cjs`): Морзик смотрит влево, микрофон и хвост на другой стороне. Холст не отзеркален.

Пересобрать: `NODE_PATH=<папка с puppeteer-core>/node_modules node design/avatar/render.cjs [fps=30] [кадр=1.0]` (нужны Google Chrome и ffmpeg). `design/avatar/render.html` без параметров показывает живую анимацию.

Ставится боту методом Bot API `setMyProfilePhoto` с `InputProfilePhotoAnimated` (MPEG4, `main_frame_timestamp` — кадр для статичной авы).

## Профиль бота

Поставлено 22.10.2026 через Bot API (`setMyName`, `setMyShortDescription`, `setMyDescription`, `setMyProfilePhoto`):

- Имя: «Морзик» (юзернейм остался `@WaveWorkerBot`).
- Короткое описание (профиль и ссылка): «Личный помощник пользователя, всегда на связи: почта, напоминания, дела и большие задачи в Helm 🐈‍⬛»
- Описание (пустой чат): «Привет, я Морзик — личный помощник пользователя. Сижу на линии: гляну почту, напомню о важном, найду что нужно, а большую работу передам агентам в Helm. Пиши как другу, коротко и по делу.»
- Ава: `design/avatar/morzik-800.mp4`, статичный кадр `main_frame_timestamp: 1.0`.

## Где живёт бот

Сам бот — в `~/.hermes` на Mac (не в этом репозитории, там токены):

- `SOUL.md` — личность и манера Морзика. В речи он домашний кот, а не дежурный: без «на связи», «принял», «дежурю» (гарнитура осталась только во внешности).
- `skills/personal/` — `helm` (передать работу в Helm через Helm MCP), `action-items` (список дел), `usage-report` (расход), `dreamer`.
- `plugins/morzik-chat/` (до 23.10.2026 — `volna-chat`, тулсет `volna`, теперь `morzik`) — разбивка ответа на несколько сообщений и статьи Telegraph (`publish_article`). Короткий ответ (до 500 знаков, до 3 абзацев, без кода и списков) уходит по абзацам: мысли Морзик разделяет пустой строкой. Старый маркер `[[split]]` больше не используется; если проскочит, плагин его вырезает.
- `config.yaml` → `mcp_servers`: `email` (`https://mcp-email.pieces.run/mcp`, раньше был на Railway), `semafor`, `helm` (`https://helm.pieces.run/mcp`, OAuth, вход `hermes mcp login helm`).
- Голосовые: `config.yaml` → `stt` — OpenAI `gpt-4o-transcribe`, язык `ru`, расшифровка в чат не дублируется (`echo_transcripts: false`); ключ `OPENAI_API_KEY` в `~/.hermes/.env`.
- Без системных сообщений Hermes в Telegram: `platforms.telegram.gateway_restart_notification: false` (нет «restarting» / «online»), `display.platforms.telegram`: `suppress_warning_notifications: true`, `long_running_notifications: false`, `cleanup_progress: true`. Ответы «⚡ Interrupting current task» выключены (`display.busy_ack_enabled: false`), одноразовые подсказки Hermes помечены показанными (`onboarding.seen`, `onboarding.profile_build: off`). Плашку `/new` («✨ Session reset!» с моделью и подсказкой) режет плагин `morzik-chat`; `/clean` теперь переписывается в `/new` без заголовка. `/start` от пользователя плагин превращает в просьбу коротко поздороваться: Морзик отвечает приветствием своими словами (сам Hermes `/start` игнорирует).
- Перезапуск после правок: `hermes gateway restart`.
