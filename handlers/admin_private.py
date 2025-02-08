from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (orm_add_detail, orm_get_details,
                                orm_delete_detail, orm_get_detail,
                                orm_update_detail, orm_get_categories,
                                orm_get_detail_report, orm_get_tasks, orm_delete_task, orm_get_task_by_id)

from filters.chat_types import ChatTypeFilter, IsAdmin
from handlers.fsm_utils import go_to_next_state
from handlers.user_private import GROUP_CHAT_ID
from kbds.callback_list import report_buttons, add_buttons
from kbds.inline_kbds import get_callback_btns
from kbds.reply_kbds import get_keyboard


admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())


ADMIN_KB = get_keyboard(
    "Добавить данные",
    "Отчет",
    "Отчет по деталям",
    "Задачи",
    placeholder="Выберите действие",
    sizes=(2,),
)


@admin_router.message(Command("admin"))
async def add_product(message: types.Message):
    await message.answer("Что хотите сделать?", reply_markup=ADMIN_KB)


########################## Отчет по деталям ####################################
class Report(StatesGroup):
    category_report = State()
    detail_report = State()


@admin_router.message(StateFilter(None), F.text == "Отчет по деталям")
async def detail_report(message: types.Message, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}
    await message.answer("Выберите изделие", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(Report.category_report)


@admin_router.callback_query(Report.category_report)
async def category_choice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    category_id = int(callback.data)
    if category_id in [category.id for category in categories]:

        await callback.answer()
        await state.update_data(category_report=callback.data)

        if category_id in report_buttons:
            btns = report_buttons[category_id]
        await callback.message.answer('Выберите деталь.', reply_markup=get_callback_btns(btns=btns))
        await state.set_state(Report.detail_report)


@admin_router.callback_query(Report.detail_report, F.data.startswith('report:'))
async def get_detail_report(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    detail_name = callback.data.split(":")[-1]
    detail_data = await orm_get_detail_report(session, detail_name)
    if detail_data:
        for detail in detail_data:
            # Преобразуем дату в нужный формат
            formatted_date = detail.updated.strftime("%d.%m.%y %H:%M:%S")

            await callback.message.answer(
                f"<b>⚙️Деталь:</b> {detail.name}\n<b>#️⃣Номер:</b> {detail.number}\n<b>♻️Статус:</b> {detail.status}"
                f"\n<b>📝Изменения статуса:</b> {formatted_date}",
                reply_markup=get_callback_btns(
                    btns={
                        "❌Удалить": f"delete_detail_{detail.id}",
                        "📝Изменить": f"change_detail_{detail.id}",
                    },
                    sizes=(2,)
                ),
                parse_mode="HTML",
            )
    await callback.answer()
    await callback.message.answer("Вот список деталей ⬆️")
    await state.clear()


########################## Полный отчет по изделию ####################################
@admin_router.message(F.text == "Отчет")
async def all_report(message: types.Message, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f'category_{category.id}' for category in categories}
    await message.answer("Выберите изделие", reply_markup=get_callback_btns(btns=btns))


@admin_router.callback_query(F.data.startswith('category_'))
async def all_report(callback: types.CallbackQuery, session: AsyncSession):
    category_id = callback.data.split('_')[-1]
    for detail in await orm_get_details(session, int(category_id)):
        await callback.message.answer(
            f"<b>⚙️Деталь:</b> {detail.name}\
                                \n<b>#️⃣Номер</b> {detail.number}\n<b>♻️Статус:</b> {detail.status}",
            reply_markup=get_callback_btns(
                btns={
                    "❌Удалить": f"delete_detail_{detail.id}",
                    "📝Изменить": f"change_detail_{detail.id}",
                },
                sizes=(2,)
            ),
            parse_mode="HTML",
        )
    await callback.answer()
    await callback.message.answer("Вот список деталий ⬆️")

#################################### Отчет по задачам ###################################
@admin_router.message(F.text == "Задачи")
async def all_tasks(message: types.Message, session: AsyncSession):
    tasks = await orm_get_tasks(session)

    if not tasks:
        await message.answer("Задачи не найдены.")
        return

    # Отправляем каждую задачу отдельным сообщением с кнопкой удаления
    for task in tasks:
        task_text = f"📌 <b>Описание:</b> {task.description}\n" \
                    f"👤 <b>От кого:</b> {task.username}\n" \
                    f"📞 <b>Контакты:</b> {task.contact_number}"

        # Используем `get_callback_btns` для создания кнопки удаления
        btns = get_callback_btns(btns={"❌ Удалить задачу": f"delete_task_{task.id}"})

        await message.answer(task_text, reply_markup=btns, parse_mode="HTML")

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
        message_text = "Задача успешно удалена! ✅"

    # Обработка для детали
    elif item_type == "detail":
        detail = await orm_get_detail(session, item_id)  # Получаем деталь
        if not detail:
            await callback.answer("Ошибка: деталь не найдена!")
            return

        await orm_delete_detail(session, item_id)  # Удаляем деталь из БД
        message_text = "Деталь успешно удалена! ✅"

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

    await callback.answer(message_text, show_alert=False)


########################## Изменение данных ####################################
class AddDetails(StatesGroup):
    category = State()
    name = State()
    process_details = State()

    detail_for_change = None

    texts = {
        'AddDetails:category': 'Выберите категорию заново:',
        'AddDetails:name': 'Введите название заново:',
        'AddDetails:process_details': 'Введите заводской номер и статус в формате: Номер, Статус',
    }


@admin_router.callback_query(StateFilter(None), F.data.startswith("change_"))
async def change_detail_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}

    detail_id = callback.data.split("_")[-1]
    AddDetails.detail_for_change = await orm_get_detail(session, int(detail_id))

    await callback.answer()
    await callback.message.answer("Выберите изделие", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddDetails.category)

############################# Код ниже для FSM ##########################################
@admin_router.message(StateFilter(None), F.text == "Добавить данные")
async def add_category(message: types.Message, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}
    await message.delete()
    await message.answer("Выберите изделие", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddDetails.category)


############################## Функции отмены и назад #######################################
@admin_router.callback_query(StateFilter('*'), F.data == "cancel:отмена")
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Действие отменено", reply_markup=ADMIN_KB)
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
async def category_choice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    category_id = int(callback.data)
    categories = await orm_get_categories(session)

    if category_id in [category.id for category in categories]:
        btns = add_buttons.get(category_id, {})

        # Сохраняем кнопки и предыдущий статус в state
        await state.update_data(category=category_id, prev_buttons=get_callback_btns(btns=btns))

        # Переход с сохранением истории состояний
        await go_to_next_state(state, AddDetails.name)

        await callback.message.edit_text('Выберите деталь.', reply_markup=get_callback_btns(btns=btns))
    else:
        await callback.answer("Выберите изделие из кнопок.")



######## Ловим любые некорректные действия, кроме нажатия на кнопку выбора категории #########
@admin_router.message(AddDetails.category)
async def category_choice2(message: types.Message):
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
    await callback.message.edit_text("Введите заводской номер и статус в формате 'Номер, Статус'",
                                     reply_markup=keyboard)



# Хендлер для отлова некорректных вводов для состояния name
@admin_router.message(AddDetails.name)
async def add_name(message: types.Message):
    await message.answer("Выберите деталь из кнопок")

##############################################################################################

@admin_router.message(AddDetails.process_details, F.text)
async def add_process_details(message: types.Message, state: FSMContext, session: AsyncSession):
    await message.delete()
    details_data = message.text.split("\n")
    state_data = await state.get_data()

    # Убедитесь, что state_data — это словарь
    if not isinstance(state_data, dict):
        await message.answer("Ошибка данных. Попробуйте начать заново.")
        await state.clear()
        return

    # Проверка на наличие категории
    if "category" not in state_data:
        await message.answer("Не выбрана категория! Пожалуйста, выберите категорию и повторите попытку.")
        return

    for detail_data in details_data:
        data = detail_data.split(',')
        if len(data) == 2:
            number, status = map(str.strip, data)
            number = AddDetails.detail_for_change.number if number == "." else number
            status = AddDetails.detail_for_change.status if status == "." else status
            state_data.update({'number': number, 'status': status})

            if AddDetails.detail_for_change:
                await orm_update_detail(session, AddDetails.detail_for_change.id, state_data)
                await message.answer("Данные детали обновлены")
            else:
                # Добавляем категорию, если она есть в state_data
                data = dict(state_data)  # Создаем копию словаря
                data["category"] = state_data["category"]
                await orm_add_detail(session, data)
                await message.answer("Детали успешно добавлены")
        else:
            await message.answer("Пожалуйста, введите данные в правильном формате: Номер, Статус")
            return

    await state.clear()
    AddDetails.detail_for_change = None
    summary = f"<b>⚙️Название:</b> {state_data.get('name')}\n<b>#️⃣Номер:</b> {state_data.get('number')}\n<b>♻️Статус:</b> {state_data.get('status')}"
    await message.answer(f"<b>📝Итоговые данные:</b>\n{summary}", parse_mode="HTML")


