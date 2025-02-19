from aiogram.types import Message
from aiogram.filters import Command
from bot import dp

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "🆘 Помощь\n\n"
        "Я бот для печати документов прямо из Telegram. 📄\n"
        "Вот что я умею:\n"
        "✅ Принимать файлы в формате PDF(в дальнейшем возможно расширение)\n"
        "✅ Настраивать параметры печати (цвет/ч/б)\n"
        "✅ Отправлять документы на печать быстро и удобно\n\n"
        "🔹 Чтобы начать, просто выбери того,у кого хочешь напечатать и отправь файл.\n"
        "🔹 Если возникли вопросы или проблемы, напиши /support.\n\n"
        "📌 Совет: Если бот не отвечает, попробуй перезапустить его командой /start."
    )