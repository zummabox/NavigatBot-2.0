from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import asyncio

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import MsgId
from database.orm_query import (orm_add_detail, orm_get_details,
                                orm_delete_detail, orm_get_detail,
                                orm_update_detail, orm_get_categories,
                                orm_get_detail_report, orm_get_tasks,
                                orm_delete_task, orm_get_task_by_id,
                                update_summary_msg_id, update_all_report_msg_id,
                                update_detail_report_msg_id,
                                update_last_action_msg_id, delete_last_action_msg_id)

from filters.chat_types import ChatTypeFilter, IsAdmin
from handlers.fsm_utils import go_to_next_state
from handlers.user_private import GROUP_CHAT_ID
from kbds.callback_list import report_buttons, add_buttons
from kbds.inline_kbds import get_callback_btns


admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())


def get_admin_menu():
    btns = {
        "➕ Добавить данные": "admin:add_data",
        "📊 Отчет": "admin:report",
        "📋 Отчет по деталям": "admin:details_report",
        "📌 Задачи": "admin:tasks",
    }
    return get_callback_btns(btns=btns, sizes=(2,))


@admin_router.message(Command("admin"))
async def show_admin_menu(message: types.Message):
    await message.answer("📝Главное меню админ панели, можете начать работу с ботом", reply_markup=get_admin_menu())


########################## Отчет по деталям ####################################
class Report(StatesGroup):
    category_report = State()
    detail_report = State()


@admin_router.callback_query(StateFilter(None), F.data == "admin:details_report")
async def detail_report(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}
    await callback.message.edit_text("Выберите изделие ⚙️", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(Report.category_report)
    await callback.answer()


@admin_router.callback_query(Report.category_report)
async def category_choice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    category_id = int(callback.data)
    if category_id in [category.id for category in categories]:

        await callback.answer()
        await state.update_data(category_report=callback.data)

        if category_id in report_buttons:
            btns = report_buttons[category_id]
        await callback.message.edit_text('Выберите деталь.', reply_markup=get_callback_btns(btns=btns))
        await state.set_state(Report.detail_report)


@admin_router.callback_query(Report.detail_report, F.data.startswith('report:'))
async def get_detail_report(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    try:
        await callback.message.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    detail_name = callback.data.split(":")[-1]
    detail_data = await orm_get_detail_report(session, detail_name)

    if detail_data:
        for detail in detail_data:
            formatted_date = detail.updated.strftime("%d.%m.%y %H:%M:%S")

            btns = {
                "❌ Удалить": f"delete_detail_{detail.id}",
                "📝 Изменить": f"change_detail_{detail.id}",
            }

            msg = await callback.message.answer(
                f"<b>⚙️Деталь:</b> {detail.name}\n<b>#️⃣Номер:</b> {detail.number}\n<b>♻️Статус:</b> {detail.status}\n<b>📝Изменения статуса:</b> {formatted_date}",
                reply_markup=get_callback_btns(btns=btns, sizes=(2,)),
                parse_mode="HTML",
            )
            await update_detail_report_msg_id(session, callback.message.chat.id, msg.message_id)

        hide_btn = {"👀 Скрыть отправленные данные": "hide_details_report"}
        hide_msg = await callback.message.answer(
            "Это последние данные. Если хотите скрыть их, нажмите ниже ⬇️",
            reply_markup=get_callback_btns(btns=hide_btn, sizes=(1,))
        )
        await update_detail_report_msg_id(session, callback.message.chat.id, hide_msg.message_id)

    # Сохраняем последнее сообщение
    summary_msg = await callback.message.answer("Хотите сделать что-то еще?", reply_markup=get_admin_menu())
    await update_last_action_msg_id(session, callback.message.chat.id, summary_msg.message_id)

    await state.clear()
    await callback.answer()

########################## Полный отчет по изделию ####################################
@admin_router.callback_query(F.data == "admin:report")
async def all_report(callback: types.CallbackQuery, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f'category_{category.id}' for category in categories}
    await callback.message.edit_text("Выберите изделие ⚙️", reply_markup=get_callback_btns(btns=btns))
    await callback.answer()


@admin_router.callback_query(F.data.startswith('category_'))
async def all_report(callback: types.CallbackQuery, session: AsyncSession):
    try:
        await callback.message.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    category_id = callback.data.split('_')[-1]
    report_msg_ids = []

    for detail in await orm_get_details(session, int(category_id)):
        msg = await callback.message.answer(
            f"<b>⚙️Деталь:</b> {detail.name}\n<b>#️⃣Номер:</b> {detail.number}\n<b>♻️Статус:</b> {detail.status}",
            reply_markup=get_callback_btns(
                btns={
                    "❌Удалить": f"delete_detail_{detail.id}",
                    "📝Изменить": f"change_detail_{detail.id}",
                },
                sizes=(2,)
            ),
            parse_mode="HTML",
        )
        report_msg_ids.append(msg.message_id)

    hide_report_msg = await callback.message.answer(
        "Это последние данные. Если хотите скрыть их, нажмите ниже.",
        reply_markup=get_callback_btns(
            btns={"👀 Скрыть отчет": f"hide_report_{category_id}"},
            sizes=(1,)
        ),
    )
    report_msg_ids.append(hide_report_msg.message_id)

    for msg_id in report_msg_ids:
        await update_all_report_msg_id(session, chat_id=callback.message.chat.id, new_msg_id=msg_id)

    # Сохраняем последнее сообщение
    summary_msg = await callback.message.answer("Хотите сделать что-то еще?", reply_markup=get_admin_menu())
    await update_last_action_msg_id(session, callback.message.chat.id, summary_msg.message_id)

    await callback.answer()


#################################### Отчет по задачам ###################################
@admin_router.callback_query(F.data == "admin:tasks")
async def all_tasks(callback: types.CallbackQuery, session: AsyncSession):
    tasks = await orm_get_tasks(session)

    if not tasks:
        await callback.message.edit_text("🙅‍♂️Нет активных задач.", reply_markup=get_admin_menu())
        await callback.answer()
        return

    # Отправляем каждую задачу отдельным сообщением с кнопкой удаления
    for task in tasks:
        task_text = f"📌 <b>Описание:</b> {task.description}\n" \
                    f"👤 <b>От кого:</b> {task.username}\n" \
                    f"📞 <b>Контакты:</b> {task.contact_number}"

        # Используем `get_callback_btns` для создания кнопки удаления
        btns = get_callback_btns(btns={"❌ Удалить задачу": f"delete_task_{task.id}"})

        await callback.message.answer(task_text, reply_markup=btns, parse_mode="HTML")

    await callback.answer()

########################## Удаление данных детали ####################################
@admin_router.callback_query(F.data.startswith('delete_'))
async def delete_item(callback: types.CallbackQuery, session: AsyncSession):
    data_parts = callback.data.split("_")  # Разбиваем callback-данные

    if len(data_parts) < 3:
        await callback.answer("Ошибка: некорректный формат данных!")
        return

    item_type = data_parts[1]  # Тип элемента (task или detail)
    try:
        item_id = int(data_parts[2])  # ID элемента
    except ValueError:
        await callback.answer("Ошибка: ID элемента должен быть числом!")
        return

    # Обработка для задачи
    if item_type == "task":
        task = await orm_get_task_by_id(session, item_id)  # Получаем задачу
        if not task:
            await callback.answer("Ошибка: задача не найдена!")
            return

        # Удаляем сообщение в группе
        if task.group_message_id:
            try:
                await callback.message.bot.delete_message(GROUP_CHAT_ID, task.group_message_id)
            except Exception as e:
                print(f"Ошибка при удалении сообщения в группе: {e}")

        await orm_delete_task(session, item_id)  # Удаляем задачу из БД

    # Обработка для детали
    elif item_type == "detail":
        detail = await orm_get_detail(session, item_id)  # Получаем деталь
        if not detail:
            await callback.answer("Ошибка: деталь не найдена!")
            return

        await orm_delete_detail(session, item_id)  # Удаляем деталь из БД

    else:
        await callback.answer("Ошибка: неизвестный тип данных!")
        return

    # Анимация удаления
    try:
        await callback.message.edit_text("🗑 Удаление...")
        await asyncio.sleep(1)
        await callback.message.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")


########################## Изменение данных ####################################
class AddDetails(StatesGroup):
    category = State()
    name = State()
    process_details = State()

    detail_for_change = None

    texts = {
        'AddDetails:category': 'Выберите изделие заново ⚙️:',
        'AddDetails:name': 'Выберите деталь заново 🔩:',
        'AddDetails:process_details': 'Введите заводской номер и статус в формате: <b>Номер</b>, <b>Статус</b>',
    }


@admin_router.callback_query(StateFilter(None), F.data.startswith("change_"))
async def change_detail_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    #Получаем последнее сообщение
    result = await session.execute(select(MsgId).filter_by(chat_id=callback.message.chat.id))
    msg_record = result.scalars().first()

    if msg_record and msg_record.last_action_msg_id:
        try:
            #Удаляем последнее сообщение
            await callback.bot.delete_message(chat_id=callback.message.chat.id,
                                              message_id=msg_record.last_action_msg_id)

            #Очищаем ID последнего сообщения в БД
            await delete_last_action_msg_id(session, chat_id=callback.message.chat.id)
        except Exception as e:
            print(f"Ошибка при удалении последнего сообщения: {e}")

    # Логика для изменения детали
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}

    btns["⏭️ Пропустить"] = "add:пропустить"

    detail_id = callback.data.split("_")[-1]
    AddDetails.detail_for_change = await orm_get_detail(session, int(detail_id))

    await callback.answer()
    await callback.message.answer("Выберите изделие ⚙️", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddDetails.category)


############################# Код ниже для FSM ##########################################
@admin_router.callback_query(StateFilter(None), F.data == "admin:add_data")
async def add_category(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}

    btns["❌Отмена"] = "cancel:отмена"

    await callback.message.edit_text("Выберите изделие ⚙️", reply_markup=get_callback_btns(btns=btns, sizes=(2,)))
    await state.set_state(AddDetails.category)
    await callback.answer()


############################## Функции отмены и назад #######################################
@admin_router.callback_query(StateFilter('*'), F.data == "cancel:отмена")
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌Действие отменено. Можете продолжить работу", reply_markup=get_admin_menu())
    await callback.answer()


@admin_router.callback_query(F.data.startswith("back"))
async def process_back_button(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    state_history = data.get('state_history', [])

    if len(state_history) < 2:
        await callback_query.answer("Вы уже на первом шаге.", show_alert=True)
        return

    # Убираем текущий шаг и берём предыдущий
    state_history.pop()
    previous_state = state_history[-1]

    # Сохраняем обновлённую историю
    await state.update_data(state_history=state_history)
    await state.set_state(previous_state)

    # Определяем текст и кнопки
    previous_text = AddDetails.texts.get(previous_state, "Текст не найден.")

    if previous_state == AddDetails.category.state:
        categories = await orm_get_categories(session)
        btns = {category.name: str(category.id) for category in categories}
        keyboard = get_callback_btns(btns=btns)
    elif previous_state == AddDetails.name.state:
        user_data = await state.get_data()
        category_id = user_data.get('category')
        btns = add_buttons.get(category_id, {})
        keyboard = get_callback_btns(btns=btns)
    else:
        keyboard = None

    await callback_query.message.edit_text(previous_text, reply_markup=keyboard)

################################################################################################

@admin_router.callback_query(AddDetails.category)
async def fsm_category_choice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    category_data = callback.data

    # Проверяем, нажата ли кнопка "Пропустить"
    if category_data == "add:пропустить":
        # Используем предыдущую категорию
        category_id = AddDetails.detail_for_change.category_id
        await state.update_data(category=category_id)
    else:
        category_id = int(category_data)
        categories = await orm_get_categories(session)

        if category_id in [category.id for category in categories]:
            await state.update_data(category=category_id)
        else:
            return await callback.answer("Выберите изделие из кнопок.")

    # Кнопки для выбора детали
    btns = add_buttons.get(category_id, {})

    # Сохраняем предыдущие кнопки в state
    await state.update_data(prev_buttons=get_callback_btns(btns=btns))

    # Переход с сохранением истории состояний
    await go_to_next_state(state, AddDetails.name)

    await callback.message.edit_text('Выберите деталь 🔩', reply_markup=get_callback_btns(btns=btns))

######## Ловим любые некорректные действия, кроме нажатия на кнопку выбора категории #########
@admin_router.message(AddDetails.category)
async def fsm_category_choice(message: types.Message):
    await message.answer("'Выберите изделие из кнопок.'")

##############################################################################################

@admin_router.callback_query(AddDetails.name, F.data.startswith("add:"))
async def add_name(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split(":")[-1]

    btns = {
        "❌Отмена": "cancel:отмена",
        "🔙Назад": "back"
    }
    keyboard = get_callback_btns(btns=btns, sizes=(2,))

    # Обновляем состояние с введённым названием
    await state.update_data(name=AddDetails.detail_for_change.name if name.strip().lower() == 'пропустить' else name)

    # Переход с сохранением истории состояний
    await go_to_next_state(state, AddDetails.process_details)

    # Редактируем сообщение с добавлением клавиатуры
    msg = await callback.message.edit_text("Введите заводской номер и статус в формате: <b>Номер</b>, <b>Статус</b>",
                                           reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(instruction_msg_id=msg.message_id)


# Хендлер для отлова некорректных вводов для состояния name
@admin_router.message(AddDetails.name)
async def add_name(message: types.Message):
    await message.answer("Выберите деталь из кнопок")

##############################################################################################

@admin_router.message(AddDetails.process_details, F.text)
async def add_process_details(message: types.Message, state: FSMContext, session: AsyncSession):
    await message.delete()  # Удаляем сообщение пользователя
    state_data = await state.get_data()

    # Удаляем старое сообщение "Введите заводской номер и статус..."
    if "instruction_msg_id" in state_data:
        try:
            await message.bot.delete_message(message.chat.id, state_data["instruction_msg_id"])
        except Exception:
            pass  # Если сообщение уже удалено, просто игнорируем ошибку

    details_data = message.text.split("\n")  # Разделяем строки
    added_details = []  # Список для итогового сообщения

    for detail_data in details_data:
        data = detail_data.split(',')
        if len(data) == 2:
            number, status = map(str.strip, data)
            number = AddDetails.detail_for_change.number if number == "." else number
            status = AddDetails.detail_for_change.status if status == "." else status

            # Обновляем state_data
            state_data.update({'number': number, 'status': status})

            if AddDetails.detail_for_change:
                await orm_update_detail(session, AddDetails.detail_for_change.id, state_data)
            else:
                await orm_add_detail(session, state_data)

            # Добавляем данные в список итогового сообщения
            added_details.append(f"<b>#️⃣Номер:</b> {number}\n<b>♻️Статус:</b> {status}")
        else:
            await message.answer("Пожалуйста, введите данные в правильном формате: <b>Номер</b>, <b>Статус</b>")
            return

    # Отправляем одно сообщение, если добавлены детали
    if added_details:
        success_msg = await message.answer("Вписываем данные... 📝")
        await asyncio.sleep(1)  # Ждём 1 секунды
        try:
            await success_msg.delete()
        except Exception:
            pass  # Если сообщение уже удалено, игнорируем ошибку

    summary = "\n\n".join(added_details)

    # Кнопка "Скрыть отправленные данные"
    hide_btn = {
        "👀 Скрыть отправленные данные": "hide_summary"
    }

    # Отправляем итоговое сообщение с клавишами
    summary_msg = await message.answer(
        f"<b>📝 Итоговые данные:</b>\n{summary}",
        reply_markup=get_callback_btns(btns=hide_btn, sizes=(1,)),
        parse_mode="HTML"
    )
    # Сохранение ID итогового сообщения в базу данных
    await update_summary_msg_id(session, message.chat.id, summary_msg.message_id)
    await message.answer("Что хотите сделать?", reply_markup=get_admin_menu())

    await state.clear()
    AddDetails.detail_for_change = None


@admin_router.callback_query(F.data == "hide_summary")
async def hide_summary_callback(call: types.CallbackQuery, session: AsyncSession):
    chat_id = call.message.chat.id
    print(f"Получен callback для скрытия отчета в чате {chat_id}")

    async with session.begin():
        result = await session.execute(select(MsgId).filter_by(chat_id=chat_id))
        msg_record = result.scalars().first()

    if msg_record and msg_record.summary_msg_id:
        print(f"Найдено сообщение для удаления: {msg_record.summary_msg_id}")
        try:
            await call.message.bot.delete_message(chat_id, msg_record.summary_msg_id)
            print(f"Сообщение с ID {msg_record.summary_msg_id} успешно удалено")
        except Exception as e:
            print(f"Ошибка при удалении сообщения: {e}")

        async with session.begin():
            msg_record.summary_msg_id = None
            await session.commit()
            print(f"ID итогового сообщения обновлен в базе")

        await call.answer("Итоговые данные скрыты", show_alert=False)
    else:
        print("Итоговые данные не найдены для скрытия")
        await call.answer("Не удалось найти итоговые данные для скрытия", show_alert=False)


@admin_router.callback_query(F.data.startswith('hide_report_'))
async def hide_report(callback: types.CallbackQuery, session: AsyncSession):
    # Извлекаем category_id из данных кнопки
    category_id = callback.data.split('_')[-1]

    # Получаем все ID сообщений для этой категории из базы данных
    async with session.begin():
        result = await session.execute(select(MsgId).filter_by(chat_id=callback.message.chat.id))
        msg_record = result.scalars().first()

    if msg_record and msg_record.all_report_msg_id:
        # Получаем список ID сообщений из строки
        msg_ids = msg_record.all_report_msg_id.split(",")

        # Удаляем каждое сообщение
        for msg_id in msg_ids:
            try:
                await callback.message.bot.delete_message(callback.message.chat.id, int(msg_id))
            except Exception as e:
                print(f"Ошибка при удалении сообщения {msg_id}: {e}")

        # Очистка ID сообщений в БД
        async with session.begin():
            msg_record.all_report_msg_id = None
            await session.commit()

    await callback.answer("Отчет скрыт", show_alert=False)


@admin_router.callback_query(F.data == "hide_details_report")
async def hide_summary(callback: types.CallbackQuery, session: AsyncSession):
    # Получаем все записи для текущего chat_id
    result = await session.execute(select(MsgId).filter_by(chat_id=callback.message.chat.id))
    msgs = result.scalars().all()

    if msgs:
        # Удаляем каждое из сообщений
        for msg in msgs:
            try:
                if msg.detail_report_msg_id:
                    await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.detail_report_msg_id)
            except Exception as e:
                print(f"Ошибка при удалении сообщения: {e}")

        # Удаляем все записи из базы данных для текущего chat_id
        try:
            for msg in msgs:
                await session.delete(msg)
            await session.commit()
            print(f"Записи для chat_id {callback.message.chat.id} успешно удалены из базы данных.")
        except Exception as e:
            print(f"Ошибка при удалении записей из базы данных: {e}")
            await session.rollback()
    else:
        print("Не удалось найти сообщения для скрытия.")

    await callback.answer()
