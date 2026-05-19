from src.database.db import AsyncSessionLocal
from src.database.models import Cache
from sqlalchemy import select

async def get_cached_file_id(url: str, media_type: str):
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
    if not url: # Safety check, can't cache without URL
        return

    try:
        async with AsyncSessionLocal() as session:
            # Check if exists to update, else insert
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
