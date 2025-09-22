from aiogram import Bot, Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from database.db import DataBase, redis_client
from colorama import Fore, Style
from logger import logger
from core.dictionary import *
from handlers.User.keyboard.replykeqyboard import get_start_menu, get_media_start_kb, get_user_stars_kb
from handlers.User.keyboard.InlineKeyboard import accounts_kb
from config import *
from commands import set_commands_admin
from core.i18n import normalize_lang
import os

db = DataBase()
start_router = Router()
TIMEOUT = 600

class StarsOrder(StatesGroup):
    stars_order = State()

def is_restricted_time() -> bool:
    now = datetime.now().time()
    return now.hour < 11 or now.hour >= 23

async def _get_lang(user_id: int) -> str:
    val = await redis_client.get(f"lang:{user_id}")
    if val and hasattr(val, "decode"):
        val = val.decode()
    return normalize_lang(val or "ru")

@start_router.message(Command(commands='start'), F.chat.type == "private")
async def start(message: Message, state: FSMContext, bot: Bot):
    logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} Ввел команду "start"' + Style.RESET_ALL)
    await state.clear()
    lang = await _get_lang(message.from_user.id)
    if is_restricted_time():
        if lang == "en":
            txt = "⏳ Good time of day!\n\nSupport works from 11:00 to 23:00 (MSK).\nWe are currently unavailable and response time is increased.\n\nPlease leave your request and we will reply during working hours.\n\nThank you for understanding 💙"
        else:
            txt = "⏳ Доброго времени суток!\n\nТехническая поддержка работает с 11:00 до 23:00 (МСК).\nСейчас мы недоступны, и время ожидания ответа увеличено.\n\nПожалуйста, оставьте ваш запрос, и мы обязательно ответим вам в рабочее время.\n\nСпасибо за понимание! 💙"
        await message.answer(txt)
    await set_commands_admin(bot, message.from_user.id)
    username = message.from_user.username
    if username is None:
        if lang == "en":
            txt = ("❌ You don't have @username set.\n\n"
                   "To use this bot you must set @username in Telegram settings:\n\n"
                   "1️⃣ Open Telegram.\n"
                   "2️⃣ Go to Settings.\n"
                   "3️⃣ Tap Edit Profile.\n"
                   "4️⃣ Set a unique @username.\n\n"
                   "After that you can use the bot! 🚀")
        else:
            txt = ("❌ У вас не установлен @username.\n\n"
                   "Для использования нашего бота вам необходимо задать @username в настройках Telegram:\n\n"
                   "1️⃣ Откройте Telegram.\n"
                   "2️⃣ Перейдите в «Настройки».\n"
                   "3️⃣ Нажмите на «Изменить профиль».\n"
                   "4️⃣ Укажите уникальный @username.\n\n"
                   "После этого вы сможете воспользоваться ботом! 🚀")
        await message.answer(txt)
        return
    result = await db.get_user(message.from_user.id, username)
    if result == 'Banned':
        await message.delete()
        logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} в черном списке' + Style.RESET_ALL)
        return
    elif result == 'admin':
        if lang == "en":
            txt = "Welcome, master"
        else:
            txt = "Добро пожаловать, мой хозяин"
        await message.answer(txt, reply_markup=get_start_menu(lang))
    elif result == 'support':
        if lang == "en":
            txt = "Hi, mate! Shall we work?"
        else:
            txt = "Привет, дружище! Поработаем?"
        await message.answer(text=txt)
    elif result == 'media':
        if lang == "en":
            txt = "Hi, our media!"
        else:
            txt = "Привет, наш медиа!"
        await message.answer(txt, reply_markup=get_media_start_kb(lang))
    elif result is True:
        if lang == "en":
            txt = "Welcome to GameBreaker. Use the menu below."
            await message.answer(txt, reply_markup=get_start_menu(lang), parse_mode='HTML')
        else:
            await message.answer(start_hello_message, reply_markup=get_start_menu(lang), parse_mode='HTML')
    else:
        if lang == "en":
            txt = "Error, please try later"
        else:
            txt = "Ошибка попробуйте позже"
        await message.answer(txt)

@start_router.message(F.text.in_({'📋 Меню', '📋 Menu'}))
async def open_menu(message: Message, state: FSMContext):
    lang = await _get_lang(message.from_user.id)
    result = await db.get_banned_users(message.from_user.id)
    if result is True:
        await message.delete()
        return
    username = message.from_user.username
    if username is None:
        if lang == "en":
            txt = ("❌ You don't have @username set.\n\n"
                   "To use this bot you must set @username in Telegram settings:\n\n"
                   "1️⃣ Open Telegram.\n"
                   "2️⃣ Go to Settings.\n"
                   "3️⃣ Tap Edit Profile.\n"
                   "4️⃣ Set a unique @username.\n\n"
                   "After that you can use the bot! 🚀")
        else:
            txt = ("❌ У вас не установлен @username.\n\n"
                   "Для использования нашего бота вам необходимо задать @username в настройках Telegram:\n\n"
                   "1️⃣ Откройте Telegram.\n"
                   "2️⃣ Перейдите в «Настройки».\n"
                   "3️⃣ Нажмите на «Изменить профиль».\n"
                   "4️⃣ Укажите уникальный @username.\n\n"
                   "После этого вы сможете воспользоваться ботом! 🚀")
        await message.answer(txt)
        return
    logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} Ввел команду "Меню"' + Style.RESET_ALL)
    services_all = await db.get_services()
    rows = [[InlineKeyboardButton(text=s.service_name, callback_data=f"service_{s.id}")] for s in services_all]
    if lang == "en":
        pri = "🚀 Priority support"
        ask = "Choose the service you need:"
    else:
        pri = "🚀 Приоритетная поддержка"
        ask = "Выберите нужную вам услугу:"
    rows.append([InlineKeyboardButton(text=pri, callback_data="priority_support")])
    keyboard_buttons = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(ask, reply_markup=keyboard_buttons)

@start_router.callback_query(F.data == "priority_support")
async def priority_support(call: CallbackQuery):
    lang = await _get_lang(call.from_user.id)
    if lang == "en":
        text = ("🚀 <b>Priority Support</b>\n\n"
                "We have expanded priority capabilities and strengthened the support team to reduce waiting time at any hours.\n\n"
                "💰 <b>Price:</b> $20 / month\n\n"
                "🎁 <b>What you get:</b>\n"
                "• ⏱️ <b>Service period:</b> 30 calendar days\n"
                "• 🪙 <b>Max loyalty bonus:</b> +10% to the e-mail linked to your account on the site\n"
                "• ⭐ <b>Chat tag:</b> “Sponsor”\n"
                "• 👥 <b>Enhanced support line:</b> more agents for faster replies\n\n"
                "ℹ️ These steps develop the project, increase the agents’ payroll and fund further R&D.\n\n"
                "Press “Pay” to enable priority now.")
        pay = "💳 Pay"
        back = "⬅️ Back"
    else:
        text = ("🚀 <b>Приоритетная поддержка</b>\n\n"
                "Мы расширили возможности приоритета и усилили команду поддержки, чтобы сократить время ожидания в любые часы.\n\n"
                "💰 <b>Стоимость:</b> 20$ / месяц\n\n"
                "🎁 <b>Что вы получаете:</b>\n"
                "• ⏱️ <b>Срок оказания услуг:</b> 30 календарных дней\n"
                "• 🪙 <b>Максимальный бонус накопительной системы:</b> +10% на e-mail, привязанный к аккаунту на сайте\n"
                "• ⭐ <b>Тег в чате:</b> «Спонсор»\n"
                "• 👥 <b>Усиленная линия поддержки:</b> больше агентов для более быстрых ответов\n\n"
                "ℹ️ Эти шаги направлены на развитие проекта, увеличение фонда оплаты труда агентов и дальнейшие инвестиции в разработки.\n\n"
                "Нажмите «Оплатить», чтобы подключить приоритет уже сейчас.")
        pay = "💳 Оплатить"
        back = "⬅️ Назад"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pay, url="https://oplata.info/asp2/pay_wm.asp?id_d=5423227&lang=ru-RU")],
            [InlineKeyboardButton(text=back, callback_data="back_to_menu")]
        ]
    )
    try:
        await call.message.delete()
    except Exception:
        pass
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(base_dir, "../../"))
    image_path = os.path.join(project_root, "IMG_20250916_172720_485.png")
    await call.bot.send_photo(
        chat_id=call.from_user.id,
        photo=FSInputFile(image_path),
        caption=text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@start_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        pass
    await open_menu(call.message, state)

@start_router.message(F.text.in_({'🆘 Помощь', '🆘 Help'}))
async def help(message: Message):
    lang = await _get_lang(message.from_user.id)
    logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} находится в разделе помощи' + Style.RESET_ALL)
    if lang == "en":
        txt = ("You are already in our support bot.\n"
               "Do you want another virtual meeting with yourself? 🤨\n"
               "Choose a service from the menu.\n\n"
               "Hint:\n"
               "/start — restart the bot\n"
               "/stop_chat — stop dialog with support\n")
    else:
        txt = ("Ты и так уже в нашем боте-поддержке, дружище!\n"
               "Что, хочешь устроить еще одну виртуальную встречу с самим собой? 🤨 \n"
               "😈 Выбери услугу из меню и не нажимай больше на кнопку помощи 😎😜\n\n"
               "Подсказка:\n"
               "/start - перезагрузить бота\n"
               "/stop_chat - остановить диалог с сапортом\n")
    await message.answer(txt, parse_mode='HTML')

@start_router.message(F.text.in_({'📩 Жалоба', '📩 Complaint'}))
async def help(message: Message):
    lang = await _get_lang(message.from_user.id)
    logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} находится в разделе помощи' + Style.RESET_ALL)
    if lang == "en":
        txt = ("Complain here <a href=\"https://telefon-doveria.ru/teenagers/\">BOT ADMINISTRATION</a> 🤨\n"
               "Choose a service from the menu.")
    else:
        txt = ("Ты совсем уже?\n"
               "<a href=\"https://telefon-doveria.ru/teenagers/\">АДМИНИСТРАЦИЯ БОТА</a> 🤨\n"
               "А здесь заходи не бойся, выходи не плачь!\n\n"
               "😈 Выбери услугу из меню и не нажимай больше на кнопку жалоба, пацаны не жалуются😎😜")
    await message.answer(txt, parse_mode='HTML', disable_web_page_preview=True)

pinned_messages = {}

async def pin_message(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True)
        pinned_messages[chat_id] = message_id
    except TelegramAPIError:
        pass

@start_router.callback_query(F.data.startswith('service_'))
async def callback_service(call: CallbackQuery, state: FSMContext):
    try:
        lang = await _get_lang(call.from_user.id)
        result = await db.get_banned_users(call.from_user.id)
        if result is True:
            await call.message.delete()
            return
        key = f"ticket_timeout:{call.from_user.id}"
        if await redis_client.exists(key):
            remaining = await redis_client.ttl(key)
            await call.message.delete()
            if lang == "en":
                txt = f"⏳ You have already sent a request, please wait:\n{remaining // 60} minutes {remaining % 60} seconds"
            else:
                txt = f"⏳ Вы уже отправляли недавно запрос, пожалуйста, подождите:\n{remaining // 60} минут {remaining % 60} секунд"
            await call.message.answer(txt)
            return
        if is_restricted_time():
            if lang == "en":
                txt = "⏳ Good time of day!\n\nSupport works from 11:00 to 23:00 (MSK).\nWe are currently unavailable and response time is increased.\n\nPlease leave your request and we will reply during working hours.\n\nThank you for understanding 💙"
            else:
                txt = "⏳ Доброго времени суток!\n\nТехническая поддержка работает с 11:00 до 23:00 (МСК).\nСейчас мы недоступны, и время ожидания ответа увеличено.\n\nПожалуйста, оставьте ваш запрос, и мы обязательно ответим вам в рабочее время.\n\nСпасибо за понимание! 💙"
            await call.message.answer(txt)
        service_id = int(call.data.split('_')[1])
        user_id = call.from_user.id
        services_all = await db.get_services()
        service_obj = next((s for s in services_all if s.id == service_id), None)
        if service_obj and service_obj.service_name == 'Техническая помощь / Technical Support':
            cnt = await db.count_user_service_requests_today(user_id, service_obj.service_name)
            if cnt >= 3:
                if lang == "en":
                    txt = "You have already sent 3 requests to technical support today. A new request will be available tomorrow."
                else:
                    txt = "Вы уже отправили 3 обращения в техническую поддержку за текущие сутки. Новое обращение будет доступно завтра."
                await call.message.answer(txt)
                return
        add_order = await db.add_orders(service_id, user_id)
        if add_order == 'Active-Ticket':
            if lang == "en":
                txt = "You already have an active ticket"
            else:
                txt = "У вас уже есть активный тикет"
            await call.message.answer(txt)
            return
        if lang == "en":
            message_send_user = (
               f"📩 Your Ticket #{add_order['id']}\n"
               f"🛠 Service: {add_order['service_name']}\n"
               f"⏳ Created: {add_order['created_at']}\n\n"
               f"💬 Please wait for a support agent to reply.\n"
               f"After your ticket is accepted, describe your problem and provide the required information.\n\n"
               f"⏱️ Average support response time:\n"
               f"• Up to 60 minutes in prime-time\n"
               f"• Up to 30 minutes at other times\n\n"
               f"🚀 For priority support\n"
               f"contact Admin: @st3lland"
            )
            cancel_txt = "🗑 Cancel"
            choose_type = "Choose account type"
            buy_now = "🛒 Buy now"
            back_txt = "⬅️ Back"
        else:
            message_send_user = (
               f"📩 Ваш Тикет №{add_order['id']}\n"
               f"🛠 Услуга: {add_order['service_name']}\n"
               f"⏳ Создана: {add_order['created_at']}\n\n"
               f"💬 Ожидайте ответа агента поддержки.\n"
               f"После того, как заявка будет принята, опишите Вашу проблему и предоставьте требуемую информацию.\n\n"
               f"⏱️ Среднее время ответа агента поддержки:\n"
               f"• До 60 минут в прайм-тайм\n"
               f"• До 30 минут в остальное время\n\n"
               f"🚀 Если Вы хотите получать приоритетную поддержку,\n"
               f"пожалуйста, свяжитесь с Администратором: @st3lland"
            )
            cancel_txt = "🗑 Отменить"
            choose_type = "Выберите тип аккаунта"
            buy_now = "🛒 Купить сейчас"
            back_txt = "⬅️ Назад"
        keyboard_client = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=cancel_txt, callback_data=f"remove_order:{add_order['id']}")]
            ]
        )
        try:
            await call.message.delete()
        except Exception:
            pass
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(base_dir, "../../"))
        image_path = os.path.join(project_root, "IMG_20250916_172720_485.png")
        user_message = await call.bot.send_photo(
            chat_id=call.from_user.id,
            photo=FSInputFile(image_path),
            caption=message_send_user,
            parse_mode="HTML",
            reply_markup=keyboard_client
        )
        excluded_usernames = ['jarkadash', 'afnskwb', 'Voldemort_1337', 'st3lland', 'MrMikita', 'GB_Support_Team']
        users = await db.get_user_role_id()
        if add_order['service_name'] == 'Получить Ключ / Get a key':
            admins = [user for user in users if user.role_id == 1 and user.username not in excluded_usernames]
            support_mentions = ", ".join([f"@{admin.username}" for admin in admins])
            tread_id = CHAT_ID_TIKETS_ADMIN
        else:
            supports = [user for user in users if user.role_id in [1, 2] and user.username not in excluded_usernames]
            support_mentions = ", ".join([f"@{support.username}" for support in supports])
            tread_id = GROUP_CHAT_ID_TIKETS_SUPPORT
        logger.info(Fore.BLUE + f'{support_mentions}' + Style.RESET_ALL)
        message_send_support = (
            f"📩 <b>Тикет</b> №{add_order['id']}\n"
            f"👤 <b>Пользователь:</b> @{add_order['client_name']}\n"
            f"🆔 <b>ID:</b> {add_order['client_id']}\n"
            f"<a href='https://t.me/{add_order['client_name']}'>🔗 1.Телеграм</a>\n"
            f"<a href='tg://user?id={add_order['client_id']}'>🔗 2.Телеграм</a>\n"
            f"🛠 <b>Услуга:</b> {add_order['service_name']}\n"
            f"ℹ️ <b>Статус:</b> <i>Новый</i>\n"
            f"⏳ <b>Создана:</b> {add_order['created_at']}\n\n"
            f"{support_mentions}\n"
            f"⚡ <b>Нажмите 'Принять', чтобы взять Тикет в работу.</b>"
        )
        keyboard_admin = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Принять Тикет", callback_data=f"accept_order:{add_order['id']}")],
                [InlineKeyboardButton(text="🗑 Отклонить Тикет", callback_data=f"cancel_order:{add_order['id']}")]
            ]
        )
        support_message = await call.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=message_send_support,
            message_thread_id=tread_id,
            reply_markup=keyboard_admin,
            parse_mode="HTML"
        )
        await db.add_messages_history(chat_id=user_message.chat.id, support_message_id=support_message.message_id, client_message_id=user_message.message_id, order_id=add_order['id'])
        await pin_message(call.bot, GROUP_CHAT_ID, support_message.message_id)
    except Exception as e:
        logger.error(f'Ошибка при обработке команды "service_": {e}')
        await call.message.answer('Ошибка попробуйте позже')

async def unpin_specific_message(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
    except TelegramAPIError:
        pass

@start_router.callback_query(F.data.startswith('remove_order:'))
async def remove_order(call: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        lang = await _get_lang(call.from_user.id)
        logger.info(f'📢 Получен запрос на удаление тикета от пользователя {call.from_user.username} (ID: {call.from_user.id})')
        order_id = int(call.data.split(':')[1])
        logger.info(f'🔍 Обрабатываем удаление тикета №{order_id}...')
        await redis_client.setex(f"ticket_timeout:{call.from_user.id}", TIMEOUT, "1")
        result = await db.remove_ticket_user(order_id)
        if result is False:
            if lang == "en":
                txt = "Error, try later"
            else:
                txt = "Ошибка, попробуйте позже"
            await call.message.answer(txt)
            return
        elif result == 'Не новый':
            if lang == "en":
                txt = "You cannot cancel your ticket if it has already been accepted or closed"
            else:
                txt = "Вы не можете отменить свой тикет, если он уже принят или закрыт"
            try:
                await call.message.edit_caption(txt)
            except Exception:
                try:
                    await call.message.edit_text(txt)
                except Exception:
                    await call.answer(txt, show_alert=True)
            return
        logger.info(f'✅ Тикет №{result["order_id"]} успешно отменён пользователем {result["client_name"]} (ID: {result["client_id"]})')
        minutes = int(TIMEOUT / 60)
        if lang == "en":
            message_send_user = (
                f"📩 Your Ticket #{result['order_id']}\n"
                f"🛠 Service: {result['service_name']}\n"
                f"❌ <b>Canceled</b>\n\n"
                f"⚠️ You can create a new ticket only after {minutes} minutes!"
            )
        else:
            message_send_user = (
                f"📩 Ваш Тикет №{result['order_id']}\n"
                f"🛠 Услуга: {result['service_name']}\n"
                f"❌ <b>Отменен</b>\n\n"
                f"⚠️ Вы сможете создать новый тикет, только после истечении {minutes} минут!"
            )
        message_send_support = (
            f"📩 <b>Тикет</b> №{result['order_id']}\n"
            f"👤 <b>Пользователь:</b> @{result['client_name']}\n"
            f"🆔 <b>ID:</b> {result['client_id']}\n"
            f"<a href='https://t.me/{result['client_name']}'>🔗 1.Телеграм</a>\n"
            f"<a href='tg://user?id={result['client_id']}'>🔗 2.Телеграм</a>\n"
            f"🛠 <b>Услуга:</b> {result['service_name']}\n"
            f"ℹ️ <b>Статус:</b> <i>Отменен</i>\n"
            f"⏳ <b>Создана:</b> {result['created_at']}\n\n"
            f"⚠️ Пользователь отменил тикет"
        )
        await call.bot.edit_message_text(
            message_id=result['support_message_id'],
            chat_id=GROUP_CHAT_ID,
            text=message_send_support,
            parse_mode="HTML"
        )
        try:
            await call.bot.edit_message_caption(
                message_id=result['client_message_id'],
                chat_id=call.from_user.id,
                caption=message_send_user,
                parse_mode="HTML"
            )
        except Exception:
            await call.bot.edit_message_text(
                message_id=result['client_message_id'],
                chat_id=call.from_user.id,
                text=message_send_user,
                parse_mode="HTML"
            )
        await unpin_specific_message(call.bot, GROUP_CHAT_ID, int(result['support_message_id']))
    except Exception as e:
        logger.error(f'🔥 Ошибка при обработке удаления тикета: {e}', exc_info=True)
        if await _get_lang(call.from_user.id) == "en":
            await call.message.answer('An error occurred, try later.')
        else:
            await call.message.answer('Произошла ошибка, попробуйте позже.')

@start_router.message(StarsOrder.stars_order)
async def star_worker(message: Message, state: FSMContext):
    lang = await _get_lang(message.from_user.id)
    data = await state.get_data()
    timeout_task = data.get('timeout_task')
    if timeout_task:
        timeout_task.cancel()
    logger.info(Fore.BLUE + f"Пользователь оценивает Тикет на {message.text.strip()} " + Style.RESET_ALL)
    reg_data = await state.get_data()
    try:
        stars = float(message.text.strip())
    except ValueError:
        if lang == "en":
            txt = "Please enter a number from 1 to 10"
        else:
            txt = "Для оценки оказания услуги пожалуйста введите число от 1 до 10"
        await message.answer(txt)
        return
    if not (1 <= stars <= 10):
        if lang == "en":
            txt = "The score must be from 1 to 10"
        else:
            txt = "Оценка должна быть в диапазоне от 1 до 10"
        await message.answer(txt)
        return
    result = await db.stars_order_update(int(reg_data.get('order_id')), stars)
    if result is True:
        if lang == "en":
            txt = f"Thank you for your rating! {stars}"
        else:
            txt = f"Благодарим вас за оценку! {stars}"
        await message.answer(txt, reply_markup=get_start_menu(lang))
    else:
        if lang == "en":
            txt = "Rating error. Try later."
        else:
            txt = "Ошибка при оценке. Попробуйте позже."
        await message.answer(txt)
        logger.error(Fore.RED + f"Ошибка при оценке Тикета: {result}" + Style.RESET_ALL)
        return
    await state.clear()

@start_router.message(F.text.in_({'Аккаунты RUST', 'RUST Accounts'}))
async def start_accounts(message: Message):
    lang = await _get_lang(message.from_user.id)
    logger.info(Fore.BLUE + f"Пользователь {message.from_user.username} (ID: {message.from_user.id}) запустил команду 'Аккаунты RUST'" + Style.RESET_ALL)
    if lang == "en":
        txt = "Choose account type"
    else:
        txt = "Выберите тип аккаунта"
    await message.answer(txt, reply_markup=accounts_kb(lang))

@start_router.callback_query(F.data.startswith('zero_accounts'))
async def zero_accounts(call: CallbackQuery):
    lang = await _get_lang(call.from_user.id)
    logger.info(Fore.BLUE + f"Пользователь {call.from_user.username} (ID: {call.from_user.id}) открыл меню Нулевый аккаунт" + Style.RESET_ALL)
    if lang == "en":
        message_text = (
            f"<b>🎮 Rust account</b> with random hours <b>🕒 0–100</b>\n\n"
            f"<b>❗️ Important:</b>\n"
            f"<u>Login:password is provided</u>\n"
            f"⛔️ It is <u>forbidden to change registration data</u> "
            f"(<b>password/email/phone</b>) — this will lead to <b>permanent ban</b> "
            f"without exchange or refund 🔐\n\n"
            f"✅ <b>Allowed to change:</b>\n"
            f"• 📝 Profile\n"
            f"• 📸 Photo\n"
            f"• 🔤 Name\n\n"
            f"<b>⚙️ Required:</b>\n"
            f"🚫 In settings <b>DISABLE</b> Remote play\n"
            f"💵 Price: 800₽"
        )
        buy_now = "🛒 Buy now"
        back = "⬅️ Back"
    else:
        message_text = (
            f"<b>🎮 Раст аккаунт</b> с рандомными часами <b>🕒 от 0 до 100</b>\n\n"
            f"<b>❗️ ВАЖНОЕ ОПИСАНИЕ:</b>\n"
            f"<u>Выдается логин:пароль</u>\n"
            f"⛔️ На аккаунте <u>запрещено менять регистрационные данные</u> "
            f"(<b>пароль/почту/телефон</b>) — это приведёт к <b>полной блокировке</b> "
            f"аккаунта <u>без обмена и возврата</u> 🔐\n\n"
            f"✅ <b>Разрешено изменять:</b>\n"
            f"• 📝 Профиль\n"
            f"• 📸 Фотографию\n"
            f"• 🔤 Имя\n\n"
            f"<b>⚙️ Обязательное условие:</b>\n"
            f"🚫 В настройках <b>ОТКЛЮЧИТЬ</b> Remote play\n"
            f"💵 Цена: 800₽"
        )
        buy_now = "🛒 Купить сейчас"
        back = "⬅️ Назад"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=buy_now, url='https://www.digiseller.market/asp2/pay_wm.asp?id_d=5075738&lang=ru-RU')],
            [InlineKeyboardButton(text=back, callback_data='accounts_back')]
        ]
    )
    await call.message.edit_text(message_text, parse_mode="HTML", reply_markup=keyboard)

@start_router.callback_query(F.data.startswith('active_accounts'))
async def active_accounts(call: CallbackQuery, bot: Bot):
    lang = await _get_lang(call.from_user.id)
    logger.info(Fore.BLUE + f"Пользователь {call.from_user.username} (ID: {call.from_user.id}) открыл меню Активный аккаунт" + Style.RESET_ALL)
    image1 = "media/image1.jpg"
    message_text_en = (
        f"<b>🎮 Rust account</b> with <b>🕒 1500+ hours + Twitch items</b>\n\n"
        f"<b>❗️ Important:</b>\n"
        f"<u>Login:password is provided, 3 days warranty, email is given after warranty period of 72 hours</u>\n"
        f"⛔️ Before the warranty ends it is <u>forbidden to change registration data</u>"
        f"(<b>password/email/phone</b>) — this will lead to <b>permanent ban</b> "
        f"without exchange or refund 🔐\n\n"
        f"✅ <b>Allowed to change:</b>\n"
        f"• 📝 Profile\n"
        f"• 📸 Photo\n"
        f"• 🔤 Name\n\n"
        f"<b>⚙️ Required:</b>\n"
        f"🚫 In settings <b>DISABLE</b> Remote play\n"
        f"💵 Price: 3000₽"
    )
    message_text_ru = (
        f"<b>🎮 Раст аккаунт</b> с часами <b>🕒 от 1500 + твич предметы</b>\n\n"
        f"<b>❗️ ВАЖНОЕ ОПИСАНИЕ:</b>\n"
        f"<u>Выдается логин:пароль, 3 дня гарантии, почта отдается - после окончания гарантии сроком в 72 часа</u>\n"
        f"⛔️ До истечения срока гарантии на аккаунте <u>запрещено менять регистрационные данные</u>"
        f"(<b>пароль/почту/телефон</b>) — это приведёт к <b>полной блокировке</b> "
        f"аккаунта <u>без обмена и возврата</u> 🔐\n\n"
        f"✅ <b>Разрешено изменять:</b>\n"
        f"• 📝 Профиль\n"
        f"• 📸 Фотографию\n"
        f"• 🔤 Имя\n\n"
        f"<b>⚙️ Обязательное условие:</b>\n"
        f"🚫 В настройках <b>ОТКЛЮЧИТЬ</b> Remote play\n"
        f"💵 Цена: 3000₽"
    )
    if lang == "en":
        message_text = message_text_en
        buy_now = "🛒 Buy now"
        back = "⬅️ Back"
    else:
        message_text = message_text_ru
        buy_now = "🛒 Купить сейчас"
        back = "⬅️ Назад"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=buy_now, url='https://www.digiseller.market/asp2/pay_wm.asp?id_d=5075744&lang=ru-RU')],
            [InlineKeyboardButton(text=back, callback_data='accounts_back')]
        ]
    )
    media = InputMediaPhoto(media=FSInputFile(image1), caption=message_text, parse_mode="HTML")
    try:
        await call.message.edit_media(media=media, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка редактирования: {e}")
        await call.answer("⚠️ Не удалось обновить", show_alert=True)

@start_router.callback_query(F.data.startswith('accounts_back'))
async def accounts_back(call: CallbackQuery):
    lang = await _get_lang(call.from_user.id)
    logger.info(Fore.BLUE + f"Пользователь {call.from_user.username} (ID: {call.from_user.id}) открыл меню аккаунтов" + Style.RESET_ALL)
    await call.message.delete()
    if lang == "en":
        txt = "Choose account type"
    else:
        txt = "Выберите тип аккаунта"
    await call.message.answer(txt, reply_markup=accounts_kb(lang))

@start_router.callback_query(F.data.startswith('close_accounts'))
async def close_accounts(call: CallbackQuery):
    logger.info(Fore.BLUE + f"Пользователь {call.from_user.username} (ID: {call.from_user.id}) закрыл меню аккаунтов" + Style.RESET_ALL)
    await call.message.delete()
