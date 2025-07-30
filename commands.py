from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from database.db import DataBase
db = DataBase()

async def set_commands(bot: Bot):
    commands = [
        BotCommand(
            command="start",
            description="Перезапуск бота",
        ),
        BotCommand(
            command="stop_chat",
            description="Закрыть тикет",
        )
     ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())


async def set_commands_admin(bot: Bot, user_id: int):
    user = await db.check_role(user_id)

    if user_id == 434791099 or user_id == 835867765:
        commands = [
            BotCommand(
                command="start",
                description="Перезапуск бота",
            ),
            BotCommand(
                command="admin",
                description="Админ панель",
            ),
            BotCommand(
                command="stop_chat",
                description="Закрыть тикет",
            ),
            BotCommand(
                command="statistics",
                description="Статистика",
            ),
            BotCommand(
                command="allstats",
                description="Общая статистика",
            )
        ]

        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
    elif user and hasattr(user, 'role_name') and user.role_name == 'support':  # Проверяем, что user не False и имеет атрибут role_name
        commands = [
            BotCommand(
                command="start",
                description="Перезапуск бота",
            ),
            BotCommand(
                command="stop_chat",
                description="Закрыть тикет",
            ),
            BotCommand(
                command="statistics",
                description="Статистика",
            )
        ]
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
    else:
        await set_commands(bot)
