from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State


async def go_to_next_state(state: FSMContext, next_state: State, buttons=None):
    data = await state.get_data()
    history = data.get('state_history', [])

    current_state = await state.get_state()
    if current_state:
        history.append({
            'state': current_state,
            'buttons': buttons,
        })
        await state.update_data(state_history=history)

    await state.set_state(next_state)


async def go_to_previous_state(state: FSMContext):
    data = await state.get_data()
    previous_state = data.get("previous_state")
    if previous_state:
        await state.set_state(previous_state)  # Возвращаемся в предыдущее состояние