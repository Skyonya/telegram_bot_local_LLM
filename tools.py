from os import getenv
import aiohttp
import json
from aiogram import types
from aiohttp import ClientTimeout
from asyncio import Lock
from functools import wraps
from dotenv import load_dotenv

load_dotenv()
token = getenv("BOT_TOKEN")
allowed_ids = list(map(int, getenv("USER_ID", "0").split(",")))
admin_ids = list(map(int, getenv("ADMIN_ID", "0").split(",")))
allow_all_users_in_groups = bool(int(getenv("ALLOW_ALL_USERS_IN_GROUPS", "0")))
model_name = getenv("MODEL")

ollama_base_url = getenv("OLLAMA_BASE_URL")
ollama_port = getenv("OLLAMA_PORT", "11434")

timeout = getenv("TIMEOUT", "3000")


async def generate(payload: dict, model_name: str, prompt: str) -> None:
    client_timeout = ClientTimeout(total=int(timeout))
    async with aiohttp.ClientSession(timeout=client_timeout) as session:
        url = f"http://{ollama_base_url}:{ollama_port}/api/chat"

        try:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    raise aiohttp.ClientResponseError(
                        status=response.status, message=response.reason
                    )
                buffer = b""

                async for chunk in response.content.iter_any():
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line = line.strip()
                        if line:
                            yield json.loads(line)
        except aiohttp.ClientError as e:
            print(f"Error during request: {e}")


def perms_allowed(func):
    @wraps(func)
    async def wrapper(message: types.Message = None, query: types.CallbackQuery = None):
        user_id = message.from_user.id if message else query.from_user.id
        if user_id in admin_ids or user_id in allowed_ids:
            if message:
                return await func(message)
            elif query:
                return await func(query=query)
        else:
            if message:
                if message and message.chat.type in ["supergroup", "group"]:
                    if allow_all_users_in_groups:
                        return await func(message)
                    return
                await message.answer("Access Denied")
            elif query:
                if message and message.chat.type in ["supergroup", "group"]:
                    return
                await query.answer("Access Denied")

    return wrapper

class ContextLock:
    lock = Lock()

    async def __aenter__(self):
        await self.lock.acquire()

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        self.lock.release()
