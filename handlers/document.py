import logging
import fitz
import time
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from handlers.callback import user_printer_selection
from database.database import get_printer_room, get_printer_info, add_review, get_average_rating, update_printer_stats

router = Router()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PrintRequest(StatesGroup):
    waiting_print_type = State()
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

    # Получаем текущие данные о документах
    data = await state.get_data()
    documents = data.get("documents", [])

    await state.update_data(printer_id=printer_id)

    # Добавляем новый файл в список
    documents.append(
        {"file_id": message.document.file_id, "file_name": message.document.file_name, "pages": page_count, "print_type": None}
    )
    await state.update_data(documents=documents)

    if len(documents) == 3:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Все файлы Ч/Б", callback_data="all_bw")],
            [InlineKeyboardButton(text="Все файлы Цвет", callback_data="all_color")],
            [InlineKeyboardButton(text="Выбрать для каждого", callback_data="choose_each")],
        ])
        await message.answer(
            "Вы загрузили 3 или более файлов. Выберите формат печати для всех сразу или для каждого отдельно:",
            reply_markup=keyboard
        )
    elif len(documents) < 3:
        await ask_print_type_for_file(message, len(documents) - 1, state)

async def ask_print_type_for_file(message: Message, index: int, state: FSMContext):
    data = await state.get_data()
    documents = data.get("documents", [])

    if index >= len(documents):
        return

    doc = documents[index]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ч/Б", callback_data=f"bw_{index}")],
        [InlineKeyboardButton(text="Цвет", callback_data=f"color_{index}")],
    ])

    await message.answer(
        f"📄 {doc['file_name']} ({doc['pages']} стр.)\nВыберите формат печати:",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "all_bw")
async def set_all_bw(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    documents = data.get("documents", [])
    printer_info = await get_printer_info(data.get("printer_id"))

    if not printer_info:
        await call.message.answer("❌ Ошибка: Не удалось получить информацию о принтере.")
        return

    price_per_page = printer_info.get("price_per_page", 0.25)  # Цена за Ч/Б страницу
    total_pages = 0
    total_price = 0
    summary_message = ""

    for doc in documents:
        doc["print_type"] = "bw"
        doc["cost"] = round(doc["pages"] * price_per_page, 2)  # Пересчитываем стоимость
        total_pages += doc["pages"]
        total_price += doc["cost"]

        summary_message += (
            f"📄 Файл: {doc['file_name']}\n"
            f"📑 Страниц в файле: {doc['pages']}\n"
            f"🎨 Формат печати: Ч/Б\n"
            f"💰 Стоимость файла: {doc['cost']} руб.\n\n"
        )

    summary_message += (
        f"📊 Общий подсчет:\n"
        f"📑 Всего страниц: {total_pages}\n"
        f"💵 Итоговая стоимость: {total_price} руб.\n\n"
        "Загрузите следующий файл или напишите дополнительные требования к распечатке.\n"
        "Напишите 'нет', если у вас нет дополнительных требований.\n"
        "Если вы отправили не тот файл, напишите /start и начните отправку снова."
    )

    await state.update_data(documents=documents, total_pages=total_pages, total_price=total_price)
    await call.message.answer(summary_message)
    await call.message.delete()
    await call.answer()
    await state.set_state(PrintRequest.waiting_for_requirements)



@router.callback_query(F.data == "all_color")
async def set_all_color(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    documents = data.get("documents", [])
    printer_info = await get_printer_info(data.get("printer_id"))

    if not printer_info:
        await call.message.answer("❌ Ошибка: Не удалось получить информацию о принтере.")
        return

    price_per_page_color = printer_info.get("price_per_page_color", 0.6)
    total_pages = 0
    total_price = 0
    summary_message = ""

    for doc in documents:
        doc["print_type"] = "color"
        doc["cost"] = round(doc["pages"] * price_per_page_color, 2)
        total_pages += doc["pages"]
        total_price += doc["cost"]

        summary_message += (
            f"📄 Файл: {doc['file_name']}\n"
            f"📑 Страниц в файле: {doc['pages']}\n"
            f"🎨 Формат печати: Цвет\n"
            f"💰 Стоимость файла: {doc['cost']} руб.\n\n"
        )

    summary_message += (
        f"📊 Общий подсчет:\n"
        f"📑 Всего страниц: {total_pages}\n"
        f"💵 Итоговая стоимость: {total_price} руб.\n\n"
        "Загрузите следующий файл или напишите дополнительные требования к распечатке.\n"
        "Напишите 'нет', если у вас нет дополнительных требований.\n"
        "Если вы отправили не тот файл, напишите /start и начните отправку снова."
    )

    await state.update_data(documents=documents, total_pages=total_pages, total_price=total_price)
    await call.message.answer(summary_message)
    await call.message.delete()
    await call.answer()
    await state.set_state(PrintRequest.waiting_for_requirements)

@router.callback_query(F.data == "choose_each")
async def choose_each_file(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    documents = data.get("documents", [])

    for index, doc in enumerate(documents):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ч/Б", callback_data=f"bw_{index}")],
            [InlineKeyboardButton(text="Цвет", callback_data=f"color_{index}")],
        ])

        await call.message.answer(
            f"📄 {doc['file_name']} ({doc['pages']} стр.)\nВыберите формат печати:",
            reply_markup=keyboard
        )

    await call.message.delete()
    await call.answer()


@router.callback_query(F.data == "back_to_upload")
async def back_to_upload(call: CallbackQuery, state: FSMContext):
    await state.update_data(documents=[])
    await call.message.answer("📤 Загрузите новый файл для печати.")
    await call.message.delete()
    await call.answer()


async def update_total_price(state: FSMContext):
    data = await state.get_data()
    documents = data.get("documents", [])

    total_price = round(sum(float(doc.get("cost", 0)) for doc in documents), 2)
    total_pages = sum(doc.get("pages", 0) for doc in documents)

    await state.update_data(total_pages=total_pages, total_price=total_price)

@router.callback_query(F.data.startswith("bw_"))
async def choose_bw(call: CallbackQuery, state: FSMContext):
    index = int(call.data.split("_")[1])
    data = await state.get_data()
    documents = data.get("documents", [])

    if index >= len(documents):
        await call.message.answer("❌ Ошибка: Файл не найден.")
        return

    printer_id = data.get("printer_id")
    printer_info = await get_printer_info(printer_id)

    if not printer_info:
        await call.message.answer("❌ Ошибка: Не удалось получить информацию о принтере.")
        return

    price_per_page = printer_info.get("price_per_page", 0.25)

    documents[index]["print_type"] = "bw"
    documents[index]["cost"] = round(documents[index]["pages"] * price_per_page, 2)

    await state.update_data(documents=documents)
    await update_total_price(state)

    # ✅ Удаляем сообщение с кнопками
    await call.message.delete()

    # ✅ Получаем обновленные данные
    updated_data = await state.get_data()
    total_pages = updated_data.get("total_pages", 0)
    total_price = updated_data.get("total_price", 0)

    await call.message.answer(
        f"📄 Файл {documents[index]['file_name']} принят.\n"
        f"📑 Страниц в файле: {documents[index]['pages']}\n"
        f"🎨 Формат печати: Ч/Б\n"
        f"💰 Стоимость файла: {documents[index]['cost']} руб.\n\n"
        f"📊 Общий подсчет:\n"
        f"📑 Всего страниц: {total_pages}\n"
        f"💵 Итоговая стоимость: {total_price} руб.\n\n"
        "Загрузите следующий файл или напишите дополнительные требования к распечатке, напишите 'нет', если у Вас нет дополнительных требований."
        "Если Вы отправили не тот файл, напишите /start и начните отправку снова."
    )
    await call.answer()
    await state.set_state(PrintRequest.waiting_for_requirements)


@router.callback_query(F.data.startswith("color_"))
async def choose_color(call: CallbackQuery, state: FSMContext):
    index = int(call.data.split("_")[1])
    data = await state.get_data()
    documents = data.get("documents", [])

    if index >= len(documents):
        await call.message.answer("❌ Ошибка: Файл не найден.")
        return

    printer_id = data.get("printer_id")
    printer_info = await get_printer_info(printer_id)

    if not printer_info:
        await call.message.answer("❌ Ошибка: Не удалось получить информацию о принтере.")
        return

    price_per_page_color = printer_info.get("price_per_page_color", 0.6)

    documents[index]["print_type"] = "color"
    documents[index]["cost"] = round(documents[index]["pages"] * price_per_page_color, 2)

    await state.update_data(documents=documents)
    await update_total_price(state)

    # ✅ Удаляем сообщение с кнопками
    await call.message.delete()

    # ✅ Получаем обновленные данные
    updated_data = await state.get_data()
    total_pages = updated_data.get("total_pages", 0)
    total_price = updated_data.get("total_price", 0)

    await call.message.answer(
        f"📄 Файл {documents[index]['file_name']} принят.\n"
        f"📑 Страниц в файле: {documents[index]['pages']}\n"
        f"🎨 Формат печати: Цвет\n"
        f"💰 Стоимость файла: {documents[index]['cost']} руб.\n\n"
        f"📊 Общий подсчет:\n"
        f"📑 Всего страниц: {total_pages}\n"
        f"💵 Итоговая стоимость: {total_price} руб.\n\n"
        "Загрузите следующий файл или напишите дополнительные требования к распечатке, напишите 'нет', если у Вас нет дополнительных требований."
        "Если Вы отправили не тот файл, напишите /start и начните отправку снова."
    )
    await call.answer()
    await state.set_state(PrintRequest.waiting_for_requirements)


@router.message(PrintRequest.waiting_for_requirements)
async def ask_payment_method(message: Message, state: FSMContext):
    await state.update_data(requirements=message.text.strip())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Картой", callback_data="pay_card")],
        [InlineKeyboardButton(text="💵 Наличными", callback_data="pay_cash")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_requirements")]
    ])
    await message.answer("Выберите способ оплаты:", reply_markup=keyboard)
    await state.set_state(PaymentState.choosing_payment_method)

@router.callback_query(F.data == "back_to_requirements")
async def back_to_requirements(call: CallbackQuery, state: FSMContext):
    await call.message.answer("✍ Введите дополнительные требования к печати или напишите 'нет', если их нет.")
    await call.message.delete()
    await call.answer()
    await state.set_state(PrintRequest.waiting_for_requirements)


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

    # ✅ Обновляем состояние перед отправкой заказа
    await state.update_data(payment_method="💳 Оплата картой")

    await send_order_to_printer(call, state, "💳 Оплата картой")

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

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную сумму (числом).")


async def send_order_to_printer(message: Message, state: FSMContext, payment_info: str):
    data = await state.get_data()
    document_list = data.get("documents", [])
    printer_id = data.get("printer_id")
    total_pages = data.get("total_pages", 0)
    total_price = data.get("total_price", 0)
    requirements = data.get("requirements", "Без дополнительных требований.")

    user = message.from_user
    order_id = f"{user.id}_{int(time.time())}"

    # 📌 Формируем описание заказа
    file_descriptions = "\n".join([
        f"📄 {doc['file_name']} - {doc['pages']} стр. ({'Ч/Б' if doc['print_type'] == 'bw' else 'Цвет'})"
        for doc in document_list
    ])

    caption = (
        f"📄 Новый заказ от @{user.username or user.full_name}\n"
        f"📂 Файлы: \n{file_descriptions}\n"
        f"📑 Всего страниц: {total_pages}\n"
        f"💰 Итоговая стоимость: {total_price} руб.\n"
        f"📌 Требования: {requirements}\n"
        f"{payment_info}"
    )

    complete_button = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"complete_{user.id}")],
            [InlineKeyboardButton(text="❌ Отказаться от выполнения", callback_data=f"reject_order_{order_id}")]
        ]
    )

    try:
        # ✅ Отправляем сообщение-заголовок с описанием заказа
        await message.bot.send_message(chat_id=printer_id, text=caption, reply_markup=complete_button)

        # ✅ Разбиваем файлы на группы по 10
        batch_size = 10
        for i in range(0, len(document_list), batch_size):
            batch = document_list[i:i + batch_size]

            media_group = [
                {
                    "type": "document",
                    "media": doc["file_id"],
                    "caption": f"{doc['file_name']} ({'Ч/Б' if doc['print_type'] == 'bw' else 'Цвет'})"
                }
                for doc in batch
            ]

            await message.bot.send_media_group(chat_id=printer_id, media=media_group)

        await message.answer(f"✅ Ваш заказ отправлен исполнителю!\n💰 Итоговая стоимость: {total_price} руб.")

    except TelegramBadRequest as e:
        logger.error(f"Ошибка при отправке файлов: {e}")
        await message.answer("❌ Ошибка при отправке файлов исполнителю.")

@router.callback_query(F.data.startswith("reject_order_"))
async def reject_order(call: CallbackQuery, state:FSMContext, bot: Bot):
    order_id = call.data.split("_")[2]  # Получаем ID заказа
    user_id = int(order_id.split("_")[0])  # Получаем ID заказчика

    try:
        await state.clear()
        await bot.send_message(user_id, "❌ Исполнитель отказался от выполнения вашего заказа.")
        await call.message.edit_text("❌ Вы отказались от выполнения заказа.")

    except Exception as e:
        logger.error(f"Ошибка при уведомлении пользователя: {e}")

@router.callback_query(F.data.startswith("complete_"))
async def complete_task(call: CallbackQuery, state: FSMContext):
    try:
        user_id = int(call.data.split("_")[1])
        printer_id = call.message.chat.id
        room_number = await get_printer_room(printer_id) or "не указана. Обратитесь к исполнителю в ЛС"

        data = await state.get_data()
        total_pages = data.get("total_pages", 0)
        total_price = data.get("total_price", 0)

        await update_printer_stats(printer_id, total_pages, total_price)
        await state.clear()

        await call.message.bot.send_message(
            chat_id=user_id,
            text=f"✅ Ваш заказ выполнен! Подойдите к {room_number} для получения распечатки."
        )

        # 🔹 Кнопка для оценки
        rating_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{printer_id}_1"),
                 InlineKeyboardButton(text="⭐ 2", callback_data=f"rate_{printer_id}_2"),
                 InlineKeyboardButton(text="⭐ 3", callback_data=f"rate_{printer_id}_3"),
                 InlineKeyboardButton(text="⭐ 4", callback_data=f"rate_{printer_id}_4"),
                 InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{printer_id}_5")]
            ]
        )

        await call.message.bot.send_message(
            chat_id=user_id,
            text="📢 Оцените исполнителя!",
            reply_markup=rating_keyboard
        )

        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("✅ Заказ выполнен.")
    except Exception as e:
        logger.exception(f"Ошибка при подтверждении: {e}")
        await call.answer("❌ Ошибка при подтверждении выполнения.")

@router.callback_query(F.data.startswith("rate_"))
async def rate_printer(call: CallbackQuery, state: FSMContext):
    _, printer_id, rating = call.data.split("_")
    printer_id, rating = int(printer_id), int(rating)

    await state.update_data(printer_id=printer_id, rating=rating)
    await call.message.delete()
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

