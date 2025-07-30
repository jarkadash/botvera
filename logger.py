import logging
from colorama import Fore, Style

# Создаем логгер
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Обработчик для вывода логов в консоль
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# Обработчик для записи логов в файл
file_handler = logging.FileHandler('app.log', mode='w', encoding='utf-8')  # Имя файла, куда будут сохраняться логи
file_handler.setLevel(logging.DEBUG)

# Форматирование сообщений
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Добавляем обработчики к логгеру
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Пример логирования
message = "Это сообщение уровня {}"

# Логирование с цветом в консоли и без цвета в файле
logger.debug(Fore.GREEN + message.format('DEBUG (отладка)') + Style.RESET_ALL)
logger.info(Fore.BLUE + message.format('INFO (информация)') + Style.RESET_ALL)
logger.warning(Fore.YELLOW + message.format('WARNING (предупреждение)') + Style.RESET_ALL)
logger.error(Fore.RED + message.format('ERROR (ошибка)') + Style.RESET_ALL)
logger.critical(Fore.MAGENTA + message.format('CRITICAL (критическое)') + Style.RESET_ALL)
