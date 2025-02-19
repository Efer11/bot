import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from database.database import get_printer_info, update_printer_info, update_printer_description, update_printer_type
from keyboards.inline import change_printer_info, printer_type

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

profile_router = Router()


class EditProfileState(StatesGroup):
    changing_room = State()
    changing_price = State()
    changing_description = State()
    add_printer_description = State()


@profile_router.message(Command("profile"))
async def take_profile(message: Message):
    await message.delete()
    printer_id = message.from_user.id

    try:
        info = await get_printer_info(printer_id)
        if not info:
            await message.answer("❌ Вы не зарегистрированы как исполнитель!")
            return

        await message.answer(
            f"👤 {info['full_name']}\n"
            f"🏠 Комната: {info['room_number']}\n"
            f"💰 Цена за лист: {info['price_per_page']} руб.\n"
            f"📌 Описание: {info['description'] or 'Не указано'}\n"
            f"🖨 Тип принтера: {info['printer_type'] or 'Не указан'}",
            f"⭐ Средний рейтинг: {avg_rating}",
            reply_markup=change_printer_info
        )
    except Exception as e:
        logger.exception(f"Ошибка при получении профиля: {e}")
        await message.answer("❌ Ошибка при загрузке профиля.")



@profile_router.callback_query(F.data == "change_room")
async def change_room(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🏠 Введите новый номер комнаты:")
    await state.set_state(EditProfileState.changing_room)
    await callback.answer()


@profile_router.callback_query(F.data == "change_price")
async def change_price(callback: CallbackQuery, state: FSMContext):
    """Изменение цены за страницу"""
    await callback.message.answer("💰 Введите новую цену за лист (например: 1.50):")
    await state.set_state(EditProfileState.changing_price)
    await callback.answer()


@profile_router.callback_query(F.data == "change_description")
async def change_description(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📌 Введите новое описание ваших услуг:")
    await state.set_state(EditProfileState.changing_description)
    await callback.answer()

@profile_router.callback_query(F.data == "add_printer_type")
async def change_printer_type(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📌 Выберите тип вашего принтера:", reply_markup=printer_type)
    await callback.answer()

@profile_router.callback_query(F.data.startswith("printer_type_"))
async def set_printer_type(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
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

    printer_type = printer_types.get(callback.data, "Не указан")

    try:
        await update_printer_type(telegram_id=callback.from_user.id, printer_type=printer_type)
        await callback.message.answer(f"✅ Тип принтера обновлён: {printer_type}")
    except Exception as e:
        logger.exception(f"Ошибка при обновлении типа принтера: {e}")
        await callback.message.answer("❌ Ошибка при обновлении типа принтера.")

    await callback.answer()

@profile_router.message(EditProfileState.changing_room)
async def update_room_number(message: Message, state: FSMContext):
    new_room = message.text.strip()

    if not new_room:
        await message.answer("❌ Ошибка! Номер комнаты не может быть пустым.")
        return

    try:
        await update_printer_info(telegram_id=message.from_user.id, room_number=new_room)
        await message.answer(f"✅ Номер комнаты обновлён: {new_room}")
    except Exception as e:
        logger.exception(f"Ошибка при обновлении номера комнаты: {e}")
        await message.answer("❌ Произошла ошибка при обновлении номера комнаты.")

    await state.clear()


@profile_router.message(EditProfileState.changing_price)
async def update_price_per_page(message: Message, state: FSMContext):
    try:
        new_price = float(message.text.strip())
        if new_price <= 0:
            raise ValueError("Цена должна быть положительным числом.")

        await update_printer_info(telegram_id=message.from_user.id, price_per_page=new_price)
        await message.answer(f"✅ Цена за лист обновлена: {new_price} руб.")
    except ValueError:
        await message.answer("❌ Ошибка! Введите корректное число, например: 1.50")
    except Exception as e:
        logger.exception(f"Ошибка при обновлении цены: {e}")
        await message.answer("❌ Произошла ошибка при обновлении цены.")

    await state.clear()


@profile_router.message(EditProfileState.changing_description)
async def update_description(message: Message, state: FSMContext):
    new_description = message.text.strip()

    if not new_description:
        await message.answer("❌ Ошибка! Описание не может быть пустым.")
        return

    try:
        await update_printer_description(telegram_id=message.from_user.id, description=new_description)
        await message.answer(f"✅ Описание обновлено: {new_description}")
    except Exception as e:
        logger.exception(f"Ошибка при обновлении описания: {e}")
        await message.answer("❌ Произошла ошибка при обновлении описания.")
    await state.clear()


@profile_router.callback_query(F.data == "close")
async def close(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()
