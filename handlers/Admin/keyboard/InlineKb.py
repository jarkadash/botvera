from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

admin_panel = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='Выдать(забрать) роль', callback_data='role_user'),
        ],
        [
          InlineKeyboardButton(text='Роли', callback_data='roles'),
        ],
        [
          InlineKeyboardButton(text='Услуги', callback_data='admin_service'),
        ],
        [
            InlineKeyboardButton(text='Черный список', callback_data='black_list'),
        ],
        [
            InlineKeyboardButton(text='Рассылка сообщений', callback_data='malling_message'),
        ],
        [
          InlineKeyboardButton(text='Выгрузка', callback_data='export')
        ],
        [
            InlineKeyboardButton(text='📸 Режим Медиа', callback_data='start_media'),
        ],
        [
            InlineKeyboardButton(text='Настройки выплат', callback_data='edit_rates'),
        ]
    ]
)

admin_roles = InlineKeyboardMarkup(
    inline_keyboard=[
        [
          InlineKeyboardButton(text='Добавить роли', callback_data='role_add'),
        ],
        [
          InlineKeyboardButton(text='Удалить роли', callback_data='role_del'),
        ],
        [
          InlineKeyboardButton(text='🔙 назад', callback_data='back_menu'),
        ],
    ]
)

admin_role_user_edit = InlineKeyboardMarkup(
    inline_keyboard=[
        [
          InlineKeyboardButton(text='Выдать роль', callback_data='roleUser_add')
        ],
        [
           InlineKeyboardButton(text='Уволить пользователя', callback_data='roleUser_del')
        ],
        [
          InlineKeyboardButton(text='🔙 назад', callback_data='back_menu'),
        ],
    ]
)

admin_services = InlineKeyboardMarkup(
    inline_keyboard=[
        [
          InlineKeyboardButton(text='Добавить услугу', callback_data='services_add')
        ],
        [
          InlineKeyboardButton(text='Удалить услугу', callback_data='services_del')
        ],
        [
          InlineKeyboardButton(text='🔙 назад', callback_data='back_menu'),
        ],
    ]
)

admin_black_list = InlineKeyboardMarkup(
    inline_keyboard=[
        [
          InlineKeyboardButton(text='Добавить в черный список', callback_data='blackList_add')
        ],
        [
           InlineKeyboardButton(text='Удалить из черного списка', callback_data='blackList_del')
        ],
        [
          InlineKeyboardButton(text='🔙 назад', callback_data='back_menu'),
        ],
    ]
)

admin_media_menu_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='Опубликовать запись', callback_data="media_add"),
        ],
        [
            InlineKeyboardButton(text='Моя статистика', callback_data="media_statistic"),
        ],
        [
          InlineKeyboardButton(text='🔙 назад', callback_data='back_menu'),
        ],
    ]
)