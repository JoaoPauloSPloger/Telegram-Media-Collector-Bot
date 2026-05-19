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
    waiting_for_cookie = State()

async def save_cookies(user_id, cookies_content, message: Message, lang: str):
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
    lang = db_user.language_code if db_user else 'en'
    if not db_user:
        return
        
    # Check if there are arguments passed directly with the command
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        # User provided the cookie content inline
        cookies_content = args[1].strip()
        await save_cookies(db_user.id, cookies_content, message, lang)
        return
        
    # No arguments, ask for the cookie
    await state.set_state(CookieState.waiting_for_cookie)
    await message.answer(get_text(locales, lang, "cookie_prompt"), parse_mode="HTML")

@router.message(CookieState.waiting_for_cookie)
async def process_cookie_input(message: Message, db_user, state: FSMContext):
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

@router.message(lambda message: message.document and message.document.file_name.endswith('.txt'))
async def process_cookie_file_direct(message: Message, db_user, state: FSMContext):
    # This handler catches document uploads even when not in FSM
    if not db_user:
        return
    lang = db_user.language_code if db_user else 'en'
    
    if message.document.file_size > 1024 * 1024:
        return
        
    file_in_memory = await message.bot.download(message.document.file_id)
    cookies_content = file_in_memory.read().decode('utf-8')
    await save_cookies(db_user.id, cookies_content, message, lang)

@router.message(Command("clearcookies"))
async def cmd_clearcookies(message: Message, db_user):
    if not db_user:
        return
        
    async with AsyncSessionLocal() as session:
        user = await get_user(session, db_user.id)
        if user:
            user.use_cookies = False
            user.encrypted_cookies = None
            await session.commit()
            
    await message.answer("🗑️ Your cookies have been deleted from the database.")
