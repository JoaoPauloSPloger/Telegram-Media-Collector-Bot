import os
import uuid
import asyncio
import subprocess
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from src.database.db import AsyncSessionLocal, Event
from src.utils.queue_manager import queue_manager

router = Router()

@router.message(F.video | F.audio | F.document | F.voice)
async def handle_media_message(message: Message, db_user):
    if not db_user:
        return

    # Only allow conversion in private chats to prevent spam in groups
    if message.chat.type != 'private':
        return

    # Check if the file is valid for conversion
    file_id = None
    media_type = None
    if message.video:
        file_id = message.video.file_id
        media_type = 'video'
    elif message.audio:
        file_id = message.audio.file_id
        media_type = 'audio'
    elif message.voice:
        file_id = message.voice.file_id
        media_type = 'audio'
    elif message.document:
        file_id = message.document.file_id
        media_type = 'doc'

    if not file_id:
        return

    event_id = str(uuid.uuid4())

    keyboard_buttons = []

    if media_type == 'video':
        keyboard_buttons.append([InlineKeyboardButton(text="🎧 Extract Audio (MP3)", callback_data=f"conv_mp3_{event_id}")])
        keyboard_buttons.append([InlineKeyboardButton(text="🖼 Convert to GIF", callback_data=f"conv_gif_{event_id}")])
    elif media_type in ['audio', 'voice']:
        keyboard_buttons.append([InlineKeyboardButton(text="🎵 Convert to MP3", callback_data=f"conv_mp3_{event_id}")])
        keyboard_buttons.append([InlineKeyboardButton(text="🎵 Convert to WAV", callback_data=f"conv_wav_{event_id}")])

    if not keyboard_buttons:
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    # Store temporary context info (just mapping event_id to file_id so the callback knows what to download)
    from src.utils.cache import set_cached_file_id # reusing this to store temp file_id
    await set_cached_file_id(f"temp_{event_id}", "upload", file_id)

    await message.reply("⚙️ What would you like to convert this file to?", reply_markup=keyboard)


@router.callback_query(lambda c: c.data.startswith('conv_'))
async def process_conversion(callback_query: CallbackQuery, db_user):
    parts = callback_query.data.split('_', 2)
    if len(parts) < 3:
        return

    target_format = parts[1]
    event_id = parts[2]

    # Retrieve the file_id from temp cache
    from src.utils.cache import get_cached_file_id, delete_cached_file_id
    temp_url = f"temp_{event_id}"
    file_id, _, _ = await get_cached_file_id(temp_url, "upload")

    if not file_id:
        await callback_query.answer("Session expired or file not found.", show_alert=True)
        return

    await callback_query.answer()
    await delete_cached_file_id(temp_url, "upload") # Clean up DB
    status_msg = await callback_query.message.edit_text("⏳ Downloading file...")

    os.makedirs("downloads", exist_ok=True)
    input_path = f"downloads/input_{event_id}"
    output_path = f"downloads/output_{event_id}.{target_format}"

    try:
        # Download the file using aiogram's bot object
        file_info = await callback_query.bot.get_file(file_id)

        # Check size (if using local API server, size limits are higher)
        from src.database.db import config
        is_local_api = bool(config.get('local_api_server'))
        if not is_local_api and file_info.file_size > 20000000: # 20MB limit for cloud bot downloading
            await status_msg.edit_text("❌ File is too large to download (20MB limit without Local API).")
            return

        await callback_query.bot.download_file(file_info.file_path, input_path)

        await status_msg.edit_text(f"⚙️ Converting to {target_format.upper()}...")

        # Perform conversion
        def run_conversion():
            if target_format == 'mp3':
                cmd = ['ffmpeg', '-y', '-i', input_path, '-vn', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_path]
            elif target_format == 'wav':
                cmd = ['ffmpeg', '-y', '-i', input_path, '-vn', output_path]
            elif target_format == 'gif':
                cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', 'fps=10,scale=320:-1:flags=lanczos', '-c:v', 'gif', output_path]
            else:
                return False

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result.returncode == 0

        success = await asyncio.get_event_loop().run_in_executor(None, run_conversion)

        if success and os.path.exists(output_path):
            await status_msg.edit_text(f"✅ Uploading {target_format.upper()}...")
            file_input = FSInputFile(output_path)

            if target_format in ['mp3', 'wav']:
                await callback_query.message.reply_audio(file_input)
            elif target_format == 'gif':
                await callback_query.message.reply_animation(file_input)
            else:
                await callback_query.message.reply_document(file_input)

            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ Conversion failed.")

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
    finally:
        # Cleanup
        for path in [input_path, output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
