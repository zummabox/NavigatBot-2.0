from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State

async def go_to_next_state(state: FSMContext, next_state: State):
    data = await state.get_data()
    state_history = data.get("state_history", [])

    # Получаем текущее состояние в строковом формате
    current_state = await state.get_state()

    # Добавляем текущее состояние в историю, если оно не None и не повторяется
    if current_state and (not state_history or state_history[-1] != current_state):
        state_history.append(current_state)

    # Добавляем следующее состояние
    state_history.append(next_state.state)

    # Обновляем историю и устанавливаем новое состояние
    await state.update_data(state_history=state_history)
    await state.set_state(next_state)


