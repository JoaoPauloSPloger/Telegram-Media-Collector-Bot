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

from typing import Any, Callable, Dict, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update, InlineQuery
from src.database.db import AsyncSessionLocal, get_user, update_group_telemetry
from src.utils.i18n import load_locales, get_text

locales = load_locales()

class EulaMiddleware(BaseMiddleware):
    """
    Middleware that enforces EULA acceptance before allowing user interactions with the bot.
    """
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """
        Processes updates and intercepts them to prompt for EULA agreement if not already accepted.
        """
        user_id = None
        user = None
        
        if isinstance(event, Message):
            user_id = event.from_user.id
            if event.text and event.text.startswith('/start'):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            if event.data.startswith('lang_') or event.data.startswith('accept_eula_'):
                return await handler(event, data)
        elif isinstance(event, InlineQuery):
            user_id = event.from_user.id
        
        if user_id:
            async with AsyncSessionLocal() as session:
                user = await get_user(session, user_id)
                
                is_group = False
                if hasattr(event, 'chat') and event.chat.type in ['group', 'supergroup']:
                    is_group = True
                    if user:
                        await update_group_telemetry(session, user, event.chat)
                elif hasattr(event, 'message') and event.message and event.message.chat.type in ['group', 'supergroup']:
                    is_group = True
                    if user:
                        await update_group_telemetry(session, user, event.message.chat)
                
            if not user or not user.eula_agreed:
                lang = user.language_code if user and user.language_code else 'en'
                msg = get_text(locales, lang, "welcome_html")
                
                if isinstance(event, Message):
                    import re
                    from src.handlers.download import URL_REGEX
                    
                    is_command = event.text and event.text.startswith('/')
                    has_url = event.text and URL_REGEX.search(event.text)
                    
                    if not is_group or is_command or has_url:
                        from src.handlers.start import get_language_keyboard
                        await event.answer(msg, reply_markup=get_language_keyboard(), parse_mode="HTML")
                        return
                    else:
                        return
                elif isinstance(event, CallbackQuery):
                    await event.answer("Please accept the EULA first.", show_alert=True)
                    return
                elif isinstance(event, InlineQuery):
                    from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
                    from src.database.db import config
                    bot_username = config.get('bot_username', 'DownloaderBot')
                    await event.answer([
                        InlineQueryResultArticle(
                            id="accept_tos",
                            title="⚠️ Accept Terms of Service",
                            description="Please start the bot to accept the ToS.",
                            input_message_content=InputTextMessageContent(
                                message_text="⚠️ You must accept the ToS first."
                            ),
                            reply_markup=None
                        )
                    ], cache_time=1, switch_pm_text="Start bot to accept ToS", switch_pm_parameter="tos")
                    return
                
        data['db_user'] = user
        return await handler(event, data)
