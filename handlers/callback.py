from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram import F, Router, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database.database import (
    register_printer, get_all_printers, toggle_printer_status,
    get_printer_status, get_printer_info, add_review, get_average_rating
)

router = Router()


class RegisterPrinter(StatesGroup):
    room_number = State()
    price_per_page = State()
    description = State()
    card_number = State()


class PrinterSelection(StatesGroup):
    choosing_importance = State()
    choosing_type = State()


user_printer_selection = {}

printer_types = {
    "printer_type_laser_bw": "Лазерный ч/б",
    "printer_type_laser_color": "Лазерный ч/б + цвет",
    "printer_type_laser_bw_scan": "Лазерный ч/б + скан",
    "printer_type_laser_color_scan": "Лазерный ч/б + цвет + скан",
    "printer_type_ink_bw": "Струйный ч/б",
    "printer_type_ink_color": "Струйный ч/б + цвет",
    "printer_type_ink_bw_scan": "Струйный ч/б + скан",
    "printer_type_ink_color_scan": "Струйный ч/б + цвет + скан"
}

# 🔹 Выбор исполнителя
@router.callback_query(F.data == "print")
async def print_callback(call: CallbackQuery, state: FSMContext):
    await call.message.delete()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, важно", callback_data="print_type_needed")],
            [InlineKeyboardButton(text="Нет, показать всех", callback_data="printer_show_all")]
        ]
    )

    await call.message.answer("Важно ли вам, какой тип принтера у исполнителя?", reply_markup=keyboard)
    await state.set_state(PrinterSelection.choosing_importance)


# 🔹 Если тип принтера важен, предлагаем выбор
@router.callback_query(F.data == "print_type_needed")
async def choose_printer_type(call: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"select_type_{key}")]
            for key, name in printer_types.items()
        ]
    )

    await call.message.edit_text("Выберите нужный тип принтера:", reply_markup=keyboard)
    await state.set_state(PrinterSelection.choosing_type)


# 🔹 Фильтрация исполнителей по типу принтера (по частичному совпадению)
@router.callback_query(F.data.startswith("select_type_"))
async def filter_printers_by_type(call: CallbackQuery):
    selected_key = call.data.replace("select_type_", "")  # Получаем ключ типа принтера
    selected_type = printer_types.get(selected_key)  # Получаем строковое значение

    if not selected_type:
        await call.message.edit_text("Ошибка: выбранный тип принтера не найден.")
        return

    printers = await get_all_printers()

    # Фильтруем по частичному совпадению
    filtered_printers = [p for p in printers if p.get("printer_type") and selected_type in p["printer_type"]]

    if not filtered_printers:
        await call.message.edit_text("Нет исполнителей с выбранным типом принтера. Попробуйте позже.")
        return

    printer_list_text = "\n\n".join([
        f"👤 {p['full_name']} | 🏠 {p['room_number']} | 💰 {p['price_per_page']} руб.\n🖨 {p['printer_type']}"
        for p in filtered_printers
    ])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{p['full_name']}", callback_data=f"printer_{p['chat_id']}")]
            for p in filtered_printers
        ]
    )

    await call.message.edit_text(f"Выберите исполнителя для печати:\n\n{printer_list_text}", reply_markup=keyboard)


# 🔹 Показать всех исполнителей
@router.callback_query(F.data == "printer_show_all")
async def show_all_printers(call: CallbackQuery):
    printers = await get_all_printers()

    if not printers:
        await call.message.edit_text("Сейчас нет доступных исполнителей. Попробуйте позже.")
        return

    printer_list_text = "\n\n".join([
        f"👤 {p['full_name']} | 🏠 {p['room_number']} | 💰 {p['price_per_page']} руб.\n🖨 {p['printer_type']}"
        for p in printers
    ])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{p['full_name']}", callback_data=f"printer_{p['chat_id']}")]
            for p in printers
        ]
    )

    await call.message.edit_text(f"Выберите исполнителя для печати:\n\n{printer_list_text}", reply_markup=keyboard)


# 🔹 Выбор исполнителя
@router.callback_query(F.data.startswith("printer_"))
async def select_printer(call: CallbackQuery, bot: Bot):
    printer_chat_id = int(call.data.split("_")[1])
    user_printer_selection[call.from_user.id] = printer_chat_id

    printer_info = await bot.get_chat(printer_chat_id)

    view_profile_btn = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Посмотреть профиль", callback_data=f"view_profile_{printer_chat_id}")]
        ]
    )

    await call.message.delete()
    await call.message.answer(
        f"Вы выбрали исполнителя. Теперь отправьте файл для печати.\n"
        "Для корректного подсчета стоимости рекомендовано отправлять файлы .pdf формата.\n"
        f"Если у Вас есть вопросы, Вы можете обратиться в ЛС исполнителя - @{printer_info.username or printer_info.full_name}",
        reply_markup=view_profile_btn
    )


# 🔹 Просмотр профиля исполнителя
@router.callback_query(F.data.startswith("view_profile_"))
async def view_profile(call: CallbackQuery):
    printer_id = int(call.data.split("_")[2])
    info = await get_printer_info(printer_id)

    if not info:
        await call.message.answer("❌ Ошибка: Исполнитель не найден.")
        return

    avg_rating = await get_average_rating(printer_id)

    cancel_button = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="cancel")]
        ]
    )

    await call.message.answer(
        f"👤 {info['full_name']}\n"
        f"🏠 Комната: {info['room_number']}\n"
        f"🖨 Тип принтера: {info['printer_type']}\n"
        f"💰 Цена за лист: {info['price_per_page']} руб.\n"
        f"📌 Описание: {info['description'] or 'Не указано'}\n"
        f"⭐ Средний рейтинг: {avg_rating}",
        reply_markup=cancel_button
    )

@router.callback_query(F.data == "cancel")
async def cancel(call: CallbackQuery):
    await call.message.delete()


# 🔹 Регистрация исполнителя
@router.callback_query(F.data == "printer")
async def printer_callback(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id

    status = await get_printer_status(user_id)
    if status is not None:
        await call.message.edit_text("Вы уже зарегистрированы!")
        return

    await call.message.delete()
    await call.message.answer("Введите номер комнаты, где Вы будете печатать (например, 114/3):")
    await state.set_state(RegisterPrinter.room_number)


@router.message(RegisterPrinter.room_number)
async def room_number_handler(message: Message, state: FSMContext):
    await state.update_data(room_number=message.text)
    await message.answer("Введите стоимость за один лист (например 0.25):")
    await state.set_state(RegisterPrinter.price_per_page)


@router.message(RegisterPrinter.price_per_page)
async def price_per_page_handler(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price_per_page=price)
        await message.answer("Добавьте описание ваших услуг:")
        await state.set_state(RegisterPrinter.description)
    except ValueError:
        await message.answer("Ошибка! Введите число, например: 0.25")


@router.message(RegisterPrinter.card_number)
async def card_number_handler(message: Message, state: FSMContext):
    await message.answer("✅ Регистрация завершена!")
    await state.clear()
