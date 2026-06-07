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

from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from src.database.db import AsyncSessionLocal, get_user, create_user
from src.utils.i18n import load_locales, get_text

router = Router()
locales = load_locales()

def get_language_keyboard():
    """
    Generate the language selection keyboard.

    Returns:
        InlineKeyboardMarkup: The markup containing language selection buttons.
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="lang_de"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")
        ],
        [
            InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang_es"),
            InlineKeyboardButton(text="🇫🇷 Français", callback_data="lang_fr")
        ],
        [
            InlineKeyboardButton(text="🇧🇷 Português", callback_data="lang_pt")
        ]
    ])
    return keyboard

@router.message(CommandStart())
async def cmd_start(message: Message):
    """
    Handle the /start command. Registers the user if new, checks for deep-link payloads,
    and prompts for language selection or presents the main welcome screen.

    Args:
        message (Message): The Telegram start message.
    """
    user_id = message.from_user.id
    name = message.from_user.first_name
    username = message.from_user.username
    lang_code = message.from_user.language_code
    
    payload = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None

    if lang_code and lang_code.startswith(('de', 'en', 'es', 'fr', 'pt')):
        lang_code = lang_code[:2]
    else:
        lang_code = 'en'
    
    async with AsyncSessionLocal() as session:
        user = await get_user(session, user_id)
        if not user:
            user = await create_user(session, user_id, name, username, lang_code)
            
        if user.eula_agreed:
            user_lang = user.language_code or 'en'

            if payload:
                from src.utils.cache import get_cached_file_id, delete_cached_file_id

                if payload.startswith('dl_'):
                    short_id = payload[3:]
                    url, _, _ = await get_cached_file_id(f"inline_{short_id}", "inline_url")
                    if url:
                        await delete_cached_file_id(f"inline_{short_id}", "inline_url")
                        from src.handlers.download import process_download
                        await process_download(message, user, url, user_lang)
                    else:
                        await message.answer("❌ This inline link has expired.")
                    return
                elif payload.startswith('audio_'):
                    short_id = payload[6:]
                    url, _, _ = await get_cached_file_id(f"inline_{short_id}", "inline_url")
                    if url:
                        await delete_cached_file_id(f"inline_{short_id}", "inline_url")
                        from src.handlers.download import process_download
                        await process_download(message, user, url, user_lang, media_type='audio')
                    else:
                        await message.answer("❌ This inline link has expired.")
                    return
                elif payload.startswith('cancelqueue_'):
                    target_user_id = payload[12:]
                    from src.handlers.admin import pending_admin_actions
                    action_id = f"cancelq_{target_user_id}"
                    pending_admin_actions[user_id] = action_id
                    await message.answer(f"🔒 Admin action requested: Cancel queue for user {target_user_id}.\nPlease enter your admin password (or /cancel to abort):")
                    return

            await message.answer(get_text(locales, user_lang, "eula_agreed_already"))
            return
            
    welcome_text = get_text(locales, lang_code, "welcome_html")
    await message.answer(welcome_text, reply_markup=get_language_keyboard(), parse_mode="HTML")

@router.callback_query(lambda c: c.data.startswith('lang_'))
async def process_language_selection(callback_query: CallbackQuery):
    """
    Handle user's language selection callback. Updates language in the database
    and prompts the user to accept the End User License Agreement (EULA).

    Args:
        callback_query (CallbackQuery): The callback query containing the language data.
    """
    lang_code = callback_query.data.split('_')[1]
    
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback_query.from_user.id)
        if user:
            user.language_code = lang_code
            await session.commit()
        else:
            await create_user(
                session,
                callback_query.from_user.id,
                callback_query.from_user.first_name,
                callback_query.from_user.username,
                lang_code
            )
            
    eula_text = get_text(locales, lang_code, "eula_text")
    accept_button_text = get_text(locales, lang_code, "accept_button")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=accept_button_text, callback_data=f"accept_eula_{lang_code}")]
    ])
    
    await callback_query.message.edit_text(eula_text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(lambda c: c.data.startswith('accept_eula_'))
async def process_eula_acceptance(callback_query: CallbackQuery):
    """
    Handle EULA acceptance callback. Updates the user's EULA status to accepted in the database
    and displays instructions on how to use the bot.

    Args:
        callback_query (CallbackQuery): The callback query confirming agreement.
    """
    lang_code = callback_query.data.split('_')[2]
    
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback_query.from_user.id)
        if user:
            user.eula_agreed = True
            await session.commit()
        else:
            user = await create_user(
                session,
                callback_query.from_user.id,
                callback_query.from_user.first_name,
                callback_query.from_user.username,
                lang_code
            )
            user.eula_agreed = True
            await session.commit()
            
    success_text = get_text(locales, lang_code, "send_url_prompt")
    await callback_query.message.edit_text(success_text, parse_mode="HTML")

@router.message(Command("help"))
async def cmd_help(message: Message, db_user):
    """
    Handle the /help command to show help options and basic usage.

    Args:
        message (Message): The Telegram help message.
        db_user: The database user object.
    """
    lang = db_user.language_code if db_user else 'en'
    help_text = get_text(locales, lang, "help_text")
    await message.answer(help_text, parse_mode="HTML")
