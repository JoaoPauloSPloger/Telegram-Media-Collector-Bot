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

import logging
import asyncio
from aiogram import Bot

class TelegramLogHandler(logging.Handler):
    def __init__(self, bot: Bot, chat_id: str):
        super().__init__()
        self.bot = bot
        self.chat_id = chat_id

    def emit(self, record):
        log_entry = self.format(record)

        # Don't log if chat_id is missing
        if not self.chat_id:
            return

        import html

        async def send_log():
            try:
                # Telegram has a 4096 char limit
                escaped_log = html.escape(log_entry[:4000])
                msg = f"<b>System Log [{record.levelname}]</b>\n<pre>{escaped_log}</pre>"
                await self.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode="HTML")
            except Exception as e:
                # Fallback to standard print if telegram send fails (avoid recursion)
                print(f"Failed to send log to Telegram: {e}")

        # Check if we have a running event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_log())
        except RuntimeError:
            # No running event loop (e.g. from a background thread).
            # We can use asyncio.run_coroutine_threadsafe if we know the main loop,
            # or simply run it synchronously if we don't care about blocking the thread.
            # Since this is for errors, it's safer to just run it.
            try:
                asyncio.run(send_log())
            except Exception:
                pass
