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
from aiogram.enums import ParseMode

from logger import logger
from config import *
from handlers.User.Start import start_router
import handlers.User.Language
from handlers.Admin.Start import admin_router
from handlers.Worker.Start import worker_router
from handlers.Media.Start import media_router
from handlers.Chat import chat_router
from commands import set_commands_admin

from database.db import DataBase, redis_client
from database.models import *
from Utils import filter_tickets_for_statistics

db = DataBase()
scheduler = AsyncIOScheduler(timezone=str(pytz.timezone('Europe/Moscow')))

load_dotenv()


async def notify_unreplied_orders(bot: Bot):
    try:
        orders = await db.get_active_orders()
        now_ms = int(datetime.now(tz=pytz.timezone('Europe/Moscow')).timestamp()) * 1000
        for order in orders:
            messages = order.get('messages', [])
            if not messages:
                continue
            last_support_message_time = None
            last_user_message_time = None
            for m in messages:
                st = m.get('support_created_at')
                ut = m.get('created_at')
                if st:
                    try:
                        last_support_message_time = parse(st).timestamp() * 1000
                    except Exception:
                        pass
                if ut:
                    try:
                        last_user_message_time = parse(ut).timestamp() * 1000
                    except Exception:
                        pass
            if last_support_message_time and last_user_message_time:
                delta = last_support_message_time - last_user_message_time
                if delta > 5 * 60 * 1000:
                    support_id = order.get('support_id')
                    if support_id:
                        try:
                            await bot.send_message(chat_id=support_id, text="Напоминание: пользователь не ответил на тикет более 5 минут.")
                        except Exception:
                            pass
    except Exception as e:
        logger.error(Fore.RED + f'Ошибка в notify_unreplied_orders: {e}' + Style.RESET_ALL)


async def startup_notify(bot: Bot):
    try:
        text = "Бот запущен."
        await bot.send_message(chat_id=ADMIN_PRIVAT, text=text)
    except Exception as e:
        logger.error(Fore.RED + f'Ошибка отправки старта: {e}' + Style.RESET_ALL)


async def shutdown_notify(bot: Bot):
    try:
        text = "Бот остановлен."
        await bot.send_message(chat_id=ADMIN_PRIVAT, text=text)
    except Exception as e:
        logger.error(Fore.RED + f'Ошибка отправки остановки: {e}' + Style.RESET_ALL)


async def clear_closed_orders_messages(bot: Bot):
    try:
        logger.debug(Fore.GREEN + 'Запущен планировщик очистки сообщений закрытых тикетов' + Style.RESET_ALL)
        orders = await db.get_closed_orders_with_messages()
        for order in orders:
            try:
                for message in order.get('messages', []):
                    try:
                        if message.get('client_message_id') and message.get('chat_id'):
                            try:
                                await bot.delete_message(
                                    chat_id=int(message['chat_id']),
                                    message_id=int(message['client_message_id'])
                                )
                            except Exception:
                                pass
                        if message.get('support_message_id') and message.get('support_id'):
                            try:
                                await bot.delete_message(
                                    chat_id=int(message['support_id']),
                                    message_id=int(message['support_message_id'])
                                )
                            except Exception:
                                pass
                    except Exception:
                        pass
                await db.clear_order_messages(order_id=order['id'])
            except Exception:
                pass
    except Exception as e:
        logger.error(Fore.RED + f'Ошибка очистки сообщений: {e}' + Style.RESET_ALL)


async def main():
    bot_token = getenv("BOT_TOKEN") or BOT_TOKEN
    bot = Bot(bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_routers(start_router, admin_router, worker_router, media_router, chat_router)

    try:
        scheduler.add_job(startup_notify, trigger='date', run_date=datetime.now(), args=(bot,))
    except Exception:
        pass

    try:
        scheduler.add_job(clear_closed_orders_messages, 'interval', minutes=10, args=(bot,))
    except Exception:
        pass

    try:
        scheduler.add_job(notify_unreplied_orders, 'interval', minutes=5, args=(bot,))
    except Exception:
        pass

    try:
        scheduler.start()
    except Exception as e:
        logger.error(Fore.RED + f'Ошибка запуска планировщика: {e}' + Style.RESET_ALL)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except TelegramForbiddenError:
        pass
    except TelegramAPIError as e:
        logger.error(Fore.RED + f'Ошибка API Telegram: {e}' + Style.RESET_ALL)
    except Exception as e:
        logger.error(Fore.RED + f'Критическая ошибка: {e}' + Style.RESET_ALL)
    finally:
        try:
            await shutdown_notify(bot)
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass
        try:
            await redis_client.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
