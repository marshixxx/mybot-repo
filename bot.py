import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery, SuccessfulPayment, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv
import os
from openai import AsyncOpenAI
import aiosqlite

logging.basicConfig(level=logging.INFO)

load_dotenv()
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
PAYMENT_TOKEN = os.getenv('PAYMENT_TOKEN', '')

# Функции БД
async def get_user_uses(user_id):
    async with aiosqlite.connect('users.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                            (id INTEGER PRIMARY KEY, uses INTEGER DEFAULT 20)''')
        await db.commit()
        cursor = await db.execute('SELECT uses FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        else:
            await db.execute('INSERT INTO users (id, uses) VALUES (?, 20)', (user_id,))
            await db.commit()
            return 20

async def decrement_uses(user_id):
    async with aiosqlite.connect('users.db') as db:
        await db.execute('UPDATE users SET uses = uses - 1 WHERE id = ?', (user_id,))
        await db.commit()

# Функции инвойсов
async def send_standard_invoice(message_or_query):
    await bot.send_invoice(
        chat_id=message_or_query.chat.id if hasattr(message_or_query, 'chat') else message_or_query.message.chat.id,
        title="Стандартная подписка",
        description="Unlimited запросы к AI на 1 месяц. Доступ к gpt-4o-mini.",
        payload="standard_200rub",
        provider_token=PAYMENT_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="Стандарт (1 месяц)", amount=20000)]
    )

async def send_premium_invoice(message_or_query):
    await bot.send_invoice(
        chat_id=message_or_query.chat.id if hasattr(message_or_query, 'chat') else message_or_query.message.chat.id,
        title="Премиум подписка",
        description="Unlimited запросы на 3 месяца + доступ к продвинутым моделям (gpt-4o).",
        payload="premium_500rub",
        provider_token=PAYMENT_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="Премиум (3 месяца)", amount=50000)]
    )

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command('start'))
async def start(message: types.Message):
    try:
        print(f"Получена команда /start от {message.from_user.id}")
        await message.reply("Привет! Я бот с AI. Отправь вопрос!")
    except Exception as e:
        print(f"Ошибка в /start: {e}")
        await message.reply("Ошибка бота. Попробуй позже.")

@dp.message(Command('pay'))
async def pay(message: types.Message):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
            [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
        ])
        await message.reply("Выбери тариф для подписки на AI:", reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка в /pay: {e}")
        await message.reply("Ошибка с оплатой.")

@dp.callback_query(lambda c: c.data in ['pay_standard', 'pay_premium'])
async def process_callback(callback: CallbackQuery):
    try:
        if callback.data == 'pay_standard':
            await send_standard_invoice(callback)
        elif callback.data == 'pay_premium':
            await send_premium_invoice(callback)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка в callback: {e}")
        await callback.answer("Ошибка оплаты.")

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(lambda message: message.successful_payment)
async def successful_payment(message: types.Message):
    try:
        user_id = message.from_user.id
        async with aiosqlite.connect('users.db') as db:
            await db.execute('UPDATE users SET uses = 9999 WHERE id = ?', (user_id,))
            await db.commit()
        await message.reply("Оплата прошла успешно! Теперь у тебя unlimited доступ. Наслаждайся! 🚀")
    except Exception as e:
        print(f"Ошибка в successful_payment: {e}")
        await message.reply("Ошибка после оплаты.")

@dp.message()
async def handle_message(message: types.Message):
    try:
        print(f"Получено сообщение от {message.from_user.id}: {message.text}")
        user_id = message.from_user.id
        uses_left = await get_user_uses(user_id)
        if uses_left > 0:
            await decrement_uses(user_id)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты полезный AI-ассистент на русском языке."},
                    {"role": "user", "content": message.text}
                ]
            )
            await message.reply(response.choices[0].message.content)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ])
            await message.reply("Бесплатные попытки закончились! Выбери подписку:", reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка в handle_message: {e}")
        await message.reply("Ошибка AI: попробуй позже.")

async def main():
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка polling: {e}")

if __name__ == '__main__':
    asyncio.run(main())