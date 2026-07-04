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
import sys
import os
import html
from aiogram import Bot

# Ensure LLM path is reachable
sys.path.append(os.path.abspath('.'))

class TelegramLogHandler(logging.Handler):
    """
    Custom logging handler that routes log records to a specified Telegram channel/chat,
    including automated LLM-powered diagnostics for ERROR events.
    """
    def __init__(self, bot: Bot, chat_id: str):
        super().__init__()
        self.bot = bot
        self.chat_id = chat_id

    def emit(self, record):
        """
        Emits a log record, sending it asynchronously to Telegram, and triggers LLM diagnostics if level is ERROR.
        """
        log_entry = self.format(record)

        if not self.chat_id:
            return

        async def send_log():
            try:
                escaped_log = html.escape(log_entry[:4000])
                msg = f"<b>System Log [{record.levelname}]</b>\n<pre>{escaped_log}</pre>"
                await self.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode="HTML")

                if record.levelname == 'ERROR':
                    try:
                        # Skip highly repetitive or transient noisy errors
                        noisy_markers = ["asyncio.exceptions.CancelledError", "TelegramRetryAfter", "NameError: cannot access free variable 'TelegramAPIError'"]
                        if any(marker in log_entry for marker in noisy_markers):
                            return

                        import hashlib
                        import datetime
                        from src.database.db import AsyncSessionLocal
                        from src.database.models import ErrorInsight
                        from sqlalchemy import select

                        error_lines = [line for line in log_entry.split('\n') if "File " in line or "Error:" in line or "Exception:" in line]
                        error_signature = "\n".join(error_lines[-5:]) if error_lines else log_entry[:500]
                        error_code_assigned = hashlib.sha256(error_signature.encode()).hexdigest()[:16]

                        cached_insight = None
                        async with AsyncSessionLocal() as session:
                            result = await session.execute(select(ErrorInsight).where(ErrorInsight.error_code_assigned == error_code_assigned))
                            record_obj = result.scalar_one_or_none()
                            if record_obj:
                                cached_insight = record_obj.llm_insight

                        if cached_insight:
                            insight = cached_insight
                            insight_msg = f"🤖 <b>LLM Insight (Cached - Code: {error_code_assigned}):</b>\n\n{insight}"
                        else:
                            from LLM.insight import get_llm_insight
                            insight = await get_llm_insight(log_entry)
                            if insight:
                                insight_msg = f"🤖 <b>LLM Insight (New - Code: {error_code_assigned}):</b>\n\n{insight}"
                                async with AsyncSessionLocal() as session:
                                    new_insight = ErrorInsight(
                                        error_code_assigned=error_code_assigned,
                                        original_error=log_entry,
                                        date=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                        llm_insight=insight
                                    )
                                    session.add(new_insight)
                                    await session.commit()

                        if insight:
                            chunk_size = 4000
                            for i in range(0, len(insight_msg), chunk_size):
                                await self.bot.send_message(
                                    chat_id=self.chat_id,
                                    text=insight_msg[i:i+chunk_size],
                                    parse_mode="HTML"
                                )
                    except Exception as llm_err:
                        print(f"LLM Insight failed silently: {llm_err}")

            except Exception as e:
                print(f"Failed to send log to Telegram: {e}")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_log())
        except RuntimeError:
            try:
                asyncio.run(send_log())
            except Exception:
                pass
