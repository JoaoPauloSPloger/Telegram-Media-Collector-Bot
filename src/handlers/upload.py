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

import os
import html
import glob
import asyncio
import time
import subprocess
import json
import logging
from aiogram import Router
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError
from src.database.db import AsyncSessionLocal, Event, config
from src.utils.i18n import load_locales, get_text
from src.utils.cache import set_cached_file_id
from src.utils.downloader import get_progress_bar

router = Router()
locales = load_locales()

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

async def ensure_apple_compatibility(filepath: str) -> str:
    """
    Check if a video file codec is Apple-compatible and remuxes/transcodes it
    using ffmpeg if necessary, ensuring faststart flags are set.

    Args:
        filepath (str): The local path of the video file to verify.

    Returns:
        str: The path to the verified/re-encoded file.
    """
    if not filepath or not isinstance(filepath, str):
        return filepath

    try:
        if not os.path.exists(filepath):
            return filepath
    except TypeError:
        return filepath

    ext = filepath.split('.')[-1].lower()
    if ext not in ['mp4', 'mkv', 'mov', 'webm']:
        return filepath

    try:
        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1',
            filepath
        ]

        process = await asyncio.create_subprocess_exec(*probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await process.communicate()
        codec = stdout.decode().strip()

        needs_reencode = False
        if codec and codec not in ['h264', 'avc1']:
            needs_reencode = True
        elif not codec:
            return filepath

        fixed_filepath = f"{filepath}_apple_fixed.mp4"

        if needs_reencode:
            vcodec_args = ['-c:v', 'libx264', '-preset', 'superfast']
        else:
            vcodec_args = ['-c:v', 'copy']

        if ext in ['mkv', 'webm']:
            acodec_args = ['-c:a', 'aac']
        else:
            acodec_args = ['-c:a', 'copy']

        fix_cmd = [
            'ffmpeg', '-y', '-i', filepath,
            *vcodec_args, *acodec_args, '-movflags', '+faststart',
            fixed_filepath
        ]

        fix_process = await asyncio.create_subprocess_exec(*fix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await fix_process.communicate()

        if fix_process.returncode == 0 and os.path.exists(fixed_filepath):
            os.remove(filepath)
            return fixed_filepath

    except Exception as e:
        print(f"Error ensuring Apple compatibility: {e}")

    return filepath

async def handle_upload(original_message: Message, result: dict, event_id: str, db_user, is_document: bool = False, status_msg: Message = None):
    """
    Format metadata, construct message captions, update DB status, and upload
    the downloaded media file to Telegram. Shows upload progress animations
    and provides fallback handling.

    Args:
        original_message (Message): The original Telegram command or query message.
        result (dict): The dictionary containing file information and metadata.
        event_id (str): The unique ID of the download event.
        db_user: The database user object.
        is_document (bool): If True, forces the upload as a generic document/file.
        status_msg (Message): Optional status message to edit with progress animations.
    """
    logging.info(f'Entered handle_upload with result: {result}')
    lang = db_user.language_code if db_user else 'en'
    
    filepath = result['filepath']
    
    if filepath and not os.path.exists(filepath):
        search_pattern = f"downloads/{event_id}_*"
        matches = glob.glob(search_pattern)
        valid_matches = [m for m in matches if not m.endswith('.part') and not m.endswith('.ytdl')]
        
        if valid_matches:
            filepath = valid_matches[0]
            
    postprocess_task = None
    if status_msg and filepath and filepath.split('.')[-1].lower() in ['mp4', 'mkv', 'mov', 'webm']:
        async def animate_postprocess():
            spinner_idx = 0
            try:
                while True:
                    spinner_idx = (spinner_idx + 1) % len(SPINNER_FRAMES)
                    spinner = SPINNER_FRAMES[spinner_idx]

                    text = f"{spinner} ⚙️ Post-processing to ensure quality...\n"
                    text += f"Please wait, this may take a moment."

                    try:
                        await status_msg.edit_text(text)
                    except TelegramAPIError:
                        pass

                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                pass

        postprocess_task = asyncio.create_task(animate_postprocess())

    try:
        filepath = await ensure_apple_compatibility(filepath)
    finally:
        if postprocess_task:
            postprocess_task.cancel()
    title = html.escape(result['title'])
    description = result.get('description', '') or ''
    
    bot_username = html.escape(config.get('bot_username', 'DownloaderBot'))
    disclaimer = get_text(locales, lang, "disclaimer_footer")

    base_caption = f"🎬 <b>{html.escape(title)}</b>\n\n"
    footer_caption = f"ID: {event_id}\n🤖 @{bot_username}\n\n{disclaimer}"

    max_caption_len = 1024
    available_space = max_caption_len - len(base_caption) - len(footer_caption) - 30

    if len(description) > available_space:
        import re
        timestamp_lines = []
        for line in description.split('\n'):
            if re.search(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', line):
                timestamp_lines.append(line)

        if timestamp_lines:
            ts_desc = "\n".join(timestamp_lines)
            if len(ts_desc) <= available_space:
                description = ts_desc
            else:
                description = ts_desc[:available_space - 3] + "..."
        else:
            description = description[:available_space - 3] + "..."

    description = html.escape(description)
    
    if not filepath or not os.path.exists(filepath):
        await original_message.answer("❌ Error: File not found after download.")
        return
        
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    
    caption = base_caption
    if description:
        caption += f"<blockquote>{description}</blockquote>\n\n"
    caption += footer_caption
    
    async def send_media(method_name, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        try:
            func = getattr(original_message, f"reply_{method_name}")
            return await func(**kwargs)
        except TelegramAPIError as e:
            if "message to reply not found" in str(e).lower() or "message is not modified" in str(e).lower():
                try:
                    func = getattr(original_message, f"answer_{method_name}")
                    return await func(**kwargs)
                except TelegramAPIError:
                    func = getattr(original_message.bot, f"send_{method_name}")
                    return await func(chat_id=original_message.from_user.id, **kwargs)
            else:
                func = getattr(original_message.bot, f"send_{method_name}")
                return await func(chat_id=original_message.from_user.id, **kwargs)

    upload_ui_task = None
    if status_msg:
        async def animate_upload():
            spinner_idx = 0
            start_time = time.time()
            try:
                while True:
                    spinner_idx = (spinner_idx + 1) % len(SPINNER_FRAMES)
                    spinner = SPINNER_FRAMES[spinner_idx]
                    elapsed = time.time() - start_time

                    assumed_speed_mb = 2.0
                    assumed_duration = file_size_mb / assumed_speed_mb if file_size_mb > 0 else 1

                    progress_pct = min((elapsed / assumed_duration) * 100, 99.0)
                    eta_s = max(int(assumed_duration - elapsed), 0)

                    bar = get_progress_bar(progress_pct)
                    text = f"{spinner} 📤 {get_text(locales, lang, 'status_uploading')}\n"
                    text += f"{bar}\n"
                    text += f"ETA: {eta_s}s | Speed: {assumed_speed_mb:.1f} MB/s"

                    try:
                        await status_msg.edit_text(text)
                    except TelegramAPIError:
                        pass

                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                pass

        upload_ui_task = asyncio.create_task(animate_upload())

    try:
        file_input = FSInputFile(filepath)
        ext = filepath.split('.')[-1].lower()
        
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
            await set_cached_file_id(f"temp_{event_id}", "upload", msg.video.file_id)

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
            msg = await send_media("document", document=file_input, caption=caption, parse_mode="HTML")
            await set_cached_file_id(result['url'], 'doc', msg.document.file_id, title=title, description=description)
            await set_cached_file_id(f"temp_{event_id}", "upload", msg.document.file_id)
        
        media_logging_channel_id = config.get('media_logging_channel_id')
        if media_logging_channel_id:
            try:
                log_caption = f"👤 User: {original_message.from_user.id} (@{original_message.from_user.username})\n🔗 URL: {result['url']}\n✅ Status: Success"
                await msg.copy_to(chat_id=media_logging_channel_id, caption=log_caption, reply_markup=None)
            except Exception as e:
                logging.error(f"Failed to log media to channel: {e}")

        async with AsyncSessionLocal() as session:
            event = await session.get(Event, event_id)
            if event:
                event.status = 'completed'
                await session.commit()
                
    except Exception as e:
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

        media_logging_channel_id = config.get('media_logging_channel_id')
        if media_logging_channel_id:
            try:
                log_text = f"👤 User: {original_message.from_user.id} (@{original_message.from_user.username})\n🔗 URL: {result['url']}\n❌ Status: Failed\nError: {e}"
                await original_message.bot.send_message(chat_id=media_logging_channel_id, text=log_text)
            except Exception as log_e:
                logging.error(f"Failed to log error to media channel: {log_e}")

        async with AsyncSessionLocal() as session:
            event = await session.get(Event, event_id)
            if event:
                event.status = 'failed'
                await session.commit()
    finally:
        if upload_ui_task:
            upload_ui_task.cancel()
        if status_msg:
            try:
                await status_msg.delete()
            except TelegramAPIError:
                pass

        search_pattern = f"downloads/{event_id}_*"
        for match in glob.glob(search_pattern):
            try:
                if os.path.exists(match):
                    os.remove(match)
            except Exception:
                pass
