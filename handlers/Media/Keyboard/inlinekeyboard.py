from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

media_menu_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='Опубликовать запись', callback_data="media_add"),
        ],
        [
            InlineKeyboardButton(text='Моя статистика', callback_data="media_statistic"),
        ],
    ]
)