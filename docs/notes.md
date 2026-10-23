# Морзик: как всё устроено

Подробные заметки по устройству бота, персонажа и приложения. Обзор — в [README](../README.md).

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

## Приложение

Кнопка меню в чате («Морзик» слева от поля ввода, `setChatMenuButton` с `web_app`) открывает Mini App: https://morzik.pieces.run (pieces, piece `morzik`, статика из `webapp/public/`, nginx на порту 80). Пока там экран «Скоро»: голова Морзика с глазами-спиральками и подпись. Макет и варианты — `design/canvas/mini-app/` (hosted: https://draftwall.pieces.run/c/mini-app-56e8), выбран «А».

- Голова — заранее отрендеренное видео с прозрачным фоном: `morzik-dizzy.mov` (HEVC с альфой, для WebKit: Telegram на iPhone и Mac, Safari) и `morzik-dizzy.webm` (VP9 с альфой, для Chrome и Telegram на Android); страница выбирает по User-Agent, пока грузится — постер `morzik-dizzy.png`.
- Модель та же (`_cat2.js`), режимы `headOnly`, `dizzy`, `transparent` (и `stars`, не используется). На прозрачном фоне светящиеся детали непрозрачные, иначе усы выпадают из альфы.
- Пересобрать видео: `NODE_PATH=<папка с puppeteer-core>/node_modules node webapp/render/render.cjs [fps=30]` (Chrome, ffmpeg с `hevc_videotoolbox`, только macOS). Выложить: `upload_code` для piece `morzik` из `webapp/public/`.

## Где работать над проектом

С 23.10.2026 проект «Морзик» в Хельме живёт на `sketch-server`: репозиторий `~/projects/Morzik` у пользователя `sketch-server-mi` (`origin` по HTTPS, пушит аккаунт SketchPiece). Бот на той же машине, к нему прямо через `sudo -u morzik …`. У Claude на сервере те же глобальные инструкции, память этого проекта, скиллы `pieces`, `canvas`, `artifact-design`, `impeccable`, MCP `pieces` и хук-сторож pieces. Копия на Маке (`~/Documents/Projects/Morzik`) больше не основная. Всё, что собирается только на macOS (мост `bridge/` на Swift, рендер видео аватарки), по-прежнему делается на Маке: подтянуть изменения с сервера, собрать, закоммитить.

## Где живёт бот

С 23.10.2026 бот живёт на домашнем сервере `sketch-server` (старый ноутбук с Ubuntu, в tailnet `sketch-server.tail923acf.ts.net`), у пользователя `morzik` без sudo, в `/home/morzik/.hermes` (не в этом репозитории, там токены). Как сервер настроен и как Морзик туда переехал — в репозитории `~/Documents/Projects/sketch-server` (`setup/60-…`, `setup/61-…`, `morzik/`). На Маке остались только мост к Календарю и Напоминаниям и Semafor; старый `~/.hermes` на Маке лежит как резервная копия, его LaunchAgent'ы убраны в `~/Library/LaunchAgents/disabled-moved-to-sketch-server/`.

На сервере:

- службы — systemd user units пользователя `morzik`: `hermes-gateway` (Telegram, cron, api_server; видит экран `DISPLAY=:1`), `morzik-voice` (голосовой прокси), `morzik-screen` (TigerVNC 1440×900), `morzik-wm` (Openbox), `morzik-chrome` (Chrome с профилем `~/.config/morzik-chrome`, CDP на `127.0.0.1:9222`), `morzik-novnc`. Управлять: `sudo -u morzik XDG_RUNTIME_DIR=/run/user/$(id -u morzik) systemctl --user …`, лог шлюза — `/home/morzik/.hermes/logs/gateway.log`.
- экран Морзика смотреть и входить в аккаунты — noVNC `https://sketch-server.tail923acf.ts.net:6080/vnc.html` (только tailnet, пароль: `sudo cat /home/morzik/.vnc/password.txt` на сервере). Браузер (Browser Use, `browser_exec`) и computer use (cua-driver) работают в этом же Chrome на этом же экране, так что входы, сделанные руками, Морзик видит.
- Telegram: `mcp_servers.semafor` — Semafor Server на этом же сервере (`http://127.0.0.1:8790/mcp`, заголовок `Authorization: ${SEMAFOR_MCP_AUTH}` из `.env`), с 23.10.2026. Это отдельный headless-клиент Telegram только для чтения, от Мака не зависит; подробнее в разделе «Telegram (Semafor Server)». До этого был `ssh` на Мак ключом `~/.ssh/semafor_mac` к `semafor-mcp` из Semafor (forced command в `authorized_keys` Мака); ключ остался, старый блок — в `config.yaml.bak-2026-10-23-before-semafor-server`.
- Календарь и Напоминания: `mcp_servers.apple.url` = `https://<mac>.tail923acf.ts.net:8765/mcp` (мост открыт в tailnet через `tailscale serve` на Маке).
- часовой пояс сервера — <local tz>, как у расписаний.
- у бота свой вход в Claude (подписка) — Claude Code пользователя `morzik`.
- задача «Сервер: обновления» (каждый день в 10:00): сторож `scripts/server_updates.py` читает список обновлений сервера, и Морзик пишет пользователю, только когда список изменился. Сам обновления не ставит (нет sudo), подсказывает `upgrade.sh` из `sketch-server`.

Как было на Маке (настройки те же):

- `SOUL.md` — личность и манера Морзика. В речи он домашний кот, а не дежурный: без «на связи», «принял», «дежурю» (гарнитура осталась только во внешности). Про свою фоновую работу говорит по-человечески, без технических подробностей и цифр; точное время называет, только когда оно важно пользователю или он спросил. Если для ответа надо куда-то сходить (почта, календарь, поиск), сначала пишет одно-два слова, что пошёл смотреть, каждый раз по-разному, а дальше работает молча.
- `skills/personal/` — `helm` (передать работу в Helm через Helm MCP), `action-items` (список дел), `usage-report` (расход), `dreamer`.
- `plugins/morzik-chat/` (до 23.10.2026 — `volna-chat`, тулсет `volna`, теперь `morzik`) — разбивка ответа на несколько сообщений и статьи Telegraph (`publish_article`). Короткий ответ (до 500 знаков, до 3 абзацев, без кода и списков) уходит по абзацам: мысли Морзик разделяет пустой строкой. Старый маркер `[[split]]` больше не используется; если проскочит, плагин его вырезает. «Печатает…» появляется только прямо перед каждым сообщением, на паузу по его длине (~25 знаков/с, 1,2–4 с). Из реплик посреди хода в чат проходит только первая, если она короткая и по-русски (без «Let me read it» между инструментами); если Морзик полез в инструменты молча, через 6 с плагин сам пишет короткое «ща» (несколько вариантов, подряд не повторяются).
- `config.yaml` → `mcp_servers`: `email` (`https://mcp-email.pieces.run/mcp`, раньше был на Railway), `semafor`, `helm` (`https://helm.pieces.run/mcp`, OAuth, вход `hermes mcp login helm`), `lotsia` (поездки, см. раздел «Поездки (Lotsia)»). `pieces` (`https://pieces.run/mcp`, хостинг: деплой, логи, базы; заголовок `Authorization: ${PIECES_MCP_AUTH}` из `~/.hermes/.env`, токен — из подключения агента на https://pieces.run/connect 23.10.2026, лежит и в `~/.config/pieces/token` пользователя `morzik`; инструкция — скилл `skills/devops/pieces`).
- Подписки на события MCP-серверов: Морзик реагирует на события сразу, без проверок по таймеру. Работает по черновому стандарту MCP Events ([SEP-3415](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3415)), режим poll. Подписаться можно на любой сервер из `mcp_servers`, который поддерживает события.
  - Подписка — файл `subscriptions/<id>.md`. В шапке `server`, `event`, `arguments` (JSON) и, если нужно, `enabled: false`. Ниже — инструкция Морзику, что делать с событием. Добавить подписку = добавить файл.
  - Задача cron «Подписки» (`6b373df40d0d`, раз в минуту, скилл `subscriptions`) запускает `scripts/mcp_events.py`. Скрипт опрашивает все подписки и будит Морзика, только если пришли события или подписка сломалась либо снова заработала. В тихие минуты модель не запускается. Курсоры лежат в `state/subscriptions/<id>.json`. Если агент упадёт посреди разбора, пачка событий не повторится.
  - `python3 ~/.hermes/scripts/mcp_events.py status` показывает подписки и их состояние. `… events <server>` показывает, на что у сервера можно подписаться.
  - Подписки: `mail` (`email.received` от `email`) — сервер присылает каждое входящее письмо без сортировки, Морзик сам решает, что важно сказать пользователю, а что пометить прочитанным; три подписки на поездки от `lotsia` (см. «Поездки (Lotsia)»).
  - `semafor` тоже умеет события: `telegram.message_received` (см. «Telegram (Semafor Server)»). Подписки на него пока нет.
  - Ограничения: пока только HTTP-серверы с заголовком авторизации (не stdio, не OAuth). Скрипт нужен, потому что Hermes ещё не умеет MCP Events сам. Когда научится или Морзик переедет на сервер, скрипт заменит прямая подписка (вебхук).
- `plugins/morzik-voice-status/` — пока Морзик думает, в чате тихо: «печатает…», которое Hermes шлёт весь ход, глушится. «Записывает голосовое…» показывается только пока работает `text_to_speech`.
- Голосовые: `config.yaml` → `stt` — OpenAI `gpt-4o-transcribe`, язык `ru`, расшифровка в чат не дублируется (`echo_transcripts: false`); ключ `OPENAI_API_KEY` в `~/.hermes/.env`.
- Ответы голосом: `config.yaml` → `tts` — ElevenLabs, модель `eleven_v4` (с 23.10.2026, до этого `eleven_v3`), голос `huzlgRetWoDUAnVe8wEL`; ключ `ELEVENLABS_API_KEY` в `~/.hermes/.env`.
- `plugins/morzik-voice-mode/` — режим «отвечать голосом». Пользователь просит словами («отвечай голосом», «я за рулём»), Морзик включает его инструментом `voice_replies`. Пока режим включён, к каждому сообщению из Telegram добавляется пометка: ответить через `text_to_speech`, коротко, ссылки и адреса — текстом рядом. Каждое сообщение продлевает режим; после 30 минут тишины он выключается сам, по просьбе «давай текстом» — сразу. Состояние — `state/voice_mode.json` (`on`, `last`), переживает перезапуск. Потом этот же файл сможет переключать автоматизация в «Командах» по CarPlay.
- Без системных сообщений Hermes в Telegram: `platforms.telegram.gateway_restart_notification: false` (нет «restarting» / «online»), `display.platforms.telegram`: `suppress_warning_notifications: true`, `long_running_notifications: false`, `cleanup_progress: true`. Ответы «⚡ Interrupting current task» выключены (`display.busy_ack_enabled: false`), одноразовые подсказки Hermes помечены показанными (`onboarding.seen`, `onboarding.profile_build: off`). Плашку `/new` («✨ Session reset!» с моделью и подсказкой) режет плагин `morzik-chat` (фоновая самопроверка Hermes при этом работает и правит скиллы и память, просто молча); `/clean` теперь переписывается в `/new` без заголовка. В списке команд остались только `/restart` и `/clean` (остальные команды Hermes работают, если их набрать). Вместо `/new` теперь `/restart` (в Telegram он перезапускает сессию, а не шлюз Hermes; старый `/new` работает так же): команда сразу удаляется из чата, приходит «сессия перезапущена» и через 3 с тоже исчезает. `/start` от пользователя плагин превращает в просьбу коротко поздороваться: Морзик отвечает приветствием своими словами (сам Hermes `/start` игнорирует).
- В чате говорит только Морзик. Плагин `morzik-chat` запоминает, что написала модель (финальный ответ через хук `transform_llm_output`, реплики посреди хода, текст, который она передаёт инструментам вроде `send_message`), а также всё, что отправляют задачи по расписанию (и скриптовые без модели, например недельный отчёт по метрикам). Любой другой текст в чат пользователя — это Hermes. Его плагин либо выбрасывает, либо, если пользователю правда надо знать, заменяет короткой фразой Морзика (несколько вариантов):
  - ошибка ответа модели → «что-то я завис и не смог ответить…»;
  - лимит или квота → «я выдохся, лимит кончился…»;
  - шлюз перезапускается и придержал сообщение → «секунду, я перезагружаюсь…»;
  - сообщение не обработано, надо повторить → «ой, я прослушал…»;
  - сбой задачи по расписанию → «фоновая задача «<имя>» не сработала…»;
  - незнакомец написал боту → «мне написал кто-то незнакомый…»;
  - не удалось отправить вложение → «не получилось прислать файл».

  Остальное (отчёты самопроверки «💾 …», «шлюз перезапущен», подсказки, «нет домашнего канала» и т. п.) не доходит. Статусные пузыри (`send_or_update_status`: заполненность контекста, сжатие) тоже. Текст с эмодзи-меткой в начале (⚠️ ⏳ 💾 ✨ …) всегда считается Hermes. Всё отфильтрованное пишется в `~/.hermes/logs/gateway.log` строкой `morzik-chat: Hermes said …` (или `kept a Hermes status …`): по ней видно, что пришло и чем заменилось. Кнопки, которые ждут ответа (подтверждение опасной команды, вопрос с вариантами, предложение обновить Hermes), остаются как есть.
- Перезапуск после правок: `hermes gateway restart`.

## Поездки (Lotsia)

Морзик ведёт наши поездки в [Lotsia](https://lotsia.pieces.run): план по дням, перелёты, жильё, машина, коды броней и маршрут на карте. Код — `~/Documents/Projects/Lotsia` (сервер, сайт и MCP в одном сервисе на pieces, piece `lotsia`, база SQLite на диске `/data`). Сайт и MCP пускают по входу Google, у каждой поездки владелец и участники («смотрит» или «правит»).

- В Hermes: `config.yaml` → `mcp_servers.lotsia` (`https://lotsia.pieces.run/mcp`, заголовок `Authorization: ${LOTSIA_MCP_AUTH}`). Ключ — личный токен «Морзик» с https://lotsia.pieces.run/account (действует от имени аккаунта пользователя, отозвать там же), лежит в `~/.hermes/.env` на сервере.
- Инструменты: `list_trips`, `get_trip`, `find_booking` (по коду, номеру рейса, названию), `find_place` (координаты из OpenStreetMap), `list_changes`; `create_trip`, `update_trip`, `share_trip`, `delete_trip`, `import_trip`; `save_*` и `delete_*` для `place`, `region`, `day`, `flight`, `stay`, `car`, `route`. `save_*` меняют только переданные поля, `save_route` сам прокладывает дорогу по точкам. У записи можно указать `source` — id письма, откуда это взято, он виден в `list_changes`.
- Откуда данные: в `subscriptions/mail.md` есть абзац про брони. Письмо авиакомпании, Airbnb, отеля или проката → `find_booking` → обновить найденное или завести новое, поправить день, если план поменялся, и коротко сказать пользователю, что изменилось.
- События (по времени, их считает сервер Lotsia, Морзик только реагирует), подписки в `subscriptions/`:
  - `lotsia-checkin` — `checkin.opening`, `leadHours: 0`: открылась онлайн-регистрация на купленный рейс. Окно берётся из `checkIn.opensHoursBefore` рейса, иначе 24 ч.
  - `lotsia-upcoming` — `itinerary.upcoming`, за 24 ч до вылета, получения и сдачи машины, заселения.
  - `lotsia-attention` — `booking.attention`: за 21 день до начала брони, которая всё ещё `idea` или `agreed`.
- Об изменениях броней событий нет: о них Морзик узнаёт из почты сам.

## Telegram (Semafor Server)

Telegram пользователя Морзик читает через [semafor-server](../../semafor-server) (`~/Documents/Projects/semafor-server`, там README со всеми подробностями): headless-клиент на Python + Telethon, своя сессия Telegram «Semafor Server» (видна в Telegram → Настройки → Устройства), работает на sketch-server. Те же инструменты, что у MCP в Semafor на Маке, но Мак для этого не нужен.

- Только чтение, и это обеспечено ниже инструментов: любой запрос к Telegram, кроме методов чтения из белого списка, отбрасывается до сети. Отправить, отредактировать, удалить, поставить реакцию, вступить или пометить прочитанным нельзя. Чтение истории не трогает счётчики непрочитанного (проверено: 245 до и после чтения 50 сообщений).
- Служба `semafor-server` (systemd, системный пользователь `semafor`). Сессия лежит в `/var/lib/semafor-server` (0700), у пользователя `morzik` доступа к ней нет. Морзик получает только HTTP на `127.0.0.1:8790` и токен (`SEMAFOR_MCP_AUTH` в `.env`).
- Управление на сервере: `sudo semafor-server status | enable | disable | media on|off | lock | unlock | log [N] | token --new`. `lock` останавливает всё сразу, как passcode lock на Маке. Каждый вызов пишется в лог. После `token --new` надо обновить `SEMAFOR_MCP_AUTH` и перезапустить шлюз.
- Сейчас включены доступ и файлы, как в Semafor на Маке. `get_media` отдаёт файл прямо в ответе: фото как картинку, голосовые как аудио, остальное как файл до 40 МБ. Hermes сохраняет его к себе в кэш.
- `chat_id` в формате Bot API (`-100…` у каналов и супергрупп), с id из Semafor на Маке не совпадают. `@username` работает везде.
- События (MCP Events, poll): `telegram.message_received` — новое входящее сообщение. Аргументы подписки: `chats` (список chat_id или @username), `private` (все личные чаты с людьми, кроме ботов, архива и чатов без звука), `mentions` (упоминания и ответы пользователю в группах). Сервер присылает всё подряд, что важно, решает Морзик. Подписки пока нет; добавить — файл `subscriptions/<id>.md` с `server: semafor`, `event: telegram.message_received`, `arguments: {"private": true, "mentions": true}`.
- Обновить сервер: `deploy/deploy.sh` из репозитория semafor-server на Маке.

## Календарь и Напоминания Apple (Morzik Bridge)

`bridge/` — маленький MCP-сервер на Swift (EventKit), через который Морзик работает с нативными Календарём и Напоминаниями на Маке. Он сделан отдельным сервером, а не скриптом внутри Hermes, чтобы Морзик мог переехать на Linux и дальше ходить к Маку по сети.

- Установка и пересборка: `bridge/install.sh`. Скрипт собирает `~/Applications/MorzikBridge.app`, подписывает его сертификатом Apple Development (иначе разрешение на Календарь слетает при каждой пересборке) и запускает LaunchAgent `dev.sketchpiece.morzik-bridge`. Лог — `~/Library/Logs/morzik-bridge.log`.
- Доступ: при первом запуске macOS спрашивает про Календарь и Напоминания. Потом настройки в System Settings → Privacy & Security → Calendars / Reminders, пункт Morzik Bridge. Без доступа инструменты отвечают ошибкой «No access», а `status` показывает состояние.
- Слушает `127.0.0.1:8765`, путь `/mcp`, без токена отвечает 401. Токен лежит в `~/.config/morzik-bridge/token`, адрес и порт — в `~/.config/morzik-bridge/env`. `GET /health` работает без токена.
- Инструменты: `status`, `calendar_list_calendars`, `calendar_list_events`, `calendar_create_event`, `calendar_update_event`, `calendar_delete_event`, `reminders_list_lists`, `reminders_list`, `reminders_create`, `reminders_update`, `reminders_complete`, `reminders_delete`. Время без смещения считается временем Мака. Если у напоминания указано время, мост ставит на него будильник, иначе Напоминания не присылают уведомление.
- В Hermes: `config.yaml` → `mcp_servers.apple` (`http://127.0.0.1:8765/mcp`, заголовок `Authorization: ${MORZIK_BRIDGE_AUTH}` из `~/.hermes/.env`). Скилл `skills/personal/apple-calendar` объясняет, когда ставить напоминание в Apple, а когда свой cron; календарь и список Напоминаний Морзик выбирает по смыслу дела и по тому, где лежат похожие, а не по умолчанию. Стоковый `apple-reminders` (через `remindctl`) выключен.

### Мост, когда Морзик на сервере (сделано 23.10.2026)

Мост остаётся на Маке, он открыт только в tailnet, наружу в интернет не торчит:

1. На Маке: `tailscale serve --bg --https=8765 http://127.0.0.1:8765`. Мост будет доступен по адресу `https://<mac>.<tailnet>.ts.net:8765/mcp` только с устройств в tailnet.
2. Linux-сервер подключить к тому же tailnet.
3. В `config.yaml` Морзика поменять `mcp_servers.apple.url` на этот адрес, а `MORZIK_BRIDGE_AUTH` перенести в `.env` на сервере. Токен остаётся тем же.

Мак при этом должен быть включён и залогинен: EventKit работает только в сессии пользователя. Если мост не отвечает, Морзик так и говорит.

## Голосовой звонок (в работе)

Звонок Морзику голосом из Mini App: агент ElevenLabs «Морзик (тест)» (`agent_9101m5n51bngesp85ymwzr63ab6q`, голос `huzlgRetWoDUAnVe8wEL`, TTS `eleven_v4`) слушает и говорит, а думает сам Морзик в Hermes, с теми же SOUL, памятью и MCP, что в Telegram. ElevenLabs ходит в него как в Custom LLM.

```
ElevenLabs → https://sketch-server.<tailnet>.ts.net/v1/chat/completions (Tailscale Funnel, только этот путь)
           → голосовой прокси на sketch-server 127.0.0.1:8650 (voice/proxy.py)
           → Hermes api_server 127.0.0.1:8642, модель morzik-voice → Haiku 5.5 по подписке
```

- Hermes (`/home/morzik/.hermes/config.yaml` на сервере): `gateway.api_server` включён на `127.0.0.1:8642`, алиас `model_routes.morzik-voice` → `haiku` у `claude-subscription-directsdk-experimental` (Telegram остаётся на `opus`), `max_concurrent_runs: 2`; `agent.reasoning_overrides.haiku: low`; `platform_toolsets.api_server: [memory, session_search, skills, todo, web, morzik]` плюс все MCP (`email`, `apple`, `helm`, `semafor`). В голосе нет терминала, файлов, браузера, computer use, кода, субагентов и cron.
- Ключи в `~/.hermes/.env`: `API_SERVER_KEY` (сам Hermes, наружу не уходит) и `MORZIK_VOICE_KEY` (его хранит ElevenLabs как секрет Custom LLM). Там же `MORZIK_VOICE_HOST=127.0.0.1` и `MORZIK_VOICE_TRUSTED_PROXIES=127.0.0.1` (Funnel приходит с localhost).
- Прокси `voice/proxy.py` (на сервере systemd user unit `morzik-voice` пользователя `morzik`, ставится из репозитория sketch-server, `morzik/install.sh`; `voice/install.sh` — прежний LaunchAgent для Мака): пускает только `POST /v1/chat/completions` со своим ключом, модель всегда `morzik-voice`, лимит 30 запросов в минуту и 1500 в день, тело до 512 КБ. Белый список IP включается `MORZIK_VOICE_ALLOWED_IPS`; адрес звонящего берётся из последнего `X-Forwarded-For`, и только если запрос пришёл от доверенного туннеля. В стриме прокси выкидывает события Hermes, говорит «Секунду, гляну... », когда Морзик берётся за инструмент молча, и заменяет сырой текст ошибки фразой («выдохся, лимит кончился» / «что-то завис»).
- Сцепка ходов: ElevenLabs присылает разговор заново текстом, без вызовов инструментов, и без неё Морзик на следующем ходу думал, что погоду придумал. Прокси после каждого ответа запоминает отпечаток разговора (с тем, что прозвучало) и id сессии Hermes; если следующий запрос продолжает ровно этот разговор, прокси шлёт `X-Hermes-Session-Id`, и Hermes берёт историю из своей базы, с инструментами. Не совпало (например, ответ перебили) — история как раньше, из запроса. В логе: `turn starts a chain` / `turn continues api-…`.
- В ElevenLabs: `LLM cascade timeout` поднят с 4 до 15 с (Settings → Advanced). С 4 с запросы с инструментами обрывались `custom_llm_error: LLM Cascade Error: TimeoutError`, хотя заполнитель уже прозвучал: ElevenLabs ждёт весь ответ. Значит, ход дольше 15 с (несколько инструментов подряд) всё равно оборвётся.
- ElevenLabs звонит с 34.59.11.47 (есть в их опубликованном списке исходящих адресов).
- Проверки: `python3 voice/check_proxy.py [url]` (что закрыто), `python3 -m unittest voice/test_proxy.py`, замер `VOICE_KEY=… python3 voice/bench.py --url …`.
- Funnel включён 23.10.2026: `ssh sketch-server-mi@sketch-server 'MORZIK_VOICE_TARGET=http://127.0.0.1:8650 sh -s' < voice/funnel.sh`. Наружу открыт порт 443 только с путём `/v1/chat/completions`; noVNC на 6080 остался только в tailnet. Выключить: `sudo tailscale funnel --https=443 off` на сервере. Публичная DNS-запись появилась примерно через 25 минут после включения. Проверено снаружи через реле Funnel: путь без ключа даёт 401, остальные пути 404, порты 6080 и 8642 закрыты; с ключом болтовня 3,7 с, погода с поиском 5,3 с («Секунду, гляну...» через 2,2 с). В логе прокси (`journalctl` пользователя `morzik`) виден настоящий адрес звонящего, так что белый список IP будет работать.

Замеры 23.10.2026 через прокси, медиана из 3 прогонов. «Первая фраза» здесь — время, когда ElevenLabs может начать говорить:

| Случай | Первая фраза | Весь ответ |
|---|---|---|
| Болтовня | 2,7 с | 2,7 с |
| Из памяти | 2,7 с | 2,7 с |
| Календарь (MCP `apple`) | 3,0 с («Секунду, гляну...») | 10,0 с |
| Погода (`web_search`) | 3,4 с («Секунду, гляну...») | 6,2 с |

Почему так:
- Подписочный провайдер запускает `claude` CLI на каждый вызов модели, это ~2 с даже при 95% кэша на промпте в 13 тыс. токенов. Hermes не стримит токены от провайдеров-процессов (`agent/turn_api_call.py::_should_stream`), поэтому ответ приходит целиком. Фразу перед инструментом модель пишет, но api_server её не отдаёт, отсюда заполнитель в прокси.
- Инструмент из MCP стоит три вызова модели: `tool_search` (MCP-инструменты отложены), сам инструмент, ответ. `tools.tool_search` настраивается только глобально, в Telegram его не трогали.
- Лимит подписки общий с Telegram-Морзиком на Opus: во время замеров 23.10 один раз упёрлись в лимит сессии.

Для Mini App (шаг 4): первая фраза агента — `{{greeting}}`, Mini App при старте звонка передаёт её случайной из набора приветствий (dynamic variables, переопределения для этого не нужны). Заполнители перед инструментом прокси тоже берёт случайно (`FILLERS` в `voice/proxy.py`, свои — `MORZIK_VOICE_FILLERS` через `|`).
