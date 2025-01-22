import os
import sqlite3
import logging
import asyncio
import signal
import re
from datetime import datetime
from threading import Thread
from flask import Flask, request
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup,
    error as telegram_error
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext,
    CallbackQueryHandler
)

# ========== ИНИЦИАЛИЗАЦИЯ FLASK ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 Бот активен! Порт: " + os.environ.get('PORT', '10000'), 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = os.environ.get('7833583184:AAGRYKayEY1wjP8TZs9rVrNgbSLAAQwHFGY')
ADMIN_CHAT_ID = os.environ.get(' 694873692')
DB_NAME = "applications.db"

# ========== ЭТАПЫ ДИАЛОГА ==========
(
    CITIZENSHIP,
    CITIZENSHIP_SNG,
    CITIZENSHIP_OTHER,
    FULL_NAME,
    PRIOR_EMPLOYMENT,
    EMPLOYMENT_PERIOD,
    PHONE,
    CITY,
    AGE,
    SELF_EMPLOYED,
    SELF_EMPLOYED_CHOICE,
    TRANSPORT,
    CONFIRMATION,
    EDIT_FIELD,
) = range(14)

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT NOT NULL,
            citizenship TEXT NOT NULL,
            prior_employment TEXT,
            employment_period TEXT,
            phone TEXT NOT NULL,
            city TEXT NOT NULL,
            age INTEGER NOT NULL,
            self_employed TEXT NOT NULL,
            self_employed_choice TEXT,
            transport TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'new'
        )
    """)
    conn.commit()
    conn.close()

def save_application(user_data, user_id, username):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO applications (
                user_id,
                username,
                full_name,
                citizenship,
                prior_employment,
                employment_period,
                phone,
                city,
                age,
                self_employed,
                self_employed_choice,
                transport
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            username,
            user_data.get('full_name'),
            user_data.get('citizenship'),
            user_data.get('prior_employment'),
            user_data.get('employment_period'),
            user_data.get('phone'),
            user_data.get('city'),
            user_data.get('age'),
            user_data.get('self_employed'),
            user_data.get('self_employed_choice'),
            user_data.get('transport')
        ))
        
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Ошибка сохранения в БД: {e}")
        return None
    finally:
        conn.close()

# ========== ВАЛИДАЦИЯ ДАННЫХ ==========
def validate_application(data: dict) -> bool:
    required_fields = [
        'citizenship', 
        'full_name',
        'phone',
        'city',
        'age',
        'self_employed',
        'transport'
    ]
    return all(data.get(field) for field in required_fields)

# ========== КЛАВИАТУРЫ ==========
def add_restart_button(keyboard):
    return keyboard + [[InlineKeyboardButton("🔄 Перезапустить", callback_data='/start')]]

SNG_COUNTRIES = [
    ["🇧🇾 Беларусь", "🇰🇿 Казахстан"],
    ["🇺🇿 Узбекистан", "🇦🇲 Армения"],
    ["🇦🇿 Азербайджан", "🇲🇩 Молдова"],
    ["🇰🇬 Кыргызстан", "🇹🇯 Таджикистан"],
    ["🌍 Другая страна", "🚫 Пропустить"]
]

CITIZENSHIP_KEYBOARD = add_restart_button([["🇷🇺 РФ", "🌍 СНГ/Другое"]])
PRIOR_EMPLOYMENT_KEYBOARD = add_restart_button([["✅ Да", "❌ Нет"]])
EMPLOYMENT_PERIOD_KEYBOARD = add_restart_button([
    ["📅 Меньше 40 дней назад"], 
    ["🗓️ Больше 40 дней назад"]
])
STATUS_KEYBOARD = add_restart_button([["✅ Да", "❌ Нет"]])
TRANSPORT_KEYBOARD = add_restart_button([["🚗 Авто", "🚲 Вело", "⚡ Электровело"]])
SELF_EMPLOYED_CHOICE_KEYBOARD = add_restart_button([["📝 Оформить сейчас", "🏢 В офисе"]])
CONFIRM_KEYBOARD = add_restart_button([["✅ Подтвердить", "✏️ Изменить"]])
EDIT_FIELD_KEYBOARD = add_restart_button([
    ["ФИО", "Телефон"],
    ["Город", "Возраст"],
    ["Транспорт", "Назад"]
])

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "🌟 Добро пожаловать в МагнитДоставка! 🌟\n"
        "Выберите гражданство:",
        reply_markup=ReplyKeyboardMarkup(
            CITIZENSHIP_KEYBOARD,
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return CITIZENSHIP

async def citizenship(update: Update, context: CallbackContext) -> int:
    choice = update.message.text
    if choice not in ["🇷🇺 РФ", "🌍 СНГ/Другое"]:
        await update.message.reply_text("Пожалуйста, выберите вариант из клавиатуры.")
        return CITIZENSHIP
    
    if choice == "🌍 СНГ/Другое":
        await update.message.reply_text(
            "🌐 Выберите вашу страну:",
            reply_markup=ReplyKeyboardMarkup(
                add_restart_button(SNG_COUNTRIES),
                resize_keyboard=True
            )
        )
        return CITIZENSHIP_SNG
    
    context.user_data["citizenship"] = "🇷🇺 Россия"
    await update.message.reply_text("👤 Введите ФИО полностью:")
    return FULL_NAME

async def citizenship_sng(update: Update, context: CallbackContext) -> int:
    country = update.message.text
    valid_choices = [item for sublist in SNG_COUNTRIES for item in sublist]
    
    if country not in valid_choices:
        await update.message.reply_text("Пожалуйста, выберите вариант из клавиатуры.")
        return CITIZENSHIP_SNG
    
    if country == "🌍 Другая страна":
        await update.message.reply_text(
            "🌐 Укажите ваше гражданство:",
            reply_markup=ReplyKeyboardMarkup(
                add_restart_button([["🚫 Пропустить"]]),
                resize_keyboard=True
            )
        )
        return CITIZENSHIP_OTHER
    
    context.user_data["citizenship"] = country
    await update.message.reply_text("👤 Введите ФИО полностью:")
    return FULL_NAME

async def citizenship_other(update: Update, context: CallbackContext) -> int:
    country = update.message.text.strip()
    if country == "🚫 Пропустить":
        country = "Не указано"
    
    context.user_data["citizenship"] = f"🌍 {country}"
    await update.message.reply_text("👤 Введите ФИО полностью:")
    return FULL_NAME

async def full_name(update: Update, context: CallbackContext) -> int:
    full_name = update.message.text.strip()
    if not re.match(r"^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+$", full_name):
        await update.message.reply_text("❌ Введите ФИО в формате: Фамилия Имя Отчество")
        return FULL_NAME
    
    context.user_data["full_name"] = full_name
    await update.message.reply_text(
        "📋 Ранее работали в МагнитДоставке?",
        reply_markup=ReplyKeyboardMarkup(
            PRIOR_EMPLOYMENT_KEYBOARD,
            resize_keyboard=True
        )
    )
    return PRIOR_EMPLOYMENT

async def prior_employment(update: Update, context: CallbackContext) -> int:
    answer = update.message.text
    if answer not in ["✅ Да", "❌ Нет"]:
        await update.message.reply_text("Пожалуйста, выберите вариант из клавиатуры.")
        return PRIOR_EMPLOYMENT
    context.user_data["prior_employment"] = answer
    
    if answer == "❌ Нет":
        await update.message.reply_text("📱 Введите номер телефона (начинается с +7, 7 или 8):")
        return PHONE
    
    await update.message.reply_text(
        "📆 Укажите срок предыдущей работы:",
        reply_markup=ReplyKeyboardMarkup(
            EMPLOYMENT_PERIOD_KEYBOARD,
            resize_keyboard=True
        )
    )
    return EMPLOYMENT_PERIOD

async def employment_period(update: Update, context: CallbackContext) -> int:
    period = update.message.text
    valid_choices = ["📅 Меньше 40 дней назад", "🗓️ Больше 40 дней назад"]
    
    if period not in valid_choices:
        await update.message.reply_text(
            "Пожалуйста, выберите вариант из клавиатуры:",
            reply_markup=ReplyKeyboardMarkup(
                EMPLOYMENT_PERIOD_KEYBOARD,
                resize_keyboard=True
            )
        )
        return EMPLOYMENT_PERIOD
    
    context.user_data["employment_period"] = period
    
    if period == "📅 Меньше 40 дней назад":
        context.user_data["special_note"] = "🚨 <b>ВНИМАНИЕ: Кандидат работал менее 40 дней назад!</b>"
    
    await update.message.reply_text("📱 Введите номер телефона (начинается с +7, 7 или 8):")
    return PHONE

async def phone(update: Update, context: CallbackContext) -> int:
    raw_phone = update.message.text
    clean_phone = ''.join(filter(str.isdigit, raw_phone))
    
    if clean_phone.startswith('8') and len(clean_phone) == 11:
        clean_phone = '7' + clean_phone[1:]
    
    if not clean_phone.startswith('7') or len(clean_phone) != 11:
        await update.message.reply_text(
            "❌ Неверный формат номера. Примеры:\n"
            "+79123456789\n79123456789\n89123456789",
            reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
        )
        return PHONE
    
    formatted_phone = f"+7 ({clean_phone[1:4]}) {clean_phone[4:7]}-{clean_phone[7:9]}-{clean_phone[9:11]}"
    context.user_data["phone"] = formatted_phone
    await update.message.reply_text("🏙️ Введите ваш город:")
    return CITY

async def city(update: Update, context: CallbackContext) -> int:
    city = update.message.text.strip()
    if len(city) < 2 or any(c.isdigit() or c in '!@#$%^&*()_+={}[]|\\:;"<>,?/~`' for c in city):
        await update.message.reply_text("❌ Введите корректное название города без цифр и спецсимволов.")
        return CITY
    
    context.user_data["city"] = city
    await update.message.reply_text("📅 Введите ваш возраст:")
    return AGE

async def age(update: Update, context: CallbackContext) -> int:
    try:
        age = int(update.message.text)
        if age < 14 or age > 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректный возраст (число от 14 до 100):")
        return AGE
    
    context.user_data["age"] = age
    
    if age < 18:
        context.user_data["age_warning"] = True
    
    await update.message.reply_text(
        "📄 Есть статус самозанятого?",
        reply_markup=ReplyKeyboardMarkup(
            STATUS_KEYBOARD,
            resize_keyboard=True
        )
    )
    return SELF_EMPLOYED

async def self_employed(update: Update, context: CallbackContext) -> int:
    status = update.message.text
    if status not in ["✅ Да", "❌ Нет"]:
        await update.message.reply_text("Пожалуйста, выберите вариант из клавиатуры.")
        return SELF_EMPLOYED
    
    context.user_data["self_employed"] = status
    context.user_data.pop("self_employed_choice", None)
    
    if status == "❌ Нет":
        await update.message.reply_text(
            "🛠️ Хотите оформить статус сейчас?",
            reply_markup=ReplyKeyboardMarkup(
                SELF_EMPLOYED_CHOICE_KEYBOARD,
                resize_keyboard=True
            )
        )
        return SELF_EMPLOYED_CHOICE
    
    await update.message.reply_text(
        "🚗 Выберите транспорт:",
        reply_markup=ReplyKeyboardMarkup(
            TRANSPORT_KEYBOARD,
            resize_keyboard=True
        )
    )
    return TRANSPORT

async def self_employed_choice(update: Update, context: CallbackContext) -> int:
    choice = update.message.text
    if choice not in ["📝 Оформить сейчас", "🏢 В офисе"]:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки ниже👇",
            reply_markup=ReplyKeyboardMarkup(
                SELF_EMPLOYED_CHOICE_KEYBOARD,
                resize_keyboard=True
            )
        )
        return SELF_EMPLOYED_CHOICE
    
    context.user_data["self_employed_choice"] = choice

    if choice == "📝 Оформить сейчас":
        instruction = """
📋 <b>Простая инструкция:</b>

1. <b>Скачайте приложение</b> 📲
   → <a href="https://npd.nalog.ru/">«Мой налог» от ФНС</a>

2. <b>Заполните данные:</b>
   • Паспорт РФ
   • СНИЛС/ИНН
   • Номер телефона

3. <b>Загрузите фото:</b>
   📷 Главная страница паспорта
   📷 Страница с пропиской

4. <b>Отправьте на проверку</b> ✅

5. <b>Получите свидетельство</b> через 1-3 дня 🎉

Готово! Теперь вы самозанятый!
"""
        await update.message.reply_text(
            instruction,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📲 Скачать приложение", url="https://npd.nalog.ru/")]
            ])
        )
    
    await update.message.reply_text(
        "🚗 Выберите транспорт:",
        reply_markup=ReplyKeyboardMarkup(
            TRANSPORT_KEYBOARD,
            resize_keyboard=True
        )
    )
    return TRANSPORT

async def transport(update: Update, context: CallbackContext) -> int:
    transport = update.message.text
    if transport not in ["🚗 Авто", "🚲 Вело", "⚡ Электровело"]:
        await update.message.reply_text(
            "Пожалуйста, выберите транспорт из предложенных👇",
            reply_markup=ReplyKeyboardMarkup(
                TRANSPORT_KEYBOARD,
                resize_keyboard=True
            )
        )
        return TRANSPORT
    
    context.user_data["transport"] = transport

    summary = [
        "📋 <b>Проверьте данные:</b>\n",
        f"▫️ ФИО: {context.user_data.get('full_name')}",
        f"▫️ Телефон: {context.user_data.get('phone')}",
        f"▫️ Город: {context.user_data.get('city')}",
        f"▫️ Возраст: {context.user_data.get('age')}",
        f"▫️ Транспорт: {transport}\n",
        "<b>Всё верно?</b>"
    ]
    
    await update.message.reply_text(
        "\n".join(summary),
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            CONFIRM_KEYBOARD,
            resize_keyboard=True
        )
    )
    return CONFIRMATION

async def confirmation(update: Update, context: CallbackContext) -> int:
    choice = update.message.text
    
    if choice == "✅ Подтвердить":
        if not validate_application(context.user_data):
            await update.message.reply_text(
                "❌ Ошибка: Не все данные заполнены! Начните заново.",
                reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
            )
            return ConversationHandler.END

        user = update.message.from_user
        app_id = save_application(
            user_data=context.user_data,
            user_id=user.id,
            username=user.username
        )
        
        if not app_id:
            await update.message.reply_text(
                "⚠️ Ошибка сохранения заявки. Пожалуйста, попробуйте снова.",
                reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
            )
            return ConversationHandler.END

        message = [
            f"🔔 <b>Новая заявка #{app_id}</b>\n\n",
            f"👤 Пользователь: @{user.username or 'не указан'} (ID: {user.id})\n",
            f"▫️ Возраст: {context.user_data.get('age', '—')}\n",
            f"▫️ Гражданство: {context.user_data.get('citizenship', '—')}\n",
            f"▫️ ФИО: {context.user_data.get('full_name', '—')}\n",
            f"▫️ Телефон: {context.user_data.get('phone', '—')}\n",
            f"▫️ Город: {context.user_data.get('city', '—')}\n",
            f"▫️ Самозанятый: {context.user_data.get('self_employed', '—')}\n"
        ]
        
        if choice := context.user_data.get('self_employed_choice'):
            message.append(f"▫️ Оформление: {choice}\n")
        
        message.append(f"▫️ Транспорт: {context.user_data.get('transport', '—')}\n")
        
        if context.user_data.get('special_note'):
            message.append(f"\n{context.user_data['special_note']}")
        
        if context.user_data.get('age_warning'):
            message.append("\n🚨 <b>ВНИМАНИЕ: Кандидат несовершеннолетний!</b>")

        keyboard = [
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"approve_{app_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{app_id}")
            ]
        ]

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text="".join(message),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        await update.message.reply_text(
            "✅ Заявка принята! Ожидайте звонка.",
            reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
        )
        return ConversationHandler.END
        
    elif choice == "✏️ Изменить":
        await update.message.reply_text(
            "Выберите поле для изменения:",
            reply_markup=ReplyKeyboardMarkup(
                EDIT_FIELD_KEYBOARD,
                resize_keyboard=True
            )
        )
        return EDIT_FIELD
        
    else:
        await update.message.reply_text("Используйте кнопки ниже👇")
        return CONFIRMATION

async def edit_field_handler(update: Update, context: CallbackContext) -> int:
    field = update.message.text
    valid_fields = ["ФИО", "Телефон", "Город", "Возраст", "Транспорт"]
    
    if field == "Назад":
        await update.message.reply_text(
            "🚗 Выберите транспорт:",
            reply_markup=ReplyKeyboardMarkup(
                TRANSPORT_KEYBOARD,
                resize_keyboard=True
            )
        )
        return TRANSPORT
    
    if field not in valid_fields:
        await update.message.reply_text(
            "Пожалуйста, выберите поле из списка",
            reply_markup=ReplyKeyboardMarkup(
                EDIT_FIELD_KEYBOARD,
                resize_keyboard=True
            )
        )
        return EDIT_FIELD
    
    context.user_data["editing_field"] = field
    await update.message.reply_text(f"Введите новое значение для поля '{field}':")
    
    return {
        "ФИО": FULL_NAME,
        "Телефон": PHONE,
        "Город": CITY,
        "Возраст": AGE,
        "Транспорт": TRANSPORT
    }[field]

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "❌ Диалог прерван.",
        reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
    )
    return ConversationHandler.END

async def error_handler(update: Update, context: CallbackContext):
    logger.error(msg="Ошибка в обработчике:", exc_info=context.error)
    
    if update and update.message:
        await update.message.reply_text(
            "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.",
            reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
        )

# ========== АДМИН-КОМАНДЫ ==========
async def admin_stats(update: Update, context: CallbackContext):
    if update.message.from_user.id != ADMIN_CHAT_ID:
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
        stats = dict(cursor.fetchall())
        
        cursor.execute("""
            SELECT id, created_at, city 
            FROM applications 
            WHERE status = 'new'
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        last_apps = cursor.fetchall()
        
        message = [
            "📊 <b>Статистика заявок</b>\n",
            f"• Новые: {stats.get('new', 0)}",
            f"• Обработанные: {stats.get('processed', 0)}\n",
            "⏳ <b>Последние заявки:</b>\n"
        ]
        
        for app in last_apps:
            message.append(f"#{app[0]} - {app[2]} ({app[1][:16]})\n")
            
        await update.message.reply_text(
            "\n".join(message),
            parse_mode="HTML"
        )
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка БД: {e}")
        await update.message.reply_text("❌ Ошибка получения статистики")
    finally:
        conn.close()

async def approve_application(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    
    try:
        app_id = int(context.args[0])
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE applications 
            SET status = 'approved' 
            WHERE id = ? AND status = 'new'
        """, (app_id,))
        
        if cursor.rowcount == 0:
            await update.message.reply_text("⚠️ Заявка не найдена или уже обработана")
            return
        
        cursor.execute("SELECT user_id, full_name FROM applications WHERE id = ?", (app_id,))
        user_id, full_name = cursor.fetchone()
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 {full_name}, ваша заявка одобрена! С вами свяжутся в ближайшее время."
            )
        except telegram_error.TelegramError as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
        
        await update.message.reply_text(f"✅ Заявка #{app_id} одобрена")
        conn.commit()
        
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /approve <ID_заявки>")
    except Exception as e:
        logger.error(f"Ошибка approve: {e}")
        await update.message.reply_text("❌ Ошибка обработки")
    finally:
        conn.close()

async def reject_application(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    
    try:
        app_id = int(context.args[0])
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE applications 
            SET status = 'rejected' 
            WHERE id = ? AND status = 'new'
        """, (app_id,))
        
        if cursor.rowcount == 0:
            await update.message.reply_text("⚠️ Заявка не найдена или уже обработана")
            return
        
        cursor.execute("SELECT user_id, full_name FROM applications WHERE id = ?", (app_id,))
        user_id, full_name = cursor.fetchone()
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"😞 {full_name}, к сожалению, ваша заявка отклонена."
            )
        except telegram_error.TelegramError as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
        
        await update.message.reply_text(f"✅ Заявка #{app_id} отклонена")
        conn.commit()
        
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /reject <ID_заявки>")
    except Exception as e:
        logger.error(f"Ошибка reject: {e}")
        await update.message.reply_text("❌ Ошибка обработки")
    finally:
        conn.close()

async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if not query.data or not query.from_user.id == ADMIN_CHAT_ID:
        return

    action, app_id = query.data.split('_')
    app_id = int(app_id)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT status, user_id, full_name 
            FROM applications 
            WHERE id = ?
        """, (app_id,))
        result = cursor.fetchone()
        
        if not result:
            await query.edit_message_text(text=f"⚠️ Заявка #{app_id} не найдена")
            return
            
        status, user_id, full_name = result
        
        if status != 'new':
            await query.edit_message_text(text=f"⚠️ Заявка #{app_id} уже обработана")
            return

        new_status = 'approved' if action == 'approve' else 'rejected'
        cursor.execute("""
            UPDATE applications 
            SET status = ? 
            WHERE id = ?
        """, (new_status, app_id))

        try:
            text = (
                f"🎉 {full_name}, ваша заявка одобрена!" 
                if action == 'approve' 
                else f"😞 {full_name}, ваша заявка отклонена"
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=text
            )
        except telegram_error.TelegramError as e:
            logger.error(f"Ошибка уведомления пользователя: {e}")

        new_text = query.message.text + f"\n\n🟢 Статус: {new_status.upper()}"
        await query.edit_message_text(
            text=new_text,
            parse_mode="HTML",
            reply_markup=None
        )

        conn.commit()
        
    except Exception as e:
        logger.error(f"Ошибка обработки callback: {e}")
        await query.edit_message_text(text=f"❌ Ошибка обработки заявки #{app_id}")
    finally:
        conn.close()

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
def main():
    init_db()
    
    # Запуск Flask в отдельном потоке
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    application = ApplicationBuilder() \
        .token(BOT_TOKEN) \
        .concurrent_updates(True) \
        .build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CITIZENSHIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, citizenship)],
            CITIZENSHIP_SNG: [MessageHandler(filters.TEXT & ~filters.COMMAND, citizenship_sng)],
            CITIZENSHIP_OTHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, citizenship_other)],
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, full_name)],
            PRIOR_EMPLOYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, prior_employment)],
            EMPLOYMENT_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, employment_period)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, city)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            SELF_EMPLOYED: [MessageHandler(filters.TEXT & ~filters.COMMAND, self_employed)],
            SELF_EMPLOYED_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self_employed_choice)],
            TRANSPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transport)],
            CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmation)],
            EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("approve", approve_application))
    application.add_handler(CommandHandler("reject", reject_application))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    def shutdown(signum, frame):
        print("\n🛑 Завершение работы бота...")
        application.stop()
        exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("✅ Бот запущен")
    application.run_polling()

if __name__ == "__main__":
    main()