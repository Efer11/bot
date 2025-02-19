import logging
import fitz
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from handlers.callback import user_printer_selection
from database.database import get_printer_room, get_printer_info, add_review, get_average_rating

router = Router()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PrintRequest(StatesGroup):
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

    price_per_page = printer_info.get("price_per_page", 1)
    file_cost = round(page_count * price_per_page, 2)

    data = await state.get_data()
    documents = data.get("documents", [])
    total_pages = data.get("total_pages", 0)
    total_price = data.get("total_price", 0)

    documents.append(
        {"file_id": message.document.file_id, "file_name": message.document.file_name, "pages": page_count})
    total_pages += page_count
    total_price += file_cost

    await state.update_data(
        documents=documents,
        printer_id=printer_id,
        total_pages=total_pages,
        total_price=total_price
    )

    await message.answer(
        f"📄 Файл `{message.document.file_name}` принят.\n"
        f"📑 Страниц в файле: {page_count}\n"
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

    file_descriptions = "\n".join([f"📄 `{doc['file_name']}` - {doc['pages']} стр." for doc in document_list])

    caption = (
        f"📄 Новый заказ от @{user.username or user.full_name}\n"
        f"📂 Файлы:\n{file_descriptions}\n"
        f"📑 Всего страниц: {total_pages}\n"
        f"💰 Итоговая стоимость: {total_price} руб.\n"
        f"📌 Требования: {requirements}\n"
        f"{payment_info}"
    )

    complete_button = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Выполнено", callback_data=f"complete_{user.id}")]]
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

@router.callback_query(F.data.startswith("complete_"))
async def complete_task(call: CallbackQuery, state: FSMContext):
    try:
        user_id = int(call.data.split("_")[1])
        printer_id = call.message.chat.id
        room_number = await get_printer_room(printer_id) or "не указана. Обратитесь к исполнителю в ЛС"

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

