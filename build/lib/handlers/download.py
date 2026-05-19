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
from src.utils.i18n import load_locales, get_text

router = Router()
locales = load_locales()

# Regex to find URLs in text
URL_REGEX = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

SPINNER_FRAMES = ['/', '-', '\\', '|']

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
    
    event_id = str(uuid.uuid4())
    
    # Save event to DB
    async with AsyncSessionLocal() as session:
        event = Event(event_id=event_id, user_id=db_user.id, url=url, status='started')
        session.add(event)
        await session.commit()
    
    status_msg = await message.answer(f"{SPINNER_FRAMES[0]} {get_text(locales, lang, 'status_analyzing')}")
    
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
                    
                    bar = get_progress_bar(percentage)
                    speed_mb = speed / 1024 / 1024 if speed else 0
                    
                    text = f"{spinner} {get_text(locales, lang, 'status_downloading')}\n"
                    text += f"{bar}\n"
                    text += f"ETA: {eta}s | Speed: {speed_mb:.1f} MB/s"
                    
                    try:
                        await status_msg.edit_text(text)
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
    
    # Start download
    result = await download_video(url, cookies_path, event_id)
    
    # Stop updater
    updater_task.cancel()
    if event_id in active_downloads:
        del active_downloads[event_id]
    
    # Cleanup cookies
    if cookies_path and os.path.exists(cookies_path):
        os.remove(cookies_path)
        
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
            async with AsyncSessionLocal() as session:
                event = await session.get(Event, event_id)
                if event:
                    event.status = 'failed'
                    await session.commit()
                    
            if error_msg == 'unsupported_url':
                error_msg = get_text(locales, lang, "error_invalid_url")
            await status_msg.edit_text(f"❌ Error: {error_msg}")
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
    event_id = callback_query.data.split('_')[1]
    
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
            if error_msg == 'unsupported_url':
                error_msg = get_text(locales, lang, "error_invalid_url")
            await status_msg.edit_text(f"❌ Error: {error_msg}")
            return
        
    # Clean up status message
    await status_msg.delete()
    
    # Next step: Upload and Finalization
    from src.handlers.upload import handle_upload
    await handle_upload(callback_query.message, result, event_id, db_user, is_document=True)
