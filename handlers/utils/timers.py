import asyncio
import os
import traceback

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramAPIError

from config import GROUP_CHAT_ID
from database.db import DataBase, redis_client
from logger import logger

# Словарь активных таймеров
active_timers = {}
db = DataBase()


async def auto_close_ticket_if_silent(ticket_id: int, user_id: int, bot: Bot, timeout_minutes: int = 5):
    """
    Автоматически закрывает тикет, если клиент не отвечает
    timeout_minutes: общее время до закрытия (по умолчанию 3 минуты)
    """
    timer_key = f"timer_{ticket_id}"

    try:
        logger.info(f"[TIMER] Запущен таймер авто-закрытия тикета №{ticket_id} ({timeout_minutes} мин)")

        # 1. Ждем 2/3 времени для предупреждения
        warning_time = int((timeout_minutes * 60) * 0.66)  # 66% от общего времени

        await asyncio.sleep(warning_time)

        # Проверяем, был ли таймер отменен
        if timer_key not in active_timers or active_timers[timer_key].done():
            logger.info(f"[TIMER] Таймер для тикета №{ticket_id} был отменен")
            return

        # Проверяем статус тикета
        order_info = await db.get_orders_by_id(ticket_id)
        if not order_info or order_info.status == "closed":
            logger.info(f"[TIMER] Тикет №{ticket_id} уже закрыт — отмена")
            if timer_key in active_timers:
                del active_timers[timer_key]
            return

        # 2. Отправляем предупреждение клиенту
        try:
            remaining_minutes = timeout_minutes - (warning_time // 60)
            await bot.send_message(
                chat_id=user_id,
                text=f"⚠️ Если не ответишь в течение {remaining_minutes} минут, тикет закроется автоматически!"
            )
            logger.info(f"[TIMER] Предупреждение отправлено клиенту по тикету №{ticket_id}")
        except TelegramForbiddenError:
            reason = "Авто-закрытие (Клиент заблокировал бота)"
            logger.warning(f"[TIMER] Клиент заблокировал бота, тикет №{ticket_id}")
            await close_ticket(ticket_id, user_id, bot, reason)
            if timer_key in active_timers:
                del active_timers[timer_key]
            return

        # 3. Ждем оставшееся время
        remaining_time = (timeout_minutes * 60) - warning_time
        await asyncio.sleep(remaining_time)

        # Проверяем, был ли таймер отменен
        if timer_key not in active_timers or active_timers[timer_key].done():
            logger.info(f"[TIMER] Таймер для тикета №{ticket_id} был отменен перед закрытием")
            return

        # 4. Проверяем статус тикета
        order_info = await db.get_orders_by_id(ticket_id)
        if not order_info or order_info.status == "closed":
            logger.info(f"[TIMER] Тикет №{ticket_id} был закрыт вручную после предупреждения")
            if timer_key in active_timers:
                del active_timers[timer_key]
            return

        # 5. Проверяем активность клиента через Redis
        message_count = await redis_client.get(f"messages:{ticket_id}")

        if message_count is None or int(message_count) == 0:
            # Клиент не отвечал
            try:
                await bot.send_chat_action(chat_id=user_id, action="typing")
                reason = f"Авто-закрытие (Клиент не ответил в течение {timeout_minutes} мин)"
            except TelegramForbiddenError:
                reason = "Авто-закрытие (Клиент заблокировал бота)"
                logger.warning(f"[TIMER] Клиент заблокировал бота до авто-закрытия тикета №{ticket_id}")

            await close_ticket(ticket_id, user_id, bot, reason)
            logger.info(f"[TIMER] Тикет №{ticket_id} закрыт автоматически")
        else:
            logger.info(f"[TIMER] Тикет №{ticket_id} не закрыт — клиент отправил {message_count} сообщений")

        # Очищаем счетчик сообщений в Redis
        await redis_client.delete(f"messages:{ticket_id}")

    except asyncio.CancelledError:
        logger.info(f"[TIMER] Таймер авто-закрытия для тикета №{ticket_id} отменён")
        raise
    except Exception as e:
        logger.error(f"[TIMER ERROR] Ошибка при авто-закрытии тикета №{ticket_id}: {e}", exc_info=True)
    finally:
        # Всегда очищаем таймер
        if timer_key in active_timers and active_timers[timer_key].done():
            del active_timers[timer_key]


async def create_ticket_timer(ticket_id: int, client_id: int, bot) -> asyncio.Task:
    """
    Создает таймер авто-закрытия для тикета
    Возвращает созданную задачу
    """
    # Уникальный ключ для таймера
    timer_key = f"timer_{ticket_id}"

    # Отменяем старый таймер, если он есть
    if timer_key in active_timers:
        old_task = active_timers[timer_key]
        if not old_task.done():
            old_task.cancel()
            logger.info(f"🗑️ Отменен старый таймер для тикета {ticket_id}")
            try:
                await asyncio.sleep(0.1)  # Даем время для корректной отмены
            except asyncio.CancelledError:
                pass

    # Создаем новую задачу
    task = asyncio.create_task(
        auto_close_ticket_if_silent(ticket_id, client_id, bot, 5),
        name=f"ticket_timer_{ticket_id}"
    )

    # Сохраняем в словарь
    active_timers[timer_key] = task

    # Добавляем обработчик завершения
    def on_task_done(t: asyncio.Task):
        if timer_key in active_timers and active_timers[timer_key] == t:
            del active_timers[timer_key]
            if t.cancelled():
                logger.info(f"⏹️ Таймер для тикета {ticket_id} отменен и удален")
            elif t.exception():
                logger.error(f"❌ Таймер для тикета {ticket_id} завершился с ошибкой: {t.exception()}")
            else:
                logger.info(f"✅ Таймер для тикета {ticket_id} успешно завершен")

    task.add_done_callback(on_task_done)

    logger.info(f"⏱️ Создан таймер авто-закрытия для тикета #{ticket_id}")
    logger.info(f"   📝 Ключ: {timer_key}, Задача: {id(task)}")

    return task

async def handle_auto_close_timer(ticket_id: int, user_id: int, bot: Bot, is_support_reply: bool = False):
    """
    Обрабатывает таймер авто-закрытия тикета
    """
    try:
        # Проверяем, что ticket_id не None
        if not ticket_id:
            logger.warning(f"Не передан ticket_id для пользователя {user_id}")
            return

        timer_key = f"timer_{ticket_id}"

        # 1. Отменяем предыдущий таймер, если есть
        if timer_key in active_timers:
            old_task = active_timers[timer_key]

            # Проверяем, не завершена ли уже задача
            if not old_task.done():
                # Отменяем задачу
                old_task.cancel()
                try:
                    # Ждем завершения отмененной задачи, но с таймаутом
                    await asyncio.wait_for(old_task, timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(f"[TIMER] Таймаут при отмене таймера {ticket_id}")
                except asyncio.CancelledError:
                    logger.debug(f"[TIMER] Таймер {ticket_id} отменен успешно")
                except Exception as cancel_error:
                    # Логируем ошибку отмены, но продолжаем
                    logger.warning(f"[TIMER] Ошибка при отмене таймера {ticket_id}: {cancel_error}")
            else:
                logger.debug(f"[TIMER] Старый таймер {ticket_id} уже завершен")

            # Удаляем старую задачу из словаря
            if timer_key in active_timers:
                del active_timers[timer_key]

            if is_support_reply:
                logger.info(f"[TIMER] Отменён таймер авто-закрытия тикета №{ticket_id} — саппорт ответил.")
            else:
                logger.info(f"[TIMER] Отменён таймер авто-закрытия тикета №{ticket_id} — клиент начал общение.")

    except Exception as e:
        logger.error(f"[DEBUG] Полная ошибка при обработке таймера для тикета {ticket_id}:")
        logger.error(f"[DEBUG] Тип: {type(e).__name__}")
        logger.error(f"[DEBUG] Сообщение: {str(e)}")
        logger.error(f"[DEBUG] Трассировка:")
        for line in traceback.format_exc().split('\n'):
            if line:  # Пропускаем пустые строки
                logger.error(f"[DEBUG] {line}")


async def safe_cancel_task(ticket_id: int):
    """Безопасная отмена задачи"""
    timer_key = f"timer_{ticket_id}"
    if timer_key in active_timers:
        task = active_timers[timer_key]
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"[TIMER] Ошибка при безопасной отмене таймера {ticket_id}: {e}")
        del active_timers[timer_key]
        logger.info(f"[TIMER] Таймер для тикета №{ticket_id} безопасно отменен")


async def cancel_all_timers():
    """Отмена всех активных таймеров (для перезапуска бота)"""
    cancelled_count = 0
    for timer_key, task in list(active_timers.items()):
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"[TIMER] Ошибка при отмене таймера {timer_key}: {e}")
        del active_timers[timer_key]
        cancelled_count += 1

    logger.info(f"[TIMER] Все активные таймеры отменены ({cancelled_count} штук)")


async def close_ticket(ticket_id: int, client_id: int, bot: Bot, reason: str):
    """Закрывает тикет автоматически"""
    try:
        # Используем правильное имя параметра и передаем бота
        result = await db.get_auto_close_order(ticket_id, reason=reason, bot=bot)

        if not result.get("success"):
            logger.error(f"[TIMER] Не удалось закрыть тикет №{ticket_id}: {result.get('error')}")
            return

        order_info = await db.get_orders_by_id(ticket_id)
        if not order_info:
            logger.warning(f"[TIMER] Не найден тикет №{ticket_id} для уведомлений")
            return

        logger.info(f"[TIMER] Тикет №{ticket_id} закрыт автоматически: {reason}")

        # Обновляем сообщение в группе
        message_info = await db.get_all_message(ticket_id)
        if message_info and hasattr(message_info, 'support_message_id'):
            message_edit_text = format_ticket_closed_message(order_info, reason)
            await bot.edit_message_text(
                message_id=int(message_info.support_message_id),
                chat_id=GROUP_CHAT_ID,
                text=message_edit_text,
                parse_mode="HTML"
            )
            await unpin_specific_message(bot, GROUP_CHAT_ID, int(message_info.support_message_id))

        # Уведомляем саппорт
        try:
            await bot.send_message(
                chat_id=order_info.support_id,
                text=f"🚪 Тикет №{ticket_id} закрыт автоматически. {reason}"
            )
        except TelegramForbiddenError:
            logger.warning(f"[TIMER] Support заблокировал бота — уведомление не отправлено")

        # Уведомляем клиента
        if "не ответил" in reason:
            try:
                await bot.send_message(
                    chat_id=client_id,
                    text=f"⛔️ Тикет №{ticket_id} был закрыт автоматически из-за отсутствия ответа. Вы можете создать новый, если помощь всё ещё нужна."
                )
            except TelegramForbiddenError:
                logger.warning(f"[TIMER] Клиент заблокировал бота — уведомление не отправлено")

        # Логируем статус удаления топика
        if result.get("topic_found"):
            if result.get("topic_deleted"):
                logger.info(f"[TOPIC] Топик тикета №{ticket_id} успешно удален")
            else:
                logger.warning(f"[TOPIC] Не удалось удалить топик тикета №{ticket_id}")

    except Exception as e:
        logger.error(f"[CLOSE ERROR] Ошибка при закрытии тикета №{ticket_id}: {e}")


def format_ticket_closed_message(order, reason: str) -> str:
    """Форматирует сообщение о закрытии тикета"""
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
        f"⏳ <b>Создана:</b> {order.created_at.strftime('%d-%m-%Y %H:%M:%S')}\n\n"
        f"⏳ <b>Принята:</b> {order.accept_at.strftime('%d-%m-%Y %H:%M:%S') if order.accept_at else 'не принята'}\n\n"
        f"⏳ <b>Закрыта:</b> {order.completed_at.strftime('%d-%m-%Y %H:%M:%S') if order.completed_at else 'автоматически'}\n\n"
        f"<a href=\"https://t.me/GBPSupport_bot\">Перейти в бота</a>"
    )


async def unpin_specific_message(bot: Bot, chat_id: int, message_id: int):
    """Открепляет конкретное сообщение"""
    try:
        await bot.unpin_chat_message(
            chat_id=chat_id,
            message_id=message_id
        )
        logger.info(f"Сообщение {message_id} откреплено!")
    except TelegramAPIError as e:
        logger.error(f"Ошибка при откреплении сообщения: {e}")
