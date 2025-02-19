from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database.database import toggle_printer_status, get_printer_status

router = Router()

@router.message(Command("status"))
async def show_status(message: Message):
    printer_id = message.from_user.id
    status = await get_printer_status(printer_id)

    if status is None:
        await message.answer("❌ Вы не зарегистрированы как исполнитель.")
        return

    status_text = "🟢 Активен" if status else "🔴 Неактивен"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Изменить статус", callback_data="toggle_status")]
        ]
    )

    await message.answer(f"Ваш текущий статус: {status_text}", reply_markup=keyboard)


@router.callback_query(F.data == "toggle_status")
async def toggle_status(call: CallbackQuery):
    printer_id = call.from_user.id
    new_status = await toggle_printer_status(printer_id)

    if new_status is None:
        await call.answer("⚠ Ошибка при изменении статуса.")
        return

    status_text = "🟢 Активен" if new_status else "🔴 Неактивен"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Изменить статус", callback_data="toggle_status")]
        ]
    )

    await call.message.edit_text(f"Ваш текущий статус: {status_text}", reply_markup=keyboard)
    await call.answer("✅ Статус обновлён!")
