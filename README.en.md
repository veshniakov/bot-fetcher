# Telegram Video Fetcher Bot

[🇷🇺 Русский](README.md) | 🇬🇧 English

A self-hosted, lightweight Telegram bot for downloading and delivering videos from YouTube and Instagram directly into Telegram chats.

Features an interactive preview with video title, author, duration, and thumbnail before downloading, and uses a local Telegram Bot API Server to support file uploads up to **2 GB**.

---

## 🌟 Key Features

- **Multi-Platform Support:**
  - **YouTube:** Standard videos and YouTube Shorts.
  - **Instagram:** Reels, posts, carousels/albums, and Stories.
  - **TikTok:** Clean video downloads without watermarks.
  - **Twitter / X, Reddit, Pinterest, VK Video**.
- **Audio Extraction (MP3):**
  - Extract pristine audio streams directly into MP3 with preserved ID3 tags (artist, title, cover art) for the Telegram audio player.
- **Resolution & Quality Selection:**
  - Choose between **1080p FHD**, **720p HD**, **480p Economy**, or **MP3 Audio**.
- **Live Progress Bar:**
  - Real-time download progress reporter showing percentage, speed, and ETA with flood-control rate limiting.
- **Quick Mode (`/mode`):**
  - Toggle auto-download for short clips (Shorts, Reels, TikTok <= 5 min) without requiring manual button confirmation.
- **Album / Carousel Delivery:**
  - Multi-item posts and galleries sent as native Telegram `MediaGroup` albums (up to 10 photos/videos).
- **Large File Support (up to 2000 MB):**
  - Uses a self-hosted `telegram-bot-api` local server container alongside the bot.
  - Transmits local file paths (`is_local=True`) directly to Telegram without double-transfer network overhead.
- **Resilient YouTube Engine:**
  - Uses `yt-dlp` configured with mobile client extraction (`android`, `ios`, `mweb`) to bypass Google's 403 Forbidden / SABR anti-bot blocks.
  - Automatic fallback retry without cookies if session cookies expire.
- **Quality Fallback Strategy:**
  - Downloads ready-to-stream formats up to selected resolution (H.264 / AAC).
  - Automatically attempts 480p and 360p if the file exceeds the maximum upload limit.
- **Concurrency Protection:**
  - Concurrency limited via `asyncio.Semaphore(10)` and per-user active task guards.
- **Background Storage Maintenance:**
  - Periodically cleans up task directories and temporary downloads according to configurable TTL.
- **Proxy Support:**
  - Optional SOCKS5 / HTTP proxy configuration via `PROXY_URL` for restricted network environments.

---

## 🚀 Quick Start

### Prerequisites

- Linux host (Debian, Ubuntu, etc.)
- Docker and Docker Compose plugin (`docker compose`)

### 1. Clone the repository

```bash
git clone https://github.com/veshniakov/bot-fetcher.git
cd bot-fetcher
```

### 2. Configure Environment

Copy the example configuration file:

```bash
cp .env.example .env
```

Edit `.env` and provide your credentials:

```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
ADMIN_USER_ID=123456789

# Obtained from https://my.telegram.org
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef

# Local Telegram Bot API configuration
TELEGRAM_API_BASE_URL=http://telegram-bot-api:8081
TELEGRAM_LOCAL_MODE=true
MAX_TELEGRAM_UPLOAD_MB=2000
TELEGRAM_REQUEST_TIMEOUT_SECONDS=1800

# Video & Storage
MAX_VIDEO_HEIGHT=720
TELEGRAM_CLOUD_LIMIT_MB=50
FFMPEG_PRESET=veryfast
WORKDIR=/data/work
CACHE_DIR=/data/cache
COOKIES_DIR=/data/cookies

# Optional: SOCKS5/HTTP Proxy
# PROXY_URL=socks5://127.0.0.1:20170
```

> **Note on Local Bot API:** If switching a bot token from the default Telegram cloud API to a local Bot API server, log out the token once from the cloud API first:
> ```bash
> curl -s "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/logOut"
> ```

### 3. Start the Services

```bash
docker compose up -d --build
```

View bot logs:

```bash
docker logs -f telegram-video-fetcher-bot
```

View local Telegram Bot API logs:

```bash
docker logs -f telegram-bot-api
```

---

## 🛠️ Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `BOT_TOKEN` | *Required* | Telegram Bot token from [@BotFather](https://t.me/BotFather) |
| `ADMIN_USER_ID` | `None` | Telegram numeric ID of the admin user for `/stats` access |
| `TELEGRAM_API_ID` | *Required* | Telegram App API ID from [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_API_HASH` | *Required* | Telegram App API Hash from [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_API_BASE_URL` | `http://telegram-bot-api:8081` | URL of the local Bot API container |
| `TELEGRAM_LOCAL_MODE` | `true` | Enables zero-copy local file transfers (`--local` mode) |
| `MAX_TELEGRAM_UPLOAD_MB` | `2000` | Upload limit for local Bot API server (in MB) |
| `MAX_VIDEO_HEIGHT` | `720` | Maximum video resolution target height (e.g., 720, 1080) |
| `PROXY_URL` | `None` | Optional SOCKS5 / HTTP outbound proxy for downloaders |
| `PENDING_TASK_TTL_MINUTES` | `30` | Expiration time for unconfirmed download tasks |

---

## 📂 Project Layout

```text
bot-downloader/
├── app/
│   ├── config.py       # Dataclass-based settings loader
│   ├── main.py         # Bot initialization and lifecycle loop
│   ├── router.py       # Message & callback event handlers
│   ├── stats.py        # Audience & system metrics manager
│   └── tasks.py        # In-memory pending task store
├── downloader/
│   ├── base.py                     # Custom exception definitions
│   ├── platform_detector.py        # URL matching & extraction
│   ├── ytdlp_downloader.py         # yt-dlp downloader engine
│   └── instagram_story_downloader.py # Instaloader story handler
├── video/
│   ├── metadata.py     # Video metadata data models
│   └── probe.py        # ffprobe media stream analyzer
├── telegram/
│   ├── captions.py     # Formatting captions & descriptions
│   ├── keyboards.py    # Inline & reply keyboards
│   └── sender.py       # Telegram delivery & upload logic
├── storage/
│   ├── cleanup.py      # Automated task cleanup routines
│   └── paths.py        # File path & directory helpers
├── docker-compose.yml  # Multi-container compose definition
├── Dockerfile          # Python 3.12 slim + ffmpeg environment
└── requirements.txt    # Python dependencies
```

---

## 🔒 Security & Privacy

- `.env`, `/data`, session credentials, and cookies are explicitly excluded in `.gitignore`.
- No sensitive keys, user IDs, or personal hostnames are committed into Git history.
- Run private sessions or cookies only within the persistent `./data/cookies` directory.

---

## 📄 License

MIT License. Feel free to modify and adapt for personal or public use.
