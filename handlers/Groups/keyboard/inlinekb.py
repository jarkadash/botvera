# Создаем инлайн-клавиатуру
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

settings_group_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⚙️ Настроить бота",
                callback_data=f"setup_bot_chat"
            )
        ],
    ]
)

setting_parameters = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Назначить саппорта на эту группу",
                callback_data=f"setup_support_chat"
            ),
        ],
        [
            InlineKeyboardButton(
                text="Переназначить саппорта на эту группу",
                callback_data=f"reinstall_support_chat"
            )
        ],
        [
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"back_settings_chat"
            )
        ]
    ]
)