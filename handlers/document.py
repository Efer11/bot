import logging
import fitz
from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from handlers.callback import user_printer_selection
from database.database import get_printer_room, get_printer_info, add_review, get_average_rating

router = Router()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PrintRequest(StatesGroup):
    choosing_print_type = State()
    waiting_for_requirements = State()

class PaymentState(StatesGroup):
    choosing_payment_method = State()
    entering_cash_amount = State()

class RatingState(StatesGroup):
    waiting_for_comment = State()

async def get_pdf_page_count(file_id, bot):
    try:
        file = await bot.get_file(file_id)
        file_path = file.file_path
        file_bytes = await bot.download_file(file_path)

        with fitz.open("pdf", file_bytes.read()) as doc:
            return len(doc)
    except Exception as e:
        logger.exception(f"Ошибка при обработке PDF: {e}")
        return 0


@router.message(F.document)
async def handle_document(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if user_id not in user_printer_selection:
        await message.answer("❌ Вы не выбрали исполнителя. Сначала выберите исполнителя перед отправкой файла.")
        return

    printer_id = user_printer_selection[user_id]
    printer_info = await get_printer_info(printer_id)

    if not printer_info:
        await message.answer("❌ Ошибка: Исполнитель не найден.")
        return

    if not message.document.file_name.lower().endswith(".pdf"):
        await message.answer("⚠ Поддерживаются только PDF-файлы для точного подсчета стоимости.")
        return

    page_count = await get_pdf_page_count(message.document.file_id, message.bot)
    if page_count == 0:
        await message.answer("⚠ Ошибка при обработке файла. Попробуйте другой файл.")
        return

    await state.update_data(
        file_id=message.document.file_id,
        file_name=message.document.file_name,
        page_count=page_count,
        printer_id=printer_id,
        price_bw=printer_info.get("price_per_page"),
        price_color=printer_info.get("price_per_page_color")
    )

    # Добавляем кнопку "✏ Заменить файл"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖤 Чёрно-белая", callback_data="print_bw")],
        [InlineKeyboardButton(text="🌈 Цветная", callback_data="print_color")],
        [InlineKeyboardButton(text="✏ Заменить файл", callback_data="replace_file")]
    ])

    await message.answer(f"📂 Загружен файл: {message.document.file_name}\nВыберите формат печати или замените файл:", reply_markup=keyboard)
    await state.set_state(PrintRequest.choosing_print_type)


@router.callback_query(F.data == "replace_file")
async def replace_file_request(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📂 Отправьте новый PDF-файл для замены текущего.")
    await state.set_state(PrintRequest.choosing_print_type)


@router.message(StateFilter(PrintRequest.choosing_print_type), F.document)
async def handle_new_document(message: Message, state: FSMContext):
    user_data = await state.get_data()

    if not message.document.file_name.lower().endswith(".pdf"):
        await message.answer("⚠ Поддерживаются только PDF-файлы для точного подсчета стоимости.")
        return

    page_count = await get_pdf_page_count(message.document.file_id, message.bot)
    if page_count == 0:
        await message.answer("⚠ Ошибка при обработке файла. Попробуйте другой файл.")
        return

    await state.update_data(
        file_id=message.document.file_id,
        file_name=message.document.file_name,
        page_count=page_count
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖤 Чёрно-белая", callback_data="print_bw")],
        [InlineKeyboardButton(text="🌈 Цветная", callback_data="print_color")],
        [InlineKeyboardButton(text="✏ Заменить файл", callback_data="replace_file")]
    ])

    await message.answer("✅ Новый файл загружен! Выберите формат печати:", reply_markup=keyboard)


@router.callback_query(F.data.in_(["print_bw", "print_color"]))
async def choose_print_mode(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    data = await state.get_data()

    color_mode = "ЧБ" if call.data == "print_bw" else "Цвет"

    # Используем .get() с значением по умолчанию
    price_per_page_bw = Decimal(data.get("price_bw", 0.25))  # ЧБ
    price_per_page_color = Decimal(data.get("price_color", 0.5))  # Цвет

    # Определяем цену за страницу в зависимости от формата
    price_per_page = price_per_page_bw if call.data == "print_bw" else price_per_page_color

    # Проверяем наличие ключей в `data`
    if "page_count" not in data or "file_id" not in data or "file_name" not in data:
        await call.message.answer("❌ Ошибка: отсутствуют данные о файле. Попробуйте загрузить файл заново.")
        return

    file_cost = Decimal(data["page_count"]) * price_per_page  # Расчет стоимости

    documents = data.get("documents", [])
    total_pages = Decimal(data.get("total_pages", 0))
    total_price = Decimal(data.get("total_price", 0))

    # Добавляем информацию о файле, включая формат печати
    documents.append({
        "file_id": data["file_id"],
        "file_name": data["file_name"],
        "pages": data["page_count"],
        "color_mode": color_mode,  # 🔥 Передаем формат печати
        "price_per_page": price_per_page,
        "file_cost": file_cost  # Добавляем стоимость файла
    })
    total_pages += Decimal(data["page_count"])
    total_price += file_cost

    await state.update_data(
        documents=documents,
        total_pages=total_pages,
        total_price=total_price
    )

    await call.message.answer(
        f"📄 Файл `{data['file_name']}` принят.\n"
        f"📑 Страниц в файле: {data['page_count']}\n"
        f"🎨 Формат печати: {color_mode}\n"
        f"💰 Стоимость файла: {file_cost} руб.\n\n"
        f"📊 Общий подсчет:\n"
        f"📑 Всего страниц: {total_pages}\n"
        f"💵 Итоговая стоимость: {total_price} руб.\n\n"
        "Если хотите отправить ещё файлы, просто загрузите их.\n"
        "Когда загрузите все файлы, отправьте сообщение с дополнительными требованиями или 'нет', если требований нет."
    )

    await state.set_state(PrintRequest.waiting_for_requirements)

@router.message(PrintRequest.waiting_for_requirements)
async def ask_payment_method(message: Message, state: FSMContext):
    await state.update_data(requirements=message.text.strip())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Картой", callback_data="pay_card")],
        [InlineKeyboardButton(text="💵 Наличными", callback_data="pay_cash")]
    ])
    await message.answer("Выберите способ оплаты:", reply_markup=keyboard)
    await state.set_state(PaymentState.choosing_payment_method)


@router.callback_query(F.data == "pay_card")
async def handle_card_payment(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    total_price = data.get("total_price", 0)
    printer_id = data.get("printer_id")
    if not printer_id:
        await call.message.answer("Не выбран исполнитель.")
        return
    printer_info = await get_printer_info(printer_id)
    if printer_info and printer_info.get("card_number"):
        card_number = printer_info["card_number"]
        await call.message.answer(f"💳 Оплата картой: {total_price} руб. Оплатите заказ по реквизитам исполнителя: {card_number}")
    else:
        await call.message.answer("Нет номера карточки у исполнителя")

    await send_order_to_printer(call, state, "💳 Оплата картой")
    await state.clear()


@router.callback_query(F.data == "pay_cash")
async def ask_cash_amount(call: CallbackQuery, state: FSMContext):
    await call.message.answer("💵 Введите сумму, которую внесёте:")
    await state.set_state(PaymentState.entering_cash_amount)


@router.message(PaymentState.entering_cash_amount)
async def handle_cash_payment(message: Message, state: FSMContext):
    try:
        amount_given = float(message.text.replace(",", "."))
        data = await state.get_data()
        total_price = data.get("total_price", 0)

        if amount_given < total_price:
            await message.answer("❌ Недостаточная сумма. Введите корректную сумму.")
            return

        change = round(float(amount_given) - float(total_price), 2)
        payment_info = f"💵 Оплата наличными: {amount_given} руб.\n💰 Сдача: {change} руб."

        await send_order_to_printer(message, state, payment_info)
        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную сумму (числом).")


async def send_order_to_printer(message: Message, state: FSMContext, payment_info: str):
    data = await state.get_data()
    document_list = data.get("documents", [])
    printer_id = data.get("printer_id")
    total_pages = data.get("total_pages", 0)
    total_price = data.get("total_price", 0)
    requirements = data.get("requirements", "Без дополнительных требований.")

    # Достаем пользователя из message
    user = message.from_user

    # Формируем список файлов с указанием типа печати
    file_descriptions = "\n".join([
        f"📄 `{doc['file_name']}` - {doc['pages']} стр. ({doc['color_mode']})"
        for doc in document_list
    ])

    caption = (
        f"📄 Новый заказ от @{user.username or user.full_name}\n"
        f"📂 Файлы:\n{file_descriptions}\n"
        f"📑 Всего страниц: {total_pages}\n"
        f"💰 Итоговая стоимость: {total_price} руб.\n"
        f"📌 Требования: {requirements}\n"
        f"{payment_info}"
    )

    complete_button = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"complete_{user.id}")],
            [InlineKeyboardButton(text="❌ Отказаться", callback_data=f"reject_{user.id}")]
        ]
    )

    try:
        if len(document_list) > 1:
            media_group = [{"type": "document", "media": doc["file_id"]} for doc in document_list]
            await message.bot.send_media_group(chat_id=printer_id, media=media_group)
            await message.bot.send_message(chat_id=printer_id, text=caption, reply_markup=complete_button)
        else:
            await message.bot.send_document(
                chat_id=printer_id,
                document=document_list[0]["file_id"],
                caption=caption,
                reply_markup=complete_button
            )

        await message.answer(f"✅ Заказ отправлен исполнителю!\n💰 Итоговая стоимость: {total_price} руб.")
    except TelegramBadRequest as e:
        logger.error(f"Ошибка при отправке файла: {e}")
        await message.answer("❌ Ошибка при отправке файлов. Возможно, исполнитель недоступен.")


@router.callback_query(F.data.startswith("complete_") | F.data.startswith("reject_"))
async def handle_order_status(call: CallbackQuery):
    action, user_id = call.data.split("_")
    user_id = int(user_id)
    printer_id = call.message.chat.id

    if action == "complete":
        room_number = await get_printer_room(printer_id) or "не указана. Обратитесь к исполнителю в ЛС"

        await call.message.bot.send_message(
            chat_id=user_id,
            text=f"✅ Ваш заказ выполнен! Подойдите к {room_number} для получения распечатки."
        )

        rating_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{printer_id}_1"),
                InlineKeyboardButton(text="⭐ 2", callback_data=f"rate_{printer_id}_2"),
                InlineKeyboardButton(text="⭐ 3", callback_data=f"rate_{printer_id}_3"),
                InlineKeyboardButton(text="⭐ 4", callback_data=f"rate_{printer_id}_4"),
                InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{printer_id}_5")
            ]]
        )

        await call.message.bot.send_message(
            chat_id=user_id,
            text="📢 Оцените исполнителя!",
            reply_markup=rating_keyboard
        )

        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("✅ Заказ выполнен.")

    elif action == "reject":
        await call.message.bot.send_message(
            chat_id=user_id,
            text="❌ Ваш заказ был отклонен исполнителем. Попробуйте выбрать другого."
        )

        # Проверяем, есть ли текст в сообщении перед редактированием
        if call.message.text:
            await call.message.edit_text("🚫 Заказ отклонен исполнителем.", reply_markup=None)
        else:
            await call.message.delete()  # Удаляем, если редактировать нельзя

        await call.answer("❌ Вы отказались от заказа.")


    # Проверяем, есть ли текст в сообщении
    if call.message.text:
        await call.message.edit_text("🚫 Заказ отклонен исполнителем.", reply_markup=None)
    else:
        await call.message.delete()

@router.callback_query(F.data.startswith("rate_"))
async def rate_printer(call: CallbackQuery, state: FSMContext):
    _, printer_id, rating = call.data.split("_")
    printer_id, rating = int(printer_id), int(rating)

    await state.update_data(printer_id=printer_id, rating=rating)
    await call.message.answer("✍ Напишите короткий отзыв о исполнителе:")
    await state.set_state(RatingState.waiting_for_comment)

@router.message(RatingState.waiting_for_comment)
async def save_review(message: Message, state: FSMContext):
    data = await state.get_data()
    printer_id = data["printer_id"]
    rating = data["rating"]
    comment = message.text

    await add_review(printer_id, message.from_user.id, rating, comment)

    await message.answer("✅ Спасибо! Ваш отзыв сохранён. 😊")
    await state.clear()

