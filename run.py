from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command, CommandStart
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tools import *
import asyncio
from os import getenv

bot = Bot(token=token)
dp = Dispatcher()

start_kb = InlineKeyboardBuilder()

modelname = getenv("INITMODEL")
mention = None

commands = [
    types.BotCommand(command="start", description="Start"),
    types.BotCommand(command="reset", description="Reset Chat"),
    types.BotCommand(command="history", description="Look through messages"),
]


async def get_bot_info():
    global mention
    if mention is None:
        get = await bot.get_me()
        mention = f"@{get.username}"
    return mention


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    start_message = f"Welcome, <b>{message.from_user.full_name}</b>!"
    await message.answer(
        start_message,
        parse_mode=ParseMode.HTML,
        reply_markup=start_kb.as_markup(),
        disable_web_page_preview=True,
    )


async def main() -> None:
    await bot.set_my_commands(commands)
    await dp.start_polling(bot, skip_update=True)

if __name__ == "__main__":
    asyncio.run(main())
