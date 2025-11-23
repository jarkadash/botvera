from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

def get_start_menu(lang: str) -> ReplyKeyboardMarkup:
    if lang == "en":
        menu_text = "📋 Menu"
        site_text = "GameBreaker🦊"
    else:
        menu_text = "📋 Меню"
        site_text = "GameBreaker🦊"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=menu_text)],
            [KeyboardButton(text=site_text, web_app=WebAppInfo(url='https://gamebreaker.ru'))]
        ],
        resize_keyboard=True
    )

def get_media_start_kb(lang: str) -> ReplyKeyboardMarkup:
    if lang == "en":
        media_menu = "📸 Media Menu"
        menu = "📋 Menu"
    else:
        media_menu = "📸 Меню"
        menu = "📋 Меню"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=media_menu), KeyboardButton(text=menu)]
        ],
        resize_keyboard=True
    )

def get_user_stars_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='1'), KeyboardButton(text='2'), KeyboardButton(text='3'), KeyboardButton(text='4'), KeyboardButton(text='5')],
            [KeyboardButton(text='6'), KeyboardButton(text='7'), KeyboardButton(text='8'), KeyboardButton(text='9'), KeyboardButton(text='10')]
        ],
        one_time_keyboard=True,
        resize_keyboard=True
    )

def start_menu() -> ReplyKeyboardMarkup:
    return get_start_menu("ru")

def user_stars_kb() -> ReplyKeyboardMarkup:
    return get_user_stars_kb()
