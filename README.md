# Telegram Downloader Bot

An asynchronous, highly robust Telegram bot built with Python, `aiogram` (v3), and `yt-dlp`. It allows users to download media from sites like YouTube, Instagram, and TikTok, with built-in telemetry, EULA enforcement, and support for downloading files up to 2GB via a Local Telegram Bot API Server.

## Features
- **Local Bot API Server Support:** Bypass the 50MB file size limit and upload files up to 2GB.
- **Strict EULA Flow:** Users must accept a multi-lingual EULA (EN, ES, PT, FR, DE) before using the bot.
- **Secure Cookie Storage:** Allows downloading age-restricted or private videos by uploading a `cookies.txt` file, which is securely encrypted using AES-256 in the database.
- **Live Progress UI:** ASCII progress bar and speed tracking edit the status message live.
- **SQLite Database with Telemetry:** Secure, SQL-Injection-proof database tracking users and group interactions.

## Prerequisites

### 1. System Requirements
- Python 3.9+
- **FFmpeg (Crucial Requirement)**: `yt-dlp` requires FFmpeg to merge high-quality video and audio streams. If FFmpeg is missing, you will see `Aborting due to --abort-on-error`.
  - **Ubuntu/Debian:** `sudo apt-get install ffmpeg`
  - **macOS:** `brew install ffmpeg`
  - **Windows:** Download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or install via `winget install ffmpeg`

### 2. Getting your AES Key
The bot requires a base64 URL-safe AES-256 key to encrypt user cookies securely. Run the following command to generate one:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copy the output string and place it in your `config.json`.

## Installation & Setup (Docker Recommended)

The most secure and robust way to run this bot is using Docker and Docker Compose. This automatically sets up an isolated environment with the `ffmpeg` dependency and a local Telegram API Server (allowing 2GB file uploads).

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/telegram-downloader-bot.git
   cd telegram-downloader-bot
   ```

2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

3. Edit the `.env` file with your credentials:
   - `BOT_TOKEN` from [@BotFather](https://t.me/botfather)
   - `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from [my.telegram.org](https://my.telegram.org)
   - Generate a new AES key: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

4. Start the containers:
   ```bash
   docker-compose up -d
   ```

Your bot is now running securely!

### Managing the Database

This project includes a built-in `sqlite-web` container that allows you to view and manage the database via a web interface.

1. Open your browser and navigate to `http://localhost:8085` (or your server's IP address and port 8085).
2. You can view tables, run SQL queries, and export the database as a `.csv` or `.sql` file.
3. If you want to import or backup the database file directly, it is located at `./database/bot_database.db` on your host machine.

### Alternative: Local Installation (Manual)
If you prefer not to use Docker:
1. Ensure `ffmpeg` is installed on your system.
2. Install Python requirements: `pip install -r requirements.txt`
3. Copy `config.example.json` to `config.json` and fill it out.
4. Run `python3 -m src.main`
