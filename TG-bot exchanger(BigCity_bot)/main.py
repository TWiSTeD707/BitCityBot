import sqlite3
import asyncio
from aiogram.filters import CommandStart
from loader import bot, dp
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# Database connection
def get_db_connection():
    conn = sqlite3.connect('clients.db')
    conn.row_factory = sqlite3.Row
    return conn


# Command /start handler
@dp.message(CommandStart())
async def send_welcome(message):
    # Create the start menu with buttons
    start_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обмен", callback_data="exchange")],
        [InlineKeyboardButton(text="История обменов", callback_data="history")],
        [InlineKeyboardButton(text="Оператор", callback_data="operator")]
    ])
    await message.answer("Привет! Выберите опцию:", reply_markup=start_menu)


import buttons


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
