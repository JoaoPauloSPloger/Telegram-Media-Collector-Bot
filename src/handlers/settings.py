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

from aiogram import Router, F
from aiogram.types import Message, Document
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.database.db import AsyncSessionLocal, get_user, encrypt_data
from src.utils.i18n import load_locales, get_text

router = Router()
locales = load_locales()

class CookieState(StatesGroup):
    """
    State group representing the cookie configuration process.
    """
    waiting_for_cookie = State()

async def save_cookies(user_id, cookies_content, message: Message, lang: str):
    """
    Encrypt and save cookies to the database for the specified user.

    Args:
        user_id (int): The Telegram ID of the user.
        cookies_content (str): The raw cookie string or file contents.
        message (Message): The Telegram message to respond to.
        lang (str): The language code for the response message.
    """
    encrypted_cookies = encrypt_data(cookies_content)
    async with AsyncSessionLocal() as session:
        user = await get_user(session, user_id)
        if user:
            user.use_cookies = True
            user.encrypted_cookies = encrypted_cookies
            await session.commit()
    await message.answer(get_text(locales, lang, "cookie_success"), parse_mode="HTML")

@router.message(Command("usecookies"))
async def cmd_usecookies(message: Message, db_user, state: FSMContext):
    """
    Handle the /usecookies command. If cookies are provided inline, save them immediately;
    otherwise, transition to the waiting_for_cookie state.

    Args:
        message (Message): The Telegram command message.
        db_user: The database user object.
        state (FSMContext): The FSM context.
    """
    lang = db_user.language_code if db_user else 'en'
    if not db_user:
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        cookies_content = args[1].strip()
        await save_cookies(db_user.id, cookies_content, message, lang)
        return
        
    await state.set_state(CookieState.waiting_for_cookie)
    await message.answer(get_text(locales, lang, "cookie_prompt"), parse_mode="HTML")

@router.message(CookieState.waiting_for_cookie)
async def process_cookie_input(message: Message, db_user, state: FSMContext):
    """
    Process cookie input (either text or a .txt file upload) while in the CookieState.waiting_for_cookie state.

    Args:
        message (Message): The message containing the cookie text or file.
        db_user: The database user object.
        state (FSMContext): The FSM context.
    """
    if not db_user:
        return
    
    lang = db_user.language_code if db_user else 'en'
    cookies_content = ""
    
    if message.document and message.document.file_name.endswith('.txt'):
        if message.document.file_size > 1024 * 1024:
            await message.answer("Error: The file is too large. Cookie files should be small text files.")
            return
        file_in_memory = await message.bot.download(message.document.file_id)
        cookies_content = file_in_memory.read().decode('utf-8')
    elif message.text:
        cookies_content = message.text.strip()
    else:
        return
        
    await state.clear()
    await save_cookies(db_user.id, cookies_content, message, lang)

@router.message(Command("clearcookies"))
async def cmd_clearcookies(message: Message, db_user):
    """
    Handle the /clearcookies command. Delete user's cookies from the database.

    Args:
        message (Message): The Telegram command message.
        db_user: The database user object.
    """
    if not db_user:
        return
        
    async with AsyncSessionLocal() as session:
        user = await get_user(session, db_user.id)
        if user:
            user.use_cookies = False
            user.encrypted_cookies = None
            await session.commit()
            
    await message.answer("🗑️ Your cookies have been deleted from the database.")
