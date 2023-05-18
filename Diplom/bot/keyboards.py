from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


start_menu_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton("⚙ Подключение через SSH", callback_data="configure")]
    ]
)


def generate_configuration_menu_keyboard(
        hostname: str = None, port: str = None, username: str = None, password: str = None,
) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру конфигурации SSH-соединения, соответствующую переданным данным."""
    configuration = locals()
    options_buttons = [
        InlineKeyboardButton(f"{'Изменить' if value else '➕ Добавить'} {option}", callback_data=f"{option}_option")
        for option, value in configuration.items()
    ]
    configuration_keyboard = InlineKeyboardMarkup(row_width=1).add(*options_buttons)
    if any(configuration.values()):
        configuration_keyboard.add(InlineKeyboardButton("Сбросить", callback_data="reset"))
    configuration_keyboard.add(
        InlineKeyboardButton(f"{'👨🏻‍💻' if all(configuration.values()) else '🚫'} Подключиться", callback_data="connect")
    )
    return configuration_keyboard
