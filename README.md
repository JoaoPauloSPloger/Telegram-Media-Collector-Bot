# Telegram Media Collector Bot (TMCB)

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPLv3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-Local%20Server%20(2GB)-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api#using-a-local-bot-api-server)

**Telegram Media Collector Bot** is a high-performance, production-ready Telegram media extractor, downloader, and audio converter bot. Built on top of `aiogram 3`, `yt-dlp`, and a prioritized multi-tier extraction pipeline, TMCB allows users to download, convert, and clip media from virtually any platform directly within Telegram.

By pairing with a local **Telegram Bot API Server**, TMCB overcomes Telegram's standard 50 MB bot file-size limit and effortlessly uploads files up to **2 GB**.

---

## 🌟 Key Features

### 🚀 Resilient Multi-Tier Extraction Engine
The download pipeline follows the **Chain of Responsibility** pattern to guarantee maximum media availability:
- **Tier 1 (yt-dlp):** Universal extraction engine supporting YouTube, Instagram, Facebook, Reddit, Twitch, Vimeo, SoundCloud, and 1,000+ sites.
- **Spotify Engine (spotdl):** Dedicated Spotify track, album, and playlist downloading with automatic ID3 tagging and embedded album art.
- **Tier 2 (Cobalt & TikWM API):** High-speed, lightweight cloud fallbacks for Instagram Reels, TikTok (watermark-free), and Douyin.
- **Tier 3 (FxTwitter / FixupX & Gallery-dl):** Specialized scrapers for X (formerly Twitter) video previews, Bluesky embeds, and multi-image galleries.
- **OpenGraph Scraper:** Fallback meta-tag parser for direct MP4/WebM video streams embedded across the web.

### 🛡️ Local Telegram Bot API (2 GB Limit Bypass)
- Bypasses standard bot upload limits (50 MB) by operating with a self-hosted Telegram Bot API server.
- Supports local file streaming directly from disk, preventing memory bloat and accelerating upload speeds.

### ⏱️ Telegram Anti-Spam Scheduler
- Built-in scheduling queue designed to survive Telegram `RetryAfter` (429 Too Many Requests) flood restrictions.
- Handles exponential backoff automatically, preventing IP or token suspensions during peak load or broadcast events.

### 📊 Real-Time Interactive Dashboard (`/status` & `/stats`)
- High-contrast visual interface featuring color-coded indicator buttons and ASCII status metrics.
- Monitors live CPU, RAM, swap, disk usage, active download queues, and network throughput.
- Refreshable on demand via inline callbacks.

### 🌐 Instant Multilingual Support (`/setlang`)
- Complete internationalization across 5 languages: **English**, **Portuguese**, **Spanish**, **French**, and **German**.
- Users can switch their language at any time using `/setlang`, `/lang`, or `/language`.
- Transparent Terms of Service / EULA enforcement prior to first use.

### 🔎 Enhanced Inline Mode (`@TMCollector_bot`)
- Instant media sharing in any group or direct message without adding the bot.
- **Smart File Cache:** If a requested URL was previously processed, the bot instantly serves the media using its cached Telegram `file_id`.
- For new URLs, an inline button invites the user to initiate the high-speed download in private chat.

### 🔐 Secure Cookie Management (`/usecookies`)
- Allows users to upload their own `cookies.txt` (via document attachment or text message) to bypass age-restricted or private content (e.g., Instagram, YouTube member videos).
- Cookies are encrypted at rest using **AES-256 (Fernet)** with user-isolated cryptographic storage.
- Safely wipe your credentials at any time with `/clearcookies`.

### ✂️ In-Chat Media Conversion & Trimming
- Direct audio extraction: convert any video to 320 kbps MP3 or lossless WAV.
- Custom video trimming (`/clip 0:30 1:45 <url>`).
- Animated GIF generator directly from video files or links.

### 🤖 LLM-Powered Incident Insights
- Automatic error aggregation and forwarding to your preferred AI model (**OpenAI**, **Google Gemini**, **Anthropic**, **Groq**, or a local endpoint).
- Posts concise, structured SRE incident diagnostics directly to your administrative log channel.

---

## 📋 Command Reference

### General Commands
| Command | Description |
| :--- | :--- |
| `/start` | Initializes the bot, prompts language selection and EULA verification. |
| `/help` | Displays the interactive guide and usage examples in your language. |
| `/setlang`, `/lang` | Changes your language preference (EN, PT, ES, FR, DE). |
| `/privacy`, `/tos` | Displays the Privacy Policy and Terms of Service. |

### Media & Download Commands
| Command | Description |
| :--- | :--- |
| `/dl <url>`, `/download <url>` | Downloads video or audio from the specified link. |
| `/audio <url>`, `/mp3 <url>` | Downloads the media as an audio track (MP3/WAV). |
| `/clip <start> <end> <url>` | Extracts a specific segment (e.g., `/clip 1:00 2:30 https://...`). |
| `/cancelAll` | Cancels all currently active and queued downloads for the user. |
| *(Direct Link)* | Sending any valid URL directly to the bot initiates standard download. |
| *(File Upload)* | Sending any video/audio/document file opens the interactive conversion menu. |

### Settings & Cookies
| Command | Description |
| :--- | :--- |
| `/usecookies` | Upload a Netscape-formatted `cookies.txt` file or paste raw cookie text. |
| `/clearcookies` | Permanently deletes your stored cookies from the encrypted database. |

### Administration & Monitoring
| Command | Description |
| :--- | :--- |
| `/status`, `/stats` | Opens the live telemetry and hardware performance dashboard. |
| `/addadmin <id> <level> [pwd]` | Adds a new administrator (Level 1: Master, Level 2: Admin, Level 3: Aspiring). |
| `/promote <id>`, `/demote <id>` | Adjusts administrator rank. |
| `/dismiss <id>` | Revokes administrator privileges. |
| `/regenpsw <id>` | Generates a new secure password and securely messages it to the admin. |
| `/broadcast <password> <msg>` | Broadcasts a notification message to all registered users. |
| `/restart`, `/shutdown` | Safely restarts or shuts down the bot container. |

---

## 🐳 Step-by-Step Docker Deployment Guide

The recommended and supported method to deploy TMCB is using **Docker Compose**. This spins up:
1. **`bot`**: The core Python application with all extractors and dependencies.
2. **`telegram_local_api`**: A local Telegram Bot API Server enabling 2 GB uploads.
3. **`sqlite_web_admin`**: A web management UI for inspecting database tables.

### Step 1: System Requirements
- **Operating System:** Linux (Ubuntu 20.04+, Debian 11+, Rocky Linux, Arch) or Windows 10/11 with Docker Desktop.
- **Docker Engine:** `v20.10+` and **Docker Compose:** `v2.0+`
- **Hardware:** Minimum 2 GB RAM, 2 CPU cores, and at least 15 GB of free disk space for downloads.

### Step 2: Clone the Repository
```bash
git clone https://github.com/yourusername/Telegram-Media-Collector-Bot.git
cd Telegram-Media-Collector-Bot
```

### Step 3: Generate the AES-256 Encryption Key
TMCB uses a 32-byte URL-safe base64 key to encrypt user cookies in the SQLite database. Generate one with:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
*Save this output string; you will paste it into your `.env` file.*

### Step 4: Obtain Telegram Credentials
1. **Bot Token:** Open Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the API token (e.g., `8825207027:AA...`).
2. **Telegram API ID & API Hash:** Log in to [my.telegram.org](https://my.telegram.org), navigate to **API Development Tools**, and create an application to obtain your `api_id` (integer) and `api_hash` (32-character string).

### Step 5: Configure the Environment File (`.env`)
Create your `.env` file from the provided example:
```bash
cp .env.example .env
```
Open `.env` in your favorite editor (e.g., `nano .env`) and configure the settings:

```dotenv
# ==========================================
# Telegram Credentials
# ==========================================
BOT_TOKEN=8825207027:AAG-0jlGvJSTC0GUINJhD8K3IxWQmy8WNuM
BOT_USERNAME=TMCollector_Bot
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef0123456789abcdef0123456789

# ==========================================
# Local Bot API Server Settings (2GB Uploads)
# ==========================================
USE_LOCAL_SERVER=True
LOCAL_SERVER_URL=http://telegram_local_api:8081
TELEGRAM_LOCAL_API_DIR=/var/lib/telegram-bot-api

# ==========================================
# Security & Cryptography
# ==========================================
# Paste your generated Fernet key from Step 3:
AES_KEY=your_generated_fernet_key_here==

# ==========================================
# Logging & SRE Channels
# ==========================================
# Telegram Channel ID for error logs and incidents (optional):
LOG_CHANNEL_ID=-1001234567890

# (Optional) LLM Error Diagnostics (openai | anthropic | gemini | groq | local)
LLM_PROVIDER=
LLM_API_KEY=

# ==========================================
# Download & Performance Limits
# ==========================================
MAX_CONCURRENT_DOWNLOADS=3
MAX_PLAYLIST_ITEMS=50
QUEUE_ALERT_THRESHOLD=10
DOWNLOAD_DIR=/app/downloads
DATABASE_PATH=/app/database/bot_database.db
```

### Step 6: Build and Launch the Containers
Launch the stack in detached mode:
```bash
docker compose up -d --build
```
Docker will build the application image with `yt-dlp`, `ffmpeg`, and all required extractors, create the internal bridge network, and start all three services.

### Step 7: Verify Service Health
Check running containers:
```bash
docker compose ps
```
You should see all three services with status `Up`:
- `telegram_downloader_bot`
- `telegram_local_api`
- `sqlite_web_admin`

Inspect live bot startup logs:
```bash
docker logs -f telegram_downloader_bot
```
Look for the startup banner confirming database connection, extractor registration, and Telegram long-polling:
```text
INFO:src.main:Bot initialization complete. Listening for updates...
```

### Step 8: Configure @BotFather Settings
To enable the best user experience, configure your bot inside [@BotFather](https://t.me/BotFather):

1. **Enable Inline Mode:**
   - Send `/setinline` to `@BotFather`.
   - Select `@TMCollector_bot`.
   - Provide a placeholder: `Paste any video or audio link...`

2. **Register Bot Commands:**
   - Send `/setcommands` to `@BotFather`.
   - Select `@TMCollector_bot`.
   - Paste the following command list:
```text
start - Initialize bot and select language
help - View usage guide and instructions
setlang - Change bot language
dl - Download video or audio from link
audio - Extract audio (MP3/WAV) from link
clip - Trim video or audio segment
usecookies - Upload cookies for private media
clearcookies - Delete stored cookies
status - Show system telemetry and performance
cancelall - Cancel active and queued downloads
privacy - View Privacy Policy and Terms of Service
```

3. **Group Privacy (Optional):**
   - If you want the bot to detect links sent directly in group chats without explicit `/dl` commands, send `/setprivacy` to `@BotFather` and choose **Disable**.

### Step 9: Database Web Administration
TMCB bundles `sqlite-web` for inspecting user records, queue telemetry, and error logs directly from your browser:
- Open your browser at: `http://localhost:8085` (or `http://YOUR_SERVER_IP:8085`).
- The interface allows you to view registered users, file ID caches, execute SQL queries, and export data.

---

## 🛠️ Maintenance & Operations

### Stopping the Services
```bash
docker compose down
```

### Restarting the Bot
```bash
docker compose restart bot
```

### Updating to the Latest Version
```bash
git pull origin main
docker compose up -d --build bot
```

### Viewing Database Tables via CLI
```bash
docker exec -it telegram_downloader_bot python -c "
import sqlite3
conn = sqlite3.connect('/app/database/bot_database.db')
cursor = conn.cursor()
cursor.execute('SELECT count(*) FROM users;')
print('Total registered users:', cursor.fetchone()[0])
"
```

---

## 💻 Manual Local Installation (Without Docker)

If you prefer to run the bot natively on your host machine:

1. **Install System Prerequisites:**
   - Python 3.10 or higher.
   - **FFmpeg** (mandatory for audio merging and stream extraction):
     - **Ubuntu/Debian:** `sudo apt-get update && sudo apt-get install -y ffmpeg`
     - **macOS:** `brew install ffmpeg`
     - **Windows:** Install via `winget install Gyan.FFmpeg` or download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).

2. **Install Python Packages:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. **Launch the Bot:**
   ```bash
   python -m src.main
   ```

---

## 🔒 Security & Privacy

- **Encrypted Storage:** User cookies and admin passwords are encrypted with AES-256 before storage in SQLite.
- **Sanitized Filenames & Links:** All input URLs and downloaded filenames are strictly scrubbed of control characters and directory traversal vectors (`../`).
- **Temporary File Purging:** Media downloads are purged from disk immediately upon successful upload to Telegram or cancellation.
- **Spam and Flood Protection:** Built-in rate limiting and Telegram flood control prevent accidental API abuse.

---

## 📄 License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

You are free to use, study, modify, and distribute this software. However, if you modify this codebase and run it as a network service accessible to users, you **must make your modified source code publicly available under the AGPLv3 license**.

For full license terms, refer to the [LICENSE](LICENSE) file.

---

*Developed by Vulpes Tech. Maintained for the Telegram open-source community.*
