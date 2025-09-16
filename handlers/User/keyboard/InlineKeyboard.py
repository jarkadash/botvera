from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def accounts_kb(lang: str) -> InlineKeyboardMarkup:
    if lang == "en":
        t1 = "Accounts 0–100 hours"
        t2 = "Accounts 1500+ hours"
        t3 = "Close menu"
    else:
        t1 = "Аккаунты 0-100 часов"
        t2 = "Аккаунты 1500+ часов"
        t3 = "Закрыть меню"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t1, callback_data="zero_accounts")],
            [InlineKeyboardButton(text=t2, callback_data="active_accounts")],
            [InlineKeyboardButton(text=t3, callback_data="close_accounts")]
        ]
    )
