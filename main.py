import asyncio
import logging
from bot import dp, bot
from handlers.menu import set_bot_commands
from handlers import start, help, document, support, print_support, status
from handlers.callback import router
from database.database import create_tables
from handlers.profile import profile_router
from handlers.print_support import support_router

async def main():
    logging.basicConfig(level=logging.INFO)
    await create_tables()
    dp.startup.register(set_bot_commands)

    #роутеры
    dp.include_router(document.router)
    dp.include_router(support_router)
    dp.include_router(profile_router)
    dp.include_router(router)
    dp.include_router(status.router)

    print(dp.resolve_used_update_types())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
