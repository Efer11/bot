from aiogram.types import BotCommand
from aiogram import Bot

async def set_bot_commands(bot: Bot):
    bot_commands = [
        BotCommand(command="/start", description="Для начала работы."),
        BotCommand(command="/help", description="Для получения дополнительной информации."),
        BotCommand(command="/support", description="Если Вам необходима помощь или Вы обнаружили ошибку"),
        BotCommand(command="/profile", description="Профиль исполнителя."),
        BotCommand(command="/status", description="Просмотреть статус активности. Только для исполнителей.")
    ]
    await bot.set_my_commands(bot_commands)