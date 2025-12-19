from aiogram.fsm.state import StatesGroup, State


class FormOrderShema(StatesGroup):
    name_game = State()
    name_cheat = State()
    problem_description = State()
    specifications = State()
