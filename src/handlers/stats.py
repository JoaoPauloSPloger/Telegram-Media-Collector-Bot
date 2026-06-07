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

import asyncio
import psutil
import time
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError
from src.database.db import AsyncSessionLocal, User, Event
from sqlalchemy import select, func

router = Router()
start_time = time.time()

active_panels = {}

def get_system_metrics():
    """
    Retrieve current system resource statistics including CPU, virtual memory,
    disk percentage, network I/O stats, and uptime.

    Returns:
        tuple: (cpu_percent, ram_percent, disk_percent, net_sent_mb, net_recv_mb, uptime_str)
    """
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    net = psutil.net_io_counters()
    net_sent = net.bytes_sent / (1024 * 1024)
    net_recv = net.bytes_recv / (1024 * 1024)

    uptime_seconds = int(time.time() - start_time)
    m, s = divmod(uptime_seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    uptime_str = f"{d}d {h}h {m}m"

    return cpu, ram, disk, net_sent, net_recv, uptime_str

async def get_db_metrics():
    """
    Retrieve database metrics containing the total number of registered users
    and total download events.

    Returns:
        tuple: (users_count, events_count)
    """
    async with AsyncSessionLocal() as session:
        users_count = await session.scalar(select(func.count()).select_from(User))
        events_count = await session.scalar(select(func.count()).select_from(Event))
        return users_count or 0, events_count or 0

def format_stats(cpu, ram, disk, net_sent, net_recv, uptime, users_count, events_count):
    """
    Format system and database metrics into a user-friendly HTML message.

    Args:
        cpu (float): CPU usage percentage.
        ram (float): RAM usage percentage.
        disk (float): Disk usage percentage.
        net_sent (float): Sent data in MB.
        net_recv (float): Received data in MB.
        uptime (str): System uptime string.
        users_count (int): Total database users.
        events_count (int): Total database download events.

    Returns:
        str: Formatted HTML text for the statistics dashboard.
    """
    return (
        f"📊 <b>Admin Live Dashboard</b>\n\n"
        f"🖥 <b>System</b>\n"
        f"├ CPU: {cpu}%\n"
        f"├ RAM: {ram}%\n"
        f"└ Disk: {disk}%\n\n"
        f"🌐 <b>Network</b>\n"
        f"├ Sent: {net_sent:.1f} MB\n"
        f"└ Recv: {net_recv:.1f} MB\n\n"
        f"📈 <b>Bot Stats</b>\n"
        f"├ Users: {users_count}\n"
        f"├ Total Downloads: {events_count}\n"
        f"└ Uptime: {uptime}\n\n"
        f"<i>Updates every 5s...</i>"
    )

@router.message(Command("stats"))
async def show_stats(message: Message, db_user):
    """
    Handle the /stats command. Verifies admin authorization, presents the initial dashboard,
    and initiates a background task to refresh the metrics every 5 seconds.

    Args:
        message (Message): The Telegram command message.
        db_user: The database user object.
    """
    if not db_user or db_user.admin_level not in [1, 2]:
        return

    cpu, ram, disk, net_sent, net_recv, uptime = get_system_metrics()
    users_count, events_count = await get_db_metrics()

    text = format_stats(cpu, ram, disk, net_sent, net_recv, uptime, users_count, events_count)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Close Dashboard", callback_data="close_stats")
    ]])

    msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    active_panels[msg.message_id] = True

    async def update_panel():
        start_update = time.time()
        try:
            while active_panels.get(msg.message_id, False):
                await asyncio.sleep(5)
                if not active_panels.get(msg.message_id, False):
                    break

                if time.time() - start_update > 300:
                    try:
                        await msg.edit_text("⏳ Dashboard expired to save system resources. Run /stats again.", reply_markup=None)
                    except TelegramAPIError:
                        pass
                    break

                cpu, ram, disk, net_sent, net_recv, uptime = get_system_metrics()
                users_count, events_count = await get_db_metrics()
                new_text = format_stats(cpu, ram, disk, net_sent, net_recv, uptime, users_count, events_count)

                try:
                    await msg.edit_text(new_text, reply_markup=keyboard, parse_mode="HTML")
                except TelegramAPIError as e:
                    if "message to edit not found" in str(e).lower() or "message is not modified" not in str(e).lower():
                        break
                    pass
        finally:
            active_panels.pop(msg.message_id, None)

    asyncio.create_task(update_panel())

@router.callback_query(lambda c: c.data == "close_stats")
async def close_stats(callback_query):
    """
    Handle the close stats callback query. Stops the dashboard background task and edits
    the message to indicate that the dashboard has closed.

    Args:
        callback_query (CallbackQuery): The Telegram callback query.
    """
    try:
        await callback_query.answer()
    except TelegramAPIError:
        pass

    msg_id = callback_query.message.message_id
    if msg_id in active_panels:
        active_panels[msg_id] = False
        del active_panels[msg_id]

    try:
        await callback_query.message.edit_text("✅ Dashboard closed.")
    except TelegramAPIError:
        pass
