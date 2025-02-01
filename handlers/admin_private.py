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
    name = State()
    number = State()
    category = State()
    status = State()

    detail_for_change = None

    texts = {
        'AddDetails:name': 'Введите название заново:',
        'AddDetails:number': 'Введите номер заново:',
        'AddDetails:category': 'Выберите категорию заново:',
        'AddDetails:status': 'Этот стейт последний, поэтому...',
    }


@admin_router.callback_query(StateFilter(None), F.data.startswith("change_"))
async def change_detail_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}

    detail_id = callback.data.split("_")[-1]

    detail_for_change = await orm_get_detail(session, int(detail_id))

    AddDetails.detail_for_change = detail_for_change

    await callback.answer()
    await callback.message.answer("Выберите изделие", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddDetails.category)

############################# Код ниже для FSM ##########################################
@admin_router.message(StateFilter(None), F.text == "Добавить данные")
async def add_category(message: types.Message, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}
    await message.answer("Выберите изделие", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddDetails.category)


############################## Функции отмены и назад #######################################
@admin_router.callback_query(StateFilter('*'), F.data == "cancel:отмена")
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    await callback.message.answer("Действие отменено", reply_markup=ADMIN_KB)
    await callback.answer()


@admin_router.callback_query(StateFilter('*'), F.data == "back:назад")
async def back_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает кнопку 🔙 Назад на любом этапе FSM"""
    current_state = await state.get_state()

    if current_state == AddDetails.name:
        await callback.message.answer("Вы на первом шаге, вернуться нельзя. Введите название или нажмите 'Отмена'")
        await callback.answer()
        return

    previous_state = None
    for step in AddDetails.__all_states__:
        if step.state == current_state:
            break
        previous_state = step

    if previous_state:
        await state.set_state(previous_state)
        await callback.message.answer(f"Вы вернулись на шаг: {previous_state.state}",
                                      reply_markup=get_callback_btns(
                                          btns={"🔙Назад": "back:назад", "❌Отмена": "cancel:отмена"}))
    else:
        await callback.message.answer("Предыдущего шага нет, нажмите 'Отмена', чтобы выйти.")

    await callback.answer()
##############################################################################################


@admin_router.callback_query(AddDetails.category)
async def category_choice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    category_id = int(callback.data)
    if category_id in [category.id for category in categories]:
        await callback.answer()

        await state.update_data(category=callback.data)

        if category_id in add_buttons:
            btns = add_buttons[category_id]

        await callback.message.delete()
        await callback.message.answer('Выберите деталь.', reply_markup=get_callback_btns(btns=btns))

        await state.set_state(AddDetails.name)
    else:
        await callback.message.answer('Выберите изделие из кнопок.')
        await callback.answer()


######## Ловим любые некорректные действия, кроме нажатия на кнопку выбора категории #########
@admin_router.message(AddDetails.category)
async def category_choice2(message: types.Message):
    await message.answer("'Выберите изделие из кнопок.'")

##############################################################################################

@admin_router.callback_query(AddDetails.name, F.data.startswith("add:"))
async def add_name(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split(":")[-1]
    if name.strip().lower() == 'пропустить':
        await state.update_data(name=AddDetails.detail_for_change.name)
    else:
        await callback.answer()
        await state.update_data(name=name)

    await callback.message.delete()
    await callback.message.answer("Введите заводской номер")
    await state.set_state(AddDetails.number)


# Хендлер для отлова некорректных вводов для состояния name
@admin_router.message(AddDetails.name)
async def add_name(message: types.Message):
    await message.answer("Выберите деталь из кнопок")

##############################################################################################

@admin_router.message(AddDetails.number, F.text)
async def add_number(message: types.Message, state: FSMContext):
    if message.text == ".":
        await state.update_data(number=AddDetails.detail_for_change.number)
    else:
        if 4 >= len(message.text):
            await message.answer(
                "Слишком короткое заводской номер. \n Введите заново"
            )
            return
        await state.update_data(number=message.text)

    await message.answer("Введите статус")
    await state.set_state(AddDetails.status)


###### Хендлер для отлова некорректных вводов для состояния description #######
@admin_router.message(AddDetails.number)
async def add_number2(message: types.Message):
    await message.answer("Вы ввели не допустимые данные, введите текст описания товара")

##############################################################################################

@admin_router.message(AddDetails.status, F.text)
async def add_status(message: types.Message, state: FSMContext, session: AsyncSession):
    if message.text == "." and AddDetails.detail_for_change:
        await state.update_data(status=AddDetails.detail_for_change.status)
    else:
        await state.update_data(status=message.text)

    data = await state.get_data()
    try:
        if AddDetails.detail_for_change:
            await orm_update_detail(session, AddDetails.detail_for_change.id, data)
        else:
            await orm_add_detail(session, data)

        await message.answer("Данные добавлены/изменены ✅", reply_markup=ADMIN_KB)
        await state.clear()

    except Exception as e:
        await message.answer(
            f"Ошибка: \n{str(e)}\nОбратитесь к программисту", reply_markup=ADMIN_KB)
        await state.clear()

    AddDetails.detail_for_change = None


# Хендлер для отлова некорректных ввода для состояния price
@admin_router.message(AddDetails.status)
async def add_price2(message: types.Message):
    await message.answer("Вы ввели не допустимые данные, введите статус детали")