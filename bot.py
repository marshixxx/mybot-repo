import asyncio
import logging
import io
import requests
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
import aiogram.types as types
from aiogram.types import LabeledPrice, PreCheckoutQuery, SuccessfulPayment, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
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
async def init_db():
    async with aiosqlite.connect('users.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                            (id INTEGER PRIMARY KEY, uses_text INTEGER DEFAULT 20, uses_image INTEGER DEFAULT 10, uses_vision INTEGER DEFAULT 3, uses_code INTEGER DEFAULT 5, premium INTEGER DEFAULT 0)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS messages 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, timestamp TEXT, role TEXT, content TEXT)''')
        await db.commit()
        # Миграция для новых полей
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in await cursor.fetchall()]
        if 'uses_code' not in columns:
            await db.execute('ALTER TABLE users ADD COLUMN uses_code INTEGER DEFAULT 5')
            await db.commit()
            print("Добавлена колонка uses_code в БД")

async def get_text_uses(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT uses_text FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        else:
            await db.execute('INSERT INTO users (id, uses_text, uses_image, uses_vision, uses_code, premium) VALUES (?, 20, 10, 3, 5, 0)', (user_id,))
            await db.commit()
            return 20

async def get_image_uses(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT uses_image FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        else:
            await db.execute('INSERT INTO users (id, uses_text, uses_image, uses_vision, uses_code, premium) VALUES (?, 20, 10, 3, 5, 0)', (user_id,))
            await db.commit()
            return 10

async def get_vision_uses(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT uses_vision FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        else:
            await db.execute('INSERT INTO users (id, uses_text, uses_image, uses_vision, uses_code, premium) VALUES (?, 20, 10, 3, 5, 0)', (user_id,))
            await db.commit()
            return 3

async def get_code_uses(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT uses_code FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        else:
            await db.execute('INSERT INTO users (id, uses_text, uses_image, uses_vision, uses_code, premium) VALUES (?, 20, 10, 3, 5, 0)', (user_id,))
            await db.commit()
            return 5

async def decrement_text_uses(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        await db.execute('UPDATE users SET uses_text = uses_text - 1 WHERE id = ?', (user_id,))
        await db.commit()

async def decrement_image_uses(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        await db.execute('UPDATE users SET uses_image = uses_image - 1 WHERE id = ?', (user_id,))
        await db.commit()

async def decrement_vision_uses(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        await db.execute('UPDATE users SET uses_vision = uses_vision - 1 WHERE id = ?', (user_id,))
        await db.commit()

async def decrement_code_uses(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        await db.execute('UPDATE users SET uses_code = uses_code - 1 WHERE id = ?', (user_id,))
        await db.commit()

async def save_message(user_id, role, content):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        timestamp = datetime.now().isoformat()
        await db.execute('INSERT INTO messages (user_id, timestamp, role, content) VALUES (?, ?, ?, ?)', (user_id, timestamp, role, content))
        await db.commit()

async def get_message_history(user_id, limit=5):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?', (user_id, limit))
        rows = await cursor.fetchall()
        return [{'role': row[0], 'content': row[1]} for row in reversed(rows)]

async def clear_history(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        await db.execute('DELETE FROM messages WHERE user_id = ?', (user_id,))
        await db.commit()
        print(f"История очищена для пользователя {user_id}")

async def get_premium_status(user_id):
    await init_db()
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT premium FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

# Функции инвойсов
async def send_standard_invoice(message_or_query):
    await bot.send_invoice(
        chat_id=message_or_query.chat.id if hasattr(message_or_query, 'chat') else message_or_query.message.chat.id,
        title="Стандартная подписка на AI-бота",
        description="Unlimited доступ к нейросети на 1 месяц: генерация текста, изображений, анализ фото, код. 20 текст + 10 изображений + 3 анализа + 5 кода вначале, потом unlimited. Идеально для повседневного использования. Поддержка на русском. Нет рекламы.",
        payload="standard_200rub",
        provider_token=PAYMENT_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="Стандарт (1 месяц)", amount=20000)]
    )

async def send_premium_invoice(message_or_query):
    await bot.send_invoice(
        chat_id=message_or_query.chat.id if hasattr(message_or_query, 'chat') else message_or_query.message.chat.id,
        title="Премиум подписка на AI-бота",
        description="Unlimited доступ на 3 месяца: генерация текста, изображений (Stable Diffusion), анализ фото, код. 20 текст + 10 изображений + 3 анализа + 5 кода вначале, потом unlimited с приоритетом. Дополнительно: история чата. Идеально для креатива и бизнеса. Поддержка на русском. Нет рекламы.",
        payload="premium_500rub",
        provider_token=PAYMENT_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="Премиум (3 месяца)", amount=50000)]
    )

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Постоянная клавиатура (reply keyboard)
reply_kb = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Новый чат"), types.KeyboardButton(text="Подписка")],
        [types.KeyboardButton(text="Текст"), types.KeyboardButton(text="Изображение")],
        [types.KeyboardButton(text="Анализ фото"), types.KeyboardButton(text="Код")],
        [types.KeyboardButton(text="Помощь")]
    ],
    resize_keyboard=True
)

@dp.message(Command('start'))
async def start(message: types.Message):
    try:
        await clear_history(message.from_user.id)  # Очистка истории для нового чата
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Текст", callback_data="text")],
            [InlineKeyboardButton(text="🖼️ Изображение", callback_data="image")],
            [InlineKeyboardButton(text="🔍 Анализ фото", callback_data="vision")],
            [InlineKeyboardButton(text="💻 Код", callback_data="code")],
            [InlineKeyboardButton(text="💳 Подписка", callback_data="pay")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
        ])
        await message.reply("Привет! Я бот с AI. Выбери действие:", reply_markup=keyboard)
        await message.answer("Постоянные кнопки внизу для быстрого доступа.", reply_markup=reply_kb)
    except Exception as e:
        print(f"Ошибка в /start: {e}")
        await message.reply("Ошибка бота. Попробуй позже.")

@dp.message(Command('help'))
async def help_command(message: types.Message):
    help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
    """
    await message.reply(help_text, parse_mode="Markdown")

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
async def process_callback(callback: types.CallbackQuery):
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
        await init_db()
        async with aiosqlite.connect('users.db') as db:
            await db.execute('UPDATE users SET uses_text = 9999, uses_image = 9999, uses_vision = 9999, uses_code = 9999, premium = 1 WHERE id = ?', (user_id,))
            await db.commit()
        await message.reply("Оплата прошла успешно! Теперь у тебя unlimited доступ. Наслаждайся! 🚀")
    except Exception as e:
        print(f"Ошибка в successful_payment: {e}")
        await message.reply("Ошибка после оплаты.")

@dp.message(F.photo)  # Handler для фото
async def handle_photo(message: types.Message):
    try:
        user_id = message.from_user.id
        is_premium = await get_premium_status(user_id)
        uses_vision_left = await get_vision_uses(user_id)
        if is_premium or uses_vision_left > 0:
            await decrement_vision_uses(user_id) if not is_premium else None
            # Скачивание файла фото
            file_id = message.photo[-1].file_id
            file = await bot.get_file(file_id)
            file_path = file.file_path
            photo_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"
            # GPT Vision анализ
            prompt = message.caption or "Что на этом фото?"
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты полезный AI-аналитик изображений на русском языке. Опиши, что на фото, или сгенерируй подпись, если попросили."},
                    {"role": "user", "content": prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Анализируй это изображение."},
                        {"type": "image_url", "image_url": {"url": photo_url}}
                    ]}
                ]
            )
            answer = response.choices[0].message.content
            await message.reply(answer)
            await save_message(user_id, 'assistant', answer)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ])
            await message.reply("Лимит на анализ фото исчерпан! Подпишись за 200 руб:", reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка в handle_photo: {str(e)}")
        await message.reply("Ошибка анализа фото: попробуй позже.")

@dp.message(F.text == "Текст")
async def text_mode(message: types.Message):
    await message.reply("Режим текста активен. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Изображение")
async def image_mode(message: types.Message):
    await message.reply("Режим изображения активен. Напиши 'Нарисуй [описание]'!", reply_markup=reply_kb)

@dp.message(F.text == "Анализ фото")
async def vision_mode(message: types.Message):
    await message.reply("Режим анализа фото активен. Пришли фото!", reply_markup=reply_kb)

@dp.message(F.text == "Код")
async def code_mode(message: types.Message):
    await message.reply("Режим генерации кода активен. Напиши 'Напиши код на Python для [задача]'!", reply_markup=reply_kb)

@dp.message(F.text == "Подписка")
async def pay_mode(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
        [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
    ])
    await message.reply("Выбери тариф для подписки на AI:", reply_markup=keyboard)

@dp.message(F.text == "Новый чат")
async def new_chat(message: types.Message):
    await clear_history(message.from_user.id)
    await message.reply("Новый чат начат! История очищена. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Помощь")
async def help_command(message: types.Message):
    help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
    """
    await message.reply(help_text, parse_mode="Markdown", reply_markup=reply_kb)

# Handler для inline кнопок из /start
@dp.callback_query(lambda c: c.data in ['text', 'image', 'vision', 'code', 'pay', 'help'])
async def inline_button_handler(callback: types.CallbackQuery):
    try:
        print(f"Inline кнопка нажата: {callback.data}")  # Лог для отладки
        if callback.data == 'text':
            await callback.message.reply("Режим текста активен. Задавай вопросы!", reply_markup=reply_kb)
        elif callback.data == 'image':
            await callback.message.reply("Режим изображения активен. Напиши 'Нарисуй [описание]'!", reply_markup=reply_kb)
        elif callback.data == 'vision':
            await callback.message.reply("Режим анализа фото активен. Пришли фото!", reply_markup=reply_kb)
        elif callback.data == 'code':
            await callback.message.reply("Режим генерации кода активен. Напиши 'Напиши код на Python для [задача]'!", reply_markup=reply_kb)
        elif callback.data == 'pay':
            await callback.message.reply("Выбери тариф для подписки на AI:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ]))
        elif callback.data == 'help':
            help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
            """
            await callback.message.reply(help_text, parse_mode="Markdown", reply_markup=reply_kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка в inline_button_handler: {e}")
        await callback.answer("Ошибка, попробуй снова.")

@dp.message(F.photo)  # Handler для фото
async def handle_photo(message: types.Message):
    try:
        user_id = message.from_user.id
        is_premium = await get_premium_status(user_id)
        uses_vision_left = await get_vision_uses(user_id)
        if is_premium or uses_vision_left > 0:
            await decrement_vision_uses(user_id) if not is_premium else None
            # Скачивание файла фото
            file_id = message.photo[-1].file_id
            file = await bot.get_file(file_id)
            file_path = file.file_path
            photo_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"
            # GPT Vision анализ
            prompt = message.caption or "Что на этом фото?"
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты полезный AI-аналитик изображений на русском языке. Опиши, что на фото, или сгенерируй подпись, если попросили."},
                    {"role": "user", "content": prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Анализируй это изображение."},
                        {"type": "image_url", "image_url": {"url": photo_url}}
                    ]}
                ]
            )
            answer = response.choices[0].message.content
            await message.reply(answer)
            await save_message(user_id, 'assistant', answer)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ])
            await message.reply("Лимит на анализ фото исчерпан! Подпишись за 200 руб:", reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка в handle_photo: {str(e)}")
        await message.reply("Ошибка анализа фото: попробуй позже.")

@dp.message(F.text == "Текст")
async def text_mode(message: types.Message):
    await message.reply("Режим текста активен. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Изображение")
async def image_mode(message: types.Message):
    await message.reply("Режим изображения активен. Напиши 'Нарисуй [описание]'!", reply_markup=reply_kb)

@dp.message(F.text == "Анализ фото")
async def vision_mode(message: types.Message):
    await message.reply("Режим анализа фото активен. Пришли фото!", reply_markup=reply_kb)

@dp.message(F.text == "Код")
async def code_mode(message: types.Message):
    await message.reply("Режим генерации кода активен. Напиши 'Напиши код на Python для [задача]'!", reply_markup=reply_kb)

@dp.message(F.text == "Подписка")
async def pay_mode(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
        [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
    ])
    await message.reply("Выбери тариф для подписки на AI:", reply_markup=keyboard)

@dp.message(F.text == "Новый чат")
async def new_chat(message: types.Message):
    await clear_history(message.from_user.id)
    await message.reply("Новый чат начат! История очищена. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Помощь")
async def help_command(message: types.Message):
    help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
    """
    await message.reply(help_text, parse_mode="Markdown", reply_markup=reply_kb)

# Handler для inline кнопок из /start
@dp.callback_query(lambda c: c.data in ['text', 'image', 'vision', 'code', 'pay', 'help'])
async def inline_button_handler(callback: types.CallbackQuery):
    try:
        print(f"Inline кнопка нажата: {callback.data}")  # Лог для отладки
        if callback.data == 'text':
            await callback.message.reply("Режим текста активен. Задавай вопросы!", reply_markup=reply_kb)
        elif callback.data == 'image':
            await callback.message.reply("Режим изображения активен. Напиши 'Нарисуй [описание]'!", reply_markup=reply_kb)
        elif callback.data == 'vision':
            await callback.message.reply("Режим анализа фото активен. Пришли фото!", reply_markup=reply_kb)
        elif callback.data == 'code':
            await callback.message.reply("Режим генерации кода активен. Напиши 'Напиши код на Python для [задача]'!", reply_markup=reply_kb)
        elif callback.data == 'pay':
            await callback.message.reply("Выбери тариф для подписки на AI:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ]))
        elif callback.data == 'help':
            help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
            """
            await callback.message.reply(help_text, parse_mode="Markdown", reply_markup=reply_kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка в inline_button_handler: {e}")
        await callback.answer("Ошибка, попробуй снова.")

@dp.message(F.photo)  # Handler для фото
async def handle_photo(message: types.Message):
    try:
        user_id = message.from_user.id
        is_premium = await get_premium_status(user_id)
        uses_vision_left = await get_vision_uses(user_id)
        if is_premium or uses_vision_left > 0:
            await decrement_vision_uses(user_id) if not is_premium else None
            # Скачивание файла фото
            file_id = message.photo[-1].file_id
            file = await bot.get_file(file_id)
            file_path = file.file_path
            photo_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"
            # GPT Vision анализ
            prompt = message.caption or "Что на этом фото?"
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты полезный AI-аналитик изображений на русском языке. Опиши, что на фото, или сгенерируй подпись, если попросили."},
                    {"role": "user", "content": prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Анализируй это изображение."},
                        {"type": "image_url", "image_url": {"url": photo_url}}
                    ]}
                ]
            )
            answer = response.choices[0].message.content
            await message.reply(answer)
            await save_message(user_id, 'assistant', answer)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ])
            await message.reply("Лимит на анализ фото исчерпан! Подпишись за 200 руб:", reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка в handle_photo: {str(e)}")
        await message.reply("Ошибка анализа фото: попробуй позже.")

@dp.message(F.text == "Текст")
async def text_mode(message: types.Message):
    await message.reply("Режим текста активен. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Изображение")
async def image_mode(message: types.Message):
    await message.reply("Режим изображения активен. Напиши 'Нарисуй [описание]'!", reply_markup=reply_kb)

@dp.message(F.text == "Анализ фото")
async def vision_mode(message: types.Message):
    await message.reply("Режим анализа фото активен. Пришли фото!", reply_markup=reply_kb)

@dp.message(F.text == "Код")
async def code_mode(message: types.Message):
    await message.reply("Режим генерации кода активен. Напиши 'Напиши код на Python для [задача]'!", reply_markup=reply_kb)

@dp.message(F.text == "Подписка")
async def pay_mode(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
        [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
    ])
    await message.reply("Выбери тариф для подписки на AI:", reply_markup=keyboard)

@dp.message(F.text == "Новый чат")
async def new_chat(message: types.Message):
    await clear_history(message.from_user.id)
    await message.reply("Новый чат начат! История очищена. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Помощь")
async def help_command(message: types.Message):
    help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
    """
    await message.reply(help_text, parse_mode="Markdown", reply_markup=reply_kb)

# Handler для inline кнопок из /start
@dp.callback_query(lambda c: c.data in ['text', 'image', 'vision', 'code', 'pay', 'help'])
async def inline_button_handler(callback: types.CallbackQuery):
    try:
        print(f"Inline кнопка нажата: {callback.data}")  # Лог для отладки
        if callback.data == 'text':
            await callback.message.reply("Режим текста активен. Задавай вопросы!", reply_markup=reply_kb)
        elif callback.data == 'image':
            await callback.message.reply("Режим изображения активен. Напиши 'Нарисуй [описание]'!", reply_markup=reply_kb)
        elif callback.data == 'vision':
            await callback.message.reply("Режим анализа фото активен. Пришли фото!", reply_markup=reply_kb)
        elif callback.data == 'code':
            await callback.message.reply("Режим генерации кода активен. Напиши 'Напиши код на Python для [задача]'!", reply_markup=reply_kb)
        elif callback.data == 'pay':
            await callback.message.reply("Выбери тариф для подписки на AI:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ]))
        elif callback.data == 'help':
            help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
            """
            await callback.message.reply(help_text, parse_mode="Markdown", reply_markup=reply_kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка в inline_button_handler: {e}")
        await callback.answer("Ошибка, попробуй снова.")

@dp.message(F.photo)  # Handler для фото
async def handle_photo(message: types.Message):
    try:
        user_id = message.from_user.id
        is_premium = await get_premium_status(user_id)
        uses_vision_left = await get_vision_uses(user_id)
        if is_premium or uses_vision_left > 0:
            await decrement_vision_uses(user_id) if not is_premium else None
            # Скачивание файла фото
            file_id = message.photo[-1].file_id
            file = await bot.get_file(file_id)
            file_path = file.file_path
            photo_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"
            # GPT Vision анализ
            prompt = message.caption or "Что на этом фото?"
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты полезный AI-аналитик изображений на русском языке. Опиши, что на фото, или сгенерируй подпись, если попросили."},
                    {"role": "user", "content": prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Анализируй это изображение."},
                        {"type": "image_url", "image_url": {"url": photo_url}}
                    ]}
                ]
            )
            answer = response.choices[0].message.content
            await message.reply(answer)
            await save_message(user_id, 'assistant', answer)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ])
            await message.reply("Лимит на анализ фото исчерпан! Подпишись за 200 руб:", reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка в handle_photo: {str(e)}")
        await message.reply("Ошибка анализа фото: попробуй позже.")

@dp.message(F.text == "Текст")
async def text_mode(message: types.Message):
    await message.reply("Режим текста активен. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Изображение")
async def image_mode(message: types.Message):
    await message.reply("Режим изображения активен. Напиши 'Нарисуй [описание]'!", reply_markup=reply_kb)

@dp.message(F.text == "Анализ фото")
async def vision_mode(message: types.Message):
    await message.reply("Режим анализа фото активен. Пришли фото!", reply_markup=reply_kb)

@dp.message(F.text == "Код")
async def code_mode(message: types.Message):
    await message.reply("Режим генерации кода активен. Напиши 'Напиши код на Python для [задача]'!", reply_markup=reply_kb)

@dp.message(F.text == "Подписка")
async def pay_mode(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
        [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
    ])
    await message.reply("Выбери тариф для подписки на AI:", reply_markup=keyboard)

@dp.message(F.text == "Новый чат")
async def new_chat(message: types.Message):
    await clear_history(message.from_user.id)
    await message.reply("Новый чат начат! История очищена. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Помощь")
async def help_command(message: types.Message):
    help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
    """
    await message.reply(help_text, parse_mode="Markdown", reply_markup=reply_kb)

# Handler для inline кнопок из /start
@dp.callback_query(lambda c: c.data in ['text', 'image', 'vision', 'code', 'pay', 'help'])
async def inline_button_handler(callback: types.CallbackQuery):
    try:
        print(f"Inline кнопка нажата: {callback.data}")  # Лог для отладки
        if callback.data == 'text':
            await callback.message.reply("Режим текста активен. Задавай вопросы!", reply_markup=reply_kb)
        elif callback.data == 'image':
            await callback.message.reply("Режим изображения активен. Напиши 'Нарисуй [описание]'!", reply_markup=reply_kb)
        elif callback.data == 'vision':
            await callback.message.reply("Режим анализа фото активен. Пришли фото!", reply_markup=reply_kb)
        elif callback.data == 'code':
            await callback.message.reply("Режим генерации кода активен. Напиши 'Напиши код на Python для [задача]'!", reply_markup=reply_kb)
        elif callback.data == 'pay':
            await callback.message.reply("Выбери тариф для подписки на AI:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ]))
        elif callback.data == 'help':
            help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
            """
            await callback.message.reply(help_text, parse_mode="Markdown", reply_markup=reply_kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка в inline_button_handler: {e}")
        await callback.answer("Ошибка, попробуй снова.")

@dp.message(F.photo)  # Handler для фото
async def handle_photo(message: types.Message):
    try:
        user_id = message.from_user.id
        is_premium = await get_premium_status(user_id)
        uses_vision_left = await get_vision_uses(user_id)
        if is_premium or uses_vision_left > 0:
            await decrement_vision_uses(user_id) if not is_premium else None
            # Скачивание файла фото
            file_id = message.photo[-1].file_id
            file = await bot.get_file(file_id)
            file_path = file.file_path
            photo_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"
            # GPT Vision анализ
            prompt = message.caption or "Что на этом фото?"
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты полезный AI-аналитик изображений на русском языке. Опиши, что на фото, или сгенерируй подпись, если попросили."},
                    {"role": "user", "content": prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Анализируй это изображение."},
                        {"type": "image_url", "image_url": {"url": photo_url}}
                    ]}
                ]
            )
            answer = response.choices[0].message.content
            await message.reply(answer)
            await save_message(user_id, 'assistant', answer)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
            ])
            await message.reply("Лимит на анализ фото исчерпан! Подпишись за 200 руб:", reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка в handle_photo: {str(e)}")
        await message.reply("Ошибка анализа фото: попробуй позже.")

@dp.message(F.text == "Текст")
async def text_mode(message: types.Message):
    await message.reply("Режим текста активен. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Изображение")
async def image_mode(message: types.Message):
    await message.reply("Режим изображения активен. Напиши 'Нарисуй [описание]'!", reply_markup=reply_kb)

@dp.message(F.text == "Анализ фото")
async def vision_mode(message: types.Message):
    await message.reply("Режим анализа фото активен. Пришли фото!", reply_markup=reply_kb)

@dp.message(F.text == "Код")
async def code_mode(message: types.Message):
    await message.reply("Режим генерации кода активен. Напиши 'Напиши код на Python для [задача]'!", reply_markup=reply_kb)

@dp.message(F.text == "Подписка")
async def pay_mode(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
        [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
    ])
    await message.reply("Выбери тариф для подписки на AI:", reply_markup=keyboard)

@dp.message(F.text == "Новый чат")
async def new_chat(message: types.Message):
    await clear_history(message.from_user.id)
    await message.reply("Новый чат начат! История очищена. Задавай вопросы!", reply_markup=reply_kb)

@dp.message(F.text == "Помощь")
async def help_command(message: types.Message):
    help_text = """
**Помощь по боту:**

- **Текст**: Задавай вопросы, GPT ответит.
- **Изображение**: "Нарисуй кота" — генерирует картинку.
- **Анализ фото**: Пришли фото + caption "Что на фото?" — анализ.
- **Код**: "Напиши код на Python для калькулятора" — генерирует код.
- **Подписка**: 200 руб/месяц за unlimited.

Бесплатно: 20 текст + 10 изображений + 3 анализа + 5 кода. /pay для подписки.

История чата сохраняется (5 сообщений бесплатно, 10 в премиум).
    """
    await message.reply(help_text, parse_mode="Markdown", reply_markup=reply_kb)

@dp.message()
async def handle_message(message: types.Message):
    try:
        await save_message(message.from_user.id, 'user', message.text)
        user_id = message.from_user.id
        is_premium = await get_premium_status(user_id)
        text_lower = message.text.lower()
        if any(word in text_lower for word in ['нарисуй', 'draw', 'generate image', 'картинка', 'изображение', 'picture']):
            uses_image_left = await get_image_uses(user_id)
            if is_premium or uses_image_left > 0:
                await decrement_image_uses(user_id) if not is_premium else None
                print("Начинаю генерацию изображения...")
                # Генерация изображения с Pollinations.ai (бесплатно, GET)
                prompt = message.text.replace(' ', '%20')  # URL-encode
                seed = random.randint(1, 1000000)  # Случайный seed для вариаций
                api_url = f"https://pollinations.ai/p/{prompt}?seed={seed}"
                response = requests.get(api_url)
                if response.status_code == 200:
                    image_bytes = response.content
                    if len(image_bytes) > 1000:  # Проверка на реальное изображение
                        bytes_io = io.BytesIO(image_bytes)
                        photo = BufferedInputFile(bytes_io.getvalue(), filename="image.png")
                        await message.reply_photo(photo=photo, caption="Вот твоё изображение! 🎨")
                        await save_message(user_id, 'assistant', 'Изображение сгенерировано.')
                    else:
                        raise Exception("Ответ не содержит изображение")
                else:
                    raise Exception(f"API error: {response.status_code} - {response.text}")
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                    [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
                ])
                await message.reply("Лимит на изображения исчерпан! Подпишись за 200 руб:", reply_markup=keyboard)
        elif any(word in text_lower for word in ['код', 'напиши код', 'code', 'программа']):
            uses_code_left = await get_code_uses(user_id)
            if is_premium or uses_code_left > 0:
                await decrement_code_uses(user_id) if not is_premium else None
                # Генерация кода
                history = await get_message_history(user_id, 5 if not is_premium else 10)
                messages = [{'role': msg['role'], 'content': msg['content']} for msg in history]
                messages.append({"role": "user", "content": message.text})
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Ты ассистент по программированию. Генерируй код с объяснением на русском языке. Используй markdown для кода (```python ... ```)."},
                        *messages
                    ]
                )
                answer = response.choices[0].message.content
                await message.reply(answer)
                await save_message(user_id, 'assistant', answer)
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                    [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
                ])
                await message.reply("Лимит на генерацию кода исчерпан! Подпишись за 200 руб:", reply_markup=keyboard)
        else:
            uses_text_left = await get_text_uses(user_id)
            if is_premium or uses_text_left > 0:
                await decrement_text_uses(user_id) if not is_premium else None
                # Текст с историей
                history = await get_message_history(user_id, 5 if not is_premium else 10)
                messages = [{'role': msg['role'], 'content': msg['content']} for msg in history]
                messages.append({"role": "user", "content": message.text})
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages
                )
                answer = response.choices[0].message.content
                await message.reply(answer)
                await save_message(user_id, 'assistant', answer)
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Стандарт: 200 руб/месяц", callback_data="pay_standard")],
                    [InlineKeyboardButton(text="⭐ Премиум: 500 руб/3 месяца", callback_data="pay_premium")]
                ])
                await message.reply("Лимит на текст исчерпан! Подпишись за 200 руб:", reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка в handle_message: {str(e)}")
        await message.reply("Ошибка AI: попробуй позже.")

async def main():
    await init_db()  # Инициализация БД при старте
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка polling: {e}")

if __name__ == '__main__':
    asyncio.run(main())