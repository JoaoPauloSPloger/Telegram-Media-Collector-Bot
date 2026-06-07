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

import hashlib
import uuid
from aiogram import Router, F
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultCachedVideo, InlineQueryResultCachedAudio
from src.handlers.download import URL_REGEX
from src.utils.i18n import load_locales, get_text

router = Router()
locales = load_locales()

@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery, db_user):
    """
    Handles incoming inline queries by returning either cached media files directly 
    or deep-link articles redirecting to the bot's private chat.
    """
    query = inline_query.query.strip()

    urls = URL_REGEX.findall(query)
    if not urls:
        return

    url = urls[0]

    video_id = hashlib.md5(f"video_{url}".encode()).hexdigest()
    audio_id = hashlib.md5(f"audio_{url}".encode()).hexdigest()

    lang = db_user.language_code if db_user else 'en'

    from src.database.db import config
    bot_username = config.get('bot_username', 'DownloaderBot')

    from src.utils.cache import set_cached_file_id

    short_id = uuid.uuid4().hex[:16]

    await set_cached_file_id(f"inline_{short_id}", "inline_url", url)

    safe_url = url.replace("https://", "").replace("http://", "")

    from src.utils.cache import get_cached_file_id
    video_file_id, video_title, video_desc = await get_cached_file_id(url, "video")
    audio_file_id, audio_title, audio_desc = await get_cached_file_id(url, "audio")

    results = []

    if video_file_id:
        results.append(
            InlineQueryResultCachedVideo(
                id=video_id,
                video_file_id=video_file_id,
                title=video_title or "Video",
                description=video_desc or f"Cached Video",
                caption=f"🎬 <b>{video_title or 'Video'}</b>\n\n🤖 @{bot_username}",
                parse_mode="HTML"
            )
        )
    else:
        results.append(
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
            )
        )

    if audio_file_id:
        results.append(
            InlineQueryResultCachedAudio(
                id=audio_id,
                audio_file_id=audio_file_id,
                caption=f"🎧 <b>{audio_title or 'Audio'}</b>\n\n🤖 @{bot_username}",
                parse_mode="HTML"
            )
        )
    else:
        results.append(
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
        )

    await inline_query.answer(results, cache_time=1)
