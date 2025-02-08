import os

from aiogram import types, Router, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import orm_add_task
from filters.chat_types import ChatTypeFilter
from aiogram.fsm.state import State, StatesGroup

from handlers.user_group import user_group_router
from kbds.reply_kbds import get_keyboard

GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

user_private_router = Router()
user_private_router.message.filter(ChatTypeFilter(['private']))

@user_private_router.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "Привет, я виртуальный помощник. Если хочешь добавить задачу, нажми на клавишу ниже ⬇️",
        reply_markup=get_keyboard(
            "Добавить задачу",
            placeholder="Что вас интересует?",
            sizes=(1,)
        ),
    )


class Task(StatesGroup):
    description = State()
    username = State()
    contact_number = State()


@user_private_router.message(StateFilter(None), F.text == "Добавить задачу")
async def add_task(message: types.Message, state: FSMContext):
    await message.reply("Опишите задачу")
    await state.set_state(Task.description)


@user_private_router.message(Task.description, F.text)
async def add_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.reply("Укажите свое Имя")
    await state.set_state(Task.username)


@user_private_router.message(Task.username, F.text)
async def add_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text)

    # Создаем кнопку для поделиться контактом
    button = types.KeyboardButton(text="Поделиться контактом", request_contact=True)

    # Создаем разметку клавиатуры с обязательным полем keyboard
    markup = types.ReplyKeyboardMarkup(
        keyboard=[[button]],  # Передаем список с кнопками
        resize_keyboard=True
    )

    await message.reply("Поделитесь своим контактом:", reply_markup=markup)
    await state.set_state(Task.contact_number)

@user_private_router.message(F.contact)
async def add_contact(message: types.Message, state: FSMContext, session: AsyncSession):
    if not message.contact:
        await message.reply("Ошибка: Пожалуйста, используйте кнопку 'Поделиться контактом'.")
        return

    contact_number = message.contact.phone_number  # Получаем номер
    await state.update_data(contact_number=contact_number)

    data = await state.get_data()

    bot = message.bot  # Получаем объект бота

    task_text = (
        f"📌 <b>Получена новая задача:</b>\n"
        f"📄 <b>Описание:</b> {data['description']}\n"
        f"👤 <b>От кого:</b> {data['username']}\n"
        f"📞 <b>Контакты:</b> {contact_number}"
    )
    group_message = None

    try:
        # Отправляем сообщение в группу
        group_message = await bot.send_message(chat_id=GROUP_CHAT_ID, text=task_text, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки сообщения в группу: {e}")

    # Сохраняем task и group_message_id в БД
    data["group_message_id"] = group_message.message_id  # Сохраняем message_id
    await orm_add_task(session, data)  # Добавляем задачу в БД с group_message_id

    await message.reply(
        "Задача добавлена",
        reply_markup=get_keyboard(
            "Добавить задачу",
            placeholder="Что вас интересует?",
            sizes=(1,)
        )
    )
    await state.clear()