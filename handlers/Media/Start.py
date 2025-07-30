import asyncio

from aiogram import Bot, Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlalchemy.testing.config import any_async
import html

from sqlalchemy.util import await_fallback

from database.db import DataBase
from colorama import Fore, Style
from logger import logger
from core.dictionary import *
from handlers.Media.Keyboard.inlinekeyboard import *
from config import *
from urllib.parse import urlparse
from more_itertools import chunked

db = DataBase()
media_router = Router()


class MediaAdd(StatesGroup):
    url = State()
    description = State()
    name_cheat = State()


@media_router.message(F.text == '📸 Меню')
async def start_media_menu(message: Message):
    logger.info(Fore.BLUE + f"Пользователь {message.from_user.username}, id: {message.from_user.id} нажал на кнопку "
                            f"media Меню" + Style.RESET_ALL)

    # Проверяем роль пользователя в базе данных
    result = await db.check_role(message.from_user.id)

    # Если роль не найдена или пользователь не имеет роли, сообщаем об ошибке
    if not result or not hasattr(result, 'role_name'):
        await message.answer('Ошибка! У вас нет доступа к этому меню. Введите /start для возврата.')
        return  # Завершаем выполнение функции

    # Проверяем, что роль == 'media'
    if result.role_name != 'media':
        await message.answer('Ошибка! У вас нет доступа к этому меню. Введите /start для возврата.')
        return  # Завершаем выполнение функции

    # Отправляем меню после проверки
    await message.answer("Выберите действие:", reply_markup=media_menu_kb)


@media_router.callback_query(F.data == 'media_add')
async def start_media_add(call: CallbackQuery, state: FSMContext):
    logger.info(Fore.BLUE + f"Пользователь {call.from_user.username}, id: {call.from_user.id} "
                            f"начал добавление медиа" + Style.RESET_ALL)

    await call.message.delete()
    await call.message.answer('Введите ссылку на видео:')
    await state.set_state(MediaAdd.url)


from urllib.parse import urlparse


@media_router.message(MediaAdd.url)
async def media_add_url(message: Message, state: FSMContext):
    logger.info(Fore.BLUE + f"Пользователь {message.from_user.username}, id: {message.from_user.id} "
                            f"ввел ссылку на видео: {message.text}" + Style.RESET_ALL)

    url = message.text
    parsed_url = urlparse(url)

    # Проверяем схему и хост
    if parsed_url.scheme != 'https':
        await message.answer('Ошибка! Ссылка должна использовать протокол HTTPS.')
        return

    # Разрешенные домены
    allowed_domains = ['www.youtube.com', 'youtube.com', 'youtu.be', 'rutube.ru', 'www.rutube.ru', 'www.youtu.be']

    if parsed_url.netloc not in allowed_domains:
        logger.info(Fore.BLUE + f"Пользователь {message.from_user.username}, id: {message.from_user.id} "
                                f"ввел неверную ссылку" + Style.RESET_ALL)
        await message.answer(
            'Ошибка! Неверная ссылка!\n\n'
            'Ваша ссылка для YouTube/Rutube должна начинаться с:\n'
            '- https://www.youtube.com/\n'
            '- https://youtu.be/\n'
            '- https://rutube.ru/\n'
            '- https://www.rutube.ru/'
        )

        return

    await state.update_data(url=url)
    await message.answer('Введите ваш никнейм на ютубе(Рутубе):')
    logger.info(Fore.BLUE + f"Пользователь {message.from_user.username}, id: {message.from_user.id} "
                            f"просим ввести никнейм" + Style.RESET_ALL)
    await state.set_state(MediaAdd.description)


@media_router.message(MediaAdd.description)
async def media_add_description(message: Message, state: FSMContext):
    logger.info(Fore.BLUE + f"Пользователь {message.from_user.username}, id: {message.from_user.id}"
                            f" ввел описание видео: {message.text}" + Style.RESET_ALL)
    description = message.text
    if len(description) > 255:
        await message.answer(f'Ошибка! Описание слишком длинное!\n\n')
        return
    await state.update_data(description=description)
    await message.answer('Введите название чита:')
    await state.set_state(MediaAdd.name_cheat)


# Основная функция для добавления медиа
@media_router.message(MediaAdd.name_cheat)
async def media_add_name_cheat(message: Message, state: FSMContext):
    logger.info(Fore.BLUE + f"Пользователь {message.from_user.username}, id: {message.from_user.id} "
                            f"ввел название чита: {message.text}" + Style.RESET_ALL)

    name_cheat = message.text
    if len(name_cheat) > 50:
        await message.answer('Ошибка! Название чита слишком длинное! Оно не должно превышать 50 символов!\n\n')
        return
    await state.update_data(name_cheat=name_cheat)
    data = await state.get_data()

    # Добавляем медиа в БД
    result = await db.media_add(message.from_user.id, data['url'], data['description'], data['name_cheat'])
    if not result:
        await message.answer('Ошибка! При добавлении Медиа, повторите позже! Либо свяжитесь с администрацией!')

    # Получаем всех пользователей
    users = await db.get_user_all()
    user_id = [user.user_id for user in users]

    # Начинаем рассылку
    result = await start_send(message, user_id, data['description'], data['name_cheat'], data['url'])
    if result != True:
        await message.answer('Ошибка! При рассылке, повторите позже! Либо свяжитесь с администрацией!')

    user_count = get_sent_count()
    sent_count_value, error_count_value = user_count
    logger.info(
        Fore.BLUE + f'Отправлено: {sent_count_value} Не удалось отправить: {error_count_value} пользователей!' + Style.RESET_ALL)
    await message.answer(f'📸 Медиа успешно добавлено!\n\n'
                         f'Рассылка завершена!\n\n'
                         )
    await state.clear()

# Функция для массовой рассылки
async def start_send(message: Message, users: list, description: str, name_cheat: str, url: str,
                     batch_size: int = 100, delay: float = 1.5):
    logger.info(Fore.BLUE + "Начинаем рассылку!" + Style.RESET_ALL)

    # Создаём текст для рассылки
    text_send = (
        f'📢 <b>Новый видео обзор чита: «{name_cheat}»</b> 🎮\n'
        f'👤 <i>Автор:</i> <b>{description}</b>\n\n'
        f'▶️ <a href="{url}">Смотреть видео</a>\n\n'
        f'📡 Больше новостей здесь: @gamebreakernews'
    )
    bot = message.bot
    await bot.send_message(chat_id=GROUP_CHAT_ID, text=text_send)

    # Разбиваем пользователей на группы
    for batch in chunked(users, batch_size):
        tasks = [send_message(user, text_send, message.bot) for user in batch]
        await asyncio.gather(*tasks)  # Асинхронно отправляем сообщения всем в пачке

        logger.info(Fore.BLUE + f"✅ Отправлено {len(batch)} пользователям. Ждём {delay} сек..." + Style.RESET_ALL)
        await asyncio.sleep(delay)  # Задержка перед отправкой следующей группы

    return True


sent_count = 0
error_count = 0


# Функция для отправки сообщения одному пользователю
async def send_message(user_id: int, text: str, bot: Bot):
    global sent_count
    global error_count
    try:
        await bot.send_message(chat_id=user_id, text=text)
        sent_count += 1  # Увеличиваем счетчик
        logger.info(Fore.BLUE + f"✅ Сообщение отправлено пользователю {user_id}" + Style.RESET_ALL)
    except TelegramAPIError as e:
        logger.warning(Fore.YELLOW + f"⚠️ Ошибка при отправке пользователю {user_id}: {e}" + Style.RESET_ALL)
        error_count += 1  # Увеличиваем счетчик ошибок


def get_sent_count():
    return sent_count, error_count


@media_router.callback_query(F.data == 'media_statistic')
async def start_media_statistic(call: CallbackQuery):
    logger.info(Fore.BLUE + f'Пользователь {call.from_user.username}, id: {call.from_user.id} нажал на кнопку '
                            f'media statistic' + Style.RESET_ALL)

    result = await db.check_role(call.from_user.id)
    if not result or not hasattr(result, 'role_name') and result.role_name != 'media':
        await call.message.answer('Ошибка! У вас нет доступа к этому меню. Введите /start для возврата.')
        return

    static = await db.get_statistic_media(call.from_user.id)
    if not static:
        await call.message.answer('Ошибка! При получении статистики, повторите позже! Либо свяжитесь с администрацией!')
        return

    count = len(static)

    await call.message.answer(f'📊 Статистика медиа:\n\n'
                              f'Всего видео: {count}')
