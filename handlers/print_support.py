from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

class SupportState(StatesGroup):
    waiting_for_question = State()
    waiting_for_reply = State()

support_router = Router()

@support_router.message(Command("print_support"))
async def ask_support_question(message: Message, state: FSMContext):
    await message.answer(
        "📩 Напишите ваш вопрос\n\n"
        "Опишите подробно, с чем вам нужна помощь, и мы обязательно ответим! "
        "Наш специалист свяжется с вами в ближайшее время. ⏳"
    )
    await state.set_state(SupportState.waiting_for_question)

@support_router.message(SupportState.waiting_for_question)
async def forward_to_support(message: Message, state: FSMContext):
    support_chat_id = 975278531
    reply_button = InlineKeyboardButton(
        text="Ответить",
        callback_data=f"reply_{message.from_user.id}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[reply_button]])

    await message.bot.send_message(
        chat_id=support_chat_id,
        text=f"✉️ Новый вопрос от пользователя: @{message.from_user.username or 'Без имени'}\n\n"
             f"Текст вопроса:\n{message.text}",
        reply_markup=keyboard
    )

    await message.answer("✅ Ваш вопрос отправлен!\nМы свяжемся с вами в ближайшее время. ⏳")
    await state.clear()

@support_router.callback_query(F.data.startswith("reply_"))
async def ask_for_reply(call: CallbackQuery, state: FSMContext):
    user_id = int(call.data.split("_")[1])
    await state.update_data(user_id=user_id)
    await call.message.answer("Введите ваш ответ пользователю:")
    await state.set_state(SupportState.waiting_for_reply)

@support_router.message(SupportState.waiting_for_reply)
async def send_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await message.answer("Ошибка: Не удалось определить пользователя для ответа.")
        return

    await message.bot.send_message(
        chat_id=user_id,
        text=f"📩 Ответ от поддержки:\n\n{message.text}"
    )

    await message.answer("✅ Ваш ответ отправлен пользователю!")
    await state.clear()
