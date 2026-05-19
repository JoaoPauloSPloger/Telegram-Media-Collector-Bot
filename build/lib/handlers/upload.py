import os
import html
import glob
from aiogram import Router
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from src.database.db import AsyncSessionLocal, Event, config
from src.utils.i18n import load_locales, get_text

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
    if len(description) > 250:
        description = description[:247] + "..."
        
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
    
    # Send the media based on file type or if it's explicitly requested as document
    try:
        file_input = FSInputFile(filepath)
        ext = filepath.split('.')[-1].lower()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text(locales, lang, "get_full_file"), callback_data=f"doc_{event_id}")]
        ])
        
        if is_document:
            await original_message.reply_document(file_input, caption=caption, parse_mode="HTML")
        elif ext in ['mp4', 'mkv', 'webm', 'mov']:
            await original_message.reply_video(file_input, caption=caption, parse_mode="HTML", reply_markup=keyboard)
        elif ext in ['jpg', 'jpeg', 'png', 'webp']:
            await original_message.reply_photo(file_input, caption=caption, parse_mode="HTML", reply_markup=keyboard)
        elif ext in ['mp3', 'm4a', 'wav', 'ogg']:
            await original_message.reply_audio(file_input, caption=caption, parse_mode="HTML", reply_markup=keyboard)
        else:
            # Fallback to document for any other format
            await original_message.reply_document(file_input, caption=caption, parse_mode="HTML")
        
        # Update Event DB
        async with AsyncSessionLocal() as session:
            event = await session.get(Event, event_id)
            if event:
                event.status = 'completed'
                await session.commit()
                
    except Exception as e:
        await original_message.answer(f"❌ Error uploading video: {e}")
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
