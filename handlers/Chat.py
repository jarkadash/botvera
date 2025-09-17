import asyncio
import html
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.fsm.storage.base import StorageKey
from dotenv import load_dotenv
from aiogram import Bot, Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from colorama import Fore, Style
from handlers.User.keyboard.replykeqyboard import user_stars_kb, start_menu, get_start_menu
from logger import logger
from database.db import DataBase, redis_client
from handlers.User.Start import StarsOrder
from handlers.Worker.Start import active_timers
from config import *
from core.i18n import normalize_lang

db = DataBase()
load_dotenv()
chat_router = Router()

async def _get_lang(user_id: int) -> str:
    val = await redis_client.get(f"lang:{user_id}")
    if val and hasattr(val, "decode"):
        val = val.decode()
    return normalize_lang(val or "ru")

async def reset_state_after_timeout(state: FSMContext, user_id: int, bot):
    try:
        await asyncio.sleep(300)
        current_state = await state.get_state()
        if current_state == StarsOrder.stars_order.state:
            await state.clear()
            lang = await _get_lang(user_id)
            txt = "Time is up. Rating not received. State reset." if lang == "en" else "Время вышло. Оценка не получена. Состояние сброшено."
            await bot.send_message(user_id, txt, reply_markup=get_start_menu(lang))
    except asyncio.CancelledError:
        pass

async def unpin_specific_message(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
        print(f"Сообщение {message_id} откреплено!")
    except TelegramAPIError as e:
        print(f"Ошибка: {e}")

@chat_router.message(Command(commands="stop_chat"))
async def stop_chat(message: Message, state: FSMContext):
    logger.info(Fore.BLUE + f"Получена команда завершить чат от {message.from_user.id}" + Style.RESET_ALL)
    chat_with = await redis_client.get(f"chat:{message.from_user.id}")
    ticket = await redis_client.get(f"ticket:{message.from_user.id}")
    lang = await _get_lang(message.from_user.id)
    if chat_with:
        chat_with = int(chat_with)
        logger.debug(Fore.GREEN + f"Найден чат с {chat_with}" + Style.RESET_ALL)
        result = await db.close_order(int(ticket))
        if result is False:
            txt = "Error closing the ticket." if lang == "en" else "Ошибка при закрытии Тикета."
            await message.answer(txt)
            return
        other_storage_key = StorageKey(bot_id=message.bot.id, user_id=result['client_id'], chat_id=result['client_id'])
        other_state = FSMContext(storage=state.storage, key=other_storage_key)
        await other_state.update_data(order_id=int(ticket))
        await other_state.set_state(StarsOrder.stars_order)
        asyncio.create_task(reset_state_after_timeout(other_state, result['client_id'], message.bot))
        await redis_client.delete(f"ticket:{chat_with}")
        await redis_client.delete(f'chat:{chat_with}')
        await redis_client.delete(f"role:{chat_with}")
        await redis_client.delete(f"chat:{message.from_user.id}")
        await redis_client.delete(f"ticket:{message.from_user.id}")
        await redis_client.delete(f"role:{message.from_user.id}")
        logger.info(Fore.BLUE + f"Тикет №{ticket} успешно закрыт." + Style.RESET_ALL)
        order = await db.get_orders_by_id(int(ticket))
        await message.bot.send_message(chat_id=result['support_id'], text=f"🚪 Тикет №{ticket} успешно закрыт!\nПользователь:@{order.client_name}\nId: {order.client_id}")
        try:
            if lang == "en":
                txt_closed = f"🚪 Ticket #{ticket} closed. Thank you for contacting us.\nIf you have any questions, we are always in touch. Have a great game!"
                txt_rate = "Please rate the support work:\nUse the buttons below or send a number from 1 to 10."
            else:
                txt_closed = f"🚪 Тикет №{ticket} закрыт! 🎮 Спасибо за обращение.\nЕсли у вас появятся вопросы, мы всегда на связи. Удачной игры!"
                txt_rate = "Пожалуйста, оцените работу поддержки:\nС помощью кнопок ниже, либо можете написать свою оценку от 1 до 10."
            await message.bot.send_message(chat_id=result['client_id'], text=txt_closed)
            kb = user_stars_kb(await _get_lang(result['client_id'])) if callable(user_stars_kb) else user_stars_kb
            await message.bot.send_message(chat_id=result['client_id'], text=txt_rate, reply_markup=kb)
        except TelegramForbiddenError as e:
            logger.error(Fore.RED + f"Пользователь заблокировал бота>: {e}" + Style.RESET_ALL)
        message_info = await db.get_all_message(int(ticket))
        if message_info and order:
            message_edit_text = (
                f"✅ Тикет закрыт!\n\n\n"
                f"📩 <b>Тикет</b> №{order.id}\n"
                f"👤 <b>Пользователь:</b> @{order.client_name}\n"
                f"🆔 <b>ID:</b> {order.client_id}\n"
                f"<a href=\"https://t.me/{html.escape(order.client_name)}\">🔗 1.Телеграм</a>\n"
                f"<a href=\"tg://user?id={order.client_id}\">🔗 2.Телеграм</a>\n"
                f"🛠 <b>Услуга:</b> {html.escape(order.service_name)}\n"
                f"🆔 <b>Support_id:</b> {order.support_id}\n"
                f"👨‍💻 <b>Support_name:</b> @{html.escape(order.support_name)}\n"
                f"ℹ️ <b>Статус:</b> {html.escape(order.status)}\n"
                f"⏳ <b>Создана:</b> {order.created_at.strftime('%d-%m-%Y %H:%M')}\n\n"
                f"⏳ <b>Принята:</b> {order.accept_at.strftime('%d-%m-%Y %H:%M')}\n\n"
                f"⏳ <b>Закрыта:</b> {order.completed_at.strftime('%d-%m-%Y %H:%M')}\n\n"
                f"<a href=\"https://t.me/GBPSupport_bot\">Перейти в бота</a>"
            )
            await message.bot.edit_message_text(message_id=int(message_info.support_message_id), chat_id=GROUP_CHAT_ID, text=message_edit_text, parse_mode="HTML")
            await unpin_specific_message(message.bot, GROUP_CHAT_ID, int(message_info.support_message_id))
    else:
        logger.warning(Fore.YELLOW + f"Пользователь {message.from_user.id} не находится в активном чате." + Style.RESET_ALL)
        txt = "⚠️ You are not in an active chat." if lang == "en" else "⚠️ Вы не находитесь в активном чате."
        await message.answer(txt)

@chat_router.message(lambda message: message.chat.type == 'private')
async def forward_message(message: Message):
    user_id = message.from_user.id
    chat_with = await redis_client.get(f"chat:{user_id}")
    lang = await _get_lang(user_id)
    if chat_with:
        chat_with = int(chat_with)
        role = await redis_client.get(f"role:{user_id}")
        if isinstance(role, bytes):
            role = role.decode("utf-8")
        ticket = await redis_client.get(f"ticket:{user_id}")
        logger.debug(f"[TIMER] Роль пользователя {user_id}: {role}")
        if role == "user":
            if ticket and int(ticket) in active_timers:
                active_timers[int(ticket)].cancel()
                del active_timers[int(ticket)]
                logger.info(f"[TIMER] Отменён таймер авто-закрытия тикета №{ticket} — клиент начал общение.")
            await redis_client.incr(f"messages:{ticket}")
        else:
            logger.debug(f"[TIMER] Сообщение от роли '{role}', таймер не отменяется")
        group_chat_id = int(GROP_MG)
        group_thread_id = int(GROUP_CHAT_ID_MESSAGE)
        user = message.from_user
        sender_name = user.full_name
        username = f"(@{user.username})" if user.username else ""
        original_text = message.text or message.caption
        caption = f'Тикет №{ticket} [{role}]\nОтправитель: {sender_name} {username}'
        if message.photo:
            content_type = "📷 Фото"
        elif message.video:
            content_type = "🎥 Видео"
        elif message.document:
            content_type = "📄 Документ"
        else:
            content_type = "✉️ Сообщение"
        caption += f"\nТип: {content_type}"
        if original_text:
            caption += f"\n\n{original_text}"
        log_prefix = f"Ticket №{ticket} [{role}] [{username}]"
        if message.photo:
            logger.info(f"{Fore.GREEN}{log_prefix}: Отправлено фото{Style.RESET_ALL}")
        elif message.video:
            logger.info(f"{Fore.GREEN}{log_prefix}: Отправлено видео{Style.RESET_ALL}")
        elif message.document:
            logger.info(f"{Fore.GREEN}{log_prefix}: Отправлен документ{Style.RESET_ALL}")
        else:
            logger.info(f"{Fore.GREEN}{log_prefix}: {original_text}{Style.RESET_ALL}")
        await message.bot.send_message(chat_id=group_chat_id, message_thread_id=group_thread_id, text=caption[:1024])
        try:
            await message.bot.copy_message(chat_id=chat_with, from_chat_id=message.chat.id, message_id=message.message_id)
            logger.debug(Fore.GREEN + f"Найден чат с {chat_with}" + Style.RESET_ALL)
        except TelegramForbiddenError as e:
            logger.error(Fore.RED + f"Пользователь заблокировал бота>: {e}" + Style.RESET_ALL)
            warn = "🚨 The user has blocked the bot, close the ticket." if lang == "en" else "🚨 Пользователь заблокировал бота!, закрывайте тикет!"
            await message.bot.send_message(text=warn, chat_id=user_id)
    else:
        logger.warning(Fore.YELLOW + f"Пользователь {user_id} не в чате." + Style.RESET_ALL)
        txt = "Press /start, then use the buttons." if lang == "en" else "Нажмите на /start, далее используйте кнопки!"
        await message.answer(txt)
