import hashlib
import uuid
from aiogram import Router, F
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from src.handlers.download import URL_REGEX
from src.utils.i18n import load_locales, get_text

router = Router()
locales = load_locales()

@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery, db_user):
    query = inline_query.query.strip()

    # We only care about URLs for downloading
    urls = URL_REGEX.findall(query)
    if not urls:
        return

    url = urls[0]

    # Generate unique IDs for the inline results
    video_id = hashlib.md5(f"video_{url}".encode()).hexdigest()
    audio_id = hashlib.md5(f"audio_{url}".encode()).hexdigest()

    lang = db_user.language_code if db_user else 'en'

    from src.database.db import config
    bot_username = config.get('bot_username', 'DownloaderBot')

    # The safest way to handle inline downloads that work universally (even if bot isn't in group)
    # is to link back to the bot's private chat passing the URL in the start parameter,
    # or utilizing the cache if available.
    # To bypass the 64 character limit of Telegram start parameter, we will save the URL in cache using a short UUID
    from src.utils.cache import set_cached_file_id

    # We use cache table to temporarily map an inline ID to the URL
    short_id = uuid.uuid4().hex[:16]

    # We do this asynchronously, however inline query is awaited anyway
    # It's not ideal to await inside inline_query but it's acceptable for this bypass
    await set_cached_file_id(f"inline_{short_id}", "inline_url", url)

    # To fix double-download bug, we change the input_message_content so that it does NOT contain the URL.
    # If the bot auto-listener in the group sees the URL in the text message, it will download it.
    # The user also clicks the button, downloading it a second time. We use an invisible character or
    # just omit the raw URL so `download.py` doesn't trigger the auto-listener.

    # We strip the schema (https://) from the visual text so regex won't catch it
    safe_url = url.replace("https://", "").replace("http://", "")

    results = [
        InlineQueryResultArticle(
            id=video_id,
            title="🎬 Download Video",
            description=f"Download {url} as Video",
            input_message_content=InputTextMessageContent(
                message_text=f"Check out this video: {safe_url}\n\n🤖 Download it via @{bot_username}"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📥 Download Video", url=f"https://t.me/{bot_username}?start=dl_{short_id}")
            ]])
        ),
        InlineQueryResultArticle(
            id=audio_id,
            title="🎧 Download Audio",
            description=f"Download {url} as MP3/Audio",
            input_message_content=InputTextMessageContent(
                message_text=f"Check out this audio: {safe_url}\n\n🤖 Download it via @{bot_username}"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📥 Download Audio", url=f"https://t.me/{bot_username}?start=audio_{short_id}")
            ]])
        )
    ]

    await inline_query.answer(results, cache_time=1)
