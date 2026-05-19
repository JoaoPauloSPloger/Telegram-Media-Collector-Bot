import os
import html
import glob
from aiogram import Router
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from src.database.db import AsyncSessionLocal, Event, config
from src.utils.i18n import load_locales, get_text
from src.utils.cache import set_cached_file_id

router = Router()
locales = load_locales()

async def handle_upload(original_message: Message, result: dict, event_id: str, db_user, is_document: bool = False):
    lang = db_user.language_code if db_user else 'en'
    
    filepath = result['filepath']
    
    # Fix: Sometimes yt-dlp returns a filepath but actually saves it with a different extension
    # (e.g. merging mkv, webm to mp4). Let's use glob to find the actual file.
    if not os.path.exists(filepath):
        # The file is saved as downloads/{event_id}_TITLE.ext
        # We can search for any file starting with downloads/{event_id}_
        search_pattern = f"downloads/{event_id}_*"
        matches = glob.glob(search_pattern)
        # Filter out .part files (incomplete downloads)
        valid_matches = [m for m in matches if not m.endswith('.part') and not m.endswith('.ytdl')]
        
        if valid_matches:
            filepath = valid_matches[0]
            
    title = html.escape(result['title'])
    description = html.escape(result.get('description', '') or '')
    
    # Truncate description to prevent exceeding Telegram's 1024 char caption limit
    if len(description) > 150:
        description = description[:147] + "..."
        
    bot_username = html.escape(config.get('bot_username', 'DownloaderBot'))
    
    # Check if file exists
    if not os.path.exists(filepath):
        await original_message.answer("❌ Error: File not found after download.")
        return
        
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    
    # Prepare caption
    disclaimer = get_text(locales, lang, "disclaimer_footer")
    caption = f"🎬 <b>{title}</b>\n\n"
    if description:
        caption += f"<blockquote>{description}</blockquote>\n\n"
        
    caption += f"ID: {event_id}\n"
    caption += f"🤖 @{bot_username}\n\n"
    caption += f"{disclaimer}"
    
    # Helper to send with fallback if message is deleted or bot kicked
    async def send_media(method_name, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        try:
            # Try replying
            func = getattr(original_message, f"reply_{method_name}")
            return await func(**kwargs)
        except TelegramAPIError as e:
            if "message to reply not found" in str(e).lower() or "message is not modified" in str(e).lower():
                try:
                    # Message deleted, try sending to the same chat
                    func = getattr(original_message, f"answer_{method_name}")
                    return await func(**kwargs)
                except TelegramAPIError:
                    # Chat deleted or bot kicked, send to user private chat
                    func = getattr(original_message.bot, f"send_{method_name}")
                    return await func(chat_id=original_message.from_user.id, **kwargs)
            else:
                # Chat deleted or bot kicked, send to user private chat directly
                func = getattr(original_message.bot, f"send_{method_name}")
                return await func(chat_id=original_message.from_user.id, **kwargs)

    # Send the media based on file type or if it's explicitly requested as document
    try:
        file_input = FSInputFile(filepath)
        ext = filepath.split('.')[-1].lower()
        
        # Conversion buttons for downloaded files
        buttons = [
            [InlineKeyboardButton(text=get_text(locales, lang, "get_full_file"), callback_data=f"doc_{event_id}")]
        ]
        if ext in ['mp4', 'mkv', 'webm', 'mov'] and not is_document:
            buttons.append([InlineKeyboardButton(text="🎧 Extract Audio (MP3)", callback_data=f"conv_mp3_{event_id}")])
            buttons.append([InlineKeyboardButton(text="🖼 Convert to GIF", callback_data=f"conv_gif_{event_id}")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        if is_document:
            msg = await send_media("document", document=file_input, caption=caption, parse_mode="HTML")
            await set_cached_file_id(result['url'], 'doc', msg.document.file_id, title=title, description=description)
        elif ext in ['mp4', 'mkv', 'webm', 'mov']:
            # Extract video metadata to ensure streaming works and previews display correctly
            import subprocess
            import json

            width = result.get('width', 0)
            height = result.get('height', 0)
            duration = result.get('duration', 0)

            try:
                cmd = [
                    'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height,duration',
                    '-of', 'json', filepath
                ]
                ffprobe_result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if ffprobe_result.returncode == 0:
                    info = json.loads(ffprobe_result.stdout)
                    if 'streams' in info and len(info['streams']) > 0:
                        stream = info['streams'][0]
                        width = int(stream.get('width', width))
                        height = int(stream.get('height', height))

                        if duration == 0:
                            duration = float(stream.get('duration', 0))
            except Exception:
                pass

            duration = int(duration)

            # Generate thumbnail using ffmpeg
            thumb_path = f"{filepath}_thumb.jpg"
            try:
                subprocess.run(['ffmpeg', '-i', filepath, '-ss', '00:00:01.000', '-vframes', '1', thumb_path, '-y'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                    thumb_input = FSInputFile(thumb_path)
                else:
                    thumb_input = None
            except Exception:
                thumb_input = None

            msg = await send_media("video",
                video=file_input,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
                width=width,
                height=height,
                duration=duration,
                supports_streaming=True,
                thumbnail=thumb_input
            )
            await set_cached_file_id(result['url'], 'video', msg.video.file_id, title=title, description=description)
            # Pre-populate conversion cache so the inline buttons work immediately
            await set_cached_file_id(f"temp_{event_id}", "upload", msg.video.file_id)

            # Clean up thumbnail
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

        elif ext in ['jpg', 'jpeg', 'png', 'webp']:
            msg = await send_media("photo", photo=file_input, caption=caption, parse_mode="HTML", reply_markup=keyboard)
            await set_cached_file_id(result['url'], 'photo', msg.photo[-1].file_id, title=title, description=description)
            await set_cached_file_id(f"temp_{event_id}", "upload", msg.photo[-1].file_id)
        elif ext in ['mp3', 'm4a', 'wav', 'ogg']:
            msg = await send_media("audio", audio=file_input, caption=caption, parse_mode="HTML", reply_markup=keyboard)
            await set_cached_file_id(result['url'], 'audio', msg.audio.file_id, title=title, description=description)
            await set_cached_file_id(f"temp_{event_id}", "upload", msg.audio.file_id)
        else:
            # Fallback to document for any other format
            msg = await send_media("document", document=file_input, caption=caption, parse_mode="HTML")
            await set_cached_file_id(result['url'], 'doc', msg.document.file_id, title=title, description=description)
            await set_cached_file_id(f"temp_{event_id}", "upload", msg.document.file_id)
        
        # Log to media logging channel
        media_logging_channel_id = config.get('media_logging_channel_id')
        if media_logging_channel_id:
            try:
                log_caption = f"👤 User: {original_message.from_user.id} (@{original_message.from_user.username})\n🔗 URL: {result['url']}\n✅ Status: Success"
                # Send using the message we just sent (which has the file_id) to avoid re-uploading
                await msg.copy_to(chat_id=media_logging_channel_id, caption=log_caption, reply_markup=None)
            except Exception as e:
                import logging
                logging.error(f"Failed to log media to channel: {e}")

        # Update Event DB
        async with AsyncSessionLocal() as session:
            event = await session.get(Event, event_id)
            if event:
                event.status = 'completed'
                await session.commit()
                
    except Exception as e:
        # Fallback error messaging
        from aiogram.exceptions import TelegramAPIError
        try:
            await original_message.reply(f"❌ Error uploading video: {e}")
        except TelegramAPIError as api_err:
            if "message to reply not found" in str(api_err).lower():
                try:
                    await original_message.answer(f"❌ Error uploading video: {e}")
                except Exception:
                    await original_message.bot.send_message(chat_id=original_message.from_user.id, text=f"❌ Error uploading video: {e}")
            else:
                try:
                    await original_message.bot.send_message(chat_id=original_message.from_user.id, text=f"❌ Error uploading video: {e}")
                except Exception:
                    pass

        # Log error to media logging channel
        media_logging_channel_id = config.get('media_logging_channel_id')
        if media_logging_channel_id:
            try:
                log_text = f"👤 User: {original_message.from_user.id} (@{original_message.from_user.username})\n🔗 URL: {result['url']}\n❌ Status: Failed\nError: {e}"
                await original_message.bot.send_message(chat_id=media_logging_channel_id, text=log_text)
            except Exception as log_e:
                import logging
                logging.error(f"Failed to log error to media channel: {log_e}")

        async with AsyncSessionLocal() as session:
            event = await session.get(Event, event_id)
            if event:
                event.status = 'failed'
                await session.commit()
    finally:
        # Clean up ALL local files matching this event_id (including temp parts)
        search_pattern = f"downloads/{event_id}_*"
        for match in glob.glob(search_pattern):
            try:
                if os.path.exists(match):
                    os.remove(match)
            except Exception:
                pass
