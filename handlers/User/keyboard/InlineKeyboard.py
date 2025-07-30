from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

accounts = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Аккаунты 0-100 часов", callback_data="zero_accounts")
        ],
        [
            InlineKeyboardButton(text="Аккаунты 1500+ часов", callback_data="active_accounts")
        ],

        [
            InlineKeyboardButton(text="Закрыть меню", callback_data="close_accounts"),
        ]
    ]
)
