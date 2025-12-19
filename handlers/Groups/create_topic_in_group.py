from aiogram import Bot, Router
from typing import Optional, Tuple
from logger import logger



class GroupManager:
    def __init__(self, bot: Optional[Bot] = None):
        self.bot = bot

    def set_bot(self, bot: Bot):
        """Установить бота (можно вызвать после создания бота)"""
        self.bot = bot

    async def check_bot_admin_rights(self, chat_id: int) -> bool:
        """Проверяет, имеет ли бот права администратора"""
        if not self.bot:
            raise ValueError("Bot not set. Call set_bot() first.")

        try:
            bot_user = await self.bot.get_me()
            bot_member = await self.bot.get_chat_member(chat_id, bot_user.id)

            return bot_member.status in ["administrator", "creator"]
        except Exception as e:
            print(f"Ошибка при проверке прав: {e}")
            return False

    async def send_admin_requirements(self, chat_id: int):
        """Отправляет сообщение с требованиями к правам"""
        if not self.bot:
            raise ValueError("Bot not set. Call set_bot() first.")

        requirements = """
⚠️ *Для корректной работы мне нужны права администратора!*
        """
        await self.bot.send_message(chat_id, requirements, parse_mode="Markdown")

    async def setup_group(self, chat_id: int) -> bool:
        """Настройка группы"""
        if not self.bot:
            raise ValueError("Bot not set. Call set_bot() first.")

        is_admin = await self.check_bot_admin_rights(chat_id)
        if is_admin:
            await self.bot.send_message(chat_id, "✅ Группа настроена!")
            return True
        else:
            await self.send_admin_requirements(chat_id)
            return False

    async def create_user_topic(
            self,
            order_id: int,
            group_id: int,
    ) -> Tuple[Optional[int], bool]:
        """
        Создает тему с названием username и отправляет сообщение

        Args:
            chat_id: ID супергруппы/форума
            user_id: ID пользователя
            username: имя пользователя для названия темы
            message: сообщение для отправки в теме

        Returns:
            Tuple[thread_id, success]: ID созданной темы и флаг успеха
        """
        if not self.bot:
            raise ValueError("Bot not set. Call set_bot() first.")

        try:
            # Создаем тему с названием username
            topic_name = f"Тикет №{order_id}"
            logger.info(group_id)
            topic = await self.bot.create_forum_topic(
                chat_id=int(group_id),
                name=topic_name, # Фиолетовый цвет
            )

            thread_id = topic.message_thread_id
            print(f"Создана тема '{topic_name}' с ID: {thread_id}")

            return thread_id, True

        except Exception as e:
            print(f"Ошибка при создании темы: {e}")
            return None, False


# Создаем глобальный экземпляр
group_manager = GroupManager()