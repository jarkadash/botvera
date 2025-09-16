import asyncio
from datetime import datetime
import pytz
import redis.asyncio as redis
import html
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from os import getenv
from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from colorama import Fore, Style
from dateutil.parser import parse
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from config import GROUP_CHAT_ID
from logger import logger
from database.db import DataBase
from handlers.User.Start import start_router
import handlers.User.Language
from handlers.Admin.Start import admin_router
from handlers.Worker.Start import worker_router
from handlers.Chat import chat_router
from handlers.Media.Start import media_router
from commands import set_commands

db = DataBase()
load_dotenv()
redis = redis.Redis(
    host=getenv('REDIS_HOST'),
    port=getenv('REDIS_PORT'),
    password=getenv('REDIS_PASSWORD'),
    username=getenv('REDIS_USER'),
    decode_responses=True,
)
token = getenv('TOKEN')
storage = RedisStorage(redis)
bot = Bot(token=token, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher(storage=storage)

async def start_up(bot: Bot):
    await bot.send_message(chat_id=776952103, text='Бот запущен')

async def stop_up(bot: Bot):
    await bot.send_message(chat_id=776952103, text='Бот остановлен')

dp.startup.register(start_up)
dp.shutdown.register(stop_up)
dp.include_routers(start_router, admin_router, worker_router, media_router, chat_router)

async def start():
    try:
        await start_scheduler(bot)
        await bot.delete_webhook(drop_pending_updates=True)
        await db.create_db()
        await set_commands(bot)
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()

async def unpin_specific_message(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.unpin_chat_message(
            chat_id=chat_id,
            message_id=message_id
        )
        print(f"Сообщение {message_id} откреплено!")
    except TelegramAPIError as e:
        print(f"Ошибка: {e}")

async def start_check(bot: Bot):
    try:
        result = await db.close_old_orders()
        if not result:
            logger.info(Fore.BLUE + 'Закрытых заказов нет' + Style.RESET_ALL)
            return
        for order in result:
            try:
                order_id = order.get('order_id', 'unknown')
                logger.info(Fore.BLUE + f'Обработка заказа {order_id}' + Style.RESET_ALL)
                client_id = order.get('client_id')
                if not client_id:
                    logger.warning(Fore.YELLOW + f'Пропуск заказа {order_id}: отсутствует client_id' + Style.RESET_ALL)
                    continue
                for message in order.get('messages', []):
                    try:
                        logger.debug(Fore.GREEN + f'Обработка сообщения {order}' + Style.RESET_ALL)
                        if message.get('client_message_id') and message.get('chat_id'):
                            try:
                                await bot.delete_message(
                                    chat_id=int(message['chat_id']),
                                    message_id=int(message['client_message_id'])
                                )
                                logger.debug(Fore.GREEN + f'Удалено сообщение {message["client_message_id"]}' + Style.RESET_ALL)
                            except Exception as delete_error:
                                logger.error(Fore.RED + f'Ошибка удаления сообщения: {delete_error}' + Style.RESET_ALL)
                        if message.get('support_message_id'):
                            try:
                                def safe_strftime(dt, default="N/A", fmt='%d-%m-%Y %H:%M'):
                                    if not dt:
                                        return default
                                    try:
                                        if isinstance(dt, str):
                                            try:
                                                dt = parse(dt)
                                            except (ValueError, TypeError):
                                                return default
                                        if hasattr(dt, 'strftime'):
                                            return dt.strftime(fmt)
                                        return default
                                    except Exception:
                                        return default
                                client_name = html.escape(order.get('client_name', 'N/A'))
                                telegram_link = f'<a href="https://t.me/{client_name}">🔗 1.Телеграм</a>' if client_name != 'N/A' else ''
                                await bot.edit_message_text(
                                    chat_id=GROUP_CHAT_ID,
                                    message_id=int(message['support_message_id']),
                                    text=(
                                        f"✅ Тикет закрыт!\n\n"
                                        f"📩 <b>Тикет</b> №{order_id}\n"
                                        f"👤 <b>Пользователь:</b> @{client_name}\n"
                                        f"🆔 <b>ID:</b> {client_id}\n"
                                        f"{telegram_link}\n"
                                        f"🛠 <b>Услуга:</b> {html.escape(order.get('service_name', 'N/A'))}\n"
                                        f"ℹ️ <b>Статус:</b> Closed\n"
                                        f"⏳ <b>Создана:</b> {safe_strftime(order.get('created_at'))}\n\n"
                                        f"⏳ <b>Закрыта:</b> {safe_strftime(order.get('completed_at'))}\n\n"
                                        f"📝 <b>Описание:</b> Закрыта автоматически системой (прошло 24 часа)\n"
                                    ),
                                    parse_mode="HTML"
                                )
                                await unpin_specific_message(bot, GROUP_CHAT_ID, int(message['support_message_id']))
                                logger.debug(Fore.GREEN + f'Откреплено сообщение {message["support_message_id"]}' + Style.RESET_ALL)
                            except Exception as edit_error:
                                logger.error(Fore.RED + f'Ошибка редактирования сообщения: {edit_error}' + Style.RESET_ALL)
                    except Exception as msg_error:
                        logger.error(Fore.RED + f'Ошибка обработки сообщения: {msg_error}' + Style.RESET_ALL)
                try:
                    await bot.send_message(
                        chat_id=int(client_id),
                        text=(
                            f"   🏷 <b>Тикет #{order_id} закрыт</b>\n"
                            f"⏳ Причина: автоматическое закрытие\n\n"
                            f"Если проблема еще актуальна, пожалуйста создайте тикет повторно!\n\n"
                            f"С уважением администрация 👨‍💻"
                            f"🤖 Автоматическое уведомление"
                        ),
                        parse_mode="HTML"
                    )
                    logger.debug(Fore.GREEN + f'Отправлено уведомление клиенту {client_id}' + Style.RESET_ALL)
                except TelegramForbiddenError as notify_error:
                    logger.error(Fore.RED + f'Ошибка отправки уведомления: {notify_error}' + Style.RESET_ALL)
            except Exception as order_error:
                logger.error(Fore.RED + f'Критическая ошибка обработки заказа: {order_error}' + Style.RESET_ALL)
                continue
    except Exception as main_error:
        error_msg = f'Ошибка в start_check: {str(main_error)}'
        logger.critical(Fore.MAGENTA + error_msg + Style.RESET_ALL)
        await bot.send_message(
            chat_id=434791099,
            text=f"❌ Критическая ошибка в автоматическом закрытии заказов: {error_msg}"
        )

async def start_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Europe/Moscow'))
    scheduler.add_job(
        start_check,
        'cron',
        hour=0,
        minute=20,
        args=(bot,)
    )
    scheduler.start()
    logger.info(Fore.GREEN +"Планировщик запущен! Проверка будет каждые 00:20 минут" + Style.RESET_ALL)

if __name__ == '__main__':
    asyncio.run(start())
