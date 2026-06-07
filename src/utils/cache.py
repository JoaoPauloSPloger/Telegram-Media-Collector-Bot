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

from src.database.db import AsyncSessionLocal
from src.database.models import Cache
from sqlalchemy import select

async def get_cached_file_id(url: str, media_type: str):
    """
    Retrieves the cached file ID, title, and description for a URL and media type.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Cache).where(Cache.url == url, Cache.media_type == media_type)
            )
            cache_entry = result.scalar_one_or_none()
            if cache_entry:
                return cache_entry.file_id, cache_entry.title, cache_entry.description
    except Exception:
        pass
    return None, None, None

async def set_cached_file_id(url: str, media_type: str, file_id: str, title: str = None, description: str = None):
    """
    Stores or updates a file ID, title, and description in the database cache.
    """
    if not url:
        return

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Cache).where(Cache.url == url, Cache.media_type == media_type)
            )
            cache_entry = result.scalar_one_or_none()

            if cache_entry:
                cache_entry.file_id = file_id
                if title: cache_entry.title = title
                if description: cache_entry.description = description
            else:
                cache_entry = Cache(url=url, media_type=media_type, file_id=file_id, title=title, description=description)
                session.add(cache_entry)

            await session.commit()
    except Exception:
        pass

async def delete_cached_file_id(url: str, media_type: str):
    """
    Deletes a cached entry for a given URL and media type from the database.
    """
    if not url:
        return

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Cache).where(Cache.url == url, Cache.media_type == media_type)
            )
            cache_entry = result.scalar_one_or_none()
            if cache_entry:
                await session.delete(cache_entry)
                await session.commit()
    except Exception:
        pass
