import asyncio
import html
import os
from html import escape as html_escape
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.fsm.storage.base import StorageKey
from dotenv import load_dotenv
from aiogram import Bot, Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from colorama import Fore, Style

from handlers.User.common_states import StarsOrder
from handlers.User.keyboard.replykeqyboard import user_stars_kb, start_menu, get_start_menu
from handlers.Worker.common_states import FormOrderShema
from logger import logger
from database.db import DataBase, redis_client
from handlers.utils.timers import handle_auto_close_timer, active_timers
from handlers.Worker.Start import active_timers
from config import *
from core.i18n import normalize_lang

from typing import Dict, Optional
import time

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

"""
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
        await message.bot.send_message(chat_id=result['support_id'],
                                       text=f"🚪 Тикет №{ticket} успешно закрыт!\nПользователь:@{order.client_name}\nId: {order.client_id}")
        try:
            if lang == "en":
                txt_closed = f"🚪 Ticket #{ticket} closed. Thank you for contacting us.\nIf you have any questions, we are always in touch. Have a great game!"
                txt_rate = "Please rate the support work:\nUse the buttons below or send a number from 1 to 10."
            else:
                txt_closed = f"🚪 Тикет №{ticket} закрыт! 🎮 Спасибо за обращение.\nЕсли у вас появятся вопросы, мы всегда на связи. Удачной игры!"
                txt_rate = "Пожалуйста, оцените работу поддержки:\nС помощью кнопок ниже, либо можете написать свою оценку от 1 до 10."
            await message.bot.send_message(chat_id=result['client_id'], text=txt_closed)
            kb = user_stars_kb()
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
                f"⏳ <b>Создана:</b> {order.created_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"⏳ <b>Принята:</b> {order.accept_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"⏳ <b>Закрыта:</b> {order.completed_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"<a href=\"https://t.me/GBPSupport_bot\">Перейти в бота</a>"
            )
            await message.bot.edit_message_text(message_id=int(message_info.support_message_id), chat_id=GROUP_CHAT_ID,
                                                text=message_edit_text, parse_mode="HTML")
            await unpin_specific_message(message.bot, GROUP_CHAT_ID, int(message_info.support_message_id))
    else:
        logger.warning(
            Fore.YELLOW + f"Пользователь {message.from_user.id} не находится в активном чате." + Style.RESET_ALL)
        txt = "⚠️ You are not in an active chat." if lang == "en" else "⚠️ Вы не находитесь в активном чате."
        await message.answer(txt)
"""

'''@chat_router.message(lambda message: message.chat.type == 'private')
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
            await message.bot.copy_message(chat_id=chat_with, from_chat_id=message.chat.id,
                                           message_id=message.message_id)
            logger.debug(Fore.GREEN + f"Найден чат с {chat_with}" + Style.RESET_ALL)
        except TelegramForbiddenError as e:
            logger.error(Fore.RED + f"Пользователь заблокировал бота>: {e}" + Style.RESET_ALL)
            warn = "🚨 The user has blocked the bot, close the ticket." if lang == "en" else "🚨 Пользователь заблокировал бота!, закрывайте тикет!"
            await message.bot.send_message(text=warn, chat_id=user_id)
    else:
        logger.warning(Fore.YELLOW + f"Пользователь {user_id} не в чате." + Style.RESET_ALL)
        txt = "Press /start, then use the buttons." if lang == "en" else "Нажмите на /start, далее используйте кнопки!"
        await message.answer(txt)
'''
class RedisTopicCache:
    def __init__(self, redis_client, prefix: str = "topic_cache:", ttl_minutes: int = 30):
        self.redis = redis_client
        self.prefix = prefix
        self.ttl_seconds = ttl_minutes * 60

    async def get_client_by_thread(self, thread_id: int) -> Optional[int]:
        """Получить Telegram ID клиента по thread_id"""
        try:
            # thread_id -> client_id
            key = f"{self.prefix}thread:{thread_id}"
            client_id = await self.redis.get(key)
            if client_id:
                # Обновляем TTL при доступе
                await self.redis.expire(key, self.ttl_seconds)
                return int(client_id)
        except Exception as e:
            logger.error(f"Ошибка Redis get_client_by_thread: {e}")
        return None

    async def get_thread_by_client(self, client_telegram_id: int) -> Optional[int]:
        """Получить thread_id по Telegram ID клиента"""
        try:
            # client_id -> thread_id
            key = f"{self.prefix}client:{client_telegram_id}"
            thread_id = await self.redis.get(key)
            if thread_id:
                await self.redis.expire(key, self.ttl_seconds)
                return int(thread_id)
        except Exception as e:
            logger.error(f"Ошибка Redis get_thread_by_client: {e}")
        return None

    async def set_mapping(self, thread_id: int, client_telegram_id: int):
        """Установить связь thread_id <-> client_id"""
        try:
            # thread_id -> client_id
            thread_key = f"{self.prefix}thread:{thread_id}"
            await self.redis.setex(thread_key, self.ttl_seconds, str(client_telegram_id))

            # client_id -> thread_id
            client_key = f"{self.prefix}client:{client_telegram_id}"
            await self.redis.setex(client_key, self.ttl_seconds, str(thread_id))

            logger.info(f"Redis кэш: {thread_id} <-> {client_telegram_id}")
        except Exception as e:
            logger.error(f"Ошибка Redis set_mapping: {e}")

    async def remove_by_thread(self, thread_id: int):
        """Удалить по thread_id"""
        try:
            # Сначала получаем client_id
            thread_key = f"{self.prefix}thread:{thread_id}"
            client_id = await self.redis.get(thread_key)

            if client_id:
                # Удаляем client_id -> thread_id
                client_key = f"{self.prefix}client:{int(client_id)}"
                await self.redis.delete(client_key)

            # Удаляем thread_id -> client_id
            await self.redis.delete(thread_key)

        except Exception as e:
            logger.error(f"Ошибка Redis remove_by_thread: {e}")

    async def remove_by_client(self, client_telegram_id: int):
        """Удалить по client_id"""
        try:
            # Сначала получаем thread_id
            client_key = f"{self.prefix}client:{client_telegram_id}"
            thread_id = await self.redis.get(client_key)

            if thread_id:
                # Удаляем thread_id -> client_id
                thread_key = f"{self.prefix}thread:{int(thread_id)}"
                await self.redis.delete(thread_key)

            # Удаляем client_id -> thread_id
            await self.redis.delete(client_key)

        except Exception as e:
            logger.error(f"Ошибка Redis remove_by_client: {e}")

    async def get_stats(self) -> Dict:
        """Получить статистику кэша"""
        try:
            # Подсчитываем ключи по паттерну
            import aioredis
            thread_keys = await self.redis.keys(f"{self.prefix}thread:*")
            client_keys = await self.redis.keys(f"{self.prefix}client:*")

            return {
                'total_mappings': len(thread_keys),
                'thread_keys': len(thread_keys),
                'client_keys': len(client_keys)
            }
        except Exception as e:
            logger.error(f"Ошибка Redis get_stats: {e}")
            return {'total_mappings': 0}


# Глобальный экземпляр
topic_cache = RedisTopicCache(redis_client, prefix="topic_chat:", ttl_minutes=3)


@chat_router.message(Command("close_chat"))
async def close_chat_command(message: Message, bot: Bot, state: FSMContext):
    """Закрыть текущий чат (заявку) из топика"""
    logger.info(f"Команда /close_chat от {message.from_user.username}")

    get_data = await state.get_data()
    ''' 
    if get_data['thread_id']:
            await message.answer(f"Сначала заполните форму в предыдущем тикете!")
            return
    '''
    if not message.message_thread_id:
        await message.answer("❌ Эта команда работает только в топиках")
        return

    thread_id = message.message_thread_id

    try:
        # Получаем информацию о чате из БД
        chat_info = await db.get_chat_by_thread_id(thread_id)
        if not chat_info:
            await message.answer("❌ Чат не найден в базе данных")
            return

        # Получаем информацию о заказе
        order_id = chat_info.get('order_id')
        if not order_id:
            await message.answer("❌ Не найден связанный тикет")
            return

        result = await db.close_order(order_id)
        support_id = result.get('support_id')
        client_id = result.get('client_id')
        lang = await _get_lang(client_id)

        # Закрываем заказ в БД

        if not result:
            txt = "Error closing the ticket." if lang == "en" else "Ошибка при закрытии Тикета."
            await message.answer(txt)
            return

        # Удаляем из кэша
        await topic_cache.remove_by_thread(thread_id)

        # Получаем полную информацию о заказе
        order = await db.get_orders_by_id(order_id)
        if not order:
            await message.answer("❌ Ошибка получения информации о тикете")
            return

        # ====== ТА ЖЕ ЛОГИКА, ЧТО И В /stop_chat ======

        # Устанавливаем состояние оценки для клиента
        other_storage_key = StorageKey(
            bot_id=message.bot.id,
            user_id=client_id,
            chat_id=client_id
        )
        other_state = FSMContext(storage=state.storage, key=other_storage_key)
        await other_state.update_data(order_id=order_id)
        await other_state.set_state(StarsOrder.stars_order)

        # Запускаем таймер сброса состояния
        asyncio.create_task(reset_state_after_timeout(other_state, client_id, message.bot))

        logger.info(Fore.BLUE + f"Тикет №{order_id} успешно закрыт." + Style.RESET_ALL)

        # Уведомляем саппорта
        await bot.send_message(
            chat_id=support_id,
            text=f"🚪 Тикет №{order_id} успешно закрыт!\nПользователь: @{order.client_name}\nID: {order.client_id}"
        )

        # Уведомляем клиента и запрашиваем оценку
        try:
            if lang == "en":
                txt_closed = f"🚪 Ticket #{order_id} closed. Thank you for contacting us.\nIf you have any questions, we are always in touch. Have a great game!"
                txt_rate = "Please rate the support work:\nUse the buttons below or send a number from 1 to 10."
            else:
                txt_closed = f"🚪 Тикет №{order_id} закрыт! 🎮 Спасибо за обращение.\nЕсли у вас появятся вопросы, мы всегда на связи. Удачной игры!"
                txt_rate = "Пожалуйста, оцените работу поддержки:\nС помощью кнопок ниже, либо можете написать свою оценку от 1 до 10."

            await bot.send_message(chat_id=client_id, text=txt_closed)

            # Импортируем клавиатуру
            from handlers.User.keyboard.replykeqyboard import user_stars_kb
            kb = user_stars_kb()

            await bot.send_message(chat_id=client_id, text=txt_rate, reply_markup=kb)

        except TelegramForbiddenError as e:
            logger.error(Fore.RED + f"Пользователь заблокировал бота: {e}" + Style.RESET_ALL)

        # Обновляем сообщение в группе
        message_info = await db.get_all_message(order_id)
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
                f"⏳ <b>Создана:</b> {order.created_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"⏳ <b>Принята:</b> {order.accept_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"⏳ <b>Закрыта:</b> {order.completed_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"<a href=\"https://t.me/GBPSupport_bot\">Перейти в бота</a>"
            )
            await bot.edit_message_text(
                message_id=int(message_info.support_message_id),
                chat_id=GROUP_CHAT_ID,
                text=message_edit_text,
                parse_mode="HTML"
            )
            await unpin_specific_message(bot, GROUP_CHAT_ID, int(message_info.support_message_id))


        await message.answer("Теперь необходимо заполнить форму обращения\n"
                             "Введите название игры:")
        await state.update_data(
            order_id=order.id,
            thread_id=message.message_thread_id,  # ← Сохраняем thread_id
            chat_id=message.chat.id  # ← И chat_id тоже
        )
        await state.set_state(FormOrderShema.name_game)
    except Exception as e:
        logger.error(f"Ошибка при закрытии чата: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при закрытии чата")


@chat_router.message(F.message_thread_id != None)
async def handle_topic_message(message: Message, bot: Bot):
    """
    Обрабатывает сообщения в топиках и пересылает клиентам
    Добавлены: таймер и бэкап-чат
    """
    if message.from_user.is_bot:
        return

    if message.text and message.text.startswith('/'):
        return
    thread_id = message.message_thread_id
    logger.info(f"📨 Сообщение в топике {thread_id} от @{message.from_user.username}")

    # 1. Проверяем кэш Redis
    client_id = await topic_cache.get_client_by_thread(thread_id)

    if not client_id:
        # 2. Ищем в БД
        chat_info = await db.get_chat_by_thread_id(thread_id)
        if not chat_info:
            logger.warning(f"Топик {thread_id} не найден")
            return

        client_id = chat_info['client_id']
        ticket_id = chat_info.get('order_id')

        # 3. Сохраняем в кэш
        await topic_cache.set_mapping(thread_id, client_id)
    else:
        # Получаем ticket_id из БД
        chat_info = await db.get_chat_by_thread_id(thread_id)
        ticket_id = chat_info.get('order_id') if chat_info else None
    if chat_info.get('order_id') is None:
        chat_info = await db.get_chat_by_thread_id(thread_id)

    order_id = chat_info['order_id']  # если order_id есть
    # 4. Отправляем в бэкап-чат (сообщение от саппорта)
    await send_support_message_to_backup(message, bot, thread_id, order_id, client_id, ticket_id)

    # 5. Пересылаем клиенту
    try:
        await bot.copy_message(
            chat_id=client_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
        logger.info(f"✅ Сообщение из топика {thread_id} -> клиенту {client_id}")

        # 6. Обработка таймера (если есть ticket_id)
        if ticket_id:
            await handle_auto_close_timer(ticket_id, client_id, bot)

    except Exception as e:
        logger.error(f"❌ Ошибка отправки клиенту {client_id}: {e}")

        error_msg = str(e).lower()
        if "blocked" in error_msg or "forbidden" in error_msg:
            logger.warning(f"⚠️ Клиент {client_id} заблокировал бота")
            await topic_cache.remove_by_thread(thread_id)

            # Уведомляем в топик
            try:
                await bot.send_message(
                    chat_id=message.chat.id,
                    message_thread_id=thread_id,
                    text="⚠️ Клиент заблокировал бота. Сообщение не доставлено."
                )
            except:
                pass


async def send_support_message_to_backup(message: Message, bot: Bot, thread_id: int, order_id: int, client_id: int,
                                         ticket_id: int = None):
    """
    Отправляет сообщение от саппорта в бэкап-чат
    """
    try:
        BACKUP_CHAT_ID = os.getenv('GP_MG')
        BACKUP_THREAD_ID = os.getenv('CHAT_ID_MESSAGE')

        if not BACKUP_CHAT_ID:
            return

        user = message.from_user
        sender_name = user.full_name
        username = f"(@{user.username})" if user.username else ""

        # Создаем информационный текст
        info_text = f"📨 Тикет {order_id}\n👤 Отправитель: {sender_name}"
        if username:
            info_text += f" {username}"

        # Для текстовых сообщений добавляем текст
        if message.text:
            info_text += f"\n\n📝 Сообщение:\n{message.text[:500]}"
            # Отправляем только текст
            await bot.send_message(
                chat_id=int(BACKUP_CHAT_ID),
                message_thread_id=int(BACKUP_THREAD_ID) if BACKUP_THREAD_ID else None,
                text=info_text
            )
        else:
            # Для медиа - пересылаем копию сообщения БЕЗ подписи
            await bot.copy_message(
                chat_id=int(BACKUP_CHAT_ID),
                message_thread_id=int(BACKUP_THREAD_ID) if BACKUP_THREAD_ID else None,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            # Отдельно отправляем информационный текст
            await bot.send_message(
                chat_id=int(BACKUP_CHAT_ID),
                message_thread_id=int(BACKUP_THREAD_ID) if BACKUP_THREAD_ID else None,
                text=info_text
            )

    except Exception as e:
        logger.error(f"Ошибка при отправке в бэкап-чат: {e}")


def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown V2"""
    if not text:
        return ""

    # Список символов, которые нужно экранировать в MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'

    # Экранируем каждый символ
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')

    return text


def escape_html(text: str) -> str:
    """Экранирует HTML-символы"""
    if not text:
        return ""
    return html_escape(text)

# При создании темы тоже добавляем в кэш
async def add_to_cache_after_topic_creation(thread_id: int, user_id: int):
    """Добавить в кэш после создания темы"""
    await topic_cache.set_mapping(thread_id, user_id)
    print(f"🎯 Тема {thread_id} добавлена в кэш для пользователя {user_id}")
