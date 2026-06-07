# Telegram Media Collector Bot
# Copyright (C) 2026 Vulpes Tech
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import asyncio
import re
import os
import uuid
import aiofiles
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from src.database.db import AsyncSessionLocal, Event, get_user, decrypt_data
from src.utils.downloader import download_video, active_downloads, get_progress_bar
from src.utils.time_parser import parse_time
from src.utils.i18n import load_locales, get_text
from src.utils.queue_manager import queue_manager
from src.utils.cache import get_cached_file_id

router = Router()
locales = load_locales()

pending_playlists = {}
URL_REGEX = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

@router.message(Command("clip", "cut"))
async def handle_clip_message(message: Message, db_user):
    """
    Command handler for `/clip` and `/cut` to download a specific time-slice of a video.
    """
    if not db_user:
        return
        
    lang = db_user.language_code if db_user else 'en'
    
    urls = URL_REGEX.findall(message.text)
    url = urls[0] if urls else None
    
    if not url and message.reply_to_message and message.reply_to_message.text:
        replied_urls = URL_REGEX.findall(message.reply_to_message.text)
        if replied_urls:
            url = replied_urls[0]
            
    if not url:
        await message.answer(f"❌ {get_text(locales, lang, 'error_invalid_url')}")
        return

    parts = message.text.split()
    times = []
    for part in parts:
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
    """
    Command handler for `/audio` and `/mp3` to download the audio track of a URL.
    """
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
    """
    Message handler for direct URL text inputs to trigger audio or video download.
    """
    if not db_user:
        return
        
    urls = URL_REGEX.findall(message.text)
    if not urls:
        return
        
    urls = [u.rstrip(',;') for u in urls]

    lang = db_user.language_code if db_user else 'en'
    
    for url in urls:
        import yt_dlp
        import asyncio

        is_playlist = False
        try:
            ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True}

            def extract_playlist_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, extract_playlist_info)

            if info and 'entries' in info:
                is_playlist = True
                playlist_urls = [entry['url'] for entry in info['entries'] if entry.get('url')]

                if playlist_urls:
                    from src.database.db import config
                    max_playlist_items = config.get('max_playlist_items', 100)

                    if len(playlist_urls) > max_playlist_items and db_user.admin_level == 0:
                        await message.answer(f"⚠️ Playlist contains {len(playlist_urls)} items, which exceeds the limit of {max_playlist_items}. Truncating to {max_playlist_items} items.")
                        playlist_urls = playlist_urls[:max_playlist_items]

                    await message.answer(f"📦 Found playlist with {len(playlist_urls)} items. Adding them to queue...")
                    for pl_url in playlist_urls:
                        media_type = 'audio' if ('spotify.com' in pl_url or 'music.apple.com' in pl_url) else 'video'
                        await process_download(message, db_user, pl_url, lang, media_type=media_type)
        except Exception:
            pass

        if not is_playlist:
            media_type = 'audio' if ('spotify.com' in url or 'music.apple.com' in url) else 'video'
            await process_download(message, db_user, url, lang, media_type=media_type)

async def process_download(message: Message, db_user, url: str, lang: str, download_range: tuple = None, media_type: str = 'video'):
    """
    Orchestrates the core download pipeline, checking the cache and handling queue semaphores.
    """
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

    if not download_range:
        cached_file_id, cached_title, cached_description = await get_cached_file_id(url, media_type)
        if cached_file_id:
            from src.database.db import config
            import html
            bot_username = config.get('bot_username', 'DownloaderBot')

            try:
                disclaimer = get_text(locales, lang, "disclaimer_footer")
                title = cached_title or "Media"
                description = cached_description or ""

                caption = f"🎬 <b>{html.escape(title)}</b>\n\n"
                if description:
                    caption += f"<blockquote>{html.escape(description)}</blockquote>\n\n"

                caption += f"⚡ 🤖 @{bot_username}\n\n"
                caption += f"{disclaimer}"

                short_cache_id = uuid.uuid4().hex[:12]

                from src.utils.cache import set_cached_file_id
                await set_cached_file_id(f"temp_{short_cache_id}", "upload", cached_file_id)

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
                pass

    event_id = str(uuid.uuid4())
    
    async with AsyncSessionLocal() as session:
        event = Event(event_id=event_id, user_id=db_user.id, url=url, status='started')
        session.add(event)
        await session.commit()
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_{event_id}"),
        InlineKeyboardButton(text="❌ Cancel All", callback_data=f"cancelall_{db_user.id}")
    ]])

    try:
        from aiogram.exceptions import TelegramAPIError
        status_msg = await message.reply(f"⏳ In queue...", reply_markup=cancel_kb)
    except TelegramAPIError as e:
        if "message to reply not found" in str(e).lower():
            status_msg = await message.answer(f"⏳ In queue...", reply_markup=cancel_kb)
        else:
            status_msg = await message.bot.send_message(chat_id=message.from_user.id, text=f"⏳ In queue...", reply_markup=cancel_kb)
    
    await queue_manager.acquire(db_user.id, event_id, bot=message.bot)

    if queue_manager.is_cancelled(event_id):
        await status_msg.edit_text("❌ Cancelled")
        return

    try:
        empty_bar = get_progress_bar(0.0)
        analyzing_text = f"{SPINNER_FRAMES[0]} {get_text(locales, lang, 'status_analyzing')}\n"
        analyzing_text += f"{empty_bar}\n"
        analyzing_text += "ETA: --- | Speed: --- MB/s"
        await status_msg.edit_text(analyzing_text, reply_markup=cancel_kb)
    except TelegramAPIError:
        pass

    cookies_path = None
    updater_task = None
    try:
        if db_user.use_cookies and db_user.encrypted_cookies:
            cookies_content = decrypt_data(db_user.encrypted_cookies)
            cookies_path = f"downloads/cookies_{event_id}.txt"
            os.makedirs("downloads", exist_ok=True)
            async with aiofiles.open(cookies_path, mode='w', encoding='utf-8') as f:
                await f.write(cookies_content)
        
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
                            pass
                    elif data['status'] == 'finished':
                        try:
                            await status_msg.edit_text(f"✅ {get_text(locales, lang, 'status_uploading')}")
                        except TelegramAPIError:
                            pass
                        break
                else:
                    try:
                        empty_bar = get_progress_bar(0.0)
                        text = f"{spinner} {get_text(locales, lang, 'status_analyzing')}\n"
                        text += f"{empty_bar}\n"
                        text += "ETA: --- | Speed: --- MB/s"
                        await status_msg.edit_text(text, reply_markup=cancel_kb)
                    except TelegramAPIError:
                        pass
                
                await asyncio.sleep(2)
                
        updater_task = asyncio.create_task(update_status())
        
        queue_manager.active_tasks[event_id] = asyncio.current_task()

        is_admin = db_user.admin_level > 0
        result = await download_video(url, cookies_path, event_id, download_range=download_range, media_type=media_type, is_admin=is_admin)
    except asyncio.CancelledError:
        return
    finally:
        queue_manager.release(db_user.id, event_id)
        
        if updater_task:
            updater_task.cancel()
        if event_id in active_downloads:
            del active_downloads[event_id]
        
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.remove(cookies_path)
            except Exception:
                pass
        
    if queue_manager.is_cancelled(event_id):
        await status_msg.edit_text("❌ Cancelled")
        return

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
        
    async with AsyncSessionLocal() as session:
        event = await session.get(Event, event_id)
        if event:
            event.status = 'downloaded'
            await session.commit()
            
    from src.handlers.upload import handle_upload
    await handle_upload(message, result, event_id, db_user, status_msg=status_msg)

import aiogram
@router.callback_query(lambda c: c.data.startswith('doc_'))
async def process_document_request(callback_query: aiogram.types.CallbackQuery, db_user):
    """
    Callback query handler to deliver the media file in standard document format.
    """
    parts = callback_query.data.split('_')

    if len(parts) > 2 and parts[1] == 'cache':
        short_cache_id = parts[2]
        from src.utils.cache import get_cached_file_id
        file_id, _, _ = await get_cached_file_id(f"temp_{short_cache_id}", "upload")

        if file_id:
            await callback_query.message.reply_document(file_id, caption="📄 Original File")
        else:
            await callback_query.answer("Session expired.", show_alert=True)

        await callback_query.answer()
        return

    event_id = parts[1]
    
    async with AsyncSessionLocal() as session:
        event = await session.get(Event, event_id)
        if not event:
            await callback_query.answer("Event not found.", show_alert=True)
            return
            
        url = event.url
        
    lang = db_user.language_code if db_user else 'en'
    
    status_msg = await callback_query.message.answer(f"{get_text(locales, lang, 'sending_doc')}")
    await callback_query.answer()
    
    cookies_path = None
    try:
        if db_user.use_cookies and db_user.encrypted_cookies:
            from src.database.db import decrypt_data
            cookies_content = decrypt_data(db_user.encrypted_cookies)
            cookies_path = f"downloads/cookies_doc_{event_id}.txt"
            os.makedirs("downloads", exist_ok=True)
            async with aiofiles.open(cookies_path, mode='w', encoding='utf-8') as f:
                await f.write(cookies_content)
        
        is_admin = db_user.admin_level > 0
        result = await download_video(url, cookies_path, event_id + "_doc", is_admin=is_admin)
    finally:
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.remove(cookies_path)
            except Exception:
                pass
        
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
        
    from src.handlers.upload import handle_upload
    await handle_upload(callback_query.message, result, event_id, db_user, is_document=True, status_msg=status_msg)

@router.callback_query(lambda c: c.data.startswith('cancel_'))
async def process_cancel_request(callback_query: aiogram.types.CallbackQuery, db_user):
    """
    Callback query handler to cancel an active download event.
    """
    event_id = callback_query.data.split('_')[1]
    queue_manager.cancel(db_user.id, event_id)
    await callback_query.answer("Cancelling download...")

@router.callback_query(lambda c: c.data.startswith('cancelall_'))
async def process_cancel_all_request(callback_query: aiogram.types.CallbackQuery, db_user):
    """
    Callback query handler to cancel all downloads for a user.
    """
    user_id = int(callback_query.data.split('_')[1])
    if user_id != db_user.id:
        if db_user.admin_level > 0:
            queue_manager.cancel_all_for_user(user_id)
            await callback_query.answer(f"Cancelled all queues for user {user_id}.")
        else:
            await callback_query.answer("You cannot cancel someone else's queue.", show_alert=True)
    else:
        queue_manager.cancel_all_for_user(db_user.id)
        await callback_query.answer("Cancelling all your downloads...")

@router.message(Command("cancelAll", "cancelall"))
async def cmd_cancel_all(message: Message, db_user):
    """
    Command handler for `/cancelall` to cancel all downloads for the calling user.
    """
    queue_manager.cancel_all_for_user(db_user.id)
    await message.answer("✅ Cancelled all your downloads.")


@router.callback_query(lambda c: c.data.startswith('pl_'))
async def handle_playlist_selection(callback_query: CallbackQuery, db_user):
    """
    Callback query handler for playlist prompts (allowing single item or bulk download selection).
    """
    parts = callback_query.data.split('_')
    if len(parts) < 3:
        await callback_query.answer("Invalid selection")
        return

    pl_id = parts[1]
    action = parts[2]

    if pl_id not in pending_playlists:
        await callback_query.answer("This selection has expired.", show_alert=True)
        return

    pl_data = pending_playlists[pl_id]
    url = pl_data['url']
    playlist_urls = pl_data['playlist_urls']
    lang = pl_data['lang']
    max_items = pl_data['max_items']

    del pending_playlists[pl_id]

    mock_msg = callback_query.message
    mock_msg = callback_query.message.model_copy(update={"from_user": callback_query.from_user})

    if action == 'single':
        await callback_query.message.edit_text("Downloading just the video...")
        media_type = 'audio' if ('spotify.com' in url or 'music.apple.com' in url) else 'video'
        await process_download(mock_msg, db_user, url, lang, media_type=media_type)
    elif action == 'all':
        if len(playlist_urls) > max_items and db_user.admin_level == 0:
            await callback_query.message.edit_text(f"⚠️ Playlist contains {len(playlist_urls)} items, exceeding the limit of {max_items}. Truncating and queuing {max_items} items...")
            playlist_urls = playlist_urls[:max_items]
        else:
            await callback_query.message.edit_text(f"📦 Queuing playlist with {len(playlist_urls)} items...")

        for pl_url in playlist_urls:
            media_type = 'audio' if ('spotify.com' in pl_url or 'music.apple.com' in pl_url) else 'video'
            await process_download(mock_msg, db_user, pl_url, lang, media_type=media_type)

    await callback_query.answer()
