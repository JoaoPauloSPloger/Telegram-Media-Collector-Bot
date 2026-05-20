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
    def __init__(self, max_concurrent_per_user=1):
        self.max_concurrent = max_concurrent_per_user
        self.user_semaphores = defaultdict(lambda: asyncio.Semaphore(self.max_concurrent))
        self.user_queues = defaultdict(list)
        self.active_tasks = {} # event_id -> asyncio.Task
        self.cancelled_events = set()

    async def acquire(self, user_id, event_id):
        self.user_queues[user_id].append(event_id)
        await self.user_semaphores[user_id].acquire()
        if event_id in self.user_queues[user_id]:
            self.user_queues[user_id].remove(event_id)

    def release(self, user_id, event_id):
        self.user_semaphores[user_id].release()
        if event_id in self.active_tasks:
            del self.active_tasks[event_id]

    def cancel(self, user_id, event_id):
        self.cancelled_events.add(event_id)
        if event_id in self.user_queues[user_id]:
            self.user_queues[user_id].remove(event_id)
            self.release(user_id, event_id) # Release early if it was waiting

        if event_id in self.active_tasks:
            self.active_tasks[event_id].cancel()

    def is_cancelled(self, event_id):
        return event_id in self.cancelled_events

queue_manager = UserQueueManager()
