# Telegram Media Collector Bot

Telegram Media Collector is a powerful bot for downloading and converting media directly in Telegram. Powered by `yt-dlp`, it supports video/audio extraction, custom time clipping, format conversion (MP3, GIF), and cookies for restricted content. Features include an async queue, multilingual UI, and support for large files via local API server.

## Features
- **Local Bot API Server Support:** Bypass the 50MB file size limit and upload files up to 2GB.
- **Strict EULA Flow:** Users must accept a multi-lingual EULA (EN, ES, PT, FR, DE) before using the bot.
- **Secure Cookie Storage:** Allows downloading age-restricted or private videos by uploading a `cookies.txt` file, which is securely encrypted using AES-256 in the database.
- **Media Conversion & Clipping:** Extract audio to MP3/WAV, convert videos to GIFs, and clip specific timestamps directly in chat.
- **Live Progress UI:** ASCII progress bar and speed tracking edit the status message live.
- **SQLite Database with Telemetry:** Secure, SQL-Injection-proof database tracking users and system metrics.

## Commands List

### General Commands
- `/start` - Initializes the bot, registers the user, and handles language selection and EULA acceptance.
- `/help` - Displays the help message in the user's selected language.
- `/privacy` or `/tos` - Displays the bot's Privacy Policy and Terms of Service.

### Download & Media Commands
- `/dl [url]` or `/download [url]` - Main command to download media from a given URL.
- `/audio [url]` or `/mp3 [url]` - Forces the bot to download the media as an audio file.
- `/clip [start] [end] [url]` or `/cut` - Clips a specific section of a video/audio (e.g., `/clip 1:00 2:00 https://...`).
- *Note: Sending a URL directly to the chat also triggers the standard download. Sending video/audio/document files directly will prompt the conversion menu.*

### Settings & Authentication
- `/usecookies` - Upload your `cookies.txt` (inline or as a text file attachment) to bypass age restrictions or login walls.
- `/clearcookies` - Deletes your saved cookies securely from the bot's database.

### System & Administration
- `/stats` - Displays a live dashboard with system metrics (CPU, RAM, Disk, Network) and bot usage statistics.

---

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

Copy the output string and place it in your `config.json` or `.env`.

## Installation & Setup (Docker Recommended)

The most secure and robust way to run this bot is using Docker and Docker Compose. This automatically sets up an isolated environment with the `ffmpeg` dependency and a local Telegram API Server (allowing 2GB file uploads).

1. Clone the repository:
```bash
git clone [https://github.com/yourusername/telegram-downloader-bot.git](https://github.com/yourusername/telegram-downloader-bot.git)
cd telegram-downloader-bot

```


2. Copy the example environment file:
```bash
cp .env.example .env

```


3. Edit the `.env` file with your credentials:
* `BOT_TOKEN` from [@BotFather](https://t.me/botfather)
* `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from [my.telegram.org](https://my.telegram.org)
* Generate a new AES key: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`


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

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

You are free to use, modify, and distribute this software. However, if you modify the code and run it as a public service over a network, you must make your modified source code available to your users under the same AGPLv3 license. 

See the [LICENSE](LICENSE) file for the full text of the license.
