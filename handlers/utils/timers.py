import asyncio
import os

from aiogram import Bot
from database.db import DataBase
from logger import logger

# Словарь активных таймеров
active_timers = {}
db = DataBase()

async def auto_close_ticket_if_silent(ticket_id: int, user_id: int, bot: Bot, timeout_minutes: int = 3):
    """
    Автоматически закрывает тикет, если нет активности от клиента
    """
    try:
        await asyncio.sleep(timeout_minutes * 60)  # Ждем N минут

        # Проверяем, активен ли еще таймер
        if ticket_id not in active_timers:
            return

        logger.info(f"[TIMER] Авто-закрытие тикета №{ticket_id} после {timeout_minutes} минут неактивности")

        # Закрываем тикет
        result = await db.get_auto_close_order(ticket_id, reason=f"Авто-закрытие (нет активности {timeout_minutes} мин)")

        if result:
            # Получаем информацию о тикете
            order = await db.get_orders_by_id(ticket_id)

            if order:
                # Уведомляем саппорта
                try:
                    await bot.send_message(
                        chat_id=int(order.support_id),
                        text=f"⏰ Тикет №{ticket_id} автоматически закрыт из-за неактивности клиента"
                    )
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
                except:
                    pass

                # Обновляем сообщение в группе
                await update_ticket_message_in_group(bot, ticket_id, order)

        # Удаляем таймер
        if ticket_id in active_timers:
            del active_timers[ticket_id]

    except asyncio.CancelledError:
        logger.info(f"[TIMER] Таймер авто-закрытия для тикета №{ticket_id} отменён")
    except Exception as e:
        logger.error(f"[TIMER] Ошибка авто-закрытия тикета №{ticket_id}: {e}")


async def update_ticket_message_in_group(bot: Bot, ticket_id: int, order):
    """Обновляет сообщение о тикете в группе"""
    try:

        msg_info = await db.get_all_message(ticket_id)
        if msg_info and hasattr(msg_info, 'support_message_id'):
            message_text = (
                f"⏰ *Авто-закрытие тикета*\n\n"
                f"📩 Тикет №{ticket_id}\n"
                f"👤 Клиент: @{order.client_name}\n"
                f"🆔 ID: {order.client_id}\n"
                f"🛠 Услуга: {order.service_name}\n"
                f"👨‍💻 Саппорт: @{order.support_name}\n"
                f"⏳ Создан: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏳ Закрыт: {order.completed_at.strftime('%d.%m.%Y %H:%M') if order.completed_at else 'автоматически'}\n"
                f"📝 Причина: неактивность клиента"
            )

            await bot.edit_message_text(
                chat_id=int(os.getenv('GROUP_CHAT_ID')),
                message_id=int(msg_info.support_message_id),
                text=message_text,
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Ошибка обновления сообщения тикета: {e}")


async def handle_auto_close_timer(ticket_id: int, user_id: int, bot: Bot):
    """Обрабатывает таймер авто-закрытия тикета"""
    if not ticket_id:
        return

    # Отменяем существующий таймер для этого тикета
    if ticket_id in active_timers:
        active_timers[ticket_id].cancel()
        del active_timers[ticket_id]
        logger.info(f"[TIMER] Отменён таймер авто-закрытия тикета №{ticket_id} — клиент начал общение.")

    # Запускаем новый таймер
    task = asyncio.create_task(auto_close_ticket_if_silent(ticket_id, user_id, bot))
    active_timers[ticket_id] = task
    logger.info(f"[TIMER] Запущен таймер авто-закрытия тикета №{ticket_id}")