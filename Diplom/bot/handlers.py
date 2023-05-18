from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import CommandStart, Text
from aiogram.types.message import ContentType
from aiogram.utils.exceptions import MessageTextIsEmpty

from loguru import logger

from bot.keyboards import generate_configuration_menu_keyboard, start_menu_keyboard
from bot.misc import ConnectionStatus, ConfigurationOptions, IsAdmin, ssh_connection


async def cmd_start(message: types.Message, state: FSMContext):
    """Сбрасывает текущее состояние (если таковое имеется), отправляет приветственное сообщение - служит точкой входа для пользователя."""
    if await state.get_state():
        await state.reset_state()
    await message.answer(
        "Этот бот предоставляет возможность подключаться через защищенную оболочку (SSH) к компьютерам на базе Linux "
        "используя общие параметры конфигурации SSH: <b>Имя хоста (в качестве IP-адреса), пользователь, порт и пароль</b>",
        reply_markup=start_menu_keyboard
    )


async def set_configuration_state(message: types.Message, state: FSMContext):
    """Переключается в состояние ожидания параметров конфигурации SSH, генерирует интерфейс настроек."""
    configuration = await state.get_data()
    await message.answer(
        "\n".join(f"<b>{option.title()}:</b> {value}" for option, value in configuration.items())
        if configuration
        else "Настройте параметры, кнопка подключения будет доступна после их настройки:",
        reply_markup=generate_configuration_menu_keyboard(**configuration)
    )
    await ConnectionStatus.configuration.set()


async def configuration_menu_button(callback: types.CallbackQuery, state: FSMContext):
    """Реагирует на нажатие кнопки клавиатуры меню "Пуск", вызывая функцию для установки состояния конфигурации SSH."""
    await set_configuration_state(callback.message, state)
    await callback.answer()


async def option_button(callback: types.CallbackQuery, state: FSMContext):
    """Переключается в состояние ожидания значения параметра конфигурации SSH, соответствующего переданным данным обратного вызова."""
    option = callback.data.split('_')[0]
    await callback.message.edit_text(f"Enter the <b>{option}</b>")
    await state.set_state(f"ConfigurationOptions:{option}")


async def update_option_value(option: str, message: types.Message, state: FSMContext) -> None:
    """Устанавливает и обновляет значение переданного параметра в данных состояния, переключается обратно в состояние конфигурации."""
    configuration = await state.get_data()
    configuration[option] = message.text
    await state.update_data(configuration)
    await set_configuration_state(message, state)


async def enter_option_value(message: types.Message, state: FSMContext):
    """Принимает и обновляет значение параметра конфигурации SSH, соответствующее переданному состоянию."""
    current_state = await state.get_state()
    option = current_state.split(':')[1]
    await update_option_value(option, message, state)


async def reset_button(callback: types.CallbackQuery, state: FSMContext):
    """Сбрасывает все пользовательские данные (параметры конфигурации SSH и их значения)."""
    await state.reset_data()
    await callback.message.edit_text("Текущие значения параметров конфигурации подключения были сброшены")
    await set_configuration_state(callback.message, state)


async def set_command_mode_state(message: types.Message):
    """Переключается в состояние ожидания ввода предопределенных команд бота."""
    await message.answer(
        "<b> Теперь вы можете использовать некоторые команды для выполнения на удаленном сервере:</b>\n"
        "/whoami для отображения имени текущего пользователя, вошедшего в систему\n"
        "/uptime чтобы узнать, как долго система активна (запущена)\n\n"
        "<b>Или переключитесь в интерактивный режим, чтобы самостоятельно вводить команды оболочки в сообщениях боту:</b>\n"
        "/interactive чтобы включить /выключить интерактивный режим (когда он включен, приведенные выше команды бота не работают)\n\n"
        "<b>Помните, что многие возможности манипулирования зависят от вашего уровня доступа.</b>"
    )
    await ConnectionStatus.command_mode.set()


async def connect_button(callback: types.CallbackQuery, state: FSMContext):
    """Проверяет возможность SSH-подключения и переключается в состояние ожидания ввода команд бота."""
    if len(await state.get_data()) < 4:
        await callback.answer()
    else:
        await callback.message.edit_text("Дождитесь подтверждения возможности подключения по SSH...")
        try:
            await ssh_connection(state)
        except Exception as e:
            await callback.message.answer(
                "Извините, подключение невозможно.\n\n"
                "<b>Error:</b>\n"
                f"{e}\n\n"
                "Попробуйте изменить настройки вашего подключения (параметры конфигурации SSH):\n"
                "/connect"
            )
        else:
            await set_command_mode_state(callback.message)


async def cmd_whoami(message: types.Message, state: FSMContext):
    """Выполняет команду оболочки whoami и возвращает ее результат."""
    whoami_response = await ssh_connection(state, command="whoami", response=True)
    await message.answer(whoami_response)


async def cmd_uptime(message: types.Message, state: FSMContext):
    """Выполняет команду оболочки uptime и возвращает ее результат."""
    uptime_response = await ssh_connection(state, command="uptime", response=True)
    await message.answer(uptime_response)


async def cmd_interactive(message: types.Message, state: FSMContext):
    """Возвращается к предыдущему состоянию или переключается в состояние интерактивного режима в зависимости от пройденного состояния."""
    current_state = await state.get_state()
    if current_state == ConnectionStatus.interactive_mode.state:
        await message.answer("Интерактивный режим отключен")
        await set_command_mode_state(message)
    elif current_state == ConnectionStatus.command_mode.state:
        await message.answer("Включен интерактивный режим")
        await message.answer(
            "<b>ВАЖНО</b>\n\n"
            "1. Каждая из ваших команд оболочки запускается из домашнего каталога пользователя.\n\n"
            "2. Если ваша команда оболочки ничего не возвращает, об этом будет сообщено в ответном сообщении.\n\n"
            "3. Также вы можете выполнить объединение нескольких команд в одной строке "
            "(например, для решения проблем, связанных с приведенными выше утверждениями):\n"
            "<b>cd dir1; ls</b> – покажет содержимое каталога <b>../dir1/</b>\n"
            "<b>mkdir dir2; cd dir2; touch file; ls -a</b> – эти команды будут возвращены (бот отправит вас обратно):\n"
            "<b>.\n"
            "..\n"
            "file</b>"
        )
        await ConnectionStatus.next()
    else:
        await undefined_request(message)


async def execute_interactive_command(message: types.Message, state: FSMContext):
    """Принимает сообщение пользователя и выполняет его как команду оболочки, возвращая результат выполнения."""
    try:
        interactive_command_response = await ssh_connection(state, command=message.text, response=True)
        await message.answer(interactive_command_response)
    except MessageTextIsEmpty:
        await message.answer("stdout/stderr пусты – ваша команда выполнена, но ничего не вернула")


async def undefined_request(message: types.Message):
    """Отвечает специальным сообщением на запросы, для которых в данный момент нет обработчиков."""
    response = "В настоящее время команда недоступна" if message.text.startswith("/") else "Неопределенный запрос"
    await message.answer(response)


async def unexpected_exception(_update: types.Update, exception: Exception):
    """Улавливает и регистрирует все ошибки и исключения."""
    logger.debug(exception)
    return True


def register_handlers(dp: Dispatcher):
    """Регистрирует все обработчики ботов."""
    dp.register_message_handler(cmd_start, IsAdmin(), CommandStart(), state="*")
    dp.register_message_handler(set_configuration_state, IsAdmin(), commands=["connect"], state="*")
    dp.register_callback_query_handler(configuration_menu_button, Text(equals="configure"))
    dp.register_callback_query_handler(option_button, Text(endswith="option"), state=ConnectionStatus.configuration)
    dp.register_message_handler(enter_option_value, state=ConfigurationOptions.states_names)
    dp.register_callback_query_handler(reset_button, Text(equals="reset"), state=ConnectionStatus.configuration)
    dp.register_callback_query_handler(connect_button, Text(equals="connect"), state=ConnectionStatus.configuration)
    dp.register_message_handler(cmd_whoami, commands=["whoami"], state=ConnectionStatus.command_mode)
    dp.register_message_handler(cmd_uptime, commands=["uptime"], state=ConnectionStatus.command_mode)
    dp.register_message_handler(cmd_interactive, commands=["interactive"], state=ConnectionStatus.states_names)
    dp.register_message_handler(execute_interactive_command, state=ConnectionStatus.interactive_mode)
    dp.register_message_handler(undefined_request, IsAdmin(), content_types=ContentType.ANY, state="*")
    dp.register_errors_handler(unexpected_exception)
