from aiogram import F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from core.i18n import t, normalize_lang
from handlers.User.Start import start_router
from database.db import redis_client

LANG_KEY = "lang:{user_id}"

def _kb_lang() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский 🇷🇺", callback_data="set_lang_ru")],
        [InlineKeyboardButton(text="English 🇬🇧", callback_data="set_lang_en")]
    ])

@start_router.message(CommandStart())
async def choose_language_on_start(message: Message):
    user_key = LANG_KEY.format(user_id=message.from_user.id)
    lang = await redis_client.get(user_key)
    if not lang:
        await message.answer(t("choose_language", "ru"), reply_markup=_kb_lang())
        return
    if hasattr(lang, "decode"):
        lang = lang.decode()
    lang = normalize_lang(lang)
    await message.answer(t("start_hello_message", lang))

@start_router.callback_query(F.data.in_(["set_lang_ru","set_lang_en"]))
async def set_language(call: CallbackQuery):
    lang = "ru" if call.data.endswith("_ru") else "en"
    user_key = LANG_KEY.format(user_id=call.from_user.id)
    await redis_client.set(user_key, lang)
    await call.message.edit_text(t("language_set", lang))
    await call.message.answer(t("start_hello_message", lang))
