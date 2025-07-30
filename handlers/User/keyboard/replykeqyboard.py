from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

start_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📋 Меню')],
        [KeyboardButton(text='Аккаунты RUST'), KeyboardButton(text='GameBreaker🦊', web_app=WebAppInfo(url='https://gamebreaker.ru'))]
    ], resize_keyboard=True
)

media_start_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📸 Меню'), KeyboardButton(text='📋 Меню')],
    ], resize_keyboard=True
)

user_stars_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='1'), KeyboardButton(text='2'), KeyboardButton(text='3'), KeyboardButton(text='4'),
         KeyboardButton(text='5')],
        [KeyboardButton(text='6'), KeyboardButton(text='7'), KeyboardButton(text='8'), KeyboardButton(text='9'),
         KeyboardButton(text='10')]
    ], one_time_keyboard=True, resize_keyboard=True
)