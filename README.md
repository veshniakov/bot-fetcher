# Telegram Video Fetcher Bot

Личный Telegram-бот для скачивания видео по ссылкам YouTube и Instagram.

Пользователь отправляет ссылку, бот сначала показывает preview с названием, автором, источником, длительностью и обложкой. Полный файл скачивается только после подтверждения.

Бот работает на домашнем Debian-сервере через Docker Compose, long polling и локальный Telegram Bot API Server. Webhook и Vercel не используются.

## Что поддерживается

- YouTube видео.
- YouTube Shorts.
- Instagram Reels.
- Instagram video posts.
- Instagram Stories по прямой ссылке на конкретную Story.

Не поддерживаются playlists, live streams, Instagram Highlights, массовая загрузка всех Stories профиля, приватный контент без доступа аккаунта, платный/DRM/закрытый контент.

## Как работает отправка больших файлов

Проект использует Local Telegram Bot API Server в режиме `--local`.

Это меняет лимит отправки:

- обычный cloud Bot API: до 50 MB;
- Local Bot API Server: загрузка файлов до 2000 MB.

Алгоритм:

1. Пользователь отправляет ссылку.
2. Бот получает metadata без скачивания полного файла.
3. Пользователь подтверждает скачивание.
4. Бот скачивает готовую версию до 720p.
5. Если файл больше лимита Local Bot API Server, бот пробует готовые варианты 480p и 360p.
6. Бот отправляет файл в Telegram.
7. После успешной отправки временный файл удаляется из `data/work`.

Тяжёлого ffmpeg-перекодирования в основном сценарии нет. `ffmpeg` остаётся в образе, потому что yt-dlp может использовать его для merge/remux.

После успешной отправки файл хранится на стороне Telegram. Удаление временного файла из `data/work` не удаляет видео из чата пользователя.



## Создание бота через BotFather

1. Откройте Telegram и найдите `@BotFather`.
2. Отправьте `/newbot`.
3. Задайте имя и username бота.
4. Скопируйте токен в `.env` как `BOT_TOKEN`.

## Telegram API ID и API Hash

Для Local Bot API Server нужны `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`.

Их получают на:

```text
https://my.telegram.org
```

Секреты храните только в локальном `.env`.

## Настройка .env

Создайте `.env` из примера:

```bash
cp .env.example .env
```

Минимум:

```env
BOT_TOKEN=
ADMIN_USER_ID=

TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_API_BASE_URL=http://telegram-bot-api:8081
TELEGRAM_LOCAL_MODE=true
MAX_TELEGRAM_UPLOAD_MB=2000
TELEGRAM_REQUEST_TIMEOUT_SECONDS=1800
```

Перед переходом с cloud Bot API на Local Bot API Server нужно один раз выполнить `logOut` у cloud API. В деплое это делается перед запуском новой связки контейнеров.

## Запуск

```bash
docker compose up -d --build
```

Логи бота:

```bash
docker logs -f telegram-video-fetcher-bot
```

Логи Local Bot API Server:

```bash
docker logs -f telegram-bot-api
```

Остановка:

```bash
docker compose down
```

Перезапуск:

```bash
docker compose restart
```

## Обновление yt-dlp

```bash
docker compose build --no-cache bot
docker compose up -d
```

## Instagram cookies/session

Для yt-dlp можно положить cookies в Netscape-формате:

```text
data/cookies/cookies.txt
```

Для Instagram Stories используется Instaloader session:

```bash
docker compose run --rm bot python -m instaloader --login=your_instagram_username --sessionfile=/data/cookies/instagram.session
```

Пароль вводится интерактивно и не должен сохраняться в `.env`, README или коде.

## Развертывание на сервере

Подключение:

```bash
ssh user@your-server-ip
```

Переход в директорию проекта:

```bash
cd bot-downloader
```

Проверенная среда:

- Linux (Debian 12/13, Ubuntu 22.04/24.04).
- Docker Engine и Docker Compose plugin установлены.

Первый переход на Local Bot API Server:

```bash
docker compose down
set -a
. ./.env
set +a
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/logOut"
docker compose up -d --build
```

Обычный запуск/обновление:

```bash
docker compose up -d --build
```

Проверка:

```bash
docker ps
docker logs -f telegram-bot-api
docker logs -f telegram-video-fetcher-bot
docker compose exec bot sh -lc "df -h /data && ls -la /data"
```

Рабочие данные на HDD:

```text
data/work
data/cache
data/cookies
data/telegram-bot-api
```

Внутри контейнера бота:

```text
/data/work
/data/cache
/data/cookies
```

После успешной отправки временные видео удаляются из `data/work`. Local Bot API Server может хранить свои служебные данные в `data/telegram-bot-api`.

## Структура

```text
bot-downloader/
  app/
  data/
    work/
    cache/
    cookies/
    telegram-bot-api/
  downloader/
  storage/
  telegram/
  utils/
  video/
  Dockerfile
  docker-compose.yml
  requirements.txt
  .env
  .env.example
  .gitignore
  README.md
```

`.env`, `data/`, cookies и session-файлы не должны попадать в Git.
