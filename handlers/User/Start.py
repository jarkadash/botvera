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
from handlers.User.keyboard.replykeqyboard import *
from handlers.User.keyboard.InlineKeyboard import *
from config import *
from commands import set_commands_admin

db = DataBase()
start_router = Router()
TIMEOUT = 600

class StarsOrder(StatesGroup):
    stars_order = State()

def is_restricted_time() -> bool:
    now = datetime.now().time()
    return now.hour < 11 or now.hour >= 23

@start_router.message(Command(commands='start'), F.chat.type == "private")
async def start(message: Message, state: FSMContext, bot: Bot):
    logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} Ввел команду "start"' + Style.RESET_ALL)
    await state.clear()
    if is_restricted_time():
        await message.answer(
            "⏳ Доброго времени суток!\n\n"
            "Техническая поддержка работает с 11:00 до 23:00 (МСК).\n"
            "Сейчас мы недоступны, и время ожидания ответа увеличено.\n\n"
            "Пожалуйста, оставьте ваш запрос, и мы обязательно ответим вам "
            "в рабочее время.\n\n"
            "Спасибо за понимание! 💙"
        )
    await set_commands_admin(bot, message.from_user.id)
    username = message.from_user.username
    if username is None:
        await message.answer(
            "❌ У вас не установлен @username.\n\n"
            "Для использования нашего бота вам необходимо задать @username в настройках Telegram:\n\n"
            "1️⃣ Откройте Telegram.\n"
            "2️⃣ Перейдите в «Настройки».\n"
            "3️⃣ Нажмите на «Изменить профиль».\n"
            "4️⃣ Укажите уникальный @username.\n\n"
            "После этого вы сможете воспользоваться ботом! 🚀"
        )
        return
    result = await db.get_user(message.from_user.id, username)
    if result == 'Banned':
        await message.delete()
        logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} в черном списке' + Style.RESET_ALL)
        return
    elif result == 'admin':
        await message.answer('Добро пожаловать, мой хозяин', reply_markup=start_menu)
    elif result == 'support':
        await message.answer(text='Привет, дружище! Поработаем?')
    elif result == 'media':
        await message.answer('Привет, наш медиа!', reply_markup=media_start_kb)
    elif result is True:
        await message.answer(start_hello_message, reply_markup=start_menu, parse_mode='HTML')
    else:
        await message.answer(f'Ошибка попробуйте позже')

@start_router.message(F.text == '📋 Меню')
async def open_menu(message: Message, state: FSMContext):
    result = await db.get_banned_users(message.from_user.id)
    if result is True:
        await message.delete()
        return
    username = message.from_user.username
    if username is None:
        await message.answer(
            "❌ У вас не установлен @username.\n\n"
            "Для использования нашего бота вам необходимо задать @username в настройках Telegram:\n\n"
            "1️⃣ Откройте Telegram.\n"
            "2️⃣ Перейдите в «Настройки».\n"
            "3️⃣ Нажмите на «Изменить профиль».\n"
            "4️⃣ Укажите уникальный @username.\n\n"
            "После этого вы сможете воспользоваться ботом! 🚀"
        )
        return
    logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} Ввел команду "Меню"' + Style.RESET_ALL)
    services_all = await db.get_services()
    rows = [[InlineKeyboardButton(text=s.service_name, callback_data=f"service_{s.id}")] for s in services_all]
    rows.append([InlineKeyboardButton(text="🚀 Приоритетная поддержка", callback_data="priority_support")])
    keyboard_buttons = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer('Выберите нужную вам услугу:', reply_markup=keyboard_buttons)


@start_router.callback_query(F.data == "priority_support")
async def priority_support(call: CallbackQuery):
    text = (
        "🚀 <b>Приоритетная поддержка</b>\n\n"
        "Приоритетная поддержка нацелена на максимальную скорость в решении любых проблем пользователя с нашими продуктами.\n\n"
        "После оплаты Вы будете добавлены в закрытую беседу, где сможете обратиться напрямую к агенту поддержки и получить помощь немедленно."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url="https://oplata.info/asp2/pay_wm.asp?id_d=5423227&lang=ru-RU")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
        ]
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)


@start_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await open_menu(call.message, state)



@start_router.message(F.text == '🆘 Помощь')
async def help(message: Message):
    logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} находится в разделе помощи' + Style.RESET_ALL)
    await message.answer('Ты и так уже в нашем боте-поддержке, дружище!\n'
                         f'Что, хочешь устроить еще одну виртуальную встречу с самим собой? 🤨 \n'
                         f'Только не говори, что ты пришел сюда, чтобы поговорить о жизни… Я тут не для того, чтобы лечить душевные раны! \n\n'
                         f'😈 Выбери услугу из меню и не нажимай больше на кнопку помощи 😎😜\n\n'
                         f'Подсказка:\n'
                         f'/start - перезагрузить бота\n'
                         f'/stop_chat - остановить диалог с сапортом\n', parse_mode='HTML')

@start_router.message(F.text == '📩 Жалоба')
async def help(message: Message):
    logger.info(Fore.BLUE + f'Пользователь {message.from_user.username} id: {message.from_user.id} находится в разделе помощи' + Style.RESET_ALL)
    await message.answer('Ты совсем уже?\n'
                         f'Пожаловаться можешь тут <a href="https://telefon-doveria.ru/teenagers/">АДМИНИСТРАЦИЯ БОТА</a> 🤨\n'
                         f'А здесь заходи не бойся, выходи не плачь!\n\n'
                         f'😈 Выбери услугу из меню и не нажимай больше на кнопку жалоба, пацаны не жалуются😎😜',
                         parse_mode='HTML', disable_web_page_preview=True)

pinned_messages = {}

async def pin_message(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.pin_chat_message(
            chat_id=chat_id,
            message_id=message_id,
            disable_notification=True
        )
        pinned_messages[chat_id] = message_id
        print(f"Сообщение закреплено в чате {pinned_messages}")
        print("Сообщение закреплено!")
    except TelegramAPIError as e:
        print(f"Ошибка: {e}")

@start_router.callback_query(F.data.startswith('service_'))
async def callback_service(call: CallbackQuery, state: FSMContext):
    try:
        result = await db.get_banned_users(call.from_user.id)
        if result is True:
            await call.message.delete()
            return
        key = f"ticket_timeout:{call.from_user.id}"
        if await redis_client.exists(key):
            remaining = await redis_client.ttl(key)
            await call.message.delete()
            await call.message.answer(f"⏳ Вы уже отправляли запрос, пожалуйста, подождите:\n{remaining} секунд(ы) \n({remaining // 60} минут(ы)).")
            return
        if is_restricted_time():
            await call.message.answer(
                "⏳ Доброго времени суток!\n\n"
                "Техническая поддержка работает с 11:00 до 23:00 (МСК).\n"
                "Сейчас мы недоступны, и время ожидания ответа увеличено.\n\n"
                "Пожалуйста, оставьте ваш запрос, и мы обязательно ответим вам "
                "в рабочее время.\n\n"
                "Спасибо за понимание! 💙"
            )
        service_id = int(call.data.split('_')[1])
        user_id = call.from_user.id
        services_all = await db.get_services()
        service_obj = next((s for s in services_all if s.id == service_id), None)
        if service_obj and service_obj.service_name == 'Техническая помощь / Technical Support':
            cnt = await db.count_user_service_requests_today(user_id, service_obj.service_name)
            if cnt >= 2:
                await call.message.answer('Вы уже отправили 2 обращения в техническую поддержку за текущие сутки. Новое обращение будет доступно завтра.')
                return
        add_order = await db.add_orders(service_id, user_id)
        if add_order == 'Active-Ticket':
            await call.message.answer('У вас уже есть активный тикет')
            return
        message_send_user = (
            f"📩 Ваш Тикет №{add_order['id']}\n"
            f"🛠 Услуга: {add_order['service_name']}\n"
            f"⏳ Создана: {add_order['created_at']}\n\n"
            f"💬 Ожидайте ответа агента поддержки.\n"
            f"После того, как заявка будет принята, опишите Вашу проблему и предоставьте требуемую информацию.\n\n"
            f"ℹ️ Обращаем ваше внимание, техническая поддержка включена в стоимость каждого продукта и не подразумевает более 2 обращений в сутки.\n\n"
            f"⏱️ Среднее время ответа агента поддержки:\n"
            f"• До 60 минут в прайм-тайм\n"
            f"• До 30 минут в остальное время\n\n"
            f"🚀 Если Вы хотите получать приоритетную поддержку,\n"
            f"пожалуйста, свяжитесь с Администратором: @st3lland"
        )
        # Клавиатура клиента: только «Отменить»
        keyboard_client = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Отменить", callback_data=f"remove_order:{add_order['id']}")]
            ]
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
        user_message = await call.message.edit_text(
            message_send_user,
            parse_mode="HTML",
            reply_markup=keyboard_client
        )
        await db.add_messages_history(chat_id=user_message.chat.id, support_message_id=support_message.message_id, client_message_id=user_message.message_id, order_id=add_order['id'])
        await pin_message(call.bot, GROUP_CHAT_ID, support_message.message_id)
    except Exception as e:
        logger.error(f'Ошибка при обработке команды "service_": {e}')
        await call.message.answer(f'Ошибка попробуйте позже')

async def unpin_specific_message(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.unpin_chat_message(
            chat_id=chat_id,
            message_id=message_id
        )
        print(f"Сообщение {message_id} откреплено!")
    except TelegramAPIError as e:
        print(f"Ошибка: {e}")

@start_router.callback_query(F.data.startswith('remove_order:'))
async def remove_order(call: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        logger.info(f'📢 Получен запрос на удаление тикета от пользователя {call.from_user.username} (ID: {call.from_user.id})')
        order_id = int(call.data.split(':')[1])
        logger.info(f'🔍 Обрабатываем удаление тикета №{order_id}...')
        await redis_client.setex(f"ticket_timeout:{call.from_user.id}", TIMEOUT, "1")
        result = await db.remove_ticket_user(order_id)
        if result is False:
            logger.warning(f'❌ Ошибка при удалении тикета №{order_id}. Возвращаем сообщение пользователю.')
            await call.message.answer('Ошибка, попробуйте позже')
            return
        elif result == 'Не новый':
            await call.message.edit_text('Вы не можете отменить свой тикет, если он уже принят или закрыт')
            return
        logger.info(f'✅ Тикет №{result["order_id"]} успешно отменён пользователем {result["client_name"]} (ID: {result["client_id"]})')
        minutes = int(TIMEOUT / 60)
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
        logger.info(f'📤 Сообщение об отмене тикета №{result["order_id"]} отправлено в поддержку.')
        await call.bot.edit_message_text(
            message_id=result['client_message_id'],
            chat_id=call.from_user.id,
            text=message_send_user,
            parse_mode="HTML"
        )
        logger.info(f'📤 Сообщение пользователю @{result["client_name"]} (ID: {result["client_id"]}) отправлено.')
        print(result['support_message_id'])
        await unpin_specific_message(call.bot, GROUP_CHAT_ID, int(result['support_message_id']))
    except Exception as e:
        logger.error(f'🔥 Ошибка при обработке удаления тикета: {e}', exc_info=True)
        await call.message.answer('Произошла ошибка, попробуйте позже.')

@start_router.message(StarsOrder.stars_order)
async def star_worker(message: Message, state: FSMContext):
    data = await state.get_data()
    timeout_task = data.get('timeout_task')
    if timeout_task:
        timeout_task.cancel()
    logger.info(Fore.BLUE + f"Пользователь оценивает Тикет на {message.text.strip()} " + Style.RESET_ALL)
    reg_data = await state.get_data()
    try:
        stars = float(message.text.strip())
    except ValueError:
        await message.answer("Для оценки оказания услуги пожалуйста введите число от 1 до 10")
        return
    if not (1 <= stars <= 10):
        await message.answer("Оценка должна быть в диапазоне от 1 до 10")
        return
    result = await db.stars_order_update(int(reg_data.get('order_id')), stars)
    if result is True:
        await message.answer(f"Благодарим вас за оценку! {stars}", reply_markup=start_menu)
    else:
        await message.answer(f"Ошибка при оценке. Попробуйте позже.")
        logger.error(Fore.RED + f"Ошибка при оценке Тикета: {result}" + Style.RESET_ALL)
        return
    await state.clear()

@start_router.message(F.text == 'Аккаунты RUST')
async def start_accounts(message: Message):
    logger.info(Fore.BLUE + f"Пользователь {message.from_user.username} (ID: {message.from_user.id}) запустил команду 'Аккаунты RUST'" + Style.RESET_ALL)
    await message.answer("Выберите тип аккаунта", reply_markup=accounts)

@start_router.callback_query(F.data.startswith('zero_accounts'))
async def zero_accounts(call: CallbackQuery):
    logger.info(Fore.BLUE + f"Пользователь {call.from_user.username} (ID: {call.from_user.id}) открыл меню Нулевый аккаунт" + Style.RESET_ALL)
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
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить сейчас", url='https://www.digiseller.market/asp2/pay_wm.asp?id_d=5075738&lang=ru-RU')],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data='accounts_back')]
        ]
    )
    await call.message.edit_text(message_text, parse_mode="HTML", reply_markup=keyboard)

@start_router.callback_query(F.data.startswith('active_accounts'))
async def active_accounts(call: CallbackQuery, bot: Bot):
    logger.info(Fore.BLUE + f"Пользователь {call.from_user.username} (ID: {call.from_user.id}) открыл меню Активный аккаунт" + Style.RESET_ALL)
    image1 = "media/image1.jpg"
    image2 = "media/image2.jpg"
    message_text = (
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
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить сейчас", url='https://www.digiseller.market/asp2/pay_wm.asp?id_d=5075744&lang=ru-RU')],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data='accounts_back')]
        ]
    )
    media = InputMediaPhoto(
        media=FSInputFile(image1),
        caption=message_text,
        parse_mode="HTML"
    )
    try:
        await call.message.edit_media(media=media, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка редактирования: {e}")
        await call.answer("⚠️ Не удалось обновить", show_alert=True)

@start_router.callback_query(F.data.startswith('accounts_back'))
async def accounts_back(call: CallbackQuery):
    logger.info(Fore.BLUE + f"Пользователь {call.from_user.username} (ID: {call.from_user.id}) открыл меню аккаунтов" + Style.RESET_ALL)
    await call.message.delete()
    await call.message.answer("Выберите тип аккаунта", reply_markup=accounts)

@start_router.callback_query(F.data.startswith('close_accounts'))
async def close_accounts(call: CallbackQuery):
    logger.info(Fore.BLUE + f"Пользователь {call.from_user.username} (ID: {call.from_user.id}) закрыл меню аккаунтов" + Style.RESET_ALL)
    await call.message.delete()
