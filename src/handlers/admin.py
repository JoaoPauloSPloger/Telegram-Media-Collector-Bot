import sys
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from src.database.db import config

router = Router()

@router.message(Command("shutdown", "restart"))
async def handle_admin_commands(message: Message):
    admin_password = config.get('admin_password')
    if not admin_password:
        return # ignore if no password is set

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or parts[1] != admin_password:
        return # ignore completely if no password or wrong password

    command_used = parts[0][1:] # e.g. "shutdown" or "restart"

    # Notify logging channels
    sys_logging_channel_id = config.get('sys_logging_channel_id')
    media_logging_channel_id = config.get('media_logging_channel_id')

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚠️ Confirm {command_used.capitalize()}", callback_data=f"confirm_admin_{command_used}")]
    ])

    msg_text = f"🚨 Admin requested a system **{command_used}**.\nWaiting for confirmation..."

    for channel_id in [sys_logging_channel_id, media_logging_channel_id]:
        if channel_id:
            try:
                await message.bot.send_message(chat_id=channel_id, text=msg_text, reply_markup=keyboard)
            except Exception as e:
                import logging
                logging.error(f"Failed to send admin confirmation to channel {channel_id}: {e}")

@router.callback_query(lambda c: c.data.startswith('confirm_admin_'))
async def process_admin_confirmation(callback_query: CallbackQuery):
    action = callback_query.data.split('_')[2]

    await callback_query.message.edit_text(f"✅ System **{action}** confirmed. Executing...")
    await callback_query.answer(f"Executing {action}...", show_alert=True)

    # Wait a moment for the message to be sent
    await asyncio.sleep(1)

    # Shut down. (Since it's likely Docker, os._exit(0) is enough to trigger a restart if restart=always is set,
    # or just cleanly exit if it's a shutdown. Docker handles the rest).
    import os
    os._exit(0)
