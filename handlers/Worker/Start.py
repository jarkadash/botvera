from aiogram import Bot, Router, F
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from Utils import get_calculated_period, filter_tickets_for_statistics
from sqlalchemy.testing.config import any_async
import html
from database.db import DataBase, redis_client
import asyncio
from colorama import Fore, Style
from logger import logger
from core.dictionary import *
from handlers.User.keyboard.replykeqyboard import *
from config import *
from aiogram.filters import Filter
from sqlalchemy import select
from database.models import Roles, Users
import pandas as pd

db = DataBase()
active_timers = {}
worker_router = Router()

class IsSupportOrAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        async with db.Session() as session:
            result = await session.execute(
                select(Roles.role_name)
                .join(Users, Users.role_id == Roles.id)
                .where(Users.user_id == message.from_user.id)
            )
            role_name = result.scalar_one_or_none()
            return role_name in ["admin", "support"]

class TicketState(StatesGroup):
    waiting_for_response = State()

@worker_router.callback_query(F.data.startswith("accept_order:"))
async def accept_order(call: CallbackQuery, state: FSMContext, bot: Bot):
    logger.info(Fore.GREEN + f"Пользователь {call.from_user.username} id: {call.from_user.id} пытается принять "
                             f"тикет {call.data.split(':')[1]}" + Style.RESET_ALL)
    order_id = int(call.data.split(":")[1])
    try:
        accept = await db.accept_orders(order_id, int(call.from_user.id))
        if accept is False or accept == 'Пользователь не имеет роли!':
            await call.answer("У вас нет доступа к этому Тикету", show_alert=True)
        elif accept == 'Active-Ticket':
            await call.answer("Вы уже работаете с другим тикетом!", show_alert=True)
        elif accept == 'Not-New':
            await call.answer("Тикет уже был принят!", show_alert=True)
        else:
            message_accept = (
                f"✅ Тикет принят!\n\n\n"
                f"📩 <b>Тикет</b> №{order_id}\n"
                f"👤 <b>Пользователь:</b> @{html.escape(accept.client_name)}\n"
                f"🆔 <b>ID:</b> {accept.client_id}\n"
                f"<a href=\"https://t.me/{html.escape(accept.client_name)}\">🔗 1.Телеграм</a>\n"
                f"<a href=\"tg://user?id={accept.client_id}\">🔗 2.Телеграм</a>\n"
                f"🛠 <b>Услуга:</b> {html.escape(accept.service_name)}\n"
                f"🆔 <b>Support_id:</b> {accept.support_id}\n"
                f"👨‍💻 <b>Support_name:</b> @{html.escape(accept.support_name)}\n"
                f"ℹ️ <b>Статус:</b> {html.escape(accept.status)}\n"
                f"⏳ <b>Создана:</b> {accept.created_at.strftime('%d-%m-%Y %H:%M')}\n\n"
                f"⏳ <b>Принята:</b> {accept.accept_at.strftime('%d-%m-%Y %H:%M')}\n\n"
                f"<a href=\"https://t.me/GBPSupport_bot\">Перейти в бота</a>"
            )
            try:
                await bot.send_message(
                    chat_id=int(accept.client_id),
                    text=(
                        f"🎉 Ваш тикет №{order_id} успешно принят!\n\n"
                        f"Теперь вы можете общаться с менеджером в этом чате. "
                        f"Пожалуйста, соблюдайте уважительный тон в общении — это поможет нам решить ваш вопрос быстрее и эффективнее.\n\n"
                        f"Команда /stop_chat — завершить диалог"
                    )
                )
                task = asyncio.create_task(auto_close_ticket_if_silent(order_id, accept.client_id, bot))
                active_timers[order_id] = task
                if accept.service_name == "Техническая помощь / Technical Support":
                    await bot.send_message(
                        chat_id=int(accept.client_id),
                        text=(
                            "Здравствуйте!\n"
                            "Для работы технической поддержки требуется следующая информация:\n\n"
                            "1. **Скриншот, подтверждающий покупку в личном кабинете**\n"
                            "   *(ключ должно быть видно на скриншоте)*\n\n"
                            "2. Нажмите `Win + R`\n"
                            "   Введите:\n"
                            "   ```"
                            "   msinfo32\n"
                            "   ```"
                            "   Нажмите Enter.\n"
                            "   *Скриншот всего окна пришлите в чат-бота.*\n\n"
                            "3. Нажмите `Win + R`\n"
                            "   Введите:\n"
                            "   ```"
                            "   winver\n"
                            "   ```"
                            "   Нажмите Enter.\n"
                            "   *Скриншот окна пришлите в чат-бота.*\n\n"
                            "4. **Опишите подробно проблему.**\n"
                            "   *При наличии ошибок — пришлите скриншот ошибки.*"
                        ), parse_mode="Markdown"
                    )
                elif accept.service_name == "HWID RESET":
                    await bot.send_message(
                        chat_id=int(accept.client_id),
                        text=(
                            f"Здравствуйте!\n"
                            f"Для сброса HWID привязки требуется следующая информация:\n\n"
                            f"1. <u><b>Скриншот</b></u>, подтверждающий покупку в личном кабинете <u>(ключ должно быть видно на скриншоте)</u>\n\n"
                            f"2. Ключ продукта <u>в текстовом формате</u>\n\n"
                            f"3. Используете ли сторонний спуфер(не встроенный в чит)?"
                        ), parse_mode="HTML"
                    )

                await redis_client.set(f"ticket:{accept.support_id}", order_id)

                await bot.send_message(
                    chat_id=call.from_user.id,
                    text=f"Тикет №{order_id} принят!\nЧат с пользователем открыт!",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
                        resize_keyboard=True,
                        one_time_keyboard=False
                    )
                )
            except TelegramForbiddenError as e:
                logger.error(Fore.RED + f"Ошибка при отправке сообщения клиенту: {e}" + Style.RESET_ALL)
                await bot.send_message(
                    chat_id=call.from_user.id,
                    text=(f"Ошибка принятия тикета! {order_id}\n"
                          f"Пользователь @{accept.client_name} заблокировал бота\n"
                          )
                )
                message_accept = (
                    f"✅ Тикет закрыт!\n\n\n"
                    f"📩 <b>Тикет</b> №{order_id}\n"
                    f"👤 <b>Пользователь:</b> @{html.escape(accept.client_name)}\n"
                    f"🆔 <b>ID:</b> {accept.client_id}\n"
                    f"<a href=\"https://t.me/{html.escape(accept.client_name)}\">🔗 1.Телеграм</a>\n"
                    f"<a href=\"tg://user?id={accept.client_id}\">🔗 2.Телеграм</a>\n"
                    f"🛠 <b>Услуга:</b> {html.escape(accept.service_name)}\n"
                    f"🆔 <b>Support_id:</b> {accept.support_id}\n"
                    f"👨‍💻 <b>Support_name:</b> @{html.escape(accept.support_name)}\n"
                    f"ℹ️ <b>Статус:</b> {html.escape(accept.status)}\n"
                    f"⏳ <b>Создана:</b> {accept.created_at.strftime('%d-%m-%Y %H:%M')}\n\n"
                    f"<b>Причина:</b> Пользователь заблокировал бота\n"
                )
                await db.get_auto_close_order(int(order_id), reason="Авто-закрытие (Заблокировал бота)")
                await redis_client.delete(f"ticket:{accept.client_id}")
                await redis_client.delete(f'chat:{accept.client_id}')
                await redis_client.delete(f"role:{accept.client_id}")
                await redis_client.delete(f"chat:{call.from_user.id}")
                await redis_client.delete(f"ticket:{call.from_user.id}")
                await redis_client.delete(f"role:{call.from_user.id}")
                await redis_client.delete(f"messages:{order_id}")
                message_info = await db.get_all_message(int(order_id))
                if message_info:
                    logger.info(Fore.BLUE + f"Получена информация о Тикете №{order_id}." + Style.RESET_ALL)
                    messages_id = message_info.support_message_id
                    await bot.edit_message_text(
                        chat_id=GROUP_CHAT_ID,
                        message_id=int(message_info.support_message_id),
                        text=message_accept,
                        parse_mode="HTML"
                    )
                    await unpin_specific_message(bot, GROUP_CHAT_ID, int(message_info.support_message_id))
            if 'message_accept' in locals():
                msg_info = await db.get_all_message(int(order_id))
                if msg_info:
                    await bot.edit_message_text(
                        chat_id=GROUP_CHAT_ID,
                        message_id=int(msg_info.support_message_id),
                        text=message_accept,
                        parse_mode="HTML"
                    )
    except Exception as e:
        logger.error(f"Ошибка при принятии Тикета: {e}")

@worker_router.message(F.contact)
async def handle_support_contact(message: Message, bot: Bot):
    ticket = await redis_client.get(f"ticket:{message.from_user.id}")
    if isinstance(ticket, bytes):
        ticket = ticket.decode()
    if ticket:
        order = await db.get_orders_by_id(int(ticket))
        if order and order.support_id == message.from_user.id:
            username = message.from_user.username
            if username:
                await bot.send_message(
                    chat_id=order.client_id,
                    text=f"👨‍💻 Ваш тикет №{order.id} принят!\nС вами работает @{username}"
                )
            else:
                await bot.send_message(
                    chat_id=order.client_id,
                    text=f"👨‍💻 Ваш тикет №{order.id} принят!\nС вами работает специалист",
                )
    await message.answer("Контакт отправлен пользователю ✅")

@worker_router.callback_query(F.data.startswith("cancel_order:"))
async def cancel_order(call: CallbackQuery, state: FSMContext):
    logger.info(Fore.RED + f"Пользователь {call.from_user.username} id: {call.from_user.id} пытается отменить "
                           f"Тикет {call.data.split(':')[1]}" + Style.RESET_ALL)
    order_id = int(call.data.split(":")[1])
    await state.update_data(order_id=order_id)
    try:
        accept = await db.check_role_for_service(int(call.from_user.id), order_id)
        if accept is False or accept == 'Пользователь не имеет роли!':
            await call.answer("У вас нет доступа к этому Тикету", show_alert=True)
        else:
            await call.message.edit_text(f"Введите причину отмены Тикета!")
            await state.update_data(message_id=call.message.message_id)
            await state.set_state(TicketState.waiting_for_response)

    except Exception as e:
        logger.error(Fore.RED + f"Ошибка при отмене Тикета: {e}" + Style.RESET_ALL)

async def unpin_specific_message(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.unpin_chat_message(
            chat_id=chat_id,
            message_id=message_id
        )
        print(f"Сообщение {message_id} откреплено!")
    except TelegramAPIError as e:
        print(f"Ошибка: {e}")

@worker_router.message(TicketState.waiting_for_response)
async def handle_ticket_response(message: Message, state: FSMContext, bot: Bot):
    logger.info(Fore.RED + f"Пользователь {message.from_user.username} id: {message.from_user.id} "
                           f"отменил тикет {message.text}" + Style.RESET_ALL)

    reg_data = await state.get_data()
    order_id = reg_data.get('order_id')
    description = message.text.strip()
    message_id = reg_data.get('message_id')
    if len(description) > 100:
        await message.answer("⛔️ Текст отмены должен быть больше 100 символов!")
        return
    try:
        cancel = await db.cancel_order(order_id, int(message.from_user.id), description)
        if cancel is False:
            await message.answer("❌ Произошла ошибка при отмене тикета. Попробуйте еще раз.")
        else:
            message_accept = (
                f"⛔️ Тикет отменен!\n\n\n"
                f"📩 <b>Тикет</b> №{order_id}\n"
                f"👤 <b>Пользователь:</b> @{cancel.client_name}\n"
                f"🆔 <b>ID:</b> {cancel.client_id}\n"
                f"<a href=\"https://t.me/{cancel.client_name}\">🔗 1.Телеграм</a>\n"
                f"<a href=\"tg://user?id={cancel.client_id}\">🔗 2.Телеграм</a>\n"
                f"🛠 <b>Услуга:</b> {cancel.service_name}\n"
                f"🆔 <b>Support_id:</b> {cancel.support_id}\n"
                f"👨‍💻 <b>Support_name:</b> @{cancel.support_name}\n"
                f"ℹ️ <b>Статус:</b> {cancel.status}\n"
                f"⏳ <b>Создана:</b> {cancel.created_at.strftime('%d-%m-%Y %H:%M')}\n\n"
                f"⏳ <b>Отменена:</b> {cancel.completed_at.strftime('%d-%m-%Y %H:%M')}\n\n"
                f"<b>Причина отмены:</b> {description}\n"
            )

            await message.bot.edit_message_text(chat_id=GROUP_CHAT_ID, text=message_accept, parse_mode="HTML",  message_id=message_id)
            await unpin_specific_message(message.bot, GROUP_CHAT_ID, message_id)
            await bot.send_message(chat_id=message.from_user.id, text=f"✅ Тикет №{order_id} успешно отменен. Причина: {description}")
            try:
                await bot.send_message(chat_id=int(cancel.client_id), text=f"⛔️ Ваш тикет №{order_id} отменен!\n Причина: {description}")
            except TelegramForbiddenError as e:
                logger.error(Fore.RED + f"Пользователь заблокировал бота: {e}" + Style.RESET_ALL)
            await state.clear()

    except Exception as e:
        logger.error(Fore.RED + f"Ошибка при отмене тикет: {e}" + Style.RESET_ALL)
        await message.answer("❌ Произошла ошибка при отмене тикета. Попробуйте еще раз.")
        await state.clear()

@worker_router.message(Command(commands='statistics'), IsSupportOrAdmin())
async def handle_statistics(message: Message, state: FSMContext):
    logger.info(
        Fore.BLUE + f"Пользователь {message.from_user.username} id: {message.from_user.id} просит статистику" + Style.RESET_ALL
    )

    try:
        start_date, end_date = get_calculated_period()
        logger.info(f"Период для статистики: {start_date} – {end_date}")

        async with db.Session() as session:
            included, excluded = await filter_tickets_for_statistics(
                session, message.from_user.id, start_date, end_date
            )

            def ticket_to_row(ticket, excluded_reason=None):
                return {
                    "id": ticket.id,
                    "client_id": ticket.client_id,
                    "client_name": ticket.client_name,
                    "support_id": ticket.support_id,
                    "support_name": ticket.support_name,
                    "service_id": ticket.service_id,
                    "service_name": ticket.service_name,
                    "created_at": ticket.created_at,
                    "accept_at": ticket.accept_at,
                    "completed_at": ticket.completed_at,
                    "status": ticket.status,
                    "stars": ticket.stars,
                    "description": ticket.description,
                    "excluded_reason": excluded_reason
                }

            all_rows = []
            for ticket in included:
                all_rows.append(ticket_to_row(ticket))
            for ticket, reason in excluded:
                all_rows.append(ticket_to_row(ticket, excluded_reason=reason))

            df = pd.DataFrame(all_rows)

            filtered_df = df[
                (df["excluded_reason"].isnull()) |
                (df["excluded_reason"].astype(str).str.strip() == "")
            ]

            total = len(filtered_df)

            stars_col = filtered_df["stars"].dropna()
            avg_rating = stars_col.mean() if not stars_col.empty else 0

            time_deltas = filtered_df.dropna(subset=["accept_at", "completed_at"])
            time_deltas["duration_sec"] = (time_deltas["completed_at"] - time_deltas["accept_at"]).dt.total_seconds()
            avg_response_time = int(time_deltas["duration_sec"].mean()) if not time_deltas.empty else 0

            rates = await db.get_user_rates(session, message.from_user.id)

            counts = filtered_df["service_name"].value_counts().to_dict()

            salary = 0
            for service, count in counts.items():
                rate = rates.get(service, 0)
                if service == "Техническая помощь / Technical Support" and message.from_user.id == 434791099 and rate < 80:
                    rate = 80
                salary += count * rate

            bonus = rates.get("Бонус", 0)
            if bonus and total >= 50:
                salary += (total // 50) * bonus

            statistics = await db.statistics_user_by_id(message.from_user.id, start_date, end_date)

            if not statistics or "error" in statistics:
                await message.answer("Ошибка при получении статистики или статистика отсутствует.")
                return

            minutes, seconds = divmod(avg_response_time, 60)
            stars = f"{avg_rating:.2f}" if avg_rating > 0 else 'статистика будет доступна после 10 тикетов!'
            salary_line = f"💰 Предполагаемая ЗП: {salary:,} руб.".replace(",", " ") if salary else ""

            message_text = (
                f"📊 Статистика пользователя @{message.from_user.username}\n\n"
                f"🟢 Всего тикетов: {statistics.get('all_orders', 0)}\n"
                f"—————————\n"
                f"📆 За период {start_date.strftime('%d.%m.%y')} – {end_date.strftime('%d.%m.%y')}\n"
                f"✅ Тикетов: {total}\n"
                f"⭐️ Рейтинг: {stars}\n"
                f"⏳ Время обработки: {minutes:02}.{seconds:02} минут\n"
                f"{salary_line}"
            )

            await message.answer(message_text)
            logger.info(Fore.BLUE + f"Статистика отправлена:\n{message_text}" + Style.RESET_ALL)

    except Exception as e:
        logger.error(f"[ERROR] Ошибка при расчете статистики: {e}", exc_info=True)
        await message.answer("Произошла внутренняя ошибка при расчёте статистики.")

def format_ticket_closed_message(order, reason: str) -> str:
    import html
    return (
        f"❗️ Тикет закрыт автоматически!\n"
        f"<b>Причина:</b> {reason}\n\n"
        f"📩 <b>Тикет</b> №{order.id}\n"
        f"👤 <b>Пользователь:</b> @{order.client_name}\n"
        f"🆔 <b>ID:</b> {order.client_id}\n"
        f"<a href=\"https://t.me/{html.escape(order.client_name)}\">🔗 1.Телеграм</a>\n"
        f"<a href=\"tg://user?id={order.client_id}\">🔗 2.Телеграм</a>\n"
        f"🛠 <b>Услуга:</b> {order.service_name}\n"
        f"🆔 <b>Support_id:</b> {order.support_id}\n"
        f"👨‍💻 <b>Support_name:</b> @{order.support_name}\n"
        f"ℹ️ <b>Статус:</b> {order.status}\n"
        f"⏳ <b>Создана:</b> {order.created_at.strftime('%d-%m-%Y %H:%M')}\n\n"
        f"⏳ <b>Принята:</b> {order.accept_at.strftime('%d-%m-%Y %H:%M')}\n\n"
        f"⏳ <b>Закрыта:</b> {order.completed_at.strftime('%d-%m-%Y %H:%M')}\n\n"
        f"<a href=\"https://t.me/GBPSupport_bot\">Перейти в бота</a>"
    )

async def close_ticket(order_id: int, client_id: int, bot: Bot, reason: str):
    try:
        await db.get_auto_close_order(order_id, reason=reason)

        order_info = await db.get_orders_by_id(order_id)
        if not order_info:
            logger.warning(f"[TIMER] Не найден тикет №{order_id} для уведомлений")
            return

        await redis_client.delete(f"ticket:{order_info.client_id}")
        await redis_client.delete(f'chat:{order_info.client_id}')
        await redis_client.delete(f"role:{order_info.client_id}")
        await redis_client.delete(f"messages:{order_id}")
        await redis_client.delete(f"ticket:{order_info.support_id}")
        await redis_client.delete(f'chat:{order_info.support_id}')
        await redis_client.delete(f"role:{order_info.support_id}")

        logger.info(f"[TIMER] Тикет №{order_id} закрыт автоматически: {reason}")

        message_info = await db.get_all_message(order_id)
        if message_info:
            message_edit_text = format_ticket_closed_message(order_info, reason)
            await bot.edit_message_text(
                message_id=int(message_info.support_message_id),
                chat_id=GROUP_CHAT_ID,
                text=message_edit_text,
                parse_mode="HTML"
            )
            await unpin_specific_message(bot, GROUP_CHAT_ID, int(message_info.support_message_id))

        try:
            await bot.send_message(
                chat_id=order_info.support_id,
                text=f"🚪 Тикет №{order_id} закрыт автоматически. {reason}"
            )
        except TelegramForbiddenError:
            logger.warning(f"[TIMER] Support заблокировал бота — уведомление не отправлено")

        if reason == "Авто-закрытие (Клиент не ответил)":
            try:
                await bot.send_message(
                    chat_id=client_id,
                    text=f"⛔️ Тикет №{order_id} был закрыт автоматически из-за отсутствия ответа. Вы можете создать новый, если помощь всё ещё нужна."
                )
            except TelegramForbiddenError:
                logger.warning(f"[TIMER] Клиент заблокировал бота — уведомление не отправлено")

    except Exception as e:
        logger.error(f"[CLOSE ERROR] Ошибка при закрытии тикета №{order_id}: {e}")

async def auto_close_ticket_if_silent(order_id: int, client_id: int, bot: Bot):
    try:
        logger.info(f"[TIMER] Запущен таймер авто-закрытия тикета №{order_id}")
        await asyncio.sleep(119)

        order_info = await db.get_orders_by_id(order_id)
        if not order_info or order_info.status == "closed":
            logger.info(f"[TIMER] Тикет №{order_id} уже был закрыт вручную — таймер завершён.")
            return

        try:
            await bot.send_message(
                chat_id=client_id,
                text="⚠️ Если вы не ответите в течение 3-х минут, тикет будет автоматически закрыт!"
            )
            logger.info(f"[TIMER] Предупреждение отправлено клиенту по тикету №{order_id}")
        except TelegramForbiddenError:
            reason = "Авто-закрытие (Заблокировал бота)"
            logger.warning(f"[TIMER] Клиент заблокировал бота до предупреждения тикета №{order_id}")
            await close_ticket(order_id, client_id, bot, reason)
            return

        await asyncio.sleep(179)
        order_info = await db.get_orders_by_id(order_id)
        if not order_info or order_info.status == "closed":
            logger.info(f"[TIMER] Тикет №{order_id} был закрыт вручную после предупреждения — авто-закрытие отменено.")
            return

        message_count = await redis_client.get(f"messages:{order_id}")
        if message_count is None or int(message_count) == 0:
            try:
                await bot.send_chat_action(chat_id=client_id, action="typing")
                reason = "Авто-закрытие (Клиент не ответил)"
            except TelegramForbiddenError:
                reason = "Авто-закрытие (Заблокировал бота)"
                logger.warning(f"[TIMER] Клиент заблокировал бота до авто-закрытия тикета №{order_id}")

            await close_ticket(order_id, client_id, bot, reason)
        else:
            logger.info(f"[TIMER] Тикет №{order_id} не закрыт — клиент отправил {message_count} сообщений")

    except Exception as e:
        logger.error(f"[TIMER ERROR] Ошибка при авто-закрытии тикета №{order_id}: {e}")
