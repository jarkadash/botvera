from typing import Dict

TEXTS: Dict[str, Dict[str, str]] = {
    "choose_language": {"ru": "Выберите язык интерфейса", "en": "Choose interface language"},
    "language_set": {"ru": "Язык установлен: Русский", "en": "Language set: English"},
    "start_hello_message": {
        "ru": "Готово. Интерфейс будет на русском. Используйте кнопки ниже или команды бота.",
        "en": "Done. The interface will be in English. Use the buttons below or bot commands."
    }
}

def t(key: str, lang: str) -> str:
    d = TEXTS.get(key, {})
    return d.get(lang) or d.get("ru") or ""

def normalize_lang(value: str) -> str:
    value = (value or "").lower()
    return "en" if value.startswith("en") else "ru"
