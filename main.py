import os
import sqlite3
import logging
import signal
import re
from threading import Thread
from datetime import datetime
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
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

# ========== FLASK INIT ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 Бот активен! Порт: " + os.environ.get('PORT', '10000'), 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# ========== CONFIG ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_CHAT_ID = int(os.environ.get('ADMIN_CHAT_ID'))
DB_NAME = "applications.db"

# ========== DIALOG STATES ==========
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

# ========== LOGGING ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== DATABASE ==========
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY,
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
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {str(e)}")
    finally:
        if conn:
            conn.close()

def save_application(user_data, user_id, username):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO applications (
                user_id, username, full_name, citizenship, 
                prior_employment, employment_period, phone, 
                city, age, self_employed, self_employed_choice, transport
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
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
        
        app_id = cursor.fetchone()[0]
        conn.commit()
        return app_id
        
    except Exception as e:
        logger.error(f"Ошибка БД: {str(e)}")
        return None
    finally:
        if conn:
            conn.close()

# ========== VALIDATION ==========
RUSSIAN_CITIES = {
    'москва', 'санкт-петербург', 'новосибирск', 'екатеринбург', 'нижний новгород',
    'казань', 'челябинск', 'самара', 'омск', 'ростов-на-дону', 'уфа', 'красноярск',
    'пермь', 'воронеж', 'волгоград', 'краснодар', 'саратов', 'тюмень', 'тольятти',
    'ижевск', 'барнаул', 'иркутск', 'ульяновск', 'хабаровск', 'ярославль', 'владивосток',
    'махачкала', 'томск', 'оренбург', 'кемерово', 'новокузнецк', 'рязань', 'астрахань',
    'набережные челны', 'пенза', 'липецк', 'киров', 'чебоксары', 'калининград', 'тула',
    'ставрополь', 'курск', 'сочи', 'тверь', 'магнитогорск', 'иваново', 'брянск', 'белгород',
    'сургут', 'владимир', 'архангельск', 'калуга', 'смоленск', 'вологда', 'салават', 'чита',
    'орёл', 'волжский', 'череповец', 'владикавказ', 'мурманск', 'петрозаводск', 'кострома',
    'нижневартовск', 'новороссийск', 'йошкар-ола', 'таганрог', 'сыктывкар', 'нальчик',
    'шахты', 'дзержинск', 'благовещенск', 'элиста', 'псков', 'бийск', 'прокопьевск',
    'ангарск', 'ставрополь', 'люберцы', 'мытищи', 'балашиха', 'химки', 'королёв', 'подольск',
    'севастополь', 'сургут', 'новый уренгой', 'волгодонск', 'абдулино', 'азов', 'александров',
    'алексин', 'альметьевск', 'анапа', 'апатиты', 'арзамас', 'армавир', 'артём', 'архангельск',
    'асбест', 'ачинск', 'балаково', 'балахна', 'батайск', 'белогорск', 'белорецк', 'белореченск',
    'бердск', 'березники', 'беслан', 'бор', 'борисоглебск', 'братск', 'бугульма', 'будённовск',
    'бузулук', 'буйнакск', 'великие луки', 'великий новгород', 'видное', 'воборка', 'волжск',
    'вологда', 'воркута', 'воскресенск', 'воткинск', 'выборг', 'выкса', 'вязьма', 'гатчина',
    'геленджик', 'горно-алтайск', 'грозный', 'губкин', 'гуково', 'гурьевск', 'дербент', 'долгопрудный',
    'домодедово', 'дубна', 'евпатория', 'егорьевск', 'ейск', 'елец', 'ессентуки', 'железногорск',
    'жигулёвск', 'жуковский', 'заречный', 'зеленодольск', 'златоуст', 'ивантеевка', 'ишим',
    'ишимбай', 'йошкар-ола', 'кадников', 'каменск-уральский', 'каменск-шахтинский', 'карачаевск',
    'кемерово', 'кинешма', 'кириши', 'киселёвск', 'клин', 'клинцы', 'ковров', 'коломна', 'комсомольск-на-амуре',
    'копейск', 'коркино', 'кострома', 'котлас', 'красногорск', 'краснокаменск', 'краснокамск',
    'кумертау', 'кунгур', 'курган', 'курчатов', 'кызыл', 'лабинск', 'лениногорск', 'лермонтов',
    'лиски', 'лобня', 'лысьва', 'лыткарино', 'люберцы', 'магадан', 'магнитогорск', 'майкоп',
    'миасс', 'минеральные воды', 'мичуринск', 'набережные челны', 'назрань', 'нальчик', 'наро-фоминск',
    'невинномысск', 'нефтекамск', 'нефтеюганск', 'нижневартовск', 'нижнекамск', 'нижняя тура',
    'новоалтайск', 'новокузнецк', 'новомосковск', 'новороссийск', 'новосибирск', 'новочебоксарск',
    'новочеркасск', 'новошахтинск', 'ногинск', 'ноябрьск', 'нюрба', 'нягань', 'обнинск', 'одинцово',
    'октябрьский', 'омск', 'орел', 'оренбург', 'орехово-зуево', 'орск', 'павлово', 'павловский посад',
    'пенза', 'первоуральск', 'пермь', 'петрозаводск', 'петропавловск-камчатский', 'подольск',
    'полевской', 'прокопьевск', 'прохладный', 'псков', 'пушкино', 'раменское', 'ревда', 'реутов',
    'рославль', 'россошь', 'ростов-на-дону', 'рубцовск', 'рыбинск', 'рязань', 'салават', 'сальск',
    'самара', 'санкт-петербург', 'саранск', 'сарапул', 'саратов', 'саров', 'свободный', 'северодвинск',
    'северск', 'сергиев посад', 'серов', 'серпухов', 'симферополь', 'славянск-на-кубани', 'смоленск',
    'соликамск', 'солнечногорск', 'сосновый бор', 'сочи', 'ставрополь', 'старый оскол', 'стерлитамак',
    'ступино', 'сургут', 'сызрань', 'сыктывкар', 'таганрог', 'тамбов', 'тверь', 'тихвин', 'тихорецк',
    'тобольск', 'тольятти', 'томск', 'троицк', 'туапсе', 'тула', 'тюмень', 'улан-удэ', 'ульяновск',
    'уссурийск', 'усть-илимск', 'уфа', 'ухта', 'хабаровск', 'хадыженск', 'химки', 'чайковский',
    'чапаевск', 'чебоксары', 'челябинск', 'черемхово', 'череповец', 'черкесск', 'черногорск',
    'чехов', 'чистополь', 'чита', 'шадринск', 'шали', 'шахты', 'шуя', 'щекино', 'щелково', 'электросталь',
    'элиста', 'энгельс', 'южно-сахалинск', 'юрга', 'якутск', 'ялта', 'ярославль'
}

def normalize_city_name(city: str) -> str:
    return re.sub(r'[^\w\s-]', '', city.lower().strip())

def is_valid_russian_city(city: str) -> bool:
    normalized = normalize_city_name(city)
    aliases = {
        'спб': 'санкт-петербург',
        'нск': 'новосибирск',
        'екб': 'екатеринбург'
    }
    return normalized in RUSSIAN_CITIES or aliases.get(normalized) in RUSSIAN_CITIES

# ========== KEYBOARDS ==========
SNG_COUNTRIES = [
    ["🇧🇾 Беларусь", "🇰🇿 Казахстан"],
    ["🇺🇿 Узбекистан", "🇦🇲 Армения"],
    ["🇦🇿 Азербайджан", "🇲🇩 Молдова"],
    ["🇰🇬 Кыргызстан", "🇹🇯 Таджикистан"],
    ["🌍 Другая страна", "🚫 Пропустить"]
]

CITIZENSHIP_KEYBOARD = [["🇷🇺 РФ", "🌍 СНГ/Другое"]]
PRIOR_EMPLOYMENT_KEYBOARD = [["✅ Да", "❌ Нет"]]
EMPLOYMENT_PERIOD_KEYBOARD = [["📅 Меньше 40 дней назад"], ["🗓️ Больше 40 дней назад"]]
STATUS_KEYBOARD = [["✅ Да", "❌ Нет"]]
TRANSPORT_KEYBOARD = [["🚗 Авто", "🚲 Вело", "⚡ Электровело"]]
SELF_EMPLOYED_CHOICE_KEYBOARD = [["📝 Оформить сейчас", "🏢 В офисе"]]
CONFIRM_KEYBOARD = [["✅ Подтвердить", "✏️ Изменить"]]
EDIT_FIELD_KEYBOARD = [
    ["ФИО", "Телефон"],
    ["Город", "Возраст"],
    ["Транспорт", "Назад"]
]

# ========== HANDLERS ==========
async def start(update: Update, context: CallbackContext) -> int:
    if context.user_data.get('active'):
        await update.message.reply_text("⚠️ Завершите текущую анкету!")
        return ConversationHandler.END
        
    context.user_data.clear()
    context.user_data['active'] = True
    
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
                SNG_COUNTRIES,
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
                [["🚫 Пропустить"]],
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
    full_name = ' '.join(full_name.split()).replace('--', '-')
    
    pattern = r"""
        ^
        [А-ЯЁ]
        [а-яё-]+
        (?:\s[А-ЯЁ][а-яё-]+){1,2}
        $
    """
    
    if not re.fullmatch(pattern, full_name, re.VERBOSE | re.IGNORECASE):
        examples = "❌ Неверный формат ФИО. Примеры:\n• Иванов Иван\n• Петров-Водкин Алексей"
        await update.message.reply_text(examples)
        return FULL_NAME
    
    parts = full_name.split()
    for part in parts:
        if len(part.replace('-', '')) < 2:
            await update.message.reply_text("❌ Каждая часть ФИО должна быть минимум из 2 букв")
            return FULL_NAME
    
    context.user_data["full_name"] = full_name.title()
    
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
        await update.message.reply_text("Пожалуйста, выберите вариант из клавиатуры.")
        return EMPLOYMENT_PERIOD
    
    context.user_data["employment_period"] = period
    
    if period == "📅 Меньше 40 дней назад":
        context.user_data["special_note"] = "🚨 ВНИМАНИЕ: Кандидат работал менее 40 дней назад!"
    
    await update.message.reply_text("📱 Введите номер телефона (начинается с +7, 7 или 8):")
    return PHONE

async def phone(update: Update, context: CallbackContext) -> int:
    raw_phone = update.message.text
    clean_phone = ''.join(filter(str.isdigit, raw_phone))
    
    if clean_phone.startswith('8') and len(clean_phone) == 11:
        clean_phone = '7' + clean_phone[1:]
    
    if not clean_phone.startswith('7') or len(clean_phone) != 11:
        await update.message.reply_text("❌ Неверный формат номера. Примеры: +79123456789, 79123456789, 89123456789")
        return PHONE
    
    formatted_phone = f"+7 ({clean_phone[1:4]}) {clean_phone[4:7]}-{clean_phone[7:9]}-{clean_phone[9:11]}"
    context.user_data["phone"] = formatted_phone
    await update.message.reply_text("🏙️ Введите ваш город:")
    return CITY

async def city(update: Update, context: CallbackContext) -> int:
    city = update.message.text.strip()
    
    if len(city) < 2:
        await update.message.reply_text("❌ Название города слишком короткое")
        return CITY
    
    if any(c.isdigit() or c in '!@#$%^&*()_+={}[]|\\:;"<>,?/~`' for c in city):
        await update.message.reply_text("❌ Город не должен содержать цифры и спецсимволы")
        return CITY
    
    if not is_valid_russian_city(city):
        await update.message.reply_text(
            "❌ Введите корректное название города России\n"
            "Примеры: Москва, Санкт-Петербург, Казань\n"
            "Или укажите ближайший крупный город"
        )
        return CITY
    
    context.user_data["city"] = city.title()
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
        await update.message.reply_text("Пожалуйста, используйте кнопки ниже👇")
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
        await update.message.reply_text("Пожалуйста, выберите транспорт из предложенных👇")
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
        required_fields = [
            'citizenship', 'full_name', 'phone',
            'city', 'age', 'self_employed', 'transport'
        ]
        
        missing = [field for field in required_fields if field not in context.user_data]
        if missing:
            await update.message.reply_text(
                f"❌ Ошибка: Отсутствуют данные ({', '.join(missing)})"
            )
            context.user_data.clear()
            return ConversationHandler.END

        try:
            user = update.message.from_user
            app_id = save_application(
                user_data=context.user_data,
                user_id=user.id,
                username=user.username
            )
            
            if not app_id:
                raise ValueError("Ошибка сохранения в БД")

            message = [
                f"🔔 <b>Новая заявка #{app_id}</b>\n\n",
                f"👤 Пользователь: @{user.username or 'не указан'} (ID: {user.id})\n",
                f"▫️ ФИО: {context.user_data['full_name']}\n",
                f"▫️ Телефон: {context.user_data['phone']}\n",
                f"▫️ Город: {context.user_data['city']}\n",
                f"▫️ Возраст: {context.user_data['age']}\n",
                f"▫️ Транспорт: {context.user_data['transport']}\n"
            ]

            if context.user_data.get('age', 0) < 18:
                message.append("\n🚨 <b>ВНИМАНИЕ: Несовершеннолетний кандидат!</b>")

            if 'special_note' in context.user_data:
                message.append(f"\n{context.user_data['special_note']}")

            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text="".join(message),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Принять", callback_data=f"approve_{app_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{app_id}")
                ]])
            )

            await update.message.reply_text(
                "✅ Заявка принята! Ожидайте звонка.",
                reply_markup=ReplyKeyboardRemove()
            )

        except sqlite3.Error as e:
            logger.error(f"Ошибка БД: {str(e)}")
            await update.message.reply_text("⚠️ Ошибка базы данных. Попробуйте позже.")
            
        except Exception as e:
            logger.error(f"Критическая ошибка: {str(e)}")
            await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте еще раз.")
            
        finally:
            context.user_data.clear()
        
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
        await update.message.reply_text("Пожалуйста, выберите поле из списка")
        return EDIT_FIELD
    
    context.user_data["editing_field"] = field
    
    if field == "Транспорт":
        await update.message.reply_text(
            "🚗 Выберите транспорт:",
            reply_markup=ReplyKeyboardMarkup(
                TRANSPORT_KEYBOARD,
                resize_keyboard=True
            )
        )
        return TRANSPORT
    else:
        await update.message.reply_text(f"Введите новое значение для поля '{field}':")
        return {
            "ФИО": FULL_NAME,
            "Телефон": PHONE,
            "Город": CITY,
            "Возраст": AGE
        }[field]

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "❌ Диалог прерван.",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: Update, context: CallbackContext):
    logger.error(msg="Ошибка:", exc_info=context.error)
    if update.message:
        await update.message.reply_text("⚠️ Произошла внутренняя ошибка. Пожалуйста, попробуйте еще раз.")

# ========== ADMIN COMMANDS ==========
async def admin_stats(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    
    conn = sqlite3.connect(DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
        stats = dict(cursor.fetchall())
        
        cursor.execute("SELECT id, created_at, city FROM applications WHERE status = 'new' ORDER BY created_at DESC LIMIT 5")
        last_apps = cursor.fetchall()
        
        message = [
            "📊 <b>Статистика заявок</b>\n",
            f"• Новые: {stats.get('new', 0)}",
            f"• Обработанные: {stats.get('processed', 0)}\n",
            "⏳ <b>Последние заявки:</b>\n"
        ]
        
        for app in last_apps:
            message.append(f"#{app[0]} - {app[2]} ({app[1][:16]})\n")
            
        await update.message.reply_text("\n".join(message), parse_mode="HTML")
        
    except sqlite3.Error as e:
        logger.error(f"DB Error: {e}")
        await update.message.reply_text("❌ Ошибка получения статистики")
    finally:
        conn.close()

async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_CHAT_ID:
        await query.message.reply_text("❌ Доступ запрещен")
        return

    try:
        action, app_id = query.data.split('_')
        app_id = int(app_id)
    except:
        logger.error("Invalid callback data")
        return

    conn = sqlite3.connect(DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status, user_id, full_name FROM applications WHERE id = ?", (app_id,))
        result = cursor.fetchone()
        
        if not result:
            await query.edit_message_text(text=f"⚠️ Заявка #{app_id} не найдена")
            return
            
        status, user_id, full_name = result
        
        if status != 'new':
            await query.edit_message_text(text=f"⚠️ Заявка #{app_id} уже обработана")
            return

        new_status = 'approved' if action == 'approve' else 'rejected'
        cursor.execute("UPDATE applications SET status = ? WHERE id = ?", (new_status, app_id))
        conn.commit()

        try:
            message_text = "🎉 Ваша заявка одобрена!" if action == 'approve' else "😞 Заявка отклонена."
            await context.bot.send_message(user_id, f"🔔 Уведомление для {full_name}:\n{message_text}")
        except telegram_error.BadRequest:
            logger.warning(f"User {user_id} blocked the bot")

        await query.edit_message_text(
            text=query.message.text.replace("Статус: new", f"Статус: {new_status}"),
            parse_mode="HTML",
            reply_markup=None
        )

    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.edit_message_text(text=f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()

# ========== MAIN ==========
def main():
    init_db()
    
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
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    def shutdown(signum, frame):
        print("\n🛑 Завершение работы...")
        application.stop()
        exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("✅ Бот запущен")
    application.run_polling()

if __name__ == "__main__":
    main()