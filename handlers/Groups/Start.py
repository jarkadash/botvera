from typing import Optional, Tuple

from aiogram import Bot, Router, F

from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ChatMemberUpdated, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from database.db import DataBase
from logger import logger
from handlers.Groups.keyboard.inlinekb import *

db = DataBase()
group_router = Router()

class TicketView(StatesGroup):
    user_id = State()
    current_index = State()
    tickets = State()




@group_router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def bot_added_to_chat(event: ChatMemberUpdated):
    """Обработчик добавления бота в чат/группу"""
    logger.info(f"=== СОБЫТИЕ ИЗМЕНЕНИЯ СТАТУСА БОТА ===")
    logger.info(f"Чат: {event.chat.title} (ID: {event.chat.id})")
    logger.info(f"Тип чата: {event.chat.type}")
    logger.info(f"Пользователь, изменивший статус: {event.from_user.username} (ID: {event.from_user.id})")
    logger.info(f"Предыдущий статус: {event.old_chat_member.status}")
    logger.info(f"Новый статус: {event.new_chat_member.status}")
    logger.info(f"ID бота в событии: {event.bot.id}")
    logger.info(f"ID пользователя в новом статусе: {event.new_chat_member.user.id}")
    logger.info(f"Это наш бот? {event.new_chat_member.user.id == event.bot.id}")

    chat = event.chat
    new_member = event.new_chat_member

    # Проверяем, что это именно бот и его добавили
    if new_member.user.id == event.bot.id and new_member.status == "administrator":

        # Проверяем, что это группа/супергруппа (не личный чат)
        if chat.type in ["supergroup"]:

            # Отправляем приветственное сообщение с кнопкой настроек
            welcome_text = (
                f"👋 Приветствую всех в группе *{chat.title}*!\n\n"
                "🤖 Я — бот-помощник для управления заявками и техподдержкой.\n\n"
                "⚙️ Чтобы начать работу, нажмите кнопку *«Настроить бота»* ниже.\n"
                "Там вы сможете:\n"
                "• Прикрепить саппорта к группе\n"
            )

            # Отправляем сообщение
            try:
                await event.bot.send_message(
                    chat_id=chat.id,
                    text=welcome_text,
                    reply_markup=settings_group_kb,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error sending welcome message: {e}")


@group_router.callback_query(F.data.startswith("setup_bot_chat"))
async def setup_bot_chat(call: CallbackQuery):
    result = await db.get_user(call.from_user.id, call.from_user.username)
    if result != 'admin':
        return await call.answer("Вы не администратор", show_alert=True)
    logger.info(f"Пользователь {call.from_user.username} нажал кнопку настройки бота в чате {call.message.chat.id}")
    await call.message.edit_text(
        text="Выберите действие",
        reply_markup=setting_parameters
    )

@group_router.callback_query(F.data.startswith("setup_support_chat"))
async def setup_admin_chat(call: CallbackQuery):
    logger.info(f"Пользователь {call.from_user.username} нажал кнопку назначить саппорта в чат {call.message.chat.id}")
    result = await db.get_user(call.from_user.id, call.from_user.username)
    if result != 'admin':
        return await call.answer("Вы не администратор", show_alert=True)
    supports = await db.get_support_not_assigned_group()

    builder = InlineKeyboardBuilder()
    if not supports:  # Пустой список = False
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="setup_bot_chat")
        )
        await call.message.edit_text(
            text="Нет свободных саппортов",
            reply_markup=builder.as_markup(),
        )
        return

    for support in supports:
        builder.row(
            InlineKeyboardButton(
                text=f"{support.username}",
                callback_data=f"Add_setup_support_chat_{support.id}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="setup_bot_chat")
    )
    await call.message.edit_text(
        text="Выберите пользователя для привязке его к этой группе",
        reply_markup=builder.as_markup()
    )

@group_router.callback_query(F.data.startswith("back_settings_chat"))
async def back_settings_chat(call: CallbackQuery):
    result = await db.get_user(call.from_user.id, call.from_user.username)
    if result != 'admin':
        return await call.answer("Вы не администратор", show_alert=True)
    logger.info("Пользователь вернулся в настройки бота")
    welcome_text = (
        "🤖 Я — бот-помощник для управления заявками и техподдержкой.\n\n"
        "⚙️ Чтобы начать работу, нажмите кнопку *«Настроить бота»* ниже.\n"
        "Там вы сможете:\n"
        "• Прикрепить саппорта к группе\n"
    )
    await call.message.edit_text(
        text = welcome_text,
        reply_markup = settings_group_kb
    )

@group_router.message(Command("start_settings_group"))
async def start_settings_group(message: Message):
    logger.info("Пользователь вернулся в настройки бота")
    result = await db.get_user(message.from_user.id, message.from_user.username)
    if result != 'admin':
        return await message.answer("Вы не администратор", show_alert=True)
    welcome_text = (
        "🤖 Я — бот-помощник для управления заявками и техподдержкой.\n\n"
        "⚙️ Чтобы начать работу, нажмите кнопку *«Настроить бота»* ниже.\n"
        "Там вы сможете:\n"
        "• Прикрепить саппорта к группе\n"
    )
    await message.answer(
        text=welcome_text,
        reply_markup=settings_group_kb
    )

@group_router.callback_query(F.data.startswith("Add_setup_support_chat_"))
async def add_setup_support_chat(call: CallbackQuery):
    logger.info(f'Пользователь назначает сапорта {call.data.split("_")[4]}, группу')
    result = await db.get_user(call.from_user.id, call.from_user.username)
    if result != 'admin':
        return await call.answer("Вы не администратор", show_alert=True)
    support_id = int(call.data.split("_")[4])
    group_id = call.message.chat.id
    add_group = await db.setup_support_groups(support_id, group_id)
    if add_group == 'Support-already-has-groups':
        await call.answer("За этим саппортом уже закреплена группа", show_alert=True)
        return
    if add_group =='The group is linked to another support account':
        await call.answer("Эта группа уже закреплена за другим саппортом", show_alert=True)
        return
    if add_group:
        await call.answer(text="Группа успешно закреплена за саппортом", show_alert=True,)
    else:
        await call.answer(text="Произошла ошибка попробуйте позже", show_alert=True,)


@group_router.callback_query(F.data.startswith("reinstall_support_chat"))
async def start_reinstall_support_chat(call: CallbackQuery):
    result = await db.get_user(call.from_user.id, call.from_user.username)
    if result != 'admin':
        return await call.answer("Вы не администратор", show_alert=True)
    logger.info("Пользователь начал перепривязывать саппортов")
    builder = InlineKeyboardBuilder()
    supports = await db.get_support_assigned_group()

    if not supports:  # Пустой список = False
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="setup_bot_chat")
        )
        await call.message.edit_text(
            text="Нет саппортов",
            reply_markup=builder.as_markup(),
        )
        return

    for support in supports:
        builder.row(
            InlineKeyboardButton(
                text=f"{support.username}",
                callback_data=f"reinstallSupport_chat_{support.id}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="setup_bot_chat")
    )

    await call.message.edit_text(
        text="Выберите саппорта для переназначении группы",
        reply_markup=builder.as_markup(),
    )

@group_router.callback_query(F.data.startswith("reinstallSupport_chat_"))
async def reinstall_support_chat(call: CallbackQuery):
    result = await db.get_user(call.from_user.id, call.from_user.username)
    if result != 'admin':
        return await call.answer("Вы не администратор", show_alert=True)
    logger.info(f"Пользователь, пере привязывает группу для саппорта {call.data.split("_")[2]}")

    support_id = int(call.data.split("_")[2])
    group_id = call.message.chat.id

    reinstall_group = await db.reinstall_group(support_id, group_id)

    if reinstall_group is False:
        await call.answer()
        await call.answer(
            "Ошибка при перезаписи группы",
            show_alert=True,
        )
        return

    await call.answer("Группа успешно перезаписана", show_alert=True)


# Состояния для хранения данных просмотра


@group_router.message(Command("qual"))
async def qual_command(message: Message, state: FSMContext):
    logger.info(f"Получена команда от пользователя: {message.text}")

    # 1. Проверяем, что сообщение в топике (в теме форума)
    if not message.message_thread_id:
        await message.answer(
            "❌ Эта команда доступна только в темах/топиках.\n"
            "Используйте её в конкретной теме поддержки.",
            parse_mode=None
        )
        return

    # 2. Проверяем права доступа
    result = await db.get_user(message.from_user.id, message.from_user.username)
    if result not in ['admin', 'support']:  # Исправлено: or → not in
        await message.answer("❌ Вы не администратор и не саппорт", parse_mode=None)
        return

    # 3. Проверяем аргументы
    args = message.text.split()

    if len(args) != 2:  # Исправлено: 5 → 2 (команда + ID = 2 аргумента)
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Используйте: /qual <ID пользователя>\n"
            "Пример: /qual 876816847",
            parse_mode=None
        )
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID пользователя должен быть числом")
        return

    # 4. Получаем тикеты пользователя
    tickets = await db.get_user_tickets_with_forms(user_id)

    if not tickets:
        await message.answer(f"📭 У пользователя с ID {user_id} нет тикетов с заполненными формами.")
        return

    # 5. Сохраняем данные в состоянии
    await state.update_data(
        user_id=user_id,
        current_index=0,
        tickets=tickets,
        total_tickets=len(tickets),
        thread_id=message.message_thread_id,  # Сохраняем ID топика
        chat_id=message.chat.id  # Сохраняем ID чата
    )

    # 6. Показываем первый тикет
    await show_ticket(message, state, 0)


async def show_ticket(message: Message, state: FSMContext, index: int = 0):
    """Показывает тикет по индексу"""
    data = await state.get_data()
    tickets = data.get('tickets', [])

    if not tickets or index >= len(tickets):
        await message.answer("❌ Ошибка: тикеты не найдены")
        return

    ticket = tickets[index]

    # Формируем сообщение
    response = format_ticket_message(ticket, index + 1, len(tickets))

    # Создаем клавиатуру с навигацией
    keyboard = create_navigation_keyboard(index, len(tickets))

    # Если сообщение уже было отправлено, редактируем его
    if 'message_id' in data:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=data['message_id'],
                text=response,
                reply_markup=keyboard
            )
            return
        except:
            pass

    # Иначе отправляем новое сообщение
    msg = await message.answer(response, reply_markup=keyboard)

    # Сохраняем ID сообщения
    await state.update_data(message_id=msg.message_id, current_index=index)


def format_ticket_message(ticket: dict, current_num: int, total: int) -> str:
    """Форматирует сообщение с информацией о тикете"""
    form = ticket['form']

    # Обработка даты создания
    created_at = ticket.get('created_at')

    if isinstance(created_at, str):
        # Если это строка (уже сериализована), просто используем её
        date_display = created_at
    elif hasattr(created_at, 'strftime'):
        # Если это datetime объект, форматируем
        date_display = created_at.strftime('%d.%m.%Y %H:%M')
    else:
        # Если нет даты
        date_display = "Не указана"

    message = (
        f"🎫 Тикет №{ticket['ticket_id']} ({current_num}/{total})\n"
        f"👤 User ID: {ticket['user_id']}\n"
        f"📛 Username: {ticket['username']}\n"
        f"📊 Статус: {ticket['status']}\n"
        f"📅 Дата создания: {date_display}\n"
        f"\n"
        f"📋 Информация из формы:\n"
    )

    # Добавляем данные формы
    points = []

    # Проверяем, что данные существуют и не пустые
    if form.get('name_cheat') and form['name_cheat'].strip():
        points.append(f"1. {form['name_cheat']}.")

    if form.get('name_game') and form['name_game'].strip():
        points.append(f"2. {form['name_game']}.")

    if form.get('problem_description') and form['problem_description'].strip():
        points.append(f"3. {form['problem_description']}.")

    if form.get('specifications') and form['specifications'].strip():
        points.append(f"4. {form['specifications']}.")

    if points:
        message += "\n".join(points)
    else:
        message += "❌ Нет данных в форме"

    return message


def create_navigation_keyboard(current_index: int, total_tickets: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для навигации"""
    keyboard = []

    # Кнопки навигации
    nav_buttons = []

    if current_index > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"ticket_prev:{current_index}")
        )

    nav_buttons.append(
        InlineKeyboardButton(text=f"{current_index + 1}/{total_tickets}", callback_data="ticket_info")
    )

    if current_index < total_tickets - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="Вперед ▶️", callback_data=f"ticket_next:{current_index}")
        )

    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопка закрытия
    keyboard.append([
        InlineKeyboardButton(text="❌ Закрыть просмотр", callback_data="ticket_close")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@group_router.callback_query(F.data.startswith("ticket_"))
async def handle_ticket_navigation(callback: CallbackQuery, state: FSMContext):
    """Обработчик навигации по тикетам"""
    # Получаем callback_data из callback
    callback_data = callback.data  # ← это строка, например "ticket_prev:0"

    if callback_data == "ticket_close":
        await callback.message.delete()
        await state.clear()
        await callback.answer("Просмотр закрыт")
        return

    elif callback_data == "ticket_info":
        await callback.answer(f"Навигация по тикетам")
        return

    # Получаем данные из состояния (это словарь)
    state_data = await state.get_data()
    tickets = state_data.get('tickets', [])
    current_index = state_data.get('current_index', 0)

    # Проверяем callback_data (строку), а не state_data (словарь)
    if callback_data.startswith("ticket_prev:"):
        # Переход к предыдущему тикету
        new_index = max(0, current_index - 1)

    elif callback_data.startswith("ticket_next:"):
        # Переход к следующему тикету
        new_index = min(len(tickets) - 1, current_index + 1)

    else:
        await callback.answer()
        return

    # Обновляем индекс
    await state.update_data(current_index=new_index)

    # Показываем новый тикет
    await show_ticket(callback.message, state, new_index)
    await callback.answer()