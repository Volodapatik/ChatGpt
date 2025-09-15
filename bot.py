import os
import telebot
import requests
import datetime
import re
import json
import pytz
import time
import signal
import atexit
import threading
import pymongo
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", 1637885523))
MONGODB_URI = os.getenv("MONGODB_URI")
FREE_LIMIT = 30
SUPPORT_USERNAME = "@uagptpredlozhkabot"
AUTOSAVE_INTERVAL = 300  # Автозбереження кожні 5 хвилин (300 секунд)
# ==========================

# Глобальні змінні (ініціалізуємо спочатку)
user_data = {}
promo_codes = {
    "TEST1H": {"seconds": 3600, "uses_left": 50},
    "WELCOME1D": {"seconds": 86400, "uses_left": 100},
    "PREMIUM7D": {"seconds": 604800, "uses_left": 30},
    "VIP30D": {"seconds": 2592000, "uses_left": 20}
}
BOT_ENABLED = True

# Списки ключових слів
MOVIE_SITES = [
    "imdb.com", "myanimelist.net", "anidb.net", "anime-planet.com",
    "anilist.co", "animego.org", "shikimori.one", "anime-news-network.com",
    "kinoukr.com", "film.ua", "kino-teatr.ua", "novyny.live", "telekritika.ua"
]

movie_keywords = ["фільм", "серіал", "аніме", "мультфільм", "movie", "anime", "series", "кіно", "фильм", "сюжет", "сюжету", "опис"]
code_keywords = ["код", "html", "css", "js", "javascript", "python", "створи", "скрипт", "програма", "create", "program"]

# Українська часова зона
UKRAINE_TZ = pytz.timezone('Europe/Kiev')

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Підключення до MongoDB
try:
    client = pymongo.MongoClient(MONGODB_URI, tls=True, tlsAllowInvalidCertificates=True)
    db = client["telegram_bot"]
    users_collection = db["users"]
    promo_collection = db["promo_codes"]
    bot_settings_collection = db["bot_settings"]
    print("✅ Підключено до MongoDB")
except Exception as e:
    print(f"❌ Помилка підключення до MongoDB: {e}")
    # Створюємо заглушки для колекцій
    users_collection = None
    promo_collection = None
    bot_settings_collection = None

# Завантаження даних з MongoDB
def load_data():
    global user_data, promo_codes, BOT_ENABLED
    
    if users_collection is None:
        print("❌ MongoDB не підключено, пропускаємо завантаження даних")
        return
    
    try:
        # Завантаження користувачів
        user_data = {}
        for user in users_collection.find():
            user_data[user['_id']] = user
            # Конвертація рядків дат назад у datetime об'єкти
            if 'reset' in user and isinstance(user['reset'], str):
                user_data[user['_id']]['reset'] = datetime.date.fromisoformat(user['reset'])
            if 'premium' in user and 'until' in user['premium'] and user['premium']['until'] and isinstance(user['premium']['until'], str):
                dt = datetime.datetime.fromisoformat(user['premium']['until'].replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = UKRAINE_TZ.localize(dt)
                user_data[user['_id']]['premium']['until'] = dt
        
        # Завантаження промокодів
        promo_doc = promo_collection.find_one({"_id": "active_promos"})
        if promo_doc:
            promo_codes = promo_doc.get('codes', {})
        else:
            # Якщо немає промокодів в базі, зберігаємо дефолтні
            promo_collection.update_one(
                {"_id": "active_promos"},
                {"$set": {"codes": promo_codes}},
                upsert=True
            )
        
        # Завантаження налаштувань бота
        settings = bot_settings_collection.find_one({"_id": "main_settings"})
        if settings:
            BOT_ENABLED = settings.get('enabled', True)
        else:
            BOT_ENABLED = True
            bot_settings_collection.insert_one({"_id": "main_settings", "enabled": True})
            
        print(f"✅ Завантажено {len(user_data)} користувачів з MongoDB")
        print(f"✅ Завантажено {len(promo_codes)} промокодів")
        
    except Exception as e:
        print(f"❌ Помилка завантаження даних: {e}")

def get_ukraine_time():
    """Повертає поточний час України"""
    return datetime.datetime.now(UKRAINE_TZ)

def save_data():
    try:
        if users_collection is None:
            print("❌ MongoDB не підключено, пропускаємо збереження")
            return
            
        # Збереження користувачів
        for user_id, user_data_item in user_data.items():
            # Конвертація datetime об'єктів у рядки для MongoDB
            user_to_save = user_data_item.copy()
            if 'reset' in user_to_save and isinstance(user_to_save['reset'], datetime.date):
                user_to_save['reset'] = user_to_save['reset'].isoformat()
            if 'premium' in user_to_save and 'until' in user_to_save['premium'] and user_to_save['premium']['until'] and isinstance(user_to_save['premium']['until'], datetime.datetime):
                user_to_save['premium']['until'] = user_to_save['premium']['until'].isoformat()
            
            users_collection.update_one(
                {"_id": user_id},
                {"$set": user_to_save},
                upsert=True
            )
        
        # Збереження промокодів
        promo_collection.update_one(
            {"_id": "active_promos"},
            {"$set": {"codes": promo_codes}},
            upsert=True
        )
        
        # Збереження налаштувань бота
        bot_settings_collection.update_one(
            {"_id": "main_settings"},
            {"$set": {"enabled": BOT_ENABLED}},
            upsert=True
        )
        
        print(f"✅ Дані збережено в MongoDB о {get_ukraine_time().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"❌ Помилка збереження даних: {e}")

def auto_save():
    """Функція для регулярного автозбереження"""
    save_data()
    # Перезапускаємо таймер
    threading.Timer(AUTOSAVE_INTERVAL, auto_save).start()

def exit_handler():
    """Функція, яка викликається при завершенні роботи"""
    print("\n🛑 Завершення роботи... Зберігаємо дані.")
    save_data()

# Додаємо обробник для сигналів завершення
signal.signal(signal.SIGINT, lambda s, f: exit_handler())
signal.signal(signal.SIGTERM, lambda s, f: exit_handler())
atexit.register(exit_handler)

def check_bot_enabled(message):
    """Перевіряє, чи увімкнений бот для користувача"""
    if not BOT_ENABLED and message.from_user.id != ADMIN_ID:
        maintenance_text = (
            "🔧 **Технічні роботи**\n"
            "Вибачте за тимчасові незручності! \n"
            "Бот тимчасово недоступний через оновлення.\n\n"
            "🕐 **Приблизний час:** 1-2 години\n"
            "✨ **Що нового:** Покращена стабільність роботи\n\n"
            "Звертайтеся до @uagptpredlozhkabot для питань"
        )
        bot.reply_to(message, maintenance_text, parse_mode="Markdown")
        return False
    return True

def parse_time_input(time_str):
    time_str = time_str.lower().strip()
    
    if time_str == "forever":
        return None
    
    match = re.match(r'(\d+)\s*([mhdwmy]|min|minute|hour|day|week|month|year)', time_str)
    if not match:
        return None
    
    amount = int(match.group(1))
    unit = match.group(2)
    
    if unit in ['m', 'min', 'minute']:
        return amount * 60
    elif unit in ['h', 'hour']:
        return amount * 3600
    elif unit in ['d', 'day']:
        return amount * 86400
    elif unit in ['w', 'week']:
        return amount * 604800
    elif unit in ['month']:
        return amount * 2592000
    elif unit in ['y', 'year']:
        return amount * 31536000
    
    return None

def format_time(seconds):
    if seconds is None:
        return "НАЗАВЖДИ ♾️"
    
    if seconds < 60:
        return f"{seconds} секунд"
    elif seconds < 3600:
        return f"{seconds//60} хвилин"
    elif seconds < 86400:
        return f"{seconds//3600} годин"
    elif seconds < 604800:
        return f"{seconds//86400} днів"
    elif seconds < 2592000:
        return f"{seconds//604800} тижнів"
    elif seconds < 31536000:
        return f"{seconds//2592000} місяців"
    else:
        return f"{seconds//31536000} років"

def google_search(query, search_type="movie"):
    sites_query = " OR ".join([f"site:{site}" for site in MOVIE_SITES])
    
    if search_type == "movie":
        query = f"{query} ({sites_query})"
    
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={SEARCH_ENGINE_ID}"
    try:
        r = requests.get(url, timeout=8)
        data = r.json()
        results = []
        
        if "items" in data:
            for item in data["items"][:3]:
                if any(site in item['link'] for site in MOVIE_SITES):
                    results.append(f"{item['title']}\n{item['link']}")
        
        return "\n\n".join(results) if results else "🔍 Нічого не знайдено на кіно-сайтах 😔"
    except Exception as e:
        return f"❌ Помилка пошуку: {e}"

def ask_gemini(user_id, question, context_messages=None):
    if context_messages is None:
        context_messages = []
    
    context_text = "\n".join(context_messages[-3:])
    
    question_lower = question.lower()
    is_movie_query = any(word in question_lower for word in movie_keywords) and not any(word in question_lower for word in code_keywords)
    is_code_query = any(word in question_lower for word in code_keywords) and not any(word in question_lower for word in movie_keywords)
    
    search_results = ""
    
    if is_movie_query:
        search_results = google_search(question)
        prompt = f"""Ти експерт по фільмах, серіалах та аніме. Відповідай ТОЧНО та КОНКРЕТНО.
        
        Запит: {question}
        
        Результати пошуку:
        {search_results if search_results else "Нічого не знайдено"}
        
        Вкажи інформацію у форматі:
        🎬 Назва: 
        📅 Рік випуску: 
        🌍 Країна: 
        🎭 Жанр: 
        ⭐ Рейтинг: 
        📖 Опис сюжету (2-3 речення):
        
        Якщo точно не знаєш - так і скажи."""
    
    elif is_code_query:
        prompt = f"""Ти експерт-програміст. Відповідай ЧІТКИМ КОДОМ на запит.
        
        Запит: {question}
        
        ВИМОГИ:
        1. Надай ПОВНИЙ робочий код
        2. Використовуй форматування з ```
        3. Додай коментарі для пояснення
        4. Вкажи мову програмування"""
    
    else:
        prompt = f"""Ти дружній AI-асистент. Відповідай природньo та зрозуміло.
        
        Запит: {question}
        
        Вимоги:
        1. Будь природнім та дружнім
        2. Відповідай розгорнуто але не занадто довго
        3. Використовуй емодзі
        4. Будь корисним та інформативним"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 1024,
            "temperature": 0.7
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        result = response.json()
        if "candidates" in result:
            reply = result["candidates"][0]["content"]["parts"][0]["text"]
            return reply
        else:
            return "❌ Помилка API."
    except Exception as e:
        return f"❌ Помилка: {e}"

def create_copy_button(code_text):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📋 Скопіювати код", callback_data=f"copy_{hash(code_text)}"))
    return keyboard

def premium_menu_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🎫 Ввести промокод"))
    kb.add(KeyboardButton("💳 Купити преміум"))
    kb.add(KeyboardButton("📊 Мій профіль"))
    kb.add(KeyboardButton("🔙 Головне меню"))
    return kb

def admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("👥 Список користувачів"))
    kb.add(KeyboardButton("🎫 Керування промокодами"))
    kb.add(KeyboardButton("➕ Додати преміум"))
    kb.add(KeyboardButton("⏰ Преміум на час"))
    kb.add(KeyboardButton("🗑️ Видалити користувача"))
    kb.add(KeyboardButton("📊 Статистика"))
    kb.add(KeyboardButton("⚙️ Керування ботом"))
    kb.add(KeyboardButton("🔙 Головне меню"))
    return kb

def bot_management_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if BOT_ENABLED:
        kb.add(KeyboardButton("🔴 Вимкнути бота"))
    else:
        kb.add(KeyboardButton("🟢 Увімкнути бота"))
    kb.add(KeyboardButton("📊 Статус бота"))
    kb.add(KeyboardButton("🔙 До адмін панелі"))
    return kb

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📊 Профіль"))
    kb.add(KeyboardButton("💎 Преміум"))
    kb.add(KeyboardButton("🆘 Допомога"))
    if ADMIN_ID:
        kb.add(KeyboardButton("⚙️ Адмін панель"))
    return kb

def help_text():
    return (
        "🤖 <b>Що може цей бот:</b>\n\n"
        "🎬 <b>Пошук фільмів/серіалів/аніме:</b>\n"
        "• Знаходження за назвою, роком, країною\n"
        "• Пошук за описом сюжету\n"
        "• Інформація про рейтинг та жанр\n\n"
        "💻 <b>Генерація коду:</b>\n"
        "• Створення HTML/CSS/JS кодів\n"
        "• Python скрипти та програми\n"
        "• Зручне копіювання\n\n"
        "💬 <b>Звичайне спілкування:</b>\n"
        "• Відповіді на будь-які запитання\n"
        "• Допомога з різних тем\n\n"
        "💎 <b>Преміум система:</b>\n"
        "• Необмежені запити\n"
        "• Пріоритетна обробка\n\n"
        f"🐞 Техпідтримка: {SUPPORT_USERNAME}"
    )

# Завантажуємо дані при старті
load_data()

@bot.message_handler(commands=["start"])
def start(message):
    if not check_bot_enabled(message):
        return
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {
            "_id": user_id,
            "used": 0,
            "premium": {"active": False, "until": None},
            "reset": get_ukraine_time().date().isoformat(),
            "history": [],
            "free_used": False,
            "last_movie_query": None,
            "last_code": None,
            "username": message.from_user.username
        }
    else:
        # ОНОВЛЮЄМО username якщо користувач вже існує
        user_data[user_id]["username"] = message.from_user.username
    
    save_data()
    bot.reply_to(message, "👋 Вітаю! Я твій AI-помічник! Можу:\n• 🎬 Шукати фільми/серіали/аніме\n• 💻 Писати код\n• 💬 Вільно спілкуватись\n\nПросто напиши що потрібно! 😊", reply_markup=main_menu())

@bot.message_handler(commands=["profile"])
def profile_command(message):
    if not check_bot_enabled(message):
        return
    profile(message)

@bot.message_handler(func=lambda m: m.text == "📊 Профіль")
def profile(message):
    if not check_bot_enabled(message):
        return
    user_id = message.from_user.id
    if user_id not in user_data:
        start(message)
        return
    user = user_data[user_id]
    today = get_ukraine_time().date()
    
    if isinstance(user["reset"], str):
        reset_date = datetime.date.fromisoformat(user["reset"])
    else:
        reset_date = user["reset"]
    
    if reset_date != today:
        user["used"] = 0
        user["reset"] = today.isoformat()
        save_data()
    
    premium_status = "❌ Немає"
    if user["premium"]["active"]:
        if user["premium"]["until"] is None:
            premium_status = "♾️ Назавжди"
        else:
            if isinstance(user["premium"]["until"], str):
                until_date = datetime.datetime.fromisoformat(user["premium"]["until"])
                if until_date.tzinfo is None:
                    until_date = UKRAINE_TZ.localize(until_date)
            else:
                until_date = user["premium"]["until"]
            
            current_time = get_ukraine_time()
            if until_date > current_time:
                premium_status = f"✅ До {until_date.astimezone(UKRAINE_TZ).strftime('%d.%m.%Y %H:%M')}"
            else:
                user["premium"] = {"active": False, "until": None}
                save_data()
    
    role = "👑 Адміністратор" if user_id == ADMIN_ID else ("💎 Преміум" if user["premium"]["active"] else "👤 Користувач")
    username = user.get('username', 'unknown')
    if username is None or username == "user_" + str(user_id):
        username = "немає"
    else:
        username = "@" + username
    
    limit_info = "♾️ Необмежено" if (user["premium"]["active"] or user_id == ADMIN_ID) else f"{user['used']}/{FREE_LIMIT}"
    
    profile_text = (
        f"📊 <b>Профіль:</b>\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Ім'я: {username}\n"
        f"🎭 Роль: {role}\n"
        f"💎 Преміум: {premium_status}\n"
        f"💬 Використано сьогодні: {user['used']}\n"
        f"🔋 Ліміт: {limit_info}\n"
        f"⏰ Оновлення: опівночі (за київським часом)\n\n"
        f"🐞 Техпідтримка: {SUPPORT_USERNAME}"
    )
    bot.reply_to(message, profile_text, parse_mode="HTML")

@bot.message_handler(commands=["premium"])
def premium_command(message):
    if not check_bot_enabled(message):
        return
    premium_info(message)

@bot.message_handler(func=lambda m: m.text == "💎 Преміум")
def premium_info(message):
    if not check_bot_enabled(message):
        return
    text = (
        "💎 <b>Преміум підписка:</b>\n\n"
        "✅ <b>Переваги:</b>\n"
        "• ♾️ Необмежена кількість запитів\n"
        "• ⚡ Пріоритетна обробка запитів\n"
        "• 🎬 Детальніші відповіді про фільми\n"
        "• 💻 Більш складний код\n\n"
        "🎫 <b>Отримати преміум:</b>\n"
        "• Введіть промокод\n"
        "• Придбайте підписку\n\n"
        "💳 <b>Ціни:</b>\n"
        "• 1 день - 10 грн\n"
        "• 7 днів - 50 грн\n"
        "• 30 днів - 100 грн\n\n"
        "📱 Для придбання звертайтеся до @uagptpredlozhkabot"
    )
    bot.reply_to(message, text, parse_mode="HTML", reply_markup=premium_menu_keyboard())

@bot.message_handler(func=lambda m: m.text == "🎫 Ввести промокод")
def enter_promo(message):
    if not check_bot_enabled(message):
        return
    bot.reply_to(message, "🔑 Введіть ваш промокод:")
    bot.register_next_step_handler(message, process_promo)

def process_promo(message):
    if not check_bot_enabled(message):
        return
    user_id = message.from_user.id
    promo = message.text.strip().upper()
    
    if promo in promo_codes:
        code_data = promo_codes[promo]
        if code_data["uses_left"] > 0:
            if code_data["seconds"] == 0:  # Безстроковий преміум
                user_data[user_id]["premium"] = {
                    "active": True,
                    "until": None
                }
            else:
                if user_data[user_id]["premium"]["active"]:
                    current_until = user_data[user_id]["premium"]["until"]
                    if current_until is None:
                        bot.reply_to(message, "❌ У вас вже є безстроковий преміум!")
                        return
                    
                    if isinstance(current_until, str):
                        current_until = datetime.datetime.fromisoformat(current_until)
                        if current_until.tzinfo is None:
                            current_until = UKRAINE_TZ.localize(current_until)
                    
                    new_until = current_until + datetime.timedelta(seconds=code_data["seconds"])
                else:
                    new_until = get_ukraine_time() + datetime.timedelta(seconds=code_data["seconds"])
                
                user_data[user_id]["premium"] = {
                    "active": True,
                    "until": new_until
                }
            
            code_data["uses_left"] -= 1
            save_data()
            
            if code_data["seconds"] == 0:
                bot.reply_to(message, "✅ Безстроковий преміум активовано! ♾️")
            else:
                bot.reply_to(message, f"✅ Преміум активовано до {new_until.astimezone(UKRAINE_TZ).strftime('%d.%m.%Y %H:%M')}!")
        else:
            bot.reply_to(message, "❌ Промокод вичерпано!")
    else:
        bot.reply_to(message, "❌ Невірний промокод!")

@bot.message_handler(func=lambda m: m.text == "💳 Купити преміум")
def buy_premium(message):
    if not check_bot_enabled(message):
        return
    bot.reply_to(message, "💳 Для придбання преміум підписки зверніться до @uagptpredlozhkabot")

@bot.message_handler(func=lambda m: m.text == "🆘 Допомога")
def help_command(message):
    if not check_bot_enabled(message):
        return
    bot.reply_to(message, help_text(), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "⚙️ Адмін панель" and m.from_user.id == ADMIN_ID)
def admin_panel(message):
    if not check_bot_enabled(message):
        return
    bot.reply_to(message, "⚙️ <b>Адмін панель:</b>", parse_mode="HTML", reply_markup=admin_keyboard())

@bot.message_handler(func=lambda m: m.text == "⚙️ Керування ботом" and m.from_user.id == ADMIN_ID)
def bot_management(message):
    bot.reply_to(message, "🤖 <b>Керування ботом:</b>", parse_mode="HTML", reply_markup=bot_management_keyboard())

@bot.message_handler(func=lambda m: m.text == "🔴 Вимкнути бота" and m.from_user.id == ADMIN_ID)
def disable_bot(message):
    global BOT_ENABLED
    BOT_ENABLED = False
    save_data()
    bot.reply_to(message, "🔴 Бот вимкнений для всіх користувачів крім адміністратора!", reply_markup=bot_management_keyboard())

@bot.message_handler(func=lambda m: m.text == "🟢 Увімкнути бота" and m.from_user.id == ADMIN_ID)
def enable_bot(message):
    global BOT_ENABLED
    BOT_ENABLED = True
    save_data()
    bot.reply_to(message, "🟢 Бot увімкнений для всіх користувачів!", reply_markup=bot_management_keyboard())

@bot.message_handler(func=lambda m: m.text == "📊 Статус бота" and m.from_user.id == ADMIN_ID)
def bot_status(message):
    status = "🟢 Увімкнений" if BOT_ENABLED else "🔴 Вимкнений"
    bot.reply_to(message, f"📊 <b>Статус бота:</b> {status}", parse_mode="HTML", reply_markup=bot_management_keyboard())

@bot.message_handler(func=lambda m: m.text == "🔙 До адмін панелі" and m.from_user.id == ADMIN_ID)
def back_to_admin(message):
    bot.reply_to(message, "⚙️ <b>Адмін панель:</b>", parse_mode="HTML", reply_markup=admin_keyboard())

@bot.message_handler(func=lambda m: m.text == "🔙 Головне меню")
def back_to_main(message):
    if not check_bot_enabled(message):
        return
    bot.reply_to(message, "🏠 <b>Головне меню:</b>", parse_mode="HTML", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "👥 Список користувачів" and m.from_user.id == ADMIN_ID)
def user_list(message):
    users_text = "👥 <b>Список користувачів:</b>\n\n"
    for uid, data in list(user_data.items())[:50]:
        premium_status = "✅" if data["premium"]["active"] else "❌"
        username = data.get('username', 'unknown')
        if username is None or username == "user_" + str(uid):
            username = "немає"
        else:
            username = "@" + username
        users_text += f"ID: {uid} | {username} | Преміум: {premium_status} | Використано: {data['used']}\n"
    
    users_text += f"\n📊 Всього користувачів: {len(user_data)}"
    bot.reply_to(message, users_text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎫 Керування промокодами" and m.from_user.id == ADMIN_ID)
def manage_promos(message):
    promos_text = "🎫 <b>Промокоди:</b>\n\n"
    for code, data in promo_codes.items():
        promos_text += f"🔑 {code}: {data['uses_left']} використань | {format_time(data['seconds'])}\n"
    
    promos_text += "\n➕ Додати новий: /addpromo код час використань\n❌ Видалити: /removepromo код"
    bot.reply_to(message, promos_text, parse_mode="HTML")

@bot.message_handler(commands=["addpromo"])
def add_promo(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 4:
            bot.reply_to(message, "❌ Використання: /addpromo код час використань\nНаприклад: /addpromo TEST1H 3600 50")
            return
        
        code = parts[1].upper()
        seconds = int(parts[2])
        uses = int(parts[3])
        
        promo_codes[code] = {"seconds": seconds, "uses_left": uses}
        save_data()
        bot.reply_to(message, f"✅ Промокод {code} додано!")
    except:
        bot.reply_to(message, "❌ Помилка формату!")

@bot.message_handler(commands=["removepromo"])
def remove_promo(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        code = message.text.split()[1].upper()
        if code in promo_codes:
            del promo_codes[code]
            save_data()
            bot.reply_to(message, f"✅ Промокод {code} видалено!")
        else:
            bot.reply_to(message, "❌ Промокод не знайдено!")
    except:
        bot.reply_to(message, "❌ Використання: /removepromo код")

@bot.message_handler(func=lambda m: m.text == "➕ Додати преміум" and m.from_user.id == ADMIN_ID)
def add_premium_prompt(message):
    bot.reply_to(message, "👤 Введіть ID користувача для надання преміуму:")
    bot.register_next_step_handler(message, process_add_premium)

def process_add_premium(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(message.text.strip())
        username = "user_" + str(user_id)
        
        # Спроба отримати username з повідомлення
        if message.forward_from:
            username = message.forward_from.username or username
        elif message.reply_to_message and message.reply_to_message.from_user:
            username = message.reply_to_message.from_user.username or username
        
        user_data[user_id] = {
            "_id": user_id,
            "used": 0,
            "premium": {"active": True, "until": None},
            "reset": get_ukraine_time().date().isoformat(),
            "history": [],
            "free_used": False,
            "last_movie_query": None,
            "last_code": None,
            "username": username
        }
        save_data()
        
        bot.reply_to(message, f"✅ Безстроковий преміум надано користувачу {user_id}!")
        
        try:
            bot.send_message(user_id,
                f"🎉 Вітаю! Адміністратор надав вам безстроковий преміум доступ! ♾️\n\n"
                f"Тепер ви можете:\n"
                f"• Робити необмежену кількість запитів\n"
                f"• Отримувати пріоритетну обробку\n"
                f"• Користуватись усіма перевагами преміуму\n\n"
                f"Щоб перевірити статус: /profile"
            )
        except:
            pass
        
    except:
        bot.reply_to(message, "❌ Помилка! Перевірте ID.")

@bot.message_handler(func=lambda m: m.text == "⏰ Преміум на час" and m.from_user.id == ADMIN_ID)
def timed_premium_prompt(message):
    bot.reply_to(message, "👤 Введіть ID користувача та час у форматі: id час\nНаприклад: 1234567 7d")
    bot.register_next_step_handler(message, process_timed_premium)

def process_timed_premium(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Використання: id час\nНаприклад: 1234567 7d")
            return
        
        user_id = int(parts[0])
        time_input = " ".join(parts[1:])
        
        seconds = parse_time_input(time_input)
        if seconds is None:
            bot.reply_to(message, "❌ Невірний формат часу!")
            return
        
        until_time = get_ukraine_time() + datetime.timedelta(seconds=seconds)
        
        if user_id not in user_data:
            user_data[user_id] = {
                "_id": user_id,
                "used": 0,
                "premium": {"active": True, "until": until_time},
                "reset": get_ukraine_time().date().isoformat(),
                "history": [],
                "free_used": False,
                "last_movie_query": None,
                "last_code": None,
                "username": f"user_{user_id}"
            }
        else:
            user_data[user_id]["premium"] = {
                "active": True,
                "until": until_time
            }
        
        save_data()
        
        time_duration = format_time(seconds)
        bot.reply_to(message, 
            f"✅ Преміум надано користувачу {user_id}!\n"
            f"⏰ Тривалість: {time_duration}\n"
            f"📅 До: {until_time.astimezone(UKRAINE_TZ).strftime('%d.%m.%Y %H:%M')}"
        )
        
        try:
            bot.send_message(user_id,
                f"🎉 Вітаю! Адміністратор надав вам преміум доступ!\n\n"
                f"⏰ Тривалість: {time_duration}\n"
                f"📅 Діє до: {until_time.astimezone(UKRAINE_TZ).strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Тепер ви можете:\n"
                f"• Робити необмежену кількість запитів\n"
                f"• Отримувати пріоритетну обробку\n"
                f"• Користуватись усіма перевагами преміуму\n\n"
                f"Щоб перевірити статус: /profile"
            )
        except:
            pass
        
    except:
        bot.reply_to(message, "❌ Помилка! Перевірте введені дані.")

@bot.message_handler(func=lambda m: m.text == "🗑️ Видалити користувача" and m.from_user.id == ADMIN_ID)
def delete_user_prompt(message):
    bot.reply_to(message, "👤 Введіть ID користувача для видалення:")
    bot.register_next_step_handler(message, process_delete_user)

def process_delete_user(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(message.text.strip())
        if user_id in user_data:
            del user_data[user_id]
            if users_collection:
                users_collection.delete_one({"_id": user_id})
            save_data()
            bot.reply_to(message, f"✅ Користувача {user_id} видалено!")
        else:
            bot.reply_to(message, "❌ Користувача не знайдено!")
    except:
        bot.reply_to(message, "❌ Помилка! Перевірте ID.")

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id == ADMIN_ID)
def stats(message):
    total_users = len(user_data)
    premium_users = sum(1 for u in user_data.values() if u["premium"]["active"])
    total_used = sum(u["used"] for u in user_data.values())
    
    stats_text = (
        f"📊 <b>Статистика:</b>\n\n"
        f"👥 Користувачів: {total_users}\n"
        f"💎 Преміум: {premium_users}\n"
        f"🔢 Звичайних: {total_users - premium_users}\n"
        f"💬 Запитів сьогодні: {total_used}\n"
        f"🎫 Промокодів: {len(promo_codes)}"
    )
    bot.reply_to(message, stats_text, parse_mode="HTML")

@bot.message_handler(commands=["clearduplicates"])
def clear_duplicates(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    unique_users = {}
    duplicates_removed = 0
    
    for uid, data in user_data.items():
        if uid not in unique_users:
            unique_users[uid] = data
        else:
            duplicates_removed += 1
    
    user_data.clear()
    user_data.update(unique_users)
    save_data()
    
    bot.reply_to(message, f"✅ Видалено {duplicates_removed} дублікатів! Залишилось {len(user_data)} унікальних користувачів")

@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_"))
def copy_code(call):
    code_hash = call.data[5:]
    for user in user_data.values():
        if user["last_code"] and hash(user["last_code"]) == int(code_hash):
            bot.answer_callback_query(call.id, "📋 Код скопійовано в буфер обміну!")
            return
    bot.answer_callback_query(call.id, "❌ Код вже не актуальний!")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    if not check_bot_enabled(message):
        return
    user_id = message.from_user.id
    
    if user_id not in user_data:
        user_data[user_id] = {
            "_id": user_id,
            "used": 0,
            "premium": {"active": False, "until": None},
            "reset": get_ukraine_time().date().isoformat(),
            "history": [],
            "free_used": False,
            "last_movie_query": None,
            "last_code": None,
            "username": message.from_user.username
        }
        save_data()
    else:
        # ОНОВЛЮЄМО username при кожному повідомленні
        user_data[user_id]["username"] = message.from_user.username
        save_data()
    
    user = user_data[user_id]
    today = get_ukraine_time().date()
    
    if isinstance(user["reset"], str):
        reset_date = datetime.date.fromisoformat(user["reset"])
    else:
        reset_date = user["reset"]
    
    if reset_date != today:
        user["used"] = 0
        user["reset"] = today.isoformat()
        save_data()
    
    if user["premium"]["active"] and user["premium"]["until"] is not None:
        if isinstance(user["premium"]["until"], str):
            until_date = datetime.datetime.fromisoformat(user["premium"]["until"])
            if until_date.tzinfo is None:
                until_date = UKRAINE_TZ.localize(until_date)
        else:
            until_date = user["premium"]["until"]
        
        if until_date < get_ukraine_time():
            user["premium"] = {"active": False, "until": None}
            save_data()
    
    is_premium = user["premium"]["active"] or user_id == ADMIN_ID
    if not is_premium and user["used"] >= FREE_LIMIT:
        if not user["free_used"]:
            user["free_used"] = True
            save_data()
            bot.reply_to(message, f"❌ Ви вичерпали безкоштовний ліміт ({FREE_LIMIT} запитів на день).\n\n💎 Отримайте преміум для необмежених запитів!", reply_markup=premium_menu_keyboard())
        else:
            bot.reply_to(message, f"❌ Ліміт вичерпано! Спробуйте завтра або отримайте преміум 💎", reply_markup=premium_menu_keyboard())
        return
    
    user["used"] += 1
    user["history"].append(message.text)
    if len(user["history"]) > 10:
        user["history"].pop(0)
    
    save_data()
    
    question = message.text.lower()
    is_movie_query = any(word in question for word in movie_keywords) and not any(word in question for word in code_keywords)
    is_code_query = any(word in question for word in code_keywords) and not any(word in question for word in movie_keywords)
    
    if is_movie_query:
        user["last_movie_query"] = message.text
        search_results = google_search(message.text)
        if "🔍 Нічого не знайдено" not in search_results:
            bot.reply_to(message, f"🔍 <b>Результати пошуку:</b>\n\n{search_results}\n\n📝 <b>А ось детальна інформація:</b>", parse_mode="HTML")
    
    bot.send_chat_action(message.chat.id, "typing")
    response = ask_gemini(user_id, message.text, user["history"])
    
    if is_code_query and "```" in response:
        user["last_code"] = response
        bot.reply_to(message, response, parse_mode="Markdown", reply_markup=create_copy_button(response))
    else:
        bot.reply_to(message, response)

if __name__ == "__main__":
    print("✅ Бот запущено з українським часом та MongoDB!")
    print(f"📊 Користувачів у пам'яті: {len(user_data)}")
    
    # Запускаємо автозбереження
    threading.Timer(AUTOSAVE_INTERVAL, auto_save).start()
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"❌ Критична помилка: {e}")
        exit_handler()