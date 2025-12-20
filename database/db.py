import asyncio
import time
import pytz
from aiogram import Bot
from dotenv import load_dotenv
from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.operators import exists
from Utils import get_calculated_period, filter_tickets_for_statistics, order_to_dict
from database.models import *
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
import redis.asyncio as redis

from logger import logger
from colorama import Fore, Style
import os
from datetime import datetime, timedelta
from sqlalchemy import text
from handlers.Groups.create_topic_in_group import GroupManager, group_manager

gp = GroupManager()

load_dotenv()

redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST'),
    port=os.getenv('REDIS_PORT'),
    password=os.getenv('REDIS_PASSWORD'),  # Сырой пароль
    username=os.getenv('REDIS_USER'),
    decode_responses=True,
)

DEFAULT_RATES = {
    "technical_support": 60,
    "payment_support": 30,
    "hwid_reset": 30,
    "get_key": 100,
    "reselling": 30,
    "bonus_per_50": 1000
}


def seconds_to_hms(seconds: float) -> str:
    """
    Конвертирует количество секунд в строку формата HH:MM:SS.

    Args:
        seconds (float): Количество секунд.

    Returns:
        str: Время в формате HH:MM:SS.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class DataBase:

    async def count_active_for(self, support_id: int) -> int:
        async with self.Session() as session:
            try:
                result = await session.execute(
                    select(func.count(Orders.id)).where(
                        Orders.support_id == support_id,
                        Orders.status == 'at work'
                    )
                )
                cnt = result.scalar() or 0
                return int(cnt)
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка count_active_for: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
            finally:
                await session.close()

    def __init__(self):
        self.db_host = os.getenv('DB_HOST')
        self.db_port = os.getenv('DB_PORT')
        self.db_name = os.getenv('DB_NAME')
        self.db_user = os.getenv('DB_USER')
        self.db_password = os.getenv('DB_PASS')
        self.connect = f"postgresql+asyncpg://{self.db_user}:{self.db_password.strip()}@{self.db_host}:{self.db_port}/{self.db_name}"
        self.async_engine = create_async_engine(
            url=self.connect,
            pool_size=10,
            max_overflow=15,
            pool_timeout=5,  # Таймаут ожидания соединения из пула
            pool_recycle=1800,  # Перезапуск соединения через 30 минут
            pool_pre_ping=True
        )
        self.Session = async_sessionmaker(bind=self.async_engine, class_=AsyncSession,
                                          autocommit=False,
                                          )

    async def create_db(self):
        try:
            async with self.async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await self.add_initial_db()
                logger.info(Fore.BLUE + f'База данных создана(загружена)!' + Style.RESET_ALL)
        except Exception as e:
            logger.error(Fore.RED + f'Ошибка при создании базы данных: {e}' + Style.RESET_ALL)
            await conn.rollback()
            raise
        finally:
            await conn.close()

    async def add_initial_db(self):
        async with self.Session() as session:
            try:
                result = await session.execute(select(Roles))
                roles = result.scalars().all()
                if not roles:
                    admin_role = Roles(role_name='admin')
                    support_role = Roles(role_name='support')
                    media_role = Roles(role_name='media')
                    session.add_all([admin_role, support_role, media_role])
                    await session.commit()
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при создании базы данных: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_user(self, user_id, username):
        async with self.Session() as session:
            try:
                # Основной запрос с JOIN
                query = (
                    select(
                        Users,
                        BannedUsers.user_id.label('banned_user_id'),
                        Roles.role_name
                    )
                    .outerjoin(BannedUsers, Users.user_id == BannedUsers.user_id)
                    .outerjoin(Roles, Users.role_id == Roles.id)
                    .where(Users.user_id == user_id)
                )

                result = await session.execute(query)
                user_data = result.first()

                # Обработка результатов
                if user_data:
                    user, banned_user_id, role_name = user_data
                    if banned_user_id:
                        return 'Banned'

                    # Обновление username при необходимости
                    if user.username != username:
                        user.username = username
                        session.add(user)
                        await session.commit()
                        logger.info(f'Пользователь {user_id} обновлен!')

                    # Проверка роли
                    if role_name:
                        logger.info(f'Пользователь {user_id} имеет роль {role_name}')
                        return role_name
                    else:
                        logger.warning(f'Пользователь {user_id} не имеет роли!')
                        return True
                else:
                    # Создание нового пользователя
                    new_user = Users(user_id=user_id, username=username)
                    session.add(new_user)
                    await session.commit()
                    logger.info(f'Пользователь {user_id} добавлен!')
                    return True

            except Exception as e:
                logger.error(f'Ошибка: {e}')
                await session.rollback()
                raise

    async def get_services(self):
        async with self.Session() as session:
            try:
                services = await session.execute(select(Services))
                services = services.scalars().all()
                return services
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при получении услуг: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return f'Ошибка при получении услуг: {e}'
            finally:
                await session.close()

    async def count_user_service_requests_today(self, user_id: int, service_name: str):
        async with self.Session() as session:
            try:
                tz = pytz.timezone('Europe/Moscow')
                now_msk = datetime.now(tz)
                start_msk = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)
                end_msk = start_msk + timedelta(days=1)
                start_utc_naive = start_msk.astimezone(pytz.utc).replace(tzinfo=None)
                end_utc_naive = end_msk.astimezone(pytz.utc).replace(tzinfo=None)

                result = await session.execute(
                    select(func.count(Orders.id)).where(
                        Orders.client_id == user_id,
                        Orders.service_name == service_name,
                        Orders.created_at >= start_utc_naive,
                        Orders.created_at < end_utc_naive
                    )
                )
                return int(result.scalar() or 0)
            finally:
                await session.close()

    async def get_banned_users(self, user_id):
        async with self.Session() as session:
            try:
                banned_users = await session.execute(select(BannedUsers).where(BannedUsers.user_id == user_id))
                banned_users = banned_users.scalars().first()
                if banned_users is not None:
                    return True
                return False
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при получении забаненных пользователей: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return f'Ошибка при получении забаненных пользователей: {e}'
            finally:
                await session.close()

    async def add_orders(self, service_id, user_id):
        async with self.Session() as session:
            try:
                order_active = await session.execute(
                    select(Orders).filter(
                        Orders.client_id == user_id,
                        Orders.status.in_(['at work', 'paused', 'new'])
                    )
                )
                result = order_active.scalars().all()
                if result:
                    return "Active-Ticket"

                services = await session.execute(select(Services).where(Services.id == service_id))

                service = services.scalars().first()

                user = await session.execute(select(Users).where(Users.user_id == user_id))
                user = user.scalars().first()

                new_order = Orders(
                    client_id=user_id,
                    client_name=str(user.username),
                    service_id=service_id,
                    service_name=str(service.service_name),
                    status='new',
                )
                session.add(new_order)
                await session.flush()  # Получаем ID нового заказа
                await session.commit()  # Подтверждаем изменения в базе
                # Обновляем объект после коммита
                await session.refresh(new_order)

                return {
                    'id': new_order.id,
                    'client_id': new_order.client_id,
                    'client_name': new_order.client_name,
                    'service_id': new_order.service_id,
                    'service_name': new_order.service_name,
                    'status': new_order.status,
                    'created_at': new_order.created_at.strftime("%d-%m-%Y %H:%M")
                }
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при добавлении Тикета: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def get_admin_by_id(self, user_id):
        async with self.Session() as session:
            try:
                admin = await session.execute(select(Users).where(Users.user_id == user_id))
                admin = admin.scalars().first()

                roles = await session.execute(select(Roles).where(Roles.id == admin.role_id))
                roles = roles.scalars().first()

                # Проверяем, найден ли объект role перед обращением к его атрибутам
                if roles is None:
                    logger.warning(Fore.YELLOW + f'Роль с id {admin.role_id} не найдена в базе!' + Style.RESET_ALL)
                    return False

                if roles.role_name == 'admin':
                    return True
                else:
                    return False

            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при получении админа: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def add_roles(self, role_name):
        async with self.Session() as session:
            try:
                result = await session.execute(select(Roles).where(Roles.role_name == role_name))
                result = result.scalars().first()
                if result is not None:
                    return "Name_is_occupied"
                else:
                    role = Roles(role_name=role_name)
                    session.add(role)
                    await session.commit()
                    logger.info(Fore.BLUE + f'Роль {role_name} добавлена в базу данных!' + Style.RESET_ALL)
                    return True
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при добавлении роли: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return f'Ошибка при добавлении роли: {e}'
            finally:
                await session.close()

    async def get_roles(self):
        async with self.Session() as session:
            try:
                roles = await session.execute(select(Roles))
                roles = roles.scalars().all()
                return roles
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при получении ролей: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return f'Ошибка при получении ролей: {e}'
            finally:
                await session.close()

    async def delete_roles(self, role_id):
        async with self.Session() as session:
            try:
                result = await session.execute(select(Roles).where(Roles.id == role_id))
                result = result.scalars().first()
                if result is not None:
                    await session.execute(delete(Roles).where(Roles.id == role_id))
                    await session.commit()
                    return True
                else:
                    return 'Роль не найдена!'
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при удалении роли: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return f'Ошибка при удалении роли: {e}'
            finally:
                await session.close()

    async def add_service(self, name, roles):
        async with self.Session() as session:
            try:
                new_service = Services(service_name=name, allowed_roles=roles)
                session.add(new_service)
                await session.commit()
                logger.info(Fore.BLUE + f'Услуга {name} добавлена в базу данных!' + Style.RESET_ALL)
                return True
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при добавлении услуги: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def service_delete(self, service_id):
        async with self.Session() as session:
            try:
                result = await session.execute(select(Services).where(Services.id == service_id))
                result = result.scalars().first()
                if result is not None:
                    await session.execute(delete(Services).where(Services.id == service_id))
                    await session.commit()
                    return True
                else:
                    return 'Услуга не найдена!'
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при удалении услуги: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return f'Ошибка при удалении услуги: {e}'
            finally:
                await session.close()

    async def banned_users(self, user_id):
        async with self.Session() as session:
            user_id = int(user_id)
            try:
                user = await session.execute(select(Users).where(Users.user_id == user_id))
                user = user.scalars().first()
                if user is not None:
                    banned_users = await session.execute(select(BannedUsers).where(BannedUsers.user_id == user_id))
                    banned_users = banned_users.scalars().first()
                    if banned_users is not None:
                        return 'Пользователь уже в черном списке!'
                    else:
                        banned_user = BannedUsers(user_id=user_id, username=user.username)
                        session.add(banned_user)
                        await session.commit()
                        return True
                else:
                    return 'Пользователь не найден!'
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при получении пользователя: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return f'Ошибка при получении пользователя: {e}'
            finally:
                await session.close()

    async def delete_banned_users(self, user_id):
        async with self.Session() as session:
            user_id = int(user_id)
            try:
                result = await session.execute(select(BannedUsers).where(BannedUsers.user_id == user_id))
                result = result.scalars().first()
                if result is not None:
                    await session.execute(delete(BannedUsers).where(BannedUsers.user_id == user_id))
                    await session.commit()
                    return True
                else:
                    return 'Пользователь не найден!'
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при удалении пользователя: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return f'Ошибка при удалении пользователя: {e}'
            finally:
                await session.close()

    async def get_users_by_username(self, username):
        async with self.Session() as session:
            try:
                users = await session.execute(select(Users).where(Users.username == username))
                users = users.scalars().all()
                if users is None:
                    return 'Пользователь не найден!'

                return users
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при получении пользователя: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def add_user_role(self, username, role_id):
        async with self.Session() as session:
            try:
                # Асинхронный запрос для пользователя
                user_result = await session.execute(
                    select(Users).where(Users.username == username)
                )
                user = user_result.scalars().first()

                # Асинхронный запрос для роли
                role_result = await session.execute(
                    select(Roles).where(Roles.id == role_id)
                )
                role = role_result.scalars().first()

                if not user:
                    return False

                if not role:
                    return False

                # Обновление роли
                user.role_id = role_id
                logger.info(f'Роль пользователя {username} изменена на {role_id}!')
                await session.commit()
                await session.refresh(role)  # Обновляем объект пользователя после коммита
                await session.refresh(user)  # Обновляем объект пользователя после коммита

                return {
                    "user_id": user.user_id,
                    "username": user.username,
                    "role_name": role.role_name
                }

            except Exception as e:
                logger.error(f'Ошибка: {e}')
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def get_user_role(self):
        async with self.Session() as session:
            try:
                user = await session.execute(select(Users).where(Users.role_id.isnot(None)))
                users = user.scalars().all()
                if users is None:
                    return 'Пользователь не найден!'
                else:
                    return users
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при получении пользователя: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def delete_user_role(self, user_id):
        async with self.Session() as session:
            try:
                user = await session.execute(select(Users).where(Users.user_id == user_id))
                user = user.scalars().first()
                if user is not None:
                    user.role_id = None
                    await session.commit()
                    return True
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при получении пользователя: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def accept_orders(self, order_id, user_id):
        async with self.Session() as session:
            try:
                # Получаем заказ (проверка существования)
                order = await session.get(Orders, order_id)
                if not order:
                    logger.warning(f'Заказ {order_id} не найден!')
                    return False
                elif order.status != 'new':
                    return 'Not-New'

                # Получаем саппорта
                user_result = await session.execute(
                    select(Users).where(Users.user_id == user_id)
                )
                user = user_result.scalars().first()
                if not user:
                    logger.warning(f'Пользователь {user_id} не найден')
                    return False

                # Сохраняем username ДО любых операций с базой, которые могут закрыть сессию
                support_username = user.username  # ЗАГРУЖАЕМ СЕЙЧАС!


                # Проверяем роль и права по сервису
                if user.role_id is None:
                    logger.warning(f'У пользователя {user_id} нет роли')
                    return False

                service = await session.get(Services, order.service_id)
                if not service or not service.allowed_roles:
                    logger.warning(f'Сервис {order.service_id} не найден или нет разрешенных ролей')
                    return False

                try:
                    allowed_roles = {
                        int(role.strip())
                        for role in service.allowed_roles.replace('.', ',').split(',')
                        if role.strip().isdigit()
                    }
                except ValueError as e:
                    logger.error(f'Ошибка парсинга allowed_roles: {e}')
                    raise

                if user.role_id not in allowed_roles:
                    logger.warning(f'Роль {user.role_id} не разрешена для сервиса {service.id}')
                    return False

                # === АТОМАРНОЕ принятие тикета ===
                result = await session.execute(
                    update(Orders)
                    .where(Orders.id == order_id, Orders.status == 'new')
                    .values(
                        support_id=user_id,
                        support_name=support_username,  # Используем сохраненное имя
                        status='at work',
                        accept_at=datetime.now()
                    )
                    .returning(Orders)
                )

                updated_order = result.scalar_one_or_none()

                if updated_order is None:
                    logger.info(f'Тикет {order_id} уже был принят другим саппортом')
                    return 'Not-New'

                # Получаем группу
                get_id_group = await self.get_id_groups(user.id)
                if get_id_group is False:
                    logger.warning(f'Не найдена группа для пользователя {user.id}')
                    await session.rollback()
                    return False

                # Проверяем, инициализирован ли бот
                if group_manager.bot is None:
                    logger.error("GroupManager не инициализирован: бот не установлен")
                    await session.rollback()
                    return False

                # Создаем топик
                thread_id, success = await group_manager.create_user_topic(
                    order_id=order_id,
                    group_id=get_id_group.group_id
                )

                if not success or thread_id is None:
                    logger.error(f'Не удалось создать топик для заказа {order_id}')
                    await session.rollback()
                    return False

                # Получаем клиента
                if not hasattr(order, 'client_id') or order.client_id is None:
                    logger.error(f'У заказа {order_id} нет client_id')
                    await session.rollback()
                    return False

                query = select(Users).where(Users.user_id == order.client_id)
                result = await session.execute(query)
                client = result.scalars().first()
                if not client:
                    logger.error(f'Клиент {order.client_id} не найден в базе')
                    await session.rollback()
                    return False

                # Добавляем запись о тикете в группе поддержки
                add_tikets = TicketsIdSupportGroupsModel(
                    order_id=order_id,
                    group_id=get_id_group.id,
                    thread_id=thread_id,
                    support_id=user.id,
                    user_id=client.id
                )
                session.add(add_tikets)
                await session.flush()

                # Делаем commit всех изменений
                await session.commit()

                # Обновляем и отсоединяем объект
                await session.refresh(updated_order)

                # ВАЖНО: Загружаем все ленивые атрибуты ПЕРЕД отсоединением
                if hasattr(updated_order, 'client_name'):
                    _ = updated_order.client_name  # Загружаем
                if hasattr(updated_order, 'service_name'):
                    _ = updated_order.service_name  # Загружаем
                if hasattr(updated_order, 'support_name'):
                    _ = updated_order.support_name  # Загружаем

                session.expunge(updated_order)

                logger.info(
                    f'Тикет №{order_id} успешно принят пользователем {support_username} ({user_id}). '
                    f'Создана тема в группе: {get_id_group.group_id}, thread_id: {thread_id}'
                )

                return {"updated_order": updated_order, "group_id": get_id_group.group_id, "thread_id": thread_id}

            except Exception as e:
                logger.error(f'Критическая ошибка в accept_orders: {e}', exc_info=True)
                if session.in_transaction():
                    await session.rollback()
                return False

    async def get_latest_topic_info(self, support_id):
        """
        Получает thread_id и group_id последнего топика для саппорта
        """
        try:
            async with self.Session() as session:
                query = (
                    select(
                        TicketsIdSupportGroupsModel.thread_id,
                        GroupsSupportModel.group_id
                    )
                    .join(GroupsSupportModel, GroupsSupportModel.id == TicketsIdSupportGroupsModel.group_id)
                    .where(TicketsIdSupportGroupsModel.support_id == support_id)
                    .order_by(TicketsIdSupportGroupsModel.created_at.desc())
                    .limit(1)
                )

                result = await session.execute(query)
                row = result.first()

                if row:
                    # row - это кортеж (thread_id, group_id)
                    thread_id, group_id = row
                    return {
                        'thread_id': thread_id.thread_id,
                        'group_id': group_id.group_id
                    }
                return None

        except Exception as e:
            logger.error(f"Ошибка при получении информации о топике: {e}")
            return None

    async def get_add_tikets_in_group_support(self, thread_id, group_id, support_id, client_id):
        try:
            async with self.Session() as session:
                add_tikets = TicketsIdSupportGroupsModel(
                    group_id=group_id,
                    thread_id=thread_id,
                    support_id=support_id,
                    user_id=client_id
                )

                session.add(add_tikets)
                await session.commit()
                return True
        except Exception as e:
            logger.error(f'Критическая ошибка: {e}', exc_info=True)
            await session.rollback()
            return False
        finally:
            await session.close()

    async def get_id_groups(self, user_id):
        try:
            async with self.Session() as session:
                query = select(GroupsSupportModel).where(GroupsSupportModel.support_id == user_id)
                result = await session.execute(query)
                groups = result.scalars().first()
                return groups if groups is not None else False

        except Exception as e:
            logger.error(f"Ошибка при получении id группы: {e}")  # Исправлена f-строка
            return False

    async def get_support(self, user_id):
        async with self.Session() as session:
            try:
                user = await session.execute(select(Users).where(Users.user_id == user_id))
                user = user.scalars().first()
                if user is not None and user.role_id is not None:
                    return True
                else:
                    return False
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка при получении пользователя: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def close_order(self, order_id):
        async with self.Session() as session:
            try:
                order = await session.get(Orders, order_id)
                if not order:
                    logger.warning(Fore.YELLOW + f'Тикет {order_id} не найден!' + Style.RESET_ALL)
                    return 'Тикет не найден!'

                if order.status in ['at work', 'paused']:
                    order.status = 'closed'
                    order.completed_at = datetime.now()
                    result = await session.execute(
                        select(TicketsIdSupportGroupsModel)
                        .where(TicketsIdSupportGroupsModel.order_id == order_id)
                    )
                    topic = result.scalar_one_or_none()

                    # Удаляем если найдена
                    if topic:
                        await session.delete(topic)
                        await session.commit()
                    await session.commit()
                    await session.refresh(order)

                    return {
                        'client_id': order.client_id,
                        'support_id': order.support_id
                    }
                else:
                    return 'Тикет уже закрыт!'
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def get_orders_by_id(self, order_id):
        async with self.Session() as session:
            try:
                order = await session.get(Orders, order_id)
                if not order:
                    logger.warning(Fore.RED + f'Тикет {order_id} не найден!' + Style.RESET_ALL)
                    return False
                return order
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def check_role_for_service(self, user_id, order_id):
        async with self.Session() as session:
            try:
                order = await session.get(Orders, order_id)
                if not order:
                    logger.warning(Fore.RED + f'Тикет {order_id} не найден!' + Style.RESET_ALL)
                    return False
                user = await session.execute(select(Users).where(Users.user_id == user_id))
                user = user.scalars().first()
                service = await session.get(Services, order.service_id)
                if not user:
                    logger.warning(Fore.RED + f'Пользователь {user_id} не найден!' + Style.RESET_ALL)
                    return False

                if service.allowed_roles == 'all':
                    return True
                elif str(user.role_id) in service.allowed_roles:
                    return True
                else:
                    return False
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def cancel_order(self, order_id, user_id, description):
        async with self.Session() as session:
            try:
                order = await session.get(Orders, order_id)
                user = await session.execute(select(Users).where(Users.user_id == user_id))
                user = user.scalars().first()
                if not order:
                    logger.warning(Fore.RED + f'Тикет {order_id} не найден!' + Style.RESET_ALL)
                    return False

                if str(order.status).lower() != 'new':
                    logger.info(
                        Fore.YELLOW + f'Отмена тикета {order_id} отклонена: статус {order.status} не new' + Style.RESET_ALL)
                    return 'STATUS_NOT_NEW'

                order.status = 'canceled'
                order.accept_at = datetime.now()
                order.completed_at = datetime.now()
                order.description = description
                order.support_id = user.user_id
                order.support_name = user.username
                await session.commit()
                await session.refresh(order)
                return order
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_auto_close_order(self, order_id, reason: str = "Авто-закрытие (Клиент не ответил)", bot: Bot = None):
        """
        Автоматическое закрытие тикета
        """
        import traceback
        import asyncio

        logger.info(f"🔧 [DEBUG] Вызов get_auto_close_order для тикета #{order_id}")

        async with self.Session() as session:
            try:
                logger.debug(f"📝 [TICKET #{order_id}] 1. Получение тикета из БД...")

                # 1. Получаем тикет с явной загрузкой всех необходимых атрибутов
                order = await session.get(Orders, order_id)
                if not order:
                    logger.warning(f'❌ Тикет {order_id} не найден!')
                    return {
                        "success": False,
                        "error": "Тикет не найден",
                        "order_id": order_id
                    }

                # 2. СОХРАНЯЕМ ВАЖНЫЕ ДАННЫЕ ДО КОММИТА!
                client_id = order.client_id
                service_name = order.service_name
                current_status = order.status

                logger.debug(f"📝 [TICKET #{order_id}] 2. Проверка статуса... (текущий: {current_status})")

                # 3. Проверяем, можно ли закрыть тикет
                if current_status in ['closed', 'cancelled', 'canceled']:
                    logger.info(f'ℹ️ Тикет {order_id} уже закрыт (статус: {current_status})')
                    return {
                        "success": False,
                        "error": f"Тикет уже закрыт (статус: {current_status})",
                        "order_id": order_id,
                        "status": current_status
                    }

                if current_status not in ['at work', 'paused', 'new']:
                    logger.warning(f'⚠️ Неожиданный статус тикета {order_id}: {current_status}')
                    return {
                        "success": False,
                        "error": f"Неожиданный статус: {current_status}",
                        "order_id": order_id,
                        "status": current_status
                    }

                logger.debug(f"📝 [TICKET #{order_id}] 3. Обновление статуса...")

                # 4. Обновляем статус тикета
                order.status = 'closed'
                order.completed_at = datetime.now()
                order.description = reason

                # 5. Получаем информацию о топике Telegram
                thread_id = None
                support_group_id = None
                topic_found = False
                topic_deleted = False

                logger.debug(f"📝 [TICKET #{order_id}] 4. Поиск топика в группах поддержки...")

                try:
                    result = await session.execute(
                        select(TicketsIdSupportGroupsModel, GroupsSupportModel)
                        .join(
                            GroupsSupportModel,
                            GroupsSupportModel.id == TicketsIdSupportGroupsModel.group_id
                        )
                        .where(TicketsIdSupportGroupsModel.order_id == order_id)
                    )

                    row = result.first()
                    if row:
                        ticket, group = row
                        thread_id = ticket.thread_id
                        support_group_id = group.group_id
                        topic_found = True

                        logger.info(f"📌 Найден топик: thread_id={thread_id}, group_id={support_group_id}")

                        # Удаляем топик в Telegram, если есть бот
                        if bot and thread_id and support_group_id:
                            try:
                                # Пытаемся удалить топик (форум-топик) в Telegram
                                await bot.delete_forum_topic(
                                    chat_id=support_group_id,
                                    message_thread_id=thread_id
                                )
                                topic_deleted = True
                                logger.info(f"🗑️ Топик {thread_id} удален в Telegram")
                            except Exception as telegram_error:
                                logger.error(f"⚠️ Не удалось удалить топик в Telegram: {telegram_error}")
                                # Если не удалось удалить топик, можно попробовать закрыть его
                                try:
                                    await bot.close_forum_topic(
                                        chat_id=support_group_id,
                                        message_thread_id=thread_id
                                    )
                                    logger.info(f"🔒 Топик {thread_id} закрыт в Telegram")
                                except Exception as close_error:
                                    logger.error(f"⚠️ Не удалось закрыть топик в Telegram: {close_error}")
                        else:
                            logger.warning(f"ℹ️ Бот не предоставлен для удаления топика")

                        # Удаляем запись о топике из БД
                        await session.delete(ticket)
                        logger.debug(f"🗑️ Запись топика удалена из БД")
                    else:
                        logger.info(f"ℹ️ Топик не найден для тикета {order_id}")

                except Exception as topic_error:
                    logger.error(f"⚠️ Ошибка при поиске/удалении топика: {topic_error}")
                    # Продолжаем закрытие тикета даже без удаления топика

                logger.debug(f"📝 [TICKET #{order_id}] 5. Коммит изменений в БД...")

                # 6. Коммитим все изменения
                await session.commit()

                # 7. ИСПОЛЬЗУЕМ СОХРАНЕННЫЕ ДАННЫЕ, А НЕ ОБЪЕКТ ПОСЛЕ КОММИТА
                logger.info(f"✅ [SUCCESS] Тикет {order_id} успешно авто-закрыт")
                logger.info(f"   📊 Статистика: клиент={client_id}, сервис={service_name}")

                return {
                    "success": True,
                    "order_id": order_id,
                    "thread_id": thread_id,
                    "group_id": support_group_id,
                    "client_id": client_id,
                    "topic_found": topic_found,
                    "topic_deleted": topic_deleted,
                    "status": "closed",
                    "service_name": service_name
                }

            except Exception as e:
                logger.error(f'❌ [ERROR] Ошибка при авто-закрытии тикета {order_id}: {e}', exc_info=True)
                logger.error(f'   🐛 Детали: тип ошибки: {type(e).__name__}')

                try:
                    await session.rollback()
                    logger.debug("🔄 Откат транзакции выполнен")
                except:
                    pass

                return {
                    "success": False,
                    "error": str(e),
                    "order_id": order_id,
                    "type": type(e).__name__
                }

    async def check_role(self, user_id):
        async with self.Session() as session:
            try:
                user = await session.execute(select(Users).where(Users.user_id == user_id))
                user = user.scalars().first()
                if user is not None:
                    if user.role_id is None:
                        return False  # Если роль не назначена, возвращаем False

                    role = await session.execute(select(Roles).where(Roles.id == user.role_id))
                    role = role.scalars().first()
                    return role  # Возвращаем объект роли
                else:
                    return False  # Если пользователь не найден, возвращаем False
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False  # В случае ошибки также возвращаем False
            finally:
                await session.close()

    async def statistics_user_by_id(self, support_id: int, start_date: datetime.date, end_date: datetime.date):
        try:
            async with self.Session() as session:
                user = await session.scalar(
                    select(Users).where(Users.user_id == support_id)
                )
                if not user:
                    logger.info(f"[DEBUG] Пользователь с ID {support_id} не найден в таблице users.")
                    return {"error": "Пользователь не найден"}

                # Получаем отфильтрованные тикеты
                filtered_orders, excluded_orders = await filter_tickets_for_statistics(
                    session, support_id, start_date, end_date
                )
                tickets = filtered_orders

                if not tickets:
                    logger.info(
                        f"[DEBUG] У пользователя ID {support_id} нет тикетов в диапазоне {start_date} – {end_date}")
                    return {"error": "Нет тикетов в указанном диапазоне"}

                total = len(tickets)
                total_all_time = await session.scalar(
                    select(func.count()).select_from(Orders).where(Orders.support_id == support_id)
                )

                total_rating = 0
                rated_orders = 0
                total_completed = 0
                total_time = 0

                categories = {
                    "Техническая помощь / Technical Support": 0,
                    "NFA / HWID RESET": 0,
                    "Помощь с платежами / Payment Support": 0,
                    "Reselling": 0,
                    "Получить Ключ / Get a key": 0,
                }

                for order in tickets:
                    if order.completed_at and order.accept_at:
                        duration = (order.completed_at - order.accept_at).total_seconds()
                        total_time += duration
                        total_completed += 1
                    if order.stars is not None:
                        total_rating += order.stars
                        rated_orders += 1
                    if order.service_name in categories:
                        categories[order.service_name] += 1

                avg_time = total_time / total_completed if total_completed > 0 else 0
                rating = total_rating / rated_orders if rated_orders > 0 else 0

                rates = await self.get_user_rates(session, support_id)

                estimated_salary = 0
                for category, count in categories.items():
                    rate = rates.get(category, 0)
                    estimated_salary += count * rate

                bonus_per_50 = rates.get("Бонус", 0)
                if bonus_per_50 and total >= 50:
                    estimated_salary += (total // 50) * bonus_per_50
                valid_dicts = [order_to_dict(o) for o in tickets]
                excluded_dicts = [order_to_dict(ticket) | {"excluded_reason": reason} for ticket, reason in
                                  excluded_orders]

                stats = {
                    "all_orders": total_all_time,
                    "orders_this_month": total,
                    "avg_response_time": int(avg_time),
                    "avg_rating": round(rating, 2),
                    "estimated_salary": round(estimated_salary)
                }

                return stats


        except Exception as e:

            logger.error(f"[ERROR] Ошибка при расчете статистики: {e}", exc_info=True)

            return {"error": f"Внутренняя ошибка сервера: {e}"}

    async def active_tickets(self, user_id):
        async with self.Session() as session:
            try:
                active_tickets = await session.execute(select(Orders).where(Orders.client_id_id == user_id,
                                                                            Orders.status.in_(
                                                                                ['at work', 'paused', 'new'])))

                active_tickets = active_tickets.scalars().all()
                if not active_tickets:
                    return False

                return active_tickets
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def add_messages_history(self, chat_id, support_message_id, client_message_id, order_id):
        async with self.Session() as session:
            try:
                new_message = HistoryMessages(chat_id=chat_id, support_message_id=support_message_id,
                                              client_message_id=client_message_id, order_id=order_id)

                session.add(new_message)
                await session.commit()
                return True
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def remove_ticket_user(self, order_id):
        async with self.Session() as session:
            try:
                logger.info(f'Попытка удаления тикета {order_id}...')

                order = await session.get(Orders, order_id)
                if not order:
                    logger.warning(f'❌ Тикет {order_id} не найден!')
                    return False
                if order.status != 'new':
                    return 'Не новый'
                logger.info(f'✔️ Тикет {order_id} найден, проверяем историю сообщений...')

                message = await session.execute(
                    select(HistoryMessages).where(HistoryMessages.order_id == order_id)
                )
                message = message.scalars().first()

                if not message:
                    logger.warning(f'❌ История сообщений для тикета {order_id} не найдена!')
                    return False  # Ошибка была: return False стоял после if, теперь исправлено.

                logger.info(f'✔️ История сообщений найдена для тикета {order_id}. Обновляем статус...')

                # Обновляем данные тикета
                order.description = 'Пользователь отклонил тикет'
                order.status = 'cancelled'
                order.support_id = None
                order.support_name = None

                await session.commit()
                await session.refresh(order)
                await session.refresh(message)

                logger.info(f'✅ Тикет {order_id} успешно отменён!')

                return {
                    'order_id': order.id,
                    'client_message_id': message.client_message_id,
                    'support_message_id': message.support_message_id,
                    'chat_id': message.chat_id,
                    'service_name': order.service_name,
                    'client_name': order.client_name,
                    'client_id': order.client_id,
                    'created_at': order.created_at.strftime('%d-%m-%Y %H:%M:%S'),
                }

            except Exception as e:
                logger.error(f'🔥 Ошибка при удалении тикета {order_id}: {e}', exc_info=True)
                await session.rollback()
                raise
                return False
            finally:
                await session.close()

    async def media_add(self, user_id, media_url, description, name_cheat):
        async with self.Session() as session:
            try:
                user = await session.execute(select(Users).where(Users.user_id == user_id))
                user = user.scalars().first()
                if not user:
                    logger.error(Fore.RED + f'Пользователь {user_id} не найден!' + Style.RESET_ALL)
                    return False

                new_media = Media(user_id=user_id,
                                  username=user.username,
                                  url=media_url,
                                  description=description,
                                  name_cheat=name_cheat
                                  )
                session.add(new_media)
                await session.commit()
                await session.refresh(new_media)

                return {
                    'url': new_media.url,
                    'description': new_media.description,
                    'name_cheat': new_media.name_cheat,
                }


            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_user_all(self):
        async with self.Session() as session:
            try:
                users = await session.execute(select(Users))
                users = users.scalars().all()
                if not users:
                    logger.error(Fore.RED + f'Пользователи не найден!' + Style.RESET_ALL)
                    return []
                return users
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_statistic_media(self, user_id):
        async with self.Session() as session:
            try:
                media = await session.execute(select(Media).where(Media.user_id == user_id))
                media = media.scalars().all()
                if not media:
                    logger.error(Fore.RED + f'Медиа не найден!' + Style.RESET_ALL)
                    return []
                return media
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
            finally:
                await session.close()

    async def fetch_all_tables_data(self):
        async with self.Session() as session:
            try:
                all_data = {}

                # Извлекаем данные из таблицы Users
                users_query = select(
                    Users.id,
                    Users.user_id,
                    Users.username,
                    Users.role_id,
                    Users.created_at
                )
                users_result = await session.execute(users_query)
                all_data["users"] = [dict(row) for row in users_result.mappings()]

                # Извлекаем данные из таблицы Orders
                orders_query = select(
                    Orders.id,
                    Orders.client_id,
                    Orders.client_name,
                    Orders.support_id,
                    Orders.support_name,
                    Orders.service_id,
                    Orders.service_name,
                    Orders.created_at,
                    Orders.accept_at,
                    Orders.completed_at,
                    Orders.status,
                    Orders.stars,
                    Orders.description
                )
                orders_result = await session.execute(orders_query)
                all_data["orders"] = [dict(row) for row in orders_result.mappings()]

                # Извлекаем данные из таблицы Media
                media_query = select(
                    Media.id,
                    Media.url,
                    Media.description,
                    Media.name_cheat,
                    Media.user_id,
                    Media.username,
                    Media.created_at
                )
                media_result = await session.execute(media_query)
                all_data["medias"] = [dict(row) for row in media_result.mappings()]

                # Извлекаем данные из таблицы HistoryMessages
                history_messages_query = select(
                    HistoryMessages.id,
                    HistoryMessages.support_message_id,
                    HistoryMessages.client_message_id,
                    HistoryMessages.chat_id,
                    HistoryMessages.order_id
                )
                history_messages_result = await session.execute(history_messages_query)
                all_data["history_messages"] = [dict(row) for row in history_messages_result.mappings()]

                # Извлекаем данные из таблицы BannedUsers
                banned_users_query = select(
                    BannedUsers.id,
                    BannedUsers.user_id,
                    BannedUsers.username,
                    BannedUsers.created_at
                )
                banned_users_result = await session.execute(banned_users_query)
                all_data["banned_users"] = [dict(row) for row in banned_users_result.mappings()]

                # Извлекаем данные из таблицы Services
                services_query = select(
                    Services.id,
                    Services.service_name,
                    Services.allowed_roles,
                    Services.created_at
                )
                services_result = await session.execute(services_query)
                all_data["services"] = [dict(row) for row in services_result.mappings()]

                # Извлекаем данные из таблицы Roles
                roles_query = select(
                    Roles.id,
                    Roles.role_name
                )
                roles_result = await session.execute(roles_query)
                all_data["roles"] = [dict(row) for row in roles_result.mappings()]

                return all_data

            except Exception as e:
                logger.error(f'Ошибка при извлечении данных: {e}')
                await session.rollback()
                raise
            finally:
                if session.is_active:
                    await session.close()

    async def stars_order_update(self, order_id, value):
        async with self.Session() as session:
            try:
                order = await session.get(Orders, order_id)
                if not order:
                    logger.error(f"Заявка с id: {order_id} не найдена!")
                    return {"error": "Заявка не найдена в базе данных."}

                order.stars = value

                await session.commit()
                return True
            except Exception as e:
                logger.error(Fore.RED + f"Ошибка при изменении звездочек заявки: {e}" + Style.RESET_ALL)
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_all_message(self, order_id):
        async with self.Session() as session:
            try:
                message = await session.execute(select(HistoryMessages).where(HistoryMessages.order_id == order_id))
                message = message.scalars().first()
                if not message:
                    logger.error(Fore.RED + f'Сообщения не найдены!' + Style.RESET_ALL)
                return message
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_user_role_id(self):
        async with self.Session() as session:
            try:
                user = await session.execute(select(Users).where(Users.role_id.isnot(None)))
                user = user.scalars().all()
                return user
            except Exception as e:
                logger.error(Fore.RED + f'Ошибка: {e}' + Style.RESET_ALL)
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close_old_orders(self):
        """Закрывает заказы старше 24 часов и собирает связанные сообщения"""
        logger.info(Fore.BLUE + "Начало процедуры закрытия старых заказов" + Style.RESET_ALL)

        async with self.Session() as session:
            try:
                # Настройка времени
                time_threshold = datetime.now() - timedelta(hours=24)
                logger.debug(Fore.GREEN + f"Пороговое время: {time_threshold}" + Style.RESET_ALL)

                # Запрос заказов
                orders = (await session.execute(
                    select(Orders)
                    .where(
                        Orders.status == 'new',
                        Orders.created_at < time_threshold
                    )
                )).scalars().all()

                if not orders:
                    logger.info(Fore.BLUE + "Нет заказов для закрытия" + Style.RESET_ALL)
                    return []

                output = []
                success_count = 0

                for order in orders:

                    try:
                        # Обновление статуса заказа
                        order.status = 'closed'
                        order.completed_at = datetime.now()
                        order.description = 'Автоматическое закрытие (24 часа неактивности)'
                        session.add(order)
                        await session.flush()
                        order_data = {
                            "order_id": order.id,
                            "client_id": getattr(order, 'client_id', None),
                            "client_name": getattr(order, 'client_name', ''),
                            "service_name": getattr(order, 'service_name', ''),
                            "service_id": getattr(order, 'service_id', None),
                            "created_at": order.created_at.isoformat() if hasattr(order,
                                                                                  'created_at') and order.created_at else None,
                            'completed_at': order.completed_at.isoformat() if hasattr(order,
                                                                                      'completed_at') and order.completed_at else None,
                            "messages": []
                        }
                        # Запрос сообщений с проверкой наличия полей
                        messages = (await session.execute(
                            select(HistoryMessages)
                            .where(HistoryMessages.order_id == order.id)
                        )).scalars().all()

                        for message in messages:
                            try:
                                order_data["messages"].append({
                                    "support_message_id": getattr(message, 'support_message_id', None),
                                    "client_message_id": getattr(message, 'client_message_id', None),
                                    "chat_id": getattr(message, 'chat_id', None)
                                })
                            except Exception as msg_error:
                                logger.warning(Fore.YELLOW +
                                               f"Ошибка обработки сообщения для Тикета № {order.id}: {msg_error}" +
                                               Style.RESET_ALL)

                        output.append(order_data)
                        success_count += 1
                        logger.debug(Fore.GREEN + f"Обработан Тикет № {order.id}" + Style.RESET_ALL)

                    except Exception as order_error:
                        logger.error(Fore.RED +
                                     f"Ошибка обработки Тикета № {order.id}: {order_error}" +
                                     Style.RESET_ALL,
                                     exc_info=True)

                await session.commit()
                logger.info(Fore.BLUE +
                            f"Успешно закрыто {success_count}/{len(orders)} заказов" +
                            Style.RESET_ALL)
                return output

            except Exception as e:
                logger.critical(Fore.MAGENTA +
                                f"Критическая ошибка: {e}" +
                                Style.RESET_ALL,
                                exc_info=True)
                await session.rollback()
                return []

    async def get_users_with_roles_for_rates(self):
        async with self.Session() as session:
            stmt = (
                select(Users.user_id, Users.username)
                .join(Roles, Users.role_id == Roles.id)
                .outerjoin(PaymentRates, Users.user_id == PaymentRates.support_id)  # LEFT JOIN
                .where(Roles.role_name.in_(["admin", "support"]))
            )
            result = await session.execute(stmt)
            return result.all()

    async def get_user_by_id(self, user_id: int):
        async with self.Session() as session:
            result = await session.execute(
                select(Users).where(Users.user_id == user_id)
            )
            return result.scalars().first()

    async def get_username_by_id(self, user_id: int):
        async with self.Session() as session:
            result = await session.execute(
                select(Users.username).where(Users.user_id == user_id)
            )
            return result.scalar_one_or_none()

    async def get_payment_rate(self, user_id: int):
        async with self.Session() as session:
            result = await session.execute(
                select(PaymentRates).where(PaymentRates.support_id == user_id)
            )
            return result.scalar_one_or_none()

    async def update_payment_rate(self, user_id: int, field: str, value: int):
        async with self.Session() as session:
            await session.execute(
                update(PaymentRates)
                .where(PaymentRates.support_id == user_id)
                .values({field: value})
            )
            await session.commit()

    async def create_payment_rate(self, user_id: int):
        async with self.Session() as session:
            new_rate = PaymentRates(support_id=user_id, **DEFAULT_RATES)
            session.add(new_rate)
            await session.commit()

    async def delete_payment_rate(self, support_id: int):
        async with self.Session() as session:
            stmt = delete(PaymentRates).where(PaymentRates.support_id == support_id)
            await session.execute(stmt)
            await session.commit()

    async def get_user_rates(self, session, support_id: int) -> dict:
        # Формируем запрос для получения ставок конкретного support'а из таблицы PaymentRates
        stmt = select(PaymentRates).where(PaymentRates.support_id == support_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

        if not row:
            logger.warning(f"[RATES] Ставки не найдены для support_id={support_id}, применяем DEFAULT_RATES")
            return {
                "Техническая помощь / Technical Support": DEFAULT_RATES["technical_support"],
                "NFA / HWID RESET": DEFAULT_RATES["hwid_reset"],
                "Помощь с платежами / Payment Support": DEFAULT_RATES["payment_support"],
                "Reselling": DEFAULT_RATES["reselling"],
                "Получить Ключ / Get a key": DEFAULT_RATES["get_key"],
                "Бонус": DEFAULT_RATES["bonus_per_50"]
            }

        # Возвращаем словарь с названиями услуг и их ставками
        return {
            "Техническая помощь / Technical Support": row.technical_support,
            "NFA / HWID RESET": row.hwid_reset,
            "Помощь с платежами / Payment Support": row.payment_support,
            "Reselling": row.reselling,
            "Получить Ключ / Get a key": row.get_key,
            "Бонус": row.bonus_per_50
        }

    async def statistics_user_by_id(self, support_id: int, start_date: datetime.date, end_date: datetime.date):
        try:
            async with self.Session() as session:
                # Получаем информацию о пользователе
                user = await session.scalar(
                    select(Users).where(Users.user_id == support_id)
                )
                if not user:
                    logger.info(f"[DEBUG] Пользователь с ID {support_id} не найден в таблице users.")
                    return {"error": "Пользователь не найден"}

                # Получаем тикеты пользователя, прошедшие фильтрацию
                filtered_orders, excluded_orders = await filter_tickets_for_statistics(
                    session, support_id, start_date, end_date
                )
                tickets = filtered_orders

                if not tickets:
                    logger.info(
                        f"[DEBUG] У пользователя ID {support_id} нет тикетов в диапазоне {start_date} – {end_date}")
                    return {"error": "Нет тикетов в указанном диапазоне"}

                # Считаем общее количество тикетов за период
                total = len(tickets)

                # Получаем общее количество тикетов за всё время
                total_all_time = await session.scalar(
                    select(func.count()).select_from(Orders).where(Orders.support_id == support_id)
                )

                # Инициализируем переменные для подсчёта
                total_rating = 0
                rated_orders = 0
                total_completed = 0
                total_time = 0

                # Словарь для подсчёта тикетов по категориям
                categories = {
                    "Техническая помощь / Technical Support": 0,
                    "NFA / HWID RESET": 0,
                    "Помощь с платежами / Payment Support": 0,
                    "Reselling": 0,
                    "Получить Ключ / Get a key": 0,
                }

                # Перебираем тикеты и собираем статистику
                for order in tickets:
                    if order.completed_at and order.accept_at:
                        duration = (order.completed_at - order.accept_at).total_seconds()
                        total_time += duration
                        total_completed += 1
                    if order.stars is not None:
                        total_rating += order.stars
                        rated_orders += 1
                    if order.service_name in categories:
                        categories[order.service_name] += 1

                # Среднее время выполнения (в секундах)
                avg_time = total_time / total_completed if total_completed > 0 else 0

                # Средняя оценка
                rating = total_rating / rated_orders if rated_orders > 0 else 0

                # Получаем ставки и бонусы для пользователя
                rates = await self.get_user_rates(session, support_id)

                # Расчёт предполагаемой зарплаты
                estimated_salary = 0
                for category, count in categories.items():
                    rate = rates.get(category, 0)
                    estimated_salary += count * rate

                # При необходимости добавляем бонусы
                bonus_per_50 = rates.get("Бонус", 0)
                if bonus_per_50 and total >= 50:
                    estimated_salary += (total // 50) * bonus_per_50

                # Формируем финальный словарь статистики
                stats = {
                    "all_orders": total_all_time,
                    "orders_this_month": total,
                    "avg_response_time": int(avg_time),
                    "avg_rating": round(rating, 2),
                    "estimated_salary": round(estimated_salary)
                }

                return stats

        except Exception as e:
            # Логируем ошибку и возвращаем ошибку в формате словаря
            logger.error(f"[ERROR] Ошибка при расчете статистики: {e}", exc_info=True)
            return {"error": f"Внутренняя ошибка сервера: {e}"}

    async def get_support_not_assigned_group(self):
        try:
            async with self.Session() as session:
                # Подзапрос: саппорты, которые уже имеют группу
                subquery = select(GroupsSupportModel.support_id).distinct()

                # Основной запрос: саппорты, которых нет в подзапросе
                query = select(Users).join(
                    Roles, Users.role_id == Roles.id
                ).where(
                    or_(  # Используем or_ из sqlalchemy
                        Roles.role_name == 'support',
                        Roles.role_name == 'admin'
                    ),
                    Users.id.not_in(subquery)  # Сравниваем Users.id с support_id
                ).order_by(
                    Users.username
                )
                result = await session.execute(query)
                return result.scalars().all()
        except Exception as e:
            logger.error(Fore.RED + f'Ошибка при получении не назначенных саппортов: {e}' + Style.RESET_ALL)
            await session.rollback()
        finally:
            await session.close()

    async def setup_support_groups(self, support_id: int, group_id: int):
        """
        Привязывает саппорта к группе с проверкой, что у саппорта нет других привязок
        """
        try:
            async with self.Session() as session:
                # 1. ПРОВЕРЯЕМ, ЕСТЬ ЛИ УЖЕ ПРИВЯЗКИ У ЭТОГО САППОРТА
                existing_groups = await session.execute(
                    select(GroupsSupportModel)
                    .where(GroupsSupportModel.support_id == support_id)
                )
                existing_groups = existing_groups.scalars().all()

                # Если у саппорта уже есть привязки, возвращаем информацию
                if existing_groups:
                    logger.warning(
                        f'У саппорта ID {support_id} уже есть привязки к группам: {[g.group_id for g in existing_groups]}')
                    return "Support-already-has-groups"  # Или можно вернуть список существующих групп

                # 2. ПРОВЕРЯЕМ, НЕ ПРИВЯЗАНА ЛИ УЖЕ ЭТА ГРУППА К ДРУГОМУ САППОРТУ
                existing_support = await session.execute(
                    select(GroupsSupportModel)
                    .where(GroupsSupportModel.group_id == group_id)
                )
                existing_support = existing_support.scalar_one_or_none()

                if existing_support:
                    logger.warning(f'Группа ID {group_id} уже привязана к саппорту ID {existing_support.support_id}')
                    return "The group is linked to another support account"

                # 3. СОЗДАЕМ НОВУЮ ПРИВЯЗКУ (только если проверки пройдены)
                new_setup_support_in_group = GroupsSupportModel(
                    support_id=support_id,
                    group_id=group_id,
                )
                session.add(new_setup_support_in_group)
                await session.commit()

                logger.info(f'Саппорт ID {support_id} успешно привязан к группе ID {group_id}')
                return True

        except Exception as e:
            logger.error(Fore.RED + f'Ошибка при привязке саппорта к группе: {e}' + Style.RESET_ALL)
            await session.rollback()
            return False
        finally:
            await session.close()

    async def get_support_assigned_group(self):
        try:
            async with self.Session() as session:
                query = select(Users).join(
                    Roles, Users.role_id == Roles.id
                ).where(
                    or_(  # Используем or_ из sqlalchemy
                        Roles.role_name == 'support',
                        Roles.role_name == 'admin'
                    )
                ).order_by(
                    Users.username
                )
                result = await session.execute(query)
                return result.scalars().all()
        except Exception as e:
            logger.error(Fore.RED + f'Ошибка при получении всех саппортов: {e}' + Style.RESET_ALL)
            await session.rollback()
        finally:
            await session.close()

    async def reinstall_group(self, support_id: int, group_id: int) -> bool:
        """Перепривязать саппорта к группе (безопасная версия)"""
        try:
            async with self.Session() as session:
                # 1. НАХОДИМ ПЕРВУЮ ЗАПИСЬ ДЛЯ ЭТОГО САППОРТА
                existing_support_result = await session.execute(
                    select(GroupsSupportModel)
                    .where(GroupsSupportModel.support_id == support_id)
                    .limit(1)
                )
                existing_support = existing_support_result.scalar_one_or_none()

                if existing_support:
                    # 2. ОБНОВЛЯЕМ СУЩЕСТВУЮЩУЮ ЗАПИСЬ
                    old_group_id = existing_support.group_id
                    existing_support.group_id = group_id
                    logger.info(f"🔄 Обновлена группа для саппорта {support_id}: {old_group_id} → {group_id}")

                    # 3. ПРОВЕРЯЕМ, ЕСТЬ ЛИ ДРУГАЯ ЗАПИСЬ С ЭТОЙ ГРУППОЙ
                    other_group_result = await session.execute(
                        select(GroupsSupportModel)
                        .where(
                            GroupsSupportModel.group_id == group_id,
                            GroupsSupportModel.id != existing_support.id
                        )
                    )
                    other_group = other_group_result.scalar_one_or_none()

                    if other_group:
                        # Обновляем другую запись на старую группу или удаляем
                        other_group.group_id = old_group_id if old_group_id != group_id else None
                        logger.info(f"🔄 Переназначена группа {group_id} для саппорта {other_group.support_id}")

                else:
                    # 4. ЕСЛИ НЕТ ЗАПИСИ ДЛЯ САППОРТА, ПРОВЕРЯЕМ ГРУППУ
                    existing_group_result = await session.execute(
                        select(GroupsSupportModel)
                        .where(GroupsSupportModel.group_id == group_id)
                        .limit(1)
                    )
                    existing_group = existing_group_result.scalar_one_or_none()

                    if existing_group:
                        # Обновляем существующую запись группы
                        old_support_id = existing_group.support_id
                        existing_group.support_id = support_id
                        logger.info(f"🔄 Обновлен саппорт для группы {group_id}: {old_support_id} → {support_id}")
                    else:
                        # Создаем новую запись
                        new_record = GroupsSupportModel(
                            support_id=support_id,
                            group_id=group_id
                        )
                        session.add(new_record)
                        logger.info(f"✅ Создана новая привязка {support_id} → {group_id}")

                await session.commit()
                return True

        except Exception as e:
            logger.error(f'Ошибка при перепривязке саппорта к группе: {e}')
            await session.rollback()
            return False
        finally:
            await session.close()

    async def get_chat_by_thread_id(self, thread_id: int):
        """Получает информацию о чате по ID темы"""
        try:
            async with self.Session() as session:
                query = select(TicketsIdSupportGroupsModel).where(
                    TicketsIdSupportGroupsModel.thread_id == thread_id
                ).limit(1)  # Добавляем limit для безопасности

                result = await session.execute(query)
                topic_mapping = result.scalar_one_or_none()

                if not topic_mapping:
                    logger.warning(f"Топик {thread_id} не найден в БД")
                    return None

                # Получаем информацию о клиенте
                client_query = select(Users).where(Users.id == topic_mapping.user_id).limit(1)
                client_result = await session.execute(client_query)
                client = client_result.scalar_one_or_none()

                if not client:
                    logger.error(f"Клиент с id {topic_mapping.user_id} не найден")
                    return None

                # Получаем информацию о группе
                group_query = select(GroupsSupportModel).where(
                    GroupsSupportModel.id == topic_mapping.group_id
                ).limit(1)
                group_result = await session.execute(group_query)
                group = group_result.scalar_one_or_none()

                if not group:
                    logger.error(f"Группа {topic_mapping.group_id} не найдена")
                    return None

                # ВАЖНО: Проверяем названия полей в модели Users
                # Если поле называется user_id (Telegram ID), то client.user_id
                # Если поле называется id (Telegram ID), то client.id
                # Скорее всего, это client.user_id

                telegram_client_id = None
                if hasattr(client, 'user_id'):
                    telegram_client_id = client.user_id  # Telegram ID
                elif hasattr(client, 'id'):
                    telegram_client_id = client.id  # Telegram ID
                else:
                    logger.error(f"У клиента нет поля user_id или id: {client}")
                    return None

                logger.info(f"Найден клиент: TG ID={telegram_client_id}, DB ID={client.id}")

                return {
                    'thread_id': thread_id,
                    'group_id': group.group_id,  # Telegram ID группы
                    'client_id': telegram_client_id,  # Telegram ID клиента
                    'support_id': topic_mapping.support_id,
                    'user_db_id': client.id,  # ID в таблице Users (БД)
                    'order_id': topic_mapping.order_id,
                    'client_username': getattr(client, 'username', None)
                }

        except Exception as e:
            logger.error(f"Ошибка получения чата по thread_id {thread_id}: {e}", exc_info=True)
            return None

    async def get_chats(self, thread_id: int = None, client_telegram_id: int = None):
        """Универсальный метод получения чата"""
        try:
            async with self.Session() as session:
                if thread_id:
                    # Поиск по thread_id
                    query = select(TicketsIdSupportGroupsModel).where(
                        TicketsIdSupportGroupsModel.thread_id == thread_id
                    )
                    result = await session.execute(query)
                    topic_mapping = result.scalar_one_or_none()

                    if topic_mapping:
                        # Получаем Telegram ID клиента
                        user_query = select(Users).where(Users.id == topic_mapping.user_id)
                        user_result = await session.execute(user_query)
                        user = user_result.scalar_one_or_none()

                        if user:
                            return user.user_id  # Telegram ID клиента

                    return "no-found-chat"

                elif client_telegram_id:
                    # Поиск по Telegram ID клиента
                    user_query = select(Users).where(Users.user_id == client_telegram_id)
                    user_result = await session.execute(user_query)
                    user = user_result.scalar_one_or_none()

                    if not user:
                        return "no-found-chat"

                    # Ищем последний активный топик
                    query = select(TicketsIdSupportGroupsModel).where(
                        TicketsIdSupportGroupsModel.user_id == user.id
                    ).order_by(TicketsIdSupportGroupsModel.created_at.desc())

                    result = await session.execute(query)
                    topic_mapping = result.scalar_one_or_none()

                    if topic_mapping:
                        return topic_mapping.thread_id

                    return "no-found-chat"

                return None
        except Exception as e:
            logger.error(f"Ошибка получения chats: {e}")
            return None

    async def get_active_ticket_for_user(self, user_telegram_id: int):
        """Получает активный тикет пользователя по его Telegram ID"""
        try:
            async with self.Session() as session:
                query = select(Orders).where(
                    Orders.client_id == user_telegram_id,
                    Orders.status.in_(['new', 'at work'])  # Только активные статусы
                ).order_by(Orders.created_at.desc())

                result = await session.execute(query)
                order = result.scalar_one_or_none()
                return order
        except Exception as e:
            logger.error(f"Ошибка получения активного тикета пользователя {user_telegram_id}: {e}")
            return None

    async def get_chat_by_client_id(self, client_telegram_id: int):
        """Получает информацию о чате по Telegram ID клиента"""
        try:
            async with self.Session() as session:
                # 1. Находим пользователя
                user_query = select(Users).where(Users.user_id == client_telegram_id)
                user_result = await session.execute(user_query)
                user_row = user_result.first()  # Возвращает кортеж или None

                if not user_row:
                    return None

                user = user_row[0]  # Извлекаем объект Users из кортежа

                # 2. Ищем последний топик
                query = (
                    select(TicketsIdSupportGroupsModel)
                    .where(TicketsIdSupportGroupsModel.user_id == user.id)
                    .order_by(TicketsIdSupportGroupsModel.created_at.desc())
                )

                result = await session.execute(query)
                topic_row = result.first()  # Возвращает кортеж

                if not topic_row:
                    return None

                topic_mapping = topic_row[0]  # Извлекаем объект TicketsIdSupportGroupsModel

                # 3. Получаем информацию о группе
                group_query = select(GroupsSupportModel).where(
                    GroupsSupportModel.id == topic_mapping.group_id
                )
                group_result = await session.execute(group_query)
                group_row = group_result.first()

                if not group_row:
                    return None

                group = group_row[0]  # Извлекаем объект GroupsSupportModel

                return {
                    'thread_id': topic_mapping.thread_id,
                    'group_id': group.group_id,
                    'client_id': client_telegram_id,
                    'support_id': topic_mapping.support_id,
                    'order_id': getattr(topic_mapping, 'order_id', None),
                    'user_db_id': user.id,
                    'created_at': topic_mapping.created_at
                }

        except Exception as e:
            logger.error(f"Ошибка получения чата клиента: {e}", exc_info=True)
            return None


    async def add_form_in_base(self,  order_id: int, name_game: str, name_cheat: str,
                               problem_description: str, specifications: str):
        try:
            async with self.Session() as session:
                add_form_in_base = FormTicketsUsersModel(
                    order_id=order_id,
                    name_game=name_game,
                    name_cheat=name_cheat,
                    problem_description=problem_description,
                    specifications=specifications,
                )

                session.add(add_form_in_base)
                await session.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении формы в базу: {e}", exc_info=True)
            await session.rollback()
            return False
        finally:
            await session.close()

    async def get_user_tickets_with_forms(self, user_id: int):
        """
        Получает все тикеты пользователя с формами
        Возвращает список тикетов, которые имеют записи в form_tickets_users
        """
        try:
            async with self.Session() as session:
                # Получаем заказы пользователя, которые имеют форму
                query = select(Orders, FormTicketsUsersModel, Users.username). \
                    join(FormTicketsUsersModel, Orders.id == FormTicketsUsersModel.order_id). \
                    join(Users, Orders.client_id == Users.user_id). \
                    where(
                    Orders.client_id == user_id
                ). \
                    order_by(Orders.id.desc())

                result = await session.execute(query)
                tickets = result.all()

                if not tickets:
                    return None

                # Преобразуем в удобный формат с конвертацией datetime в строку
                ticket_list = []
                for order, form, username in tickets:
                    ticket_list.append({
                        'ticket_id': order.id,
                        'user_id': order.client_id,
                        'username': username or "Не указан",
                        'status': order.status,
                        'created_at': order.created_at.isoformat() if order.created_at else None,
                        # ← Конвертируем в строку
                        'form': {
                            'name_cheat': form.name_cheat,
                            'name_game': form.name_game,
                            'specifications': form.specifications,
                            'problem_description': form.problem_description,
                            'created_at': form.created_at.isoformat() if form.created_at else None
                            # ← Конвертируем в строку
                        }
                    })

                return ticket_list

        except Exception as e:
            logger.error(f"Ошибка при получении тикетов пользователя: {e}", exc_info=True)
            return None
        finally:
            await session.close()

    async def get_tickets_statistics(self):
        """
        Получает статистику по тикетам:
        - Новые тикеты (статус 'New')
        - В работе (статус 'At work')
        - Общее количество за последние 24 часа
        """
        try:
            async with self.Session() as session:
                from datetime import datetime, timedelta

                # Время 5 часов назад
                twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=5)

                # Новые тикеты (статус 'New')
                new_tickets_query = select(func.count(Orders.id)).where(
                    Orders.status == 'new',
                    Orders.created_at >= twenty_four_hours_ago
                )
                new_tickets_result = await session.execute(new_tickets_query)
                new_tickets_count = new_tickets_result.scalar() or 0

                # Тикеты в работе (статус 'At work')
                at_work_tickets_query = select(func.count(Orders.id)).where(
                    Orders.status == 'at work',
                    Orders.created_at >= twenty_four_hours_ago
                )
                at_work_tickets_result = await session.execute(at_work_tickets_query)
                at_work_tickets_count = at_work_tickets_result.scalar() or 0




                return {
                    'new_tickets': new_tickets_count,
                    'at_work_tickets': at_work_tickets_count,
                    'period': '5 часа'
                }

        except Exception as e:
            logger.error(f"Ошибка получения статистики тикетов: {e}")
            return None
        finally:
            await session.close()