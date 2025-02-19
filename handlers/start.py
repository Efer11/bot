from aiogram.types import Message
from aiogram.filters import Command
from bot import dp
from keyboards.inline import start_inline_keyboard

@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я бот для печати документов. 📄\n\n"
        "С моей помощью ты можешь удобно и быстро распечатать файлы прямо из Telegram. "
        "Я поддерживаю различные форматы документов и изображений.\n\n"
        "Чтобы начать, выбери нужное действие ниже. Если у тебя возникнут вопросы, просто напиши /help."
    )
    await message.answer("Выберите действие:", reply_markup=start_inline_keyboard)
