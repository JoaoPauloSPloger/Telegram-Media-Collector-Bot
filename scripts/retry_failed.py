import os
import sys
import asyncio
import logging

# Add the root directory to sys.path so we can import src modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database.db import AsyncSessionLocal, Event, User, config
from src.utils.downloader import download_video

# Create a minimal fake message class to pass to handle_upload
class FakeUser:
    def __init__(self, id, username):
        self.id = id
        self.username = username

class FakeBot:
    def __init__(self, bot, user_id):
        self._bot = bot
        self.user_id = user_id

    async def send_document(self, chat_id, **kwargs):
        return await self._bot.send_document(chat_id=chat_id, **kwargs)

    async def send_video(self, chat_id, **kwargs):
        return await self._bot.send_video(chat_id=chat_id, **kwargs)

    async def send_audio(self, chat_id, **kwargs):
        return await self._bot.send_audio(chat_id=chat_id, **kwargs)

    async def send_photo(self, chat_id, **kwargs):
        return await self._bot.send_photo(chat_id=chat_id, **kwargs)

    async def send_message(self, chat_id, **kwargs):
        return await self._bot.send_message(chat_id=chat_id, **kwargs)

class FakeMessage:
    def __init__(self, bot, user_id, username):
        self.bot = FakeBot(bot, user_id)
        self.from_user = FakeUser(user_id, username)

    async def reply(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("message to reply not found")

    async def reply_video(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("message to reply not found")

    async def reply_audio(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("message to reply not found")

    async def reply_photo(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("message to reply not found")

    async def reply_document(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("message to reply not found")

    async def answer(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("chat not found")

    async def answer_video(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("chat not found")

    async def answer_audio(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("chat not found")

    async def answer_photo(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("chat not found")

    async def answer_document(self, *args, **kwargs):
        from aiogram.exceptions import TelegramAPIError
        raise TelegramAPIError("chat not found")

async def retry_failed_downloads():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("RetryScript")

    bot_token = config['bot_token']
    local_api_server = config.get('local_api_server')

    if local_api_server:
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(local_api_server),
            timeout=300
        )
        bot = Bot(token=bot_token, session=session)
    else:
        session = AiohttpSession(timeout=300)
        bot = Bot(token=bot_token, session=session)

    try:
        async with AsyncSessionLocal() as db_session:
            # Find all failed events
            stmt = select(Event).where(Event.status == 'failed')
            result = await db_session.execute(stmt)
            failed_events = result.scalars().all()

            logger.info(f"Found {len(failed_events)} failed events to retry.")

            if not failed_events:
                return

            from src.handlers.upload import handle_upload

            for event in failed_events:
                logger.info(f"Retrying event {event.event_id}: {event.url}")

                # Update status to started
                event.status = 'started'
                await db_session.commit()

                # Fetch user
                user = await db_session.get(User, event.user_id)
                if not user:
                    logger.warning(f"User {event.user_id} not found for event {event.event_id}. Skipping.")
                    event.status = 'failed'
                    event.error_msg = 'User not found'
                    await db_session.commit()
                    continue

                # Determine media type (matching download logic)
                import urllib.parse
                parsed_url = urllib.parse.urlparse(event.url)
                domain = parsed_url.netloc.lower()

                audio_domains = [
                    'open.spotify.com', 'spotify.com',
                    'y.qq.com', 'qq.com',
                    'music.youtube.com',
                    'music.apple.com',
                    'music.amazon.com',
                    'music.163.com',
                    'soundcloud.com',
                    'jiosaavn.com', 'www.jiosaavn.com',
                    'gaana.com', 'www.gaana.com',
                    'deezer.com', 'www.deezer.com',
                    'tidal.com'
                ]

                media_type = 'audio' if any(audio_domain in domain for audio_domain in audio_domains) else 'video'

                # Download
                dl_result = await download_video(event.url, event_id=event.event_id, media_type=media_type)

                if dl_result.get('success'):
                    # Upload (using FakeMessage which will force fallback to DMing the user)
                    fake_msg = FakeMessage(bot, user.id, user.username)

                    try:
                        await handle_upload(fake_msg, dl_result, event.event_id, user)
                        logger.info(f"Successfully retried and sent {event.event_id}")
                    except Exception as e:
                        logger.error(f"Error uploading {event.event_id}: {e}")
                else:
                    logger.error(f"Failed to download {event.event_id} again: {dl_result.get('error')}")
                    event.status = 'failed'
                    event.error_msg = dl_result.get('error', 'Unknown error')
                    await db_session.commit()

                # Sleep briefly to avoid spamming the bot API
                await asyncio.sleep(2)

    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(retry_failed_downloads())
