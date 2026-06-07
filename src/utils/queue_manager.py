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
from collections import defaultdict

class UserQueueManager:
    """
    Manages concurrent downloads on a per-user basis using semaphores, allowing queueing and cancellation of events.
    """
    def __init__(self, max_concurrent_per_user=1):
        self.max_concurrent = max_concurrent_per_user
        self.user_semaphores = defaultdict(lambda: asyncio.Semaphore(self.max_concurrent))
        self.user_queues = defaultdict(list)
        self.active_tasks = {}
        self.user_active_events = defaultdict(set)
        self.cancelled_events = set()

    async def acquire(self, user_id, event_id, bot=None):
        """
        Enqueues an event and waits for the user's semaphore to be acquired.
        """
        self.user_queues[user_id].append(event_id)

        from src.database.db import config
        threshold = config.get('queue_alert_threshold', 50)
        current_queue_len = len(self.user_queues[user_id])

        if current_queue_len == threshold and bot:
            await self._send_queue_alert(user_id, current_queue_len, bot)

        await self.user_semaphores[user_id].acquire()
        if event_id in self.user_queues[user_id]:
            self.user_queues[user_id].remove(event_id)
        self.user_active_events[user_id].add(event_id)

    async def _send_queue_alert(self, user_id, queue_len, bot=None):
        """
        Sends an alert message to the media channel when a user's queue exceeds the threshold.
        """
        from src.database.db import config
        media_channel = config.get('media_logging_channel_id')
        if not media_channel or not bot:
            return

        bot_username = config.get('bot_username')
        if not bot_username:
            try:
                me = await bot.get_me()
                bot_username = me.username
            except Exception:
                bot_username = "unknown_bot"

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Cancel User Queue", url=f"https://t.me/{bot_username}?start=cancelqueue_{user_id}")
        ]])

        msg = f"⚠️ **Queue Alert** ⚠️\n\nUser ID `{user_id}` has reached `{queue_len}` items in their download queue!"
        try:
            await bot.send_message(chat_id=media_channel, text=msg, reply_markup=keyboard, parse_mode="Markdown")
        except Exception as e:
            import logging
            logging.error(f"Failed to send queue alert to media channel: {e}")

    def release(self, user_id, event_id):
        """
        Releases the user's semaphore and cleans up task tracking metadata.
        """
        self.user_semaphores[user_id].release()
        if event_id in self.user_active_events[user_id]:
            self.user_active_events[user_id].remove(event_id)
        if event_id in self.active_tasks:
            del self.active_tasks[event_id]

    def cancel(self, user_id, event_id):
        """
        Cancels a specific download event and releases its associated slot.
        """
        self.cancelled_events.add(event_id)
        if event_id in self.user_queues[user_id]:
            self.user_queues[user_id].remove(event_id)
            self.release(user_id, event_id)

        if event_id in self.active_tasks:
            self.active_tasks[event_id].cancel()

    def cancel_all_for_user(self, user_id):
        """
        Cancels all pending and active download events for a specific user.
        """
        events_to_cancel = list(self.user_queues[user_id]) + list(self.user_active_events[user_id])
        for event_id in events_to_cancel:
            self.cancel(user_id, event_id)

    def is_cancelled(self, event_id):
        """
        Checks if a download event has been marked as cancelled.
        """
        return event_id in self.cancelled_events

queue_manager = UserQueueManager()
