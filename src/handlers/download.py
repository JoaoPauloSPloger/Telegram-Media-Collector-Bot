import asyncio
import re
import os
import uuid
import aiofiles
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from src.database.db import AsyncSessionLocal, Event, get_user, decrypt_data
from src.utils.downloader import download_video, active_downloads, get_progress_bar
from src.utils.time_parser import parse_time
from src.utils.i18n import load_locales, get_text
from src.utils.queue_manager import queue_manager
from src.utils.cache import get_cached_file_id
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

router = Router()
locales = load_locales()

# Regex to find URLs in text
URL_REGEX = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

SPINNER_FRAMES = ['/', '-', '\\', '|']

@router.message(Command("clip", "cut"))
async def handle_clip_message(message: Message, db_user):
    if not db_user:
        return
        
    lang = db_user.language_code if db_user else 'en'
    
    # Try to find URL in current message
    urls = URL_REGEX.findall(message.text)
    url = urls[0] if urls else None
    
    # If no URL, try to find in replied message
    if not url and message.reply_to_message and message.reply_to_message.text:
        replied_urls = URL_REGEX.findall(message.reply_to_message.text)
        if replied_urls:
            url = replied_urls[0]
            
    if not url:
        await message.answer(f"❌ {get_text(locales, lang, 'error_invalid_url')}")
        return

    # Extract time arguments from the command message
    # e.g., /clip 1:00 2:00 https://...
    # split by whitespace
    parts = message.text.split()
    times = []
    for part in parts:
        # Avoid treating the URL or command as a time
        if part.startswith('/') or URL_REGEX.match(part):
            continue
        parsed = parse_time(part)
        if parsed is not None:
            times.append(parsed)
            
    if len(times) == 0:
        await message.answer(f"❌ {get_text(locales, lang, 'error_invalid_timestamp')}")
        return
        
    start_time = times[0]
    end_time = times[1] if len(times) > 1 else None
    
    if end_time is not None and start_time >= end_time:
        await message.answer(f"❌ {get_text(locales, lang, 'error_start_after_end')}")
        return
        
    download_range = (start_time, end_time)
    
    await process_download(message, db_user, url, lang, download_range=download_range)


@router.message(Command("audio", "mp3"))
async def handle_audio_message(message: Message, db_user):
    if not db_user:
        return

    urls = URL_REGEX.findall(message.text)
    if not urls:
        if message.reply_to_message and message.reply_to_message.text:
            urls = URL_REGEX.findall(message.reply_to_message.text)
    if not urls:
        lang = db_user.language_code if db_user else 'en'
        await message.answer(f"❌ {get_text(locales, lang, 'error_invalid_url')}")
        return

    url = urls[0]
    lang = db_user.language_code if db_user else 'en'
    await process_download(message, db_user, url, lang, media_type='audio')


@router.message(Command("dl", "download"))
@router.message(F.text & ~F.text.startswith('/'))
async def handle_url_message(message: Message, db_user):
    if not db_user:
        return
        
    urls = URL_REGEX.findall(message.text)
    if not urls:
        # Ignore non-URL messages
        return
        
    url = urls[0] # Take the first URL found
    lang = db_user.language_code if db_user else 'en'
    
    # Process Spotify/Apple Music URLs (yt-dlp often handles them but ytsearch fallback is safer for some tracks)
    if 'spotify.com' in url or 'music.apple.com' in url:
        # We will attempt to download it natively first, but set default media_type to audio
        await process_download(message, db_user, url, lang, media_type='audio')
    else:
        await process_download(message, db_user, url, lang)

async def process_download(message: Message, db_user, url: str, lang: str, download_range: tuple = None, media_type: str = 'video'):
    # Check if URL belongs to an audio-only platform
    import urllib.parse
    parsed_url = urllib.parse.urlparse(url)
    domain = parsed_url.netloc.lower()

    audio_domains = [
        'open.spotify.com', 'spotify.com',
        'y.qq.com', 'qq.com',
        'music.youtube.com',
        'music.apple.com',
        'music.amazon.com',
        'music.163.com',
        'soundcloud.com',
        'jiosaavn.com', 'www.jiosaavn.com',
        'gaana.com', 'www.gaana.com',
        'deezer.com', 'www.deezer.com',
        'tidal.com'
    ]

    if any(audio_domain in domain for audio_domain in audio_domains):
        media_type = 'audio'

    # Check cache first (skip cache if clipping a specific range)
    if not download_range:
        cached_file_id, cached_title, cached_description = await get_cached_file_id(url, media_type)
        if cached_file_id:
            # We have it in cache, just send the file_id directly!
            from src.database.db import config
            import html
            bot_username = config.get('bot_username', 'DownloaderBot')

            try:
                # Prepare caption with cached metadata
                disclaimer = get_text(locales, lang, "disclaimer_footer")
                title = cached_title or "Media"
                description = cached_description or ""

                caption = f"🎬 <b>{html.escape(title)}</b>\n\n"
                if description:
                    caption += f"<blockquote>{html.escape(description)}</blockquote>\n\n"

                caption += f"⚡ 🤖 @{bot_username}\n\n"
                caption += f"{disclaimer}"

                # Telegram has a strict 64-character limit for callback_data
                # We generate a short unique ID to map to the long file_id to pass around
                short_cache_id = uuid.uuid4().hex[:12]

                from src.utils.cache import set_cached_file_id
                # Temporarily store the long file_id keyed by this short_cache_id
                await set_cached_file_id(f"temp_cache_{short_cache_id}", "upload", cached_file_id)

                # Conversion buttons for cached files
                buttons = [
                    [InlineKeyboardButton(text=get_text(locales, lang, "get_full_file"), callback_data=f"doc_cache_{short_cache_id}")]
                ]
                if media_type in ['video', 'audio', 'doc'] and media_type != 'doc':
                    if media_type == 'video':
                        buttons.append([InlineKeyboardButton(text="🎧 Extract Audio (MP3)", callback_data=f"conv_mp3_{short_cache_id}")])
                        buttons.append([InlineKeyboardButton(text="🖼 Convert to GIF", callback_data=f"conv_gif_{short_cache_id}")])

                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

                if media_type == 'audio':
                    await message.answer_audio(cached_file_id, caption=caption, parse_mode="HTML", reply_markup=keyboard)
                elif media_type == 'doc':
                    await message.answer_document(cached_file_id, caption=caption, parse_mode="HTML", reply_markup=keyboard)
                else:
                    await message.answer_video(cached_file_id, caption=caption, parse_mode="HTML", reply_markup=keyboard)
                return
            except TelegramAPIError:
                # If sending cached file fails (e.g. file deleted from TG servers), fallback to download
                pass

    event_id = str(uuid.uuid4())
    
    # Save event to DB
    async with AsyncSessionLocal() as session:
        event = Event(event_id=event_id, user_id=db_user.id, url=url, status='started')
        session.add(event)
        await session.commit()
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_{event_id}")
    ]])

    try:
        from aiogram.exceptions import TelegramAPIError
        status_msg = await message.reply(f"⏳ In queue...", reply_markup=cancel_kb)
    except TelegramAPIError as e:
        if "message to reply not found" in str(e).lower():
            status_msg = await message.answer(f"⏳ In queue...", reply_markup=cancel_kb)
        else:
            status_msg = await message.bot.send_message(chat_id=message.from_user.id, text=f"⏳ In queue...", reply_markup=cancel_kb)
    
    # Wait in queue
    await queue_manager.acquire(db_user.id, event_id)

    if queue_manager.is_cancelled(event_id):
        await status_msg.edit_text("❌ Cancelled")
        # queue_manager.cancel already releases the semaphore, we should not double-release
        return

    try:
        await status_msg.edit_text(f"{SPINNER_FRAMES[0]} {get_text(locales, lang, 'status_analyzing')}", reply_markup=cancel_kb)
    except TelegramAPIError:
        pass

    # Handle Cookies
    cookies_path = None
    if db_user.use_cookies and db_user.encrypted_cookies:
        cookies_content = decrypt_data(db_user.encrypted_cookies)
        cookies_path = f"downloads/cookies_{event_id}.txt"
        os.makedirs("downloads", exist_ok=True)
        async with aiofiles.open(cookies_path, mode='w', encoding='utf-8') as f:
            await f.write(cookies_content)
    
    # Start async task to update progress
    async def update_status():
        spinner_idx = 0
        while True:
            spinner_idx = (spinner_idx + 1) % len(SPINNER_FRAMES)
            spinner = SPINNER_FRAMES[spinner_idx]
            
            if event_id in active_downloads:
                data = active_downloads[event_id]
                if data['status'] == 'downloading':
                    percentage = data.get('percentage', 0)
                    eta = data.get('eta', 0)
                    speed = data.get('speed', 0)
                    
                    if download_range:
                        # ffmpeg doesn't report typical percentage during download_range extraction
                        text = f"{spinner} ✂️ {get_text(locales, lang, 'status_clipping')}\n"
                        text += "(This may take a while as it processes directly from the source)"
                    else:
                        bar = get_progress_bar(percentage)
                        speed_mb = speed / 1024 / 1024 if speed else 0
                        
                        text = f"{spinner} {get_text(locales, lang, 'status_downloading')}\n"
                        text += f"{bar}\n"
                        text += f"ETA: {eta}s | Speed: {speed_mb:.1f} MB/s"
                    
                    try:
                        await status_msg.edit_text(text, reply_markup=cancel_kb)
                    except TelegramAPIError:
                        pass # Ignore "Message is not modified" errors
                elif data['status'] == 'finished':
                    try:
                        await status_msg.edit_text(f"✅ {get_text(locales, lang, 'status_uploading')}")
                    except TelegramAPIError:
                        pass
                    break
            
            await asyncio.sleep(2) # Update every 2 seconds to avoid rate limits
            
    updater_task = asyncio.create_task(update_status())
    
    # Track task in queue manager for cancelation
    queue_manager.active_tasks[event_id] = asyncio.current_task()

    # Start download
    try:
        result = await download_video(url, cookies_path, event_id, download_range=download_range, media_type=media_type)
    except asyncio.CancelledError:
        updater_task.cancel()
        queue_manager.release(db_user.id, event_id)
        if cookies_path and os.path.exists(cookies_path):
            os.remove(cookies_path)
        return

    # Release queue slot
    queue_manager.release(db_user.id, event_id)
    
    # Stop updater
    updater_task.cancel()
    if event_id in active_downloads:
        del active_downloads[event_id]
    
    # Cleanup cookies
    if cookies_path and os.path.exists(cookies_path):
        os.remove(cookies_path)
        
    if queue_manager.is_cancelled(event_id):
        await status_msg.edit_text("❌ Cancelled")
        return

    if not result['success']:
        error_msg = result.get('error', 'Unknown error')
        
        # If yt-dlp doesn't support it, attempt generic fallback web scraping
        if error_msg == 'unsupported_url':
            from src.utils.scraper import download_generic_media
            from src.database.db import config
            is_local_api = bool(config.get('local_api_server'))
            max_filesize = 2000000000 if is_local_api else 50000000
            
            await status_msg.edit_text(f"{SPINNER_FRAMES[0]} Attempting generic media extraction...")
            result = await download_generic_media(url, event_id, max_filesize)
            
            if not result['success']:
                error_msg = result.get('error', 'Unknown error')
        
        if not result['success']:
            status_code = result.get('status_code', 500)
            async with AsyncSessionLocal() as session:
                event = await session.get(Event, event_id)
                if event:
                    event.status = 'failed'
                    event.error_msg = error_msg
                    await session.commit()
                    
            # Log error to media logging channel
            from src.database.db import config
            media_logging_channel_id = config.get('media_logging_channel_id')
            if media_logging_channel_id:
                try:
                    log_text = f"👤 User: {message.from_user.id} (@{message.from_user.username})\n🔗 URL: {url}\n❌ Status: Failed\nError: {error_msg}"
                    await message.bot.send_message(chat_id=media_logging_channel_id, text=log_text)
                except Exception as log_e:
                    import logging
                    logging.error(f"Failed to log error to media channel: {log_e}")

            if error_msg == 'unsupported_url':
                display_msg = get_text(locales, lang, "error_invalid_url")
            else:
                display_msg = f"Error {status_code}"

            await status_msg.edit_text(f"❌ {display_msg} (ID: {event_id})")
            return
        
    # Download successful, update DB and proceed to upload
    async with AsyncSessionLocal() as session:
        event = await session.get(Event, event_id)
        if event:
            event.status = 'downloaded'
            await session.commit()
            
    # Clean up status message temporarily
    await status_msg.delete()
    
    # Next step: Upload and Finalization
    from src.handlers.upload import handle_upload
    await handle_upload(message, result, event_id, db_user)

import aiogram
@router.callback_query(lambda c: c.data.startswith('doc_'))
async def process_document_request(callback_query: aiogram.types.CallbackQuery, db_user):
    parts = callback_query.data.split('_')

    if len(parts) > 2 and parts[1] == 'cache':
        # the user clicked "Get File" on a cached video, we need to send the document form
        short_cache_id = parts[2]
        from src.utils.cache import get_cached_file_id
        file_id, _, _ = await get_cached_file_id(f"temp_cache_{short_cache_id}", "upload")

        if file_id:
            await callback_query.message.reply_document(file_id, caption="📄 Original File")
        else:
            await callback_query.answer("Session expired.", show_alert=True)

        await callback_query.answer()
        return

    event_id = parts[1]
    
    # Retrieve event from DB
    async with AsyncSessionLocal() as session:
        event = await session.get(Event, event_id)
        if not event:
            await callback_query.answer("Event not found.", show_alert=True)
            return
            
        url = event.url
        
    lang = db_user.language_code if db_user else 'en'
    
    status_msg = await callback_query.message.answer(f"{get_text(locales, lang, 'sending_doc')}")
    await callback_query.answer()
    
    # Handle Cookies
    cookies_path = None
    if db_user.use_cookies and db_user.encrypted_cookies:
        from src.database.db import decrypt_data
        cookies_content = decrypt_data(db_user.encrypted_cookies)
        cookies_path = f"downloads/cookies_doc_{event_id}.txt"
        os.makedirs("downloads", exist_ok=True)
        async with aiofiles.open(cookies_path, mode='w', encoding='utf-8') as f:
            await f.write(cookies_content)
    
    # Start download again for document format
    result = await download_video(url, cookies_path, event_id + "_doc")
    
    # Cleanup cookies
    if cookies_path and os.path.exists(cookies_path):
        os.remove(cookies_path)
        
    if not result['success']:
        error_msg = result.get('error', 'Unknown error')
        if error_msg == 'unsupported_url':
            from src.utils.scraper import download_generic_media
            from src.database.db import config
            is_local_api = bool(config.get('local_api_server'))
            max_filesize = 2000000000 if is_local_api else 50000000
            result = await download_generic_media(url, event_id + "_doc", max_filesize)
            if not result['success']:
                error_msg = result.get('error', 'Unknown error')
                
        if not result['success']:
            status_code = result.get('status_code', 500)
            async with AsyncSessionLocal() as session:
                event = await session.get(Event, event_id)
                if event:
                    event.status = 'failed'
                    event.error_msg = error_msg
                    await session.commit()

            # Log error to media logging channel
            from src.database.db import config
            media_logging_channel_id = config.get('media_logging_channel_id')
            if media_logging_channel_id:
                try:
                    log_text = f"👤 User: {callback_query.from_user.id} (@{callback_query.from_user.username})\n🔗 URL: {url}\n❌ Status: Failed (Doc Request)\nError: {error_msg}"
                    await callback_query.bot.send_message(chat_id=media_logging_channel_id, text=log_text)
                except Exception as log_e:
                    import logging
                    logging.error(f"Failed to log error to media channel: {log_e}")

            if error_msg == 'unsupported_url':
                display_msg = get_text(locales, lang, "error_invalid_url")
            else:
                display_msg = f"Error {status_code}"

            await status_msg.edit_text(f"❌ {display_msg} (ID: {event_id})")
            return
        
    # Clean up status message
    await status_msg.delete()
    
    # Next step: Upload and Finalization
    from src.handlers.upload import handle_upload
    await handle_upload(callback_query.message, result, event_id, db_user, is_document=True)

@router.callback_query(lambda c: c.data.startswith('cancel_'))
async def process_cancel_request(callback_query: aiogram.types.CallbackQuery, db_user):
    event_id = callback_query.data.split('_')[1]
    queue_manager.cancel(db_user.id, event_id)
    await callback_query.answer("Cancelling download...")
