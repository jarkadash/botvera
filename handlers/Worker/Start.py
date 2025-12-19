import time

from aiogram import Bot, Router, F
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, \
    KeyboardButton
from aiogram.fsm.context import FSMContext
from Utils import get_calculated_period, filter_tickets_for_statistics
from sqlalchemy.testing.config import any_async
import html
from database.db import DataBase, redis_client
import asyncio
from colorama import Fore, Style

from handlers.Worker.common_states import FormOrderShema
from handlers.utils.timers import close_ticket, auto_close_ticket_if_silent
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
                             f"тикет №{call.data.split(':')[1]}" + Style.RESET_ALL)
    order_id = int(call.data.split(":")[1])
    try:
        accept = await db.accept_orders(order_id, int(call.from_user.id))
        if isinstance(accept, dict):
            # Результат - словарь с ключами updated_order, group_id, thread_id
            updated_order = accept.get("updated_order")
            group_id = accept.get("group_id")
            thread_id = accept.get("thread_id")

            if not updated_order:
                await call.answer("Ошибка при принятии тикета", show_alert=True)
                return

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
                f"👤 <b>Пользователь:</b> @{html.escape(updated_order.client_name)}\n"
                f"🆔 <b>ID:</b> {updated_order.client_id}\n"
                f"<a href=\"https://t.me/{html.escape(updated_order.client_name)}\">🔗 1.Телеграм</a>\n"
                f"<a href=\"tg://user?id={updated_order.client_id}\">🔗 2.Телеграм</a>\n"
                f"🛠 <b>Услуга:</b> {html.escape(updated_order.service_name)}\n"
                f"🆔 <b>Support_id:</b> {updated_order.support_id}\n"
                f"👨‍💻 <b>Support_name:</b> @{html.escape(updated_order.support_name)}\n"
                f"ℹ️ <b>Статус:</b> {html.escape(updated_order.status)}\n"
                f"⏳ <b>Создана:</b> {updated_order.created_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"⏳ <b>Принята:</b> {updated_order.accept_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"<a href=\"https://t.me/GBPSupport_bot\">Перейти в бота</a>"
            )
            try:
                await bot.send_message(
                    chat_id=int(updated_order.client_id),
                    text=(
                        f"🎉 Ваш тикет №{order_id} успешно принят!\n\n"
                        f"Теперь вы можете общаться с менеджером в этом чате. "
                        f"Пожалуйста, соблюдайте уважительный тон в общении — это поможет нам решить ваш вопрос быстрее и эффективнее.\n\n"
                        f"Команда /stop_chat — завершить диалог"
                    )
                )
                task = asyncio.create_task(auto_close_ticket_if_silent(order_id, updated_order.client_id, bot))
                active_timers[order_id] = task
                if updated_order.service_name == "Техническая помощь / Technical Support":
                    await bot.send_message(
                        chat_id=int(updated_order.client_id),
                        text=(
                            "   *Приветствую!*\n"
                            "*Предоставь информацию по форме:* \n\n"
                            "*1.* *Скриншот, подтверждающий покупку в личном кабинете*\n"
                            "   *-ключ должно быть видно на скриншоте*\n"
                            "   *-пришли ключ в текстовом формате*\n\n"
                            "*2.* Нажми  `Win + R`  введи: ``` msinfo32   ```\n"
                            "   Нажми Enter.\n"
                            "   *Скриншот всего окна пришли в чат-бота.*\n\n"
                            "*3.* Нажми  `Win + R`  введи: ``` winver   ```\n"
                            "   Нажми Enter.\n"
                            "   *Скриншот окна пришли в чат-бота.*\n\n"
                            "*4.* *Опиши подробно проблему.*\n"
                            "   *При наличии ошибок — предоставь скриншот ошибки.*"
                        ), parse_mode="markdown"
                    )
                elif updated_order.service_name == "NFA / HWID RESET":
                    await bot.send_message(
                        chat_id=int(updated_order.client_id),
                        text=(
                            f"Приветствую!\n"
                            f"Для сброса HWID предоставь информацию по форме:\n\n"
                            f"1. <u><b>Скриншот</b></u>, подтверждающий покупку в личном кабинете <u>(ключ должно быть видно на скриншоте)</u>\n\n"
                            f"2. Ключ продукта <u>в текстовом формате</u>\n\n"
                            f"3. Используешь сторонний спуфер(не встроенный в чит)?"
                        ), parse_mode="HTML", reply_markup=None
                    )

                await bot.send_message(
                    chat_id=int(group_id),
                    message_thread_id=int(thread_id),  # ⚠️ ВАЖНО: message_thread_id, а не thread_id!
                    text=f"Тикет №{order_id} принят!\nЧат с пользователем открыт!\n\n"
                         f"⚠️Напоминаем⚠️\n"
                         f"Обязательно уточните у пользователя, (Название игры, название чита, сформулируйте причину обращения пользователя)\n"
                         f"В конце общения с пользователем, после закрытия тикета, "
                         f"Вам, необходимо заполнить форму обращения, для текущего тикета, "
                         f"так же нужно сразу заполнить форму, не переходя в другой тикет(тему) и не откладывать на потом!!\n"
                         f"Сразу закрыли и заполнили!!\n\n\n"
                         f"⚠️Самое главное, пока не заполните форму, не закрывайте другой тикет, закрыли заполнили!⚠️",

                )
            except TelegramForbiddenError as e:
                logger.error(Fore.RED + f"Ошибка при отправке сообщения клиенту: {e}" + Style.RESET_ALL)
                await bot.send_message(
                    chat_id=call.from_user.id,
                    text=(f"Ошибка принятия тикета! {order_id}\n"
                          f"Пользователь @{updated_order.client_name} заблокировал бота\n"
                          )
                )
                message_accept = (
                    f"✅ Тикет закрыт!\n\n\n"
                    f"📩 <b>Тикет</b> №{order_id}\n"
                    f"👤 <b>Пользователь:</b> @{html.escape(updated_order.client_name)}\n"
                    f"🆔 <b>ID:</b> {updated_order.client_id}\n"
                    f"<a href=\"https://t.me/{html.escape(updated_order.client_name)}\">🔗 1.Телеграм</a>\n"
                    f"<a href=\"tg://user?id={updated_order.client_id}\">🔗 2.Телеграм</a>\n"
                    f"🛠 <b>Услуга:</b> {html.escape(updated_order.service_name)}\n"
                    f"🆔 <b>Support_id:</b> {updated_order.support_id}\n"
                    f"👨‍💻 <b>Support_name:</b> @{html.escape(updated_order.support_name)}\n"
                    f"ℹ️ <b>Статус:</b> {html.escape(updated_order.status)}\n"
                    f"⏳ <b>Создана:</b> {updated_order.created_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                    f"<b>Причина:</b> Пользователь заблокировал бота\n"
                )
                result = await db.get_auto_close_order(int(order_id), reason="Авто-закрытие (Заблокировал бота)")

                try:
                    await bot.delete_forum_topic(
                        chat_id=int(result['group_id']),
                        message_thread_id=int(result['thread_id']),
                    )
                    logger.info(f"Топик {result['thread_id']} удален в Telegram")
                except Exception as e:
                    logger.warning(f"Не удалось удалить топик: {e}")
                # Пробуем закрыть топик вместо удаления
                try:
                    await bot.close_forum_topic(
                        chat_id=int(result['group_id']),
                        message_thread_id=int(result['thread_id'])
                    )
                    logger.info(f"Топик {result['thread_id']} закрыт в Telegram")
                except Exception as e2:
                    logger.warning(f"Не удалось закрыть топик: {e2}")
                message_info = await db.get_all_message(int(order_id))
                if message_info:
                    logger.info(Fore.BLUE + f"Получена информация о Тикете №{order_id}." + Style.RESET_ALL)
                    messages_id = message_info.support_message_id
                    await bot.edit_message_text(
                        chat_id=GROUP_CHAT_ID,
                        message_id=int(message_info.support_message_id),
                        text=message_accept,
                        parse_mode="HTML", reply_markup=None
                    )
                    await unpin_specific_message(bot, GROUP_CHAT_ID, int(message_info.support_message_id))
            if 'message_accept' in locals():
                msg_info = await db.get_all_message(int(order_id))
                if msg_info:
                    await bot.edit_message_text(
                        chat_id=GROUP_CHAT_ID,
                        message_id=int(msg_info.support_message_id),
                        text=message_accept,
                        parse_mode="HTML", reply_markup=None
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
                           f"Тикет №{call.data.split(':')[1]}" + Style.RESET_ALL)
    order_id = int(call.data.split(":")[1])
    await state.update_data(order_id=order_id)
    try:
        accept = await db.check_role_for_service(int(call.from_user.id), order_id)
        if accept is False or accept == 'Пользователь не имеет роли!':
            await call.answer("У вас нет доступа к этому Тикету", show_alert=True)
        else:
            order = await db.get_orders_by_id(order_id)
            if not order:
                await call.answer("Тикет не найден", show_alert=True)
                return
            if str(order.status).lower() != 'new':
                await call.answer("Ошибка: статус не new", show_alert=True)
                return
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
    logger.info(
        Fore.YELLOW
        + f"Пользователь {message.from_user.username} id:{message.from_user.id} "
          f"отправил запрос на отмену тикета. Причина: {message.text}"
        + Style.RESET_ALL
    )

    reg_data = await state.get_data()
    order_id = reg_data.get('order_id')
    description = message.text.strip()
    message_id = reg_data.get('message_id')
    if len(description) > 100:
        await message.answer("⛔️ Текст отмены должен быть больше 100 символов!")
        return

    order = await db.get_orders_by_id(order_id)
    if not order:
        await message.answer("Тикет не найден.")
        await state.clear()
        return
    if str(order.status).lower() != 'new':
        await message.answer("Ошибка при попытке отмены тикета: статус не new")
        await state.clear()
        return

    try:
        cancel = await db.cancel_order(order_id, int(message.from_user.id), description)
        if cancel == 'STATUS_NOT_NEW':
            await message.answer("Ошибка при попытке отмены тикета: статус не new")
            logger.warning(
                Fore.CYAN
                + f"Отмена тикета {order_id} отклонена — статус не NEW. "
                  f"Текущий статус: {order.status}"
                + Style.RESET_ALL
            )
            await state.clear()
            return
        if cancel is False:
            await message.answer("❌ Произошла ошибка при отмене тикета. Попробуйте еще раз.")
        else:
            logger.info(
                Fore.GREEN
                + f"Тикет №{order_id} успешно отменён пользователем {message.from_user.id}"
                + Style.RESET_ALL
            )
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
                f"⏳ <b>Создана:</b> {cancel.created_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"⏳ <b>Отменена:</b> {cancel.completed_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"<b>Причина отмены:</b> {description}\n"
            )

            await message.bot.edit_message_text(chat_id=GROUP_CHAT_ID, text=message_accept, parse_mode="HTML",
                                                message_id=message_id)
            await unpin_specific_message(message.bot, GROUP_CHAT_ID, message_id)
            await bot.send_message(chat_id=message.from_user.id,
                                   text=f"✅ Тикет №{order_id} успешно отменен. Причина: {description}")
            try:
                await bot.send_message(chat_id=int(cancel.client_id),
                                       text=f"⛔️ Ваш тикет №{order_id} отменен!\n Причина: {description}")
            except TelegramForbiddenError as e:
                logger.error(Fore.RED + f"Пользователь заблокировал бота: {e}" + Style.RESET_ALL)
            await state.clear()

    except Exception as e:
        logger.error(Fore.RED + f"Ошибка при отмене тикета: {e}" + Style.RESET_ALL)
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


@worker_router.message(FormOrderShema.name_game)
async def add_name_game_for_form(message: Message, state: FSMContext):
    logger.info(f"Пользователь ввел название игры: {message.text}")
    data = await state.get_data()
    saved_thread_id = data.get('thread_id')

    if message.message_thread_id != saved_thread_id:
        await message.answer("⚠️ Пожалуйста, продолжайте заполнение формы в исходном топике.")
        return

    game_name = message.text

    await state.update_data(name_game=game_name)
    await message.answer("Введите название чита:")
    await state.set_state(FormOrderShema.name_cheat)


@worker_router.message(FormOrderShema.name_cheat)
async def add_name_cheat_for_form(message: Message, state: FSMContext):
    logger.info(f"Пользователь ввел название чита:{message.text}")
    data = await state.get_data()
    saved_thread_id = data.get('thread_id')

    if message.message_thread_id != saved_thread_id:
        await message.answer("⚠️ Пожалуйста, продолжайте заполнение формы в исходном топике.")
        return
    cheat_name = message.text

    await state.update_data(name_cheat=cheat_name)
    await message.answer("Ведите описание обращение:")
    await state.set_state(FormOrderShema.problem_description)


@worker_router.message(FormOrderShema.problem_description)
async def add_problem_description_for_form(message: Message, state: FSMContext):
    logger.info(f"Пользователь ввел причину обращение: {message.text}")
    data = await state.get_data()
    saved_thread_id = data.get('thread_id')

    if message.message_thread_id != saved_thread_id:
        await message.answer("⚠️ Пожалуйста, продолжайте заполнение формы в исходном топике.")
        return

    problem_description = message.text
    await state.update_data(problem_description=problem_description)
    await message.answer("Введите характеристики пк пользователя который обратился:")
    await state.set_state(FormOrderShema.specifications)


@worker_router.message(FormOrderShema.specifications)
async def add_specifications_for_form(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"Пользователь ввел характеристики пк: {message.text}")
    data = await state.get_data()
    saved_thread_id = data.get('thread_id')

    if message.message_thread_id != saved_thread_id:
        await message.answer("⚠️ Пожалуйста, продолжайте заполнение формы в исходном топике.")
        return

    specifications = message.text
    await state.update_data(specifications=specifications)
    get_data = await state.get_data()
    order_id = get_data["order_id"]
    name_game = get_data["name_game"]
    name_cheat = get_data["name_cheat"]
    problem_description = get_data["problem_description"]

    # ИСПРАВЛЕНИЕ: Получаем thread_id правильно
    # Вариант 1: Из сообщения (если сообщение в треде/теме)
    thread_id = message.message_thread_id

    # Вариант 2: Из данных состояния (если сохраняли ранее)
    if not thread_id:
        thread_id = get_data.get("thread_id")

    # Вариант 3: Если все равно не нашли, логируем предупреждение
    if not thread_id:
        logger.warning(f"Не удалось найти thread_id для удаления топика. order_id: {order_id}")
        await message.answer("Форма успешно заполнена!")
        await state.clear()
        return

    add_form_in_base = await db.add_form_in_base(order_id, name_game, name_cheat, problem_description, specifications)

    if add_form_in_base is not False:
        await message.answer("Форма успешно заполнена, эта тема удалится автоматически!")
        await state.clear()
        # Небольшая задержка перед удалением
        await asyncio.sleep(5)  # Используем asyncio.sleep вместо time.sleep

        try:
            # Сначала пробуем удалить топик
            await bot.delete_forum_topic(
                chat_id=message.chat.id,
                message_thread_id=thread_id
            )
            logger.info(f"Топик {thread_id} удален в Telegram")
        except Exception as e:
            logger.warning(f"Не удалось удалить топик: {e}")

            # Если не удалось удалить, пробуем закрыть
            try:
                await bot.close_forum_topic(
                    chat_id=message.chat.id,
                    message_thread_id=thread_id
                )
                logger.info(f"Топик {thread_id} закрыт в Telegram")
            except Exception as e2:
                logger.warning(f"Не удалось закрыть топик: {e2}")
