from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram import F, Router, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database.database import (
    register_printer, get_all_printers, toggle_printer_status,
    get_printer_status, get_printer_info, add_review, get_average_rating, get_reviews
)

router = Router()

class RegisterPrinter(StatesGroup):
    room_number = State()
    price_per_page = State()
    price_per_page_color = State()
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
        f"👤 {p['full_name']} | 🏠 {p['room_number']} | 💰 {p['price_per_page']} руб.(ч/б) | 💰 {p['price_per_page_color']} руб.(цвет)\n🖨 {p['printer_type']}"
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

    # Кнопки профиля исполнителя
    profile_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Посмотреть отзывы", callback_data=f"view_reviews_{printer_id}_0")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="cancel")]
        ]
    )

    await call.message.answer(
        f"👤 {info['full_name']}\n"
        f"🏠 Комната: {info['room_number']}\n"
        f"🖨 Тип принтера: {info['printer_type']}\n"
        f"💰 Цена за лист ч/б: {info['price_per_page']} руб.\n"
        f"💰 Цена за лист цвет: {info['price_per_page_color']} руб.\n"
        f"📌 Описание: {info['description'] or 'Не указано'}\n"
        f"⭐ Средний рейтинг: {avg_rating}",
        reply_markup=profile_buttons
    )


@router.callback_query(F.data.startswith("view_reviews_"))
async def view_reviews(call: CallbackQuery):
    parts = call.data.split("_")

    if len(parts) < 3:  # Проверяем, достаточно ли частей в callback-данных
        await call.answer("❌ Ошибка: Некорректные данные.", show_alert=True)
        return

    printer_id = int(parts[2])  # Берем printer_id
    page = int(parts[3]) if len(parts) > 3 else 0  # Берем page, если есть

    reviews = await get_reviews(printer_id)
    total_reviews = len(reviews)

    if total_reviews == 0:
        await call.answer("❌ Отзывов пока нет.", show_alert=True)
        return

    # Разбиваем отзывы на страницы (по 3 отзыва на страницу)
    reviews_per_page = 3
    start_index = page * reviews_per_page
    end_index = start_index + reviews_per_page
    reviews_on_page = reviews[start_index:end_index]

    # Формируем текст отзывов
    review_texts = []
    for review in reviews_on_page:
        stars = "⭐" * review["rating"] + "☆" * (5 - review["rating"])
        comment = review["comment"] or "Без комментария"
        review_texts.append(f"{stars}\n📝 {comment}")

    reviews_text = "\n\n".join(review_texts)

    # Кнопки управления страницами
    buttons = []
    if start_index > 0:
        buttons.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"view_reviews_{printer_id}_{page - 1}"))
    if end_index < total_reviews:
        buttons.append(InlineKeyboardButton(text="Вперед ▶", callback_data=f"view_reviews_{printer_id}_{page + 1}"))

    # Добавляем кнопку закрытия
    buttons.append(InlineKeyboardButton(text="❌ Закрыть", callback_data="close_reviews"))

    review_buttons = InlineKeyboardMarkup(inline_keyboard=[buttons])

    # Отправляем сообщение с отзывами
    if call.message.text:
        await call.message.edit_text(f"📢 Отзывы об исполнителе:\n\n{reviews_text}", reply_markup=review_buttons)
    else:
        await call.message.answer(f"📢 Отзывы об исполнителе:\n\n{reviews_text}", reply_markup=review_buttons)


@router.callback_query(F.data == "close_reviews")
async def close_reviews(call: CallbackQuery):
    await call.message.delete()


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
        await state.set_state(RegisterPrinter.price_per_page_color)
    except ValueError:
        await message.answer("Ошибка! Введите число, например: 0.25")

@router.message(RegisterPrinter.price_per_page_color)
async def price_per_page_handler(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price_per_page_color=price)
        await message.answer("Добавьте описание ваших услуг:")
        await state.set_state(RegisterPrinter.description)
    except ValueError:
        await message.answer("Ошибка! Введите число, например: 0.25")

@router.message(RegisterPrinter.description)
async def description_handler(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите номер карты для оплаты (например, 1234 5678 9012 3456):")
    await state.set_state(RegisterPrinter.card_number)


@router.message(RegisterPrinter.card_number)
async def card_number_handler(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    chat = await bot.get_chat(user_id)

    # Получаем данные, введённые ранее
    data = await state.get_data()

    await register_printer(
        telegram_id=user_id,  # Исправлено: передаём telegram_id
        chat_id=message.chat.id,
        full_name=chat.full_name,
        username=chat.username or "",  # Если username отсутствует, передаём пустую строку
        room_number=data["room_number"],
        price_per_page=data["price_per_page"],
        price_per_page_color=data["price_per_page_color"],
        description=data.get("description", ""),  # Описание может отсутствовать
        card_number=message.text
    )

    await message.answer("✅ Регистрация завершена!")
    await state.clear()

