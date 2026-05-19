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

    sys_logging_channel_id = config.get('sys_logging_channel_id')
    if sys_logging_channel_id:
        from src.utils.telegram_logger import TelegramLogHandler
        telegram_handler = TelegramLogHandler(bot, sys_logging_channel_id)
        telegram_handler.setLevel(logging.ERROR) # Let's only send ERRORS to avoid spam
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        telegram_handler.setFormatter(formatter)
        logging.getLogger().addHandler(telegram_handler)

    dp = Dispatcher()
    dp.include_router(start.router)
    
    from src.handlers import settings
    dp.include_router(settings.router)
    
    from src.handlers import download, upload, stats, privacy
    dp.include_router(download.router)
    dp.include_router(upload.router)
    dp.include_router(stats.router)
    dp.include_router(privacy.router)
    
    from src.handlers import convert
    dp.include_router(convert.router)

    from src.handlers import inline
    dp.include_router(inline.router)

    # Register middleware
    from src.middlewares.eula import EulaMiddleware
    dp.message.middleware(EulaMiddleware())
    dp.callback_query.middleware(EulaMiddleware())
    dp.inline_query.middleware(EulaMiddleware())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
