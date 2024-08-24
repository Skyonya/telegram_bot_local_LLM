import collections
from tools import *
import asyncio
import traceback
import logging
import json

from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command, CommandStart
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiohttp
from aiohttp import ClientTimeout

bot = Bot(token=token)
dp = Dispatcher()

start_kb = InlineKeyboardBuilder()
mention = None

commands = [
    types.BotCommand(command="start", description="Start"),
    #types.BotCommand(command="reset", description="Reset Chat"),
    #types.BotCommand(command="history", description="Look through messages"),
]
ACTIVE_CHATS = {}
ACTIVE_CHATS_LOCK = ContextLock()


async def get_bot_info() -> str:
    global mention
    if mention is None:
        get = await bot.get_me()
        mention = f"@{get.username}"
    return mention


# example: https://docs.aiogram.dev/en/latest/
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    start_message = f"Welcome, <b>{message.from_user.full_name}</b>!"
    await message.answer(
        start_message,
        parse_mode=ParseMode.HTML,
        reply_markup=start_kb.as_markup(),
        disable_web_page_preview=True,
    )


@dp.message()
@perms_allowed
async def handle_message(message: types.Message) -> None:
    await get_bot_info()

    if message.chat.type == "private":
        await ollama_request(message)
        return

    if await is_mentioned_in_group_or_supergroup(message):
        thread = await collect_message_thread(message)
        prompt = format_thread_for_prompt(thread)

        await ollama_request(message, prompt)


async def is_mentioned_in_group_or_supergroup(message: types.Message) -> str or bool:
    if message.chat.type not in ["group", "supergroup"]:
        return False

    is_mentioned = (
            (message.text and message.text.startswith(mention)) or
            (message.caption and message.caption.startswith(mention))
    )

    is_reply_to_bot = (
            message.reply_to_message and
            message.reply_to_message.from_user.id == bot.id
    )

    return is_mentioned or is_reply_to_bot


async def collect_message_thread(message: types.Message, thread=None):
    if thread is None:
        thread = []

    thread.insert(0, message)

    if message.reply_to_message:
        await collect_message_thread(message.reply_to_message, thread)

    return thread


def format_thread_for_prompt(thread) -> str:
    prompt = "Conversation thread:\n\n"
    for msg in thread:
        sender = "User" if msg.from_user.id != bot.id else "Bot"
        content = msg.text or msg.caption or "[No text content]"
        prompt += f"{sender}: {content}\n\n"

    prompt += "History:"
    return prompt



async def add_prompt_to_active_chats(message: Message, prompt: str, model_name: str) -> None:
    async with ACTIVE_CHATS_LOCK:
        if ACTIVE_CHATS.get(message.from_user.id) is None:
            ACTIVE_CHATS[message.from_user.id] = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "stream": True,
            }
        else:
            ACTIVE_CHATS[message.from_user.id]["messages"].append(
                {
                    "role": "user",
                    "content": prompt,
                }
            )


async def handle_response(message: Message, response_data, full_response) -> None or bool:
    full_response_stripped = full_response.strip()
    if full_response_stripped == "":
        return
    if response_data.get("done"):
        text = f"{full_response_stripped}\n\n⚙️ {model_name}\nGenerated in {response_data.get('total_duration') / 1e9:.2f}s."
        await send_response(message, text)
        async with ACTIVE_CHATS_LOCK:
            if ACTIVE_CHATS.get(message.from_user.id) is not None:
                ACTIVE_CHATS[message.from_user.id]["messages"].append(
                    {"role": "assistant", "content": full_response_stripped}
                )
        logging.info(
            f"[Response]: '{full_response_stripped}' for {message.from_user.first_name} {message.from_user.last_name}"
        )
        return True
    return False


async def send_response(message: Message, text) -> None:
    # A negative message.chat.id is a group message
    if message.chat.id < 0 or message.chat.id == message.from_user.id:
        await bot.send_message(chat_id=message.chat.id, text=text)
    else:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=text
        )


async def ollama_request(message: types.Message, prompt: str = None) -> None:
    try:
        full_response = ""
        await bot.send_chat_action(message.chat.id, "typing")
        if prompt is None:
            prompt = message.text or message.caption

        await add_prompt_to_active_chats(message, prompt, model_name)
        logging.info(
            f"[OllamaAPI]: Processing '{prompt}' for {message.from_user.first_name} {message.from_user.last_name}"
        )
        payload = ACTIVE_CHATS.get(message.from_user.id)
        async for response_data in generate(payload, model_name, prompt):
            msg = response_data.get("message")
            if msg is None:
                continue
            chunk = msg.get("content", "")
            full_response += chunk

            if any([c in chunk for c in ".\n!?"]) or response_data.get("done"):
                if await handle_response(message, response_data, full_response):
                    break

    except Exception as e:
        print(f"Error during Ollama request: {e}")
        print(f"-----\n[OllamaAPI-ERR]!\n{traceback.format_exc()}\n-----")
        await bot.send_message(
            chat_id=message.chat.id,
            text=f"Something went wrong.",
            parse_mode=ParseMode.HTML,
        )


async def main() -> None:
    await bot.set_my_commands(commands)
    await dp.start_polling(bot, skip_update=True)

if __name__ == "__main__":
    asyncio.run(main())
