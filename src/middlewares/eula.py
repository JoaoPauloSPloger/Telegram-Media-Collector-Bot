from typing import Any, Callable, Dict, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update, InlineQuery
from src.database.db import AsyncSessionLocal, get_user, update_group_telemetry
from src.utils.i18n import load_locales, get_text

locales = load_locales()

class EulaMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        
        # We need to handle Message and CallbackQuery events differently to get user_id
        user_id = None
        user = None
        
        if isinstance(event, Message):
            user_id = event.from_user.id
            # Don't block /start command
            if event.text and event.text.startswith('/start'):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            # Don't block language and EULA acceptance callbacks
            if event.data.startswith('lang_') or event.data.startswith('accept_eula_'):
                return await handler(event, data)
        elif isinstance(event, InlineQuery):
            user_id = event.from_user.id
        
        if user_id:
            async with AsyncSessionLocal() as session:
                user = await get_user(session, user_id)
                
                # Telemetry: Record group data if the interaction happened in a group
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
                # User hasn't agreed to EULA yet
                lang = user.language_code if user and user.language_code else 'en'
                msg = get_text(locales, lang, "welcome_html")
                
                if isinstance(event, Message):
                    # To avoid spamming groups, only send EULA prompt if it's a direct command
                    # or if the message contains a URL that the bot would otherwise process.
                    import re
                    from src.handlers.download import URL_REGEX
                    
                    is_command = event.text and event.text.startswith('/')
                    has_url = event.text and URL_REGEX.search(event.text)
                    
                    if not is_group or is_command or has_url:
                        from src.handlers.start import get_language_keyboard
                        await event.answer(msg, reply_markup=get_language_keyboard(), parse_mode="HTML")
                        return # Block execution
                    else:
                        # Ignore other messages in groups without prompting
                        return
                elif isinstance(event, CallbackQuery):
                    await event.answer("Please accept the EULA first.", show_alert=True)
                    return # Block execution
                elif isinstance(event, InlineQuery):
                    from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
                    # Provide an inline prompt to accept ToS via the bot DM
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
                
        # Inject the user object into the handler data
        data['db_user'] = user
        return await handler(event, data)
