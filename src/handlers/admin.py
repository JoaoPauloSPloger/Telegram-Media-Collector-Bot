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

import sys
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from src.database.db import config

router = Router()

@router.message(Command("test_error"))
async def cmd_test_error(message: Message, db_user):
    """
    Command handler for `/test_error` to trigger an error log for the diagnostic pipeline.
    """
    if not db_user or db_user.admin_level < 1:
        await message.answer("You do not have permission to use this command.")
        return

    await message.answer("Generating a test error for the LLM pipeline...")

    import logging
    logging.error("RuntimeError: This is a generated failure to test the LLM insight system. [29/05/2026 07:58] latanmcbot media log: User: 7309238470 URL: https://www.instagram.com/reel/DY2dvOkJ6Xt/ Status: Failed Error: ERROR: [Instagram] Instagram sent an empty media response.")

def verify_master_password(provided_pw: str) -> bool:
    """
    Validates a password against the configured master admin_password,
    supporting plaintext, base64 SHA-256 hash, and encrypted Fernet ciphertext.
    """
    admin_password = config.get('admin_password')
    if not admin_password or not provided_pw:
        return False
    if provided_pw == admin_password:
        return True
    try:
        import hashlib
        import base64
        hashed = base64.b64encode(hashlib.sha256(provided_pw.encode()).digest()).decode()
        if hashed == admin_password:
            return True
    except Exception:
        pass
    try:
        from src.database.db import decrypt_data
        decrypted = decrypt_data(admin_password)
        if decrypted and decrypted == provided_pw:
            return True
    except Exception:
        pass
    return False

pending_admin_actions = {}

import random
import string
import datetime
from src.database.db import AsyncSessionLocal, get_user, encrypt_data

def generate_random_password(length=12):
    """
    Generates a secure random password of specified length.
    """
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for i in range(length))

async def delete_message_later(message: Message, delay: int):
    """
    Deletes a Telegram message after a specified delay in seconds.
    """
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass

async def audit_log(bot, admin_user, action_type, text=""):
    """
    Formats and sends an audit log message to the system logging channel.
    """
    from src.database.db import config
    sys_log_channel = config.get('sys_logging_channel_id')
    if not sys_log_channel:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    full_date = now.strftime("%d/%m/%Y %H:%M")

    msg = (f"[{full_date}] latanmcbot sys log: System Log [AUDIT] - "
           f"Admin UID: {admin_user.id} - Username: @{admin_user.username or 'unknown'} - "
           f"Action: {action_type} - Date: {date_str} - Time (UTC): {time_str} - {text}")

    try:
        await bot.send_message(chat_id=sys_log_channel, text=msg)
    except Exception as e:
        print(f"Failed to send audit log: {e}")

@router.message(Command("shutdown", "restart"))
async def handle_admin_commands(message: Message, db_user):
    """
    Command handler for `/shutdown` and `/restart` to trigger a system shutdown/restart.
    """
    is_master = False
    provided_pw = None
    parts = message.text.split(maxsplit=1)
    if len(parts) >= 2:
        provided_pw = parts[1]

    if provided_pw:
        if verify_master_password(provided_pw):
            is_master = True
        elif db_user and db_user.admin_level == 1:
            from src.database.db import decrypt_data
            if db_user.admin_password and decrypt_data(db_user.admin_password) == provided_pw:
                is_master = True

    if not is_master:
        return

    command_used = parts[0][1:]

    await audit_log(message.bot, db_user, command_used, f"Requested {command_used}")

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
    """
    Callback query handler to confirm and execute the shutdown/restart request.
    """
    action = callback_query.data.split('_')[2]

    await callback_query.message.edit_text(f"✅ System **{action}** confirmed. Executing...")
    await callback_query.answer(f"Executing {action}...", show_alert=True)

    await asyncio.sleep(1)

    import os
    os._exit(0)

@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, db_user):
    """
    Command handler for `/addadmin` to grant administrative access to a user.
    """
    if not db_user:
        return
    is_master = db_user.admin_level == 1

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /addadmin <user_id> <level> [master_password]")
        return

    target_id = parts[1]
    try:
        level = int(parts[2])
    except ValueError:
        await message.answer("Level must be a number (1=Master, 2=Admin, 3=Aspiring).")
        return

    if level not in [1, 2, 3]:
        await message.answer("Level must be 1, 2, or 3.")
        return

    if len(parts) < 4:
        pending_admin_actions[db_user.id] = f"addadmin_{target_id}_{level}"
        await message.answer("🔒 Please enter your master password:")
        return

    await process_addadmin(message, db_user, target_id, level, parts[3], is_master)

async def process_addadmin(message, db_user, target_id, level, master_pw, is_master):
    """
    Validates and executes user additions to the admin list, generating their password.
    """
    from src.database.db import decrypt_data

    password_valid = False
    if verify_master_password(master_pw):
        password_valid = True
    elif is_master and db_user and db_user.admin_password and decrypt_data(db_user.admin_password) == master_pw:
        password_valid = True

    if not password_valid:
        await message.answer("❌ Invalid password.")
        return

    target_id = int(target_id)
    async with AsyncSessionLocal() as session:
        target_user = await get_user(session, target_id)
        if not target_user:
            await message.answer("❌ User not found in database. They must start the bot first.")
            return

        new_pw = generate_random_password()
        target_user.admin_level = level
        target_user.admin_password = encrypt_data(new_pw)
        await session.commit()

    await audit_log(message.bot, db_user, "addadmin", f"Added/Updated user {target_id} to level {level}")
    await message.answer(f"✅ User {target_id} is now admin level {level}.")

    try:
        msg = await message.bot.send_message(
            chat_id=target_id,
            text=f"🎉 You have been granted admin level {level}!\n\nYour personal password is: `{new_pw}`\n\n_This message will be deleted in 30 minutes._",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_message_later(msg, 30 * 60))
    except Exception as e:
        await message.answer(f"⚠️ Could not DM the user their password. {e}")

@router.message(Command("promote", "demote", "dismiss"))
async def cmd_hierarchy(message: Message, db_user):
    """
    Command handler for `/promote`, `/demote`, and `/dismiss` hierarchical actions.
    """
    if not db_user:
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(f"Usage: {parts[0]} <user_id> [master_password]")
        return

    command = parts[0][1:]
    target_id = parts[1]

    if len(parts) < 3:
        pending_admin_actions[db_user.id] = f"{command}_{target_id}"
        await message.answer("🔒 Please enter your master password:")
        return

    await process_hierarchy(message, db_user, target_id, command, parts[2])

async def process_hierarchy(message, db_user, target_id, command, master_pw):
    """
    Updates the database record to promote, demote, or remove an admin user.
    """
    from src.database.db import decrypt_data
    password_valid = False
    if verify_master_password(master_pw):
        password_valid = True
    elif db_user and db_user.admin_level == 1 and db_user.admin_password and decrypt_data(db_user.admin_password) == master_pw:
        password_valid = True

    if not password_valid:
        await message.answer("❌ Invalid password.")
        return

    target_id = int(target_id)
    async with AsyncSessionLocal() as session:
        target_user = await get_user(session, target_id)
        if not target_user:
            await message.answer("❌ User not found.")
            return

        current_level = target_user.admin_level
        if current_level == 0 and command != "dismiss":
            await message.answer("❌ User is not an admin. Use /addadmin first.")
            return

        if command == "promote" and current_level > 1:
            target_user.admin_level -= 1
        elif command == "demote" and current_level < 3 and current_level > 0:
            target_user.admin_level += 1
        elif command == "dismiss":
            target_user.admin_level = 0
            target_user.admin_password = None

        new_level = target_user.admin_level
        await session.commit()

    await audit_log(message.bot, db_user, command, f"User {target_id} is now level {new_level}")
    await message.answer(f"✅ User {target_id} is now admin level {new_level}.")

@router.message(Command("regenpsw"))
async def cmd_regenpsw(message: Message, db_user):
    """
    Command handler for `/regenpsw` to regenerate an admin's password.
    """
    if not db_user:
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /regenpsw <user_id> [master_password]")
        return

    target_id = parts[1]

    if len(parts) < 3:
        pending_admin_actions[db_user.id] = f"regenpsw_{target_id}"
        await message.answer("🔒 Please enter your master password:")
        return

    await process_regenpsw(message, db_user, target_id, parts[2])

async def process_regenpsw(message, db_user, target_id, master_pw):
    """
    Generates a new secure password for an admin and updates their database record.
    """
    from src.database.db import decrypt_data
    password_valid = False
    if verify_master_password(master_pw):
        password_valid = True
    elif db_user and db_user.admin_level == 1 and db_user.admin_password and decrypt_data(db_user.admin_password) == master_pw:
        password_valid = True

    if not password_valid:
        await message.answer("❌ Invalid password.")
        return

    target_id = int(target_id)
    async with AsyncSessionLocal() as session:
        target_user = await get_user(session, target_id)
        if not target_user or target_user.admin_level == 0:
            await message.answer("❌ User not found or not an admin.")
            return

        new_pw = generate_random_password()
        target_user.admin_password = encrypt_data(new_pw)
        await session.commit()

    await audit_log(message.bot, db_user, "regenpsw", f"Regenerated password for user {target_id}")
    await message.answer(f"✅ Regenerated password for user {target_id}.")

    try:
        msg = await message.bot.send_message(
            chat_id=target_id,
            text=f"🔑 Your admin password has been regenerated.\n\nYour new password is: `{new_pw}`\n\n_This message will be deleted in 30 minutes._",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_message_later(msg, 30 * 60))
    except Exception as e:
        await message.answer(f"⚠️ Could not DM the user their new password. {e}")

@router.message(lambda message: message.from_user.id in pending_admin_actions and not message.text.startswith('/'))
async def handle_pending_admin_input(message: Message, db_user):
    """
    Router that intercepts non-command text inputs for pending administrative actions.
    """
    action = pending_admin_actions[message.from_user.id]

    if action == "broadcast":
        password = message.text
        pending_admin_actions[message.from_user.id] = f"broadcast_msg_{password}"
        await message.answer("Please enter the message to broadcast:")
        asyncio.create_task(delete_message_later(message, 1))
        return

    if action.startswith("broadcast_msg_"):
        password = action.split("_", 2)[2]
        text_to_broadcast = message.text
        del pending_admin_actions[message.from_user.id]
        await process_broadcast(message, db_user, password, text_to_broadcast)
        return

    if action.startswith("addadmin_"):
        parts = action.split("_")
        target_id = parts[1]
        level = int(parts[2])
        password = message.text
        del pending_admin_actions[message.from_user.id]
        asyncio.create_task(delete_message_later(message, 1))
        is_master = (db_user and db_user.admin_level == 1)
        await process_addadmin(message, db_user, target_id, level, password, is_master)
        return

    if action.startswith("regenpsw_"):
        target_id = action.split("_")[1]
        password = message.text
        del pending_admin_actions[message.from_user.id]
        asyncio.create_task(delete_message_later(message, 1))
        await process_regenpsw(message, db_user, target_id, password)
        return

    if action.startswith("promote_") or action.startswith("demote_") or action.startswith("dismiss_"):
        parts = action.split("_")
        command = parts[0]
        target_id = parts[1]
        password = message.text
        del pending_admin_actions[message.from_user.id]
        asyncio.create_task(delete_message_later(message, 1))
        await process_hierarchy(message, db_user, target_id, command, password)
        return

    if action.startswith("cancelq_"):
        target_id = int(action.split("_")[1])
        password = message.text
        del pending_admin_actions[message.from_user.id]
        asyncio.create_task(delete_message_later(message, 1))

        from src.database.db import decrypt_data
        password_valid = False
        if verify_master_password(password):
            password_valid = True
        elif db_user and db_user.admin_password and decrypt_data(db_user.admin_password) == password:
            password_valid = True

        if not password_valid:
            await message.answer("❌ Invalid password.")
            return

        from src.utils.queue_manager import queue_manager
        queue_manager.cancel_all_for_user(target_id)
        await audit_log(message.bot, db_user, "cancel_queue", f"Cancelled queue for user {target_id}")
        await message.answer(f"✅ Cancelled all downloads for user {target_id}.")
        return

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, db_user):
    """
    Command handler for `/broadcast` to initiate broadcasting messages to all users.
    """
    if not db_user:
        return

    parts = message.text.split(maxsplit=2)

    if len(parts) == 1:
        pending_admin_actions[db_user.id] = "broadcast"
        await message.answer("🔒 Please enter your admin password:")
        return

    if len(parts) == 2:
        pending_admin_actions[db_user.id] = f"broadcast_msg_{parts[1]}"
        await message.answer("Please enter the message to broadcast:")
        return

    await process_broadcast(message, db_user, parts[1], parts[2])

async def process_broadcast(message, db_user, password, text_to_broadcast):
    """
    Validates admin password and sends the broadcast message to all users in the database.
    """
    from src.database.db import decrypt_data
    password_valid = False
    if verify_master_password(password):
        password_valid = True
    elif db_user and db_user.admin_level in [1, 2] and db_user.admin_password and decrypt_data(db_user.admin_password) == password:
        password_valid = True

    if not password_valid:
        await message.answer("❌ Invalid password.")
        return

    await message.answer("Broadcasting message...")
    await audit_log(message.bot, db_user, "broadcast", f"Sent broadcast message: {text_to_broadcast[:50]}...")

    success_users = []
    failed_users = []

    from sqlalchemy import select
    from src.database.models import User

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.id))
        users = result.scalars().all()

    for u_id in users:
        try:
            await message.bot.send_message(chat_id=u_id, text=text_to_broadcast)
            success_users.append(u_id)
            await asyncio.sleep(0.05)
        except Exception:
            failed_users.append(u_id)

    summary_msg = f"✅ Broadcast complete.\nSuccess: {len(success_users)}\nFailed: {len(failed_users)}"
    await message.answer(summary_msg)

    from src.database.db import config
    sys_log_channel = config.get('sys_logging_channel_id')
    if sys_log_channel:
        try:
            detailed_log = "<b>Broadcast Details:</b>\n"
            for uid in success_users:
                detailed_log += f"✅ {uid}\n"
            for uid in failed_users:
                detailed_log += f"❌ {uid}\n"

            chunk_size = 4000
            for i in range(0, len(detailed_log), chunk_size):
                await message.bot.send_message(chat_id=sys_log_channel, text=detailed_log[i:i+chunk_size], parse_mode="HTML")
        except Exception as e:
            import logging
            logging.error(f"Failed to log detailed broadcast info: {e}")
