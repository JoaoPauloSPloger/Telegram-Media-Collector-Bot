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
import logging
import time
from typing import Any, Callable, Dict, Optional
from aiogram import Bot
from aiogram.exceptions import (
    TelegramRetryAfter,
    TelegramForbiddenError,
    TelegramBadRequest,
    TelegramAPIError,
)

logger = logging.getLogger(__name__)

class SchedulerPriority:
    CRITICAL = 0   # Security alerts, admin emergency notifications
    HIGH = 1       # Delivered media files to users
    NORMAL = 2     # Command responses, user notifications
    LOW = 3        # UI progress bars, broadcast items, channel audit logs

class ScheduledTask:
    def __init__(self, priority: int, coro_fn: Callable, args: tuple, kwargs: dict, chat_id: Optional[int] = None, future: Optional[asyncio.Future] = None):
        self.priority = priority
        self.coro_fn = coro_fn
        self.args = args
        self.kwargs = kwargs
        self.chat_id = chat_id
        self.future = future
        self.timestamp = time.time()
        self.retry_count = 0

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp

class TelegramScheduler:
    """
    Intelligent Rate-Limiter and Message Scheduler for Telegram Bot API.
    
    Protects the bot against Telegram flood restrictions, spam throttling,
    and temporary account blocks by:
    - Queuing outbound messages and media with priority support.
    - Enforcing strict dispatch rate limits (default max 25 req/sec globally,
      and minimum intervals between messages to the same chat).
    - Automatically intercepting TelegramRetryAfter (HTTP 429) errors,
      suspending the queue for the exact required duration, and retrying
      the failed message without losing data.
    - Providing both queue-based async dispatch and direct execute_safe wrappers.
    """

    def __init__(self, max_rate_per_sec: float = 25.0, min_chat_interval: float = 0.08):
        self.max_rate_per_sec = max_rate_per_sec
        self.min_chat_interval = min_chat_interval
        self.queue: asyncio.PriorityQueue[ScheduledTask] = asyncio.PriorityQueue()
        self.worker_task: Optional[asyncio.Task] = None
        self.is_running = False

        self._pause_until = 0.0
        self._last_send_time = 0.0
        self._chat_last_send: Dict[int, float] = {}

        # Telemetry
        self.total_processed = 0
        self.total_flood_waits = 0
        self.last_flood_wait_seconds = 0
        self.consecutive_errors = 0

    def start(self):
        """Starts the background worker queue processor."""
        if not self.is_running:
            self.is_running = True
            self.worker_task = asyncio.create_task(self._worker_loop())
            logger.info("🚀 TelegramScheduler started.")

    async def stop(self):
        """Stops the worker and drains or cancels remaining tasks."""
        self.is_running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
            logger.info("🛑 TelegramScheduler stopped.")

    @property
    def is_paused(self) -> bool:
        return time.time() < self._pause_until

    @property
    def remaining_pause(self) -> float:
        return max(0.0, self._pause_until - time.time())

    def pause(self, seconds: float, reason: str = "Flood restriction"):
        """Temporarily pause all message dispatch for specified seconds."""
        self._pause_until = max(self._pause_until, time.time() + seconds)
        self.total_flood_waits += 1
        self.last_flood_wait_seconds = int(seconds)
        logger.warning(
            f"⚠️ [TelegramScheduler] {reason}: Pausing all outbound Telegram requests for {seconds:.1f}s "
            f"(Queue size: {self.queue.qsize()})"
        )

    async def execute_safe(
        self,
        coro_fn: Callable[..., Any],
        *args,
        max_retries: int = 5,
        target_chat_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        Directly executes an async Telegram API call with automatic rate-limit
        enforcement and TelegramRetryAfter backoff recovery.
        """
        effective_chat_id = target_chat_id or chat_id or kwargs.get('chat_id')
        call_kwargs = dict(kwargs)

        if chat_id is not None and 'chat_id' not in call_kwargs:
            import inspect
            try:
                sig = inspect.signature(coro_fn)
                if 'chat_id' in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                    call_kwargs['chat_id'] = chat_id
            except (ValueError, TypeError):
                call_kwargs['chat_id'] = chat_id

        retries = 0
        while retries <= max_retries:
            # Respect active pause
            while self.is_paused:
                wait_time = self.remaining_pause
                if wait_time > 0:
                    await asyncio.sleep(min(wait_time + 0.1, 5.0))

            # Enforce chat interval
            if effective_chat_id:
                last_chat = self._chat_last_send.get(effective_chat_id, 0.0)
                diff = time.time() - last_chat
                if diff < self.min_chat_interval:
                    await asyncio.sleep(self.min_chat_interval - diff)

            try:
                if asyncio.iscoroutinefunction(coro_fn):
                    res = await coro_fn(*args, **call_kwargs)
                else:
                    res = coro_fn(*args, **call_kwargs)
                    if asyncio.iscoroutine(res):
                        res = await res

                now = time.time()
                self._last_send_time = now
                if effective_chat_id:
                    self._chat_last_send[effective_chat_id] = now
                self.total_processed += 1
                self.consecutive_errors = 0
                return res

            except TelegramRetryAfter as e:
                retries += 1
                sleep_s = int(e.retry_after) + 1
                self.pause(sleep_s, reason=f"Telegram 429 Flood Control (retry {retries}/{max_retries})")
                await asyncio.sleep(sleep_s)

            except TelegramForbiddenError as e:
                # Bot blocked or kicked
                logger.info(f"🚫 [TelegramScheduler] Target chat {chat_id} forbidden: {e}")
                raise

            except TelegramBadRequest as e:
                err_lower = str(e).lower()
                if "message to reply not found" in err_lower or "message is not modified" in err_lower:
                    raise
                # Check for rate-limiting inside bad request
                if "flood" in err_lower or "too many requests" in err_lower:
                    retries += 1
                    sleep_s = 5 * retries
                    self.pause(sleep_s, reason="Transient flood detected in BadRequest")
                    await asyncio.sleep(sleep_s)
                else:
                    raise

            except TelegramAPIError as e:
                retries += 1
                if retries > max_retries:
                    raise
                backoff = min(2 ** retries, 15)
                logger.warning(f"⚠️ [TelegramScheduler] Telegram API Error: {e}. Backing off {backoff}s...")
                await asyncio.sleep(backoff)

            except Exception:
                raise

        raise RuntimeError(f"Max retries ({max_retries}) exceeded in TelegramScheduler.execute_safe")

    async def schedule(
        self,
        coro_fn: Callable[..., Any],
        *args,
        priority: int = SchedulerPriority.NORMAL,
        chat_id: Optional[int] = None,
        **kwargs
    ) -> asyncio.Future:
        """
        Enqueues an async action into the PriorityQueue to be executed safely in background.
        Returns a Future that can be awaited if the caller needs the return value.
        """
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        task = ScheduledTask(
            priority=priority,
            coro_fn=coro_fn,
            args=args,
            kwargs=kwargs,
            chat_id=chat_id,
            future=fut
        )
        await self.queue.put(task)
        return fut

    async def send_message_safe(
        self,
        bot: Bot,
        chat_id: int,
        text: str,
        priority: int = SchedulerPriority.NORMAL,
        **kwargs
    ) -> Any:
        """Helper to send a message via execute_safe."""
        return await self.execute_safe(bot.send_message, chat_id=chat_id, text=text, **kwargs)

    async def edit_message_safe(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        text: str,
        priority: int = SchedulerPriority.LOW,
        **kwargs
    ) -> Any:
        """Helper to safely edit message text, handling unmodified or missing messages gracefully."""
        try:
            return await self.execute_safe(
                bot.edit_message_text,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                **kwargs
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower() or "message to edit not found" in str(e).lower():
                return None
            raise

    async def _worker_loop(self):
        """Continuously dequeues and executes scheduled tasks with rate and flood controls."""
        min_interval = 1.0 / self.max_rate_per_sec

        while self.is_running:
            try:
                # Respect flood pause
                while self.is_paused:
                    wait_s = self.remaining_pause
                    if wait_s > 0:
                        await asyncio.sleep(min(wait_s + 0.1, 2.0))

                task: ScheduledTask = await self.queue.get()

                # Global rate throttle
                elapsed = time.time() - self._last_send_time
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

                # Execute with recovery
                try:
                    result = await self.execute_safe(
                        task.coro_fn,
                        *task.args,
                        target_chat_id=task.chat_id,
                        **task.kwargs
                    )
                    if task.future and not task.future.done():
                        task.future.set_result(result)
                except Exception as e:
                    if task.future and not task.future.done():
                        task.future.set_exception(e)
                finally:
                    self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in scheduler worker: {e}")
                await asyncio.sleep(1)

    def get_stats(self) -> dict:
        """Returns diagnostic metrics about scheduler operation."""
        return {
            "queue_size": self.queue.qsize(),
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "remaining_pause": round(self.remaining_pause, 1),
            "total_processed": self.total_processed,
            "total_flood_waits": self.total_flood_waits,
            "last_flood_wait_seconds": self.last_flood_wait_seconds,
            "max_rate_per_sec": self.max_rate_per_sec,
        }

# Global singleton
telegram_scheduler = TelegramScheduler()
