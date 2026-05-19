import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from src.database.db import init_db, config
from src.handlers import start

async def main():
    logging.basicConfig(level=logging.INFO)
    
    await init_db()

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
        
    dp = Dispatcher()
    dp.include_router(start.router)
    
    from src.handlers import settings
    dp.include_router(settings.router)
    
    from src.handlers import download, upload
    dp.include_router(download.router)
    dp.include_router(upload.router)
    
    # Register middleware
    from src.middlewares.eula import EulaMiddleware
    dp.message.middleware(EulaMiddleware())
    dp.callback_query.middleware(EulaMiddleware())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
