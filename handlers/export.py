from pandas.tseries.offsets import DateOffset
import pandas as pd
import os
from aiogram import Bot, types
from aiogram.types import CallbackQuery
from database.db import DataBase  # Функция для получения данных из БД
from logger import logger

db = DataBase()


def format_processing_time(minutes: float) -> str:
    """Форматирование времени обработки в HH:MM:SS с округлением"""
    try:
        if pd.isna(minutes) or minutes < 0:
            return "N/A"

        # Округляем до целых секунд
        total_seconds = int(round(minutes * 60))

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except Exception as e:
        logger.error(f"Ошибка форматирования времени: {e}")
        return "N/A"


async def export_data(callback_query: CallbackQuery, bot: Bot):
    user_id = callback_query.from_user.id
    logger.info(f"Пользователь {user_id} запросил выгрузку данных.")

    try:
        # Получаем данные из базы
        all_data = await db.fetch_all_tables_data()
        if not all_data:
            logger.warning(f"Пользователь {user_id}: нет данных для выгрузки.")
            await callback_query.message.answer("В базе данных нет данных для выгрузки.")
            return

        # Настройки для Excel
        custom_sheet_names = {
            "users": "Пользователи",
            "orders": "Тикеты",
            "medias": "Медиа",
            "history_messages": "История сообщений",
            "banned_users": "ЧС список",
            "services": "Услуги",
            "roles": "Роли",
        }

        file_path = "exported_data.xlsx"

        # Создаем основной файл
        with pd.ExcelWriter(file_path, engine="openpyxl", mode="w") as writer:
            for table_name, rows in all_data.items():
                if rows:
                    df = pd.DataFrame(rows)
                    sheet_name = custom_sheet_names.get(table_name, table_name)
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    logger.info(f"Добавлена таблица: {sheet_name}")

        # Обработка таблицы "orders"
        if "orders" in all_data and all_data["orders"]:
            try:
                df_orders = pd.DataFrame(all_data["orders"])
                logger.info(f"Загружено {len(df_orders)} тикетов")

                # Преобразование дат
                date_cols = ["created_at", "accept_at", "completed_at"]
                df_orders[date_cols] = df_orders[date_cols].apply(lambda col: pd.to_datetime(col, errors='coerce'))

                # Удаление тикетов с некорректными датами
                df_orders = df_orders.dropna(subset=date_cols)
                df_orders = df_orders[df_orders["completed_at"] > df_orders["accept_at"]]

                # Расчет времени обработки
                df_orders["processing_time"] = (df_orders["completed_at"] - df_orders["accept_at"]).dt.total_seconds() / 60

                # Фильтрация аномальных значений
                df_orders = df_orders[
                    (df_orders["support_name"].notna()) &
                    (df_orders["support_name"].astype(str).str.strip().ne("")) &
                    (~df_orders["support_name"].astype(str).str.isdigit())
                ]

                logger.info(f"Валидных тикетов: {len(df_orders)}")

                # Периоды анализа
                current_date = pd.Timestamp.now()
                current_month = current_date.replace(day=1)
                prev_month = (current_month - DateOffset(months=1)).replace(day=1)

                # Фильтрация по периоду
                date_filter = lambda df, start: df[
                    (df["created_at"].dt.normalize() >= start.normalize())
                    & (df["created_at"].dt.normalize() < (start + DateOffset(months=1)).normalize())
                    ]
                
                print("Min date:", df_orders["created_at"].min())
                print("Max date:", df_orders["created_at"].max())
                print("Current month filter range:", current_month, "to", current_month + DateOffset(months=1))


                df_current = date_filter(df_orders, current_month)
                df_previous = date_filter(df_orders, prev_month)

                # Функция расчета статистики
                def calculate_stats(df, period_name):
                    if df.empty:
                        logger.warning(f"Нет данных за {period_name}")
                        return pd.DataFrame()

                    try:
                        stats = (
                            df.groupby("support_name", dropna=False)
                            .agg(
                                total_tickets=("id", "size"),
                                avg_processing_minutes=("processing_time", "mean"),
                                avg_stars=("stars", "mean"),
                            )
                            .reset_index()
                            .rename(columns={
                                "support_name": "Специалист",
                                "total_tickets": "Количество тикетов",
                                "avg_processing_minutes": "Среднее время обработки (мин)",
                                "avg_stars": "Средний рейтинг ⭐",
                            })
                        )

                        # Форматируем время обработки
                        stats["Среднее время обработки (мин)"] = stats["Среднее время обработки (мин)"].apply(
                            lambda x: f"{x:.1f}" if pd.notna(x) else "Нет данных"
                        )

                        # Округляем рейтинг до 1 знака после запятой
                        stats["Средний рейтинг ⭐"] = stats["Средний рейтинг ⭐"].apply(
                            lambda x: f"{x:.1f}" if pd.notna(x) else "Нет оценок"
                        )

                        return stats

                    except Exception as e:
                        logger.error(f"Ошибка расчета статистики: {str(e)}")
                        return pd.DataFrame()

                # Расчет статистики
                stats_current = calculate_stats(df_current, "Текущий месяц")
                stats_previous = calculate_stats(df_previous, "Предыдущий месяц")

                # Выводим данные в лог (замена сохранения в Excel)
                logger.info("Статистика за текущий месяц:\n" + str(stats_current))
                logger.info("Статистика за предыдущий месяц:\n" + str(stats_previous))

            except Exception as e:
                logger.error(f"Ошибка обработки тикетов: {str(e)}")
                raise

            try:
                with pd.ExcelWriter(file_path, engine="openpyxl", mode='a') as writer:
                    if not stats_current.empty:
                        stats_current.to_excel(writer, sheet_name="Текущий месяц", index=False)
                        logger.info("✅ Данные за текущий месяц записаны в файл")

                    if not stats_previous.empty:
                        stats_previous.to_excel(writer, sheet_name="Предыдущий месяц", index=False)
                        logger.info("✅ Данные за предыдущий месяц записаны в файл")
            except Exception as e:
                logger.error(f"Ошибка при записи в файл: {str(e)}")

        # Отправка файла
        try:
            await bot.send_document(
                chat_id=user_id,
                document=types.FSInputFile(file_path),
                caption="📊 Полная выгрузка данных\n⚠️ Файл будет автоматически удален через 15 минут"
            )
            logger.info(f"Файл отправлен пользователю {user_id}")

        except Exception as e:
            logger.error(f"Ошибка отправки файла: {str(e)}")
            raise

        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Файл {file_path} удален")

        await callback_query.message.answer("✅ Выгрузка успешно завершена!")
        logger.info(f"Пользователь {user_id} получил выгрузку")

    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
        await callback_query.message.answer("❌ Произошла ошибка при формировании отчета. Попробуйте позже.")