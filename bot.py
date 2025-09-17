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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", 1637885523))
MONGODB_URI = os.getenv("MONGODB_URI")
FREE_LIMIT = 30
SUPPORT_USERNAME = "@uagptpredlozhkabot"
AUTOSAVE_INTERVAL = 300

user_data = {}
promo_codes = {
    "TEST1H": {"seconds": 3600, "uses_left": 50},
    "WELCOME1D": {"seconds": 86400, "uses_left": 100},
    "PREMIUM7D": {"seconds": 604800, "uses_left": 30},
    "VIP30D": {"seconds": 2592000, "uses_left": 20}
}
BOT_ENABLED = True

# Українські сайти що працюють без VPN
BASE_MOVIE_SITES = [
    # Українські кіносайти
    "kinoukr.com", "film.ua", "kino-teatr.ua", "novyny.live", 
    "telekritika.ua", "moviegram.com.ua", "kinofilms.ua",
    
    # Українські медіа про кіно
    "vgolos.com.ua", "kinozagolovkom.com.ua", "cinema.in.ua",
    
    # Міжнародні сайти що доступні в Україні
    "imdb.com", "themoviedb.org", "letterboxd.com",
    
    # Аніме сайти доступні в Україні
    "myanimelist.net", "anilist.co", "anime-planet.com",
    
    # Кінопортали
    "rottentomatoes.com", "metacritic.com", "boxofficemojo.com"
]

PREMIUM_MOVIE_SITES = BASE_MOVIE_SITES

movie_keywords = ["фільм", "серіал", "аніме", "мультфільм", "movie", "anime", "series", "кіно", "фильм", "сюжет", "сюжету", "опис"]
code_keywords = ["код", "html", "css", "js", "javascript", "python", "створи", "скрипт", "програма", "create", "program"]

UKRAINE_TZ = pytz.timezone('Europe/Kiev')

bot = telebot.TeleBot(TELEGRAM_TOKEN)

try:
    client = pymongo.MongoClient(
        MONGODB_URI,
        tls=True,
        retryWrites=True,
        w='majority',
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
        serverSelectionTimeoutMS=30000
    )
    
    client.admin.command('ping')
    db = client["telegram_bot"]
    users_collection = db["users"]
    promo_collection = db["promo_codes"]
    bot_settings_collection = db["bot_settings"]
    print("✅ Підключено до MongoDB Atlas!")
    
except Exception as e:
    print(f"❌ Помилка підключення до MongoDB: {e}")
    print("⚠️  Бот працюватиме в режимі без бази даних")
    users_collection = None
    promo_collection = None
    bot_settings_collection = None

def load_data():
    global user_data, promo_codes, BOT_ENABLED
    
    if users_collection is None:
        print("❌ MongoDB не підключено, пропускаємо завантаження даних")
        return
    
    try:
        user_data = {}
        for user in users_collection.find():
            user_data[user['_id']] = user
            if 'reset' in user and isinstance(user['reset'], str):
                user_data[user['_id']]['reset'] = datetime.date.fromisoformat(user['reset'])
            if 'premium' in user and 'until' in user['premium'] and user['premium']['until'] and isinstance(user['premium']['until'], str):
                dt = datetime.datetime.fromisoformat(user['premium']['until'].replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = UKRAINE_TZ.localize(dt)
                user_data[user['_id']]['premium']['until'] = dt
        
        promo_doc = promo_collection.find_one({"_id": "active_promos"})
        if promo_doc:
            promo_codes = promo_doc.get('codes', {})
        else:
            promo_collection.update_one(
                {"_id": "active_promos"},
                {"$set": {"codes": promo_codes}},
                upsert=True
            )
        
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
    return datetime.datetime.now(UKRAINE_TZ)

def save_data():
    try:
        if users_collection is None:
            print("❌ MongoDB не підключено, пропускаємо збереження")
            return
            
        for user_id, user_data_item in user_data.items():
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
        
        promo_collection.update_one(
            {"_id": "active_promos"},
            {"$set": {"codes": promo_codes}},
            upsert=True
        )
        
        bot_settings_collection.update_one(
            {"_id": "main_settings"},
            {"$set": {"enabled": BOT_ENABLED}},
            upsert=True
        )
        
        print(f"✅ Дані збережено в MongoDB о {get_ukraine_time().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"❌ Помилка збереження даних: {e}")

def auto_save():
    save_data()
    threading.Timer(AUTOSAVE_INTERVAL, auto_save).start()

def exit_handler():
    print("\n🛑 Завершення роботи... Зберігаємо дані.")
    save_data()

signal.signal(signal.SIGINT, lambda s, f: exit_handler())
signal.signal(signal.SIGTERM, lambda s, f: exit_handler())
atexit.register(exit_handler)

def check_bot_enabled(message):
    if not BOT_ENABLED and message.from_user.id != ADMIN_ID:
        maintenance_text = (
            "🔧 **Технічні роботи**\n"
            "Вибачте за тимчасові незручності! \n"
            "Бot тимчасово недоступний через оновлення.\n\n"
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

def is_russian_site(url):
    russian_domains = ['.ru', '.рф', 'tinkoff', 'yandex', 'mail.ru', 'rambler', 'kinopoisk']
    return any(domain in url for domain in russian_domains)

def google_search(query, user_id=None):
    # Визначаємо чи це преміум-користувач
    is_premium = False
    if user_id and user_id in user_data:
        user = user_data[user_id]
        is_premium = user.get('premium', {}).get('active', False) or user_id == ADMIN_ID
    
    # Використовуємо українські сайти
    sites_to_use = BASE_MOVIE_SITES
    
    # Додаємо ключові слова для жанрів
    genre_keywords = {
        "катастроф": "disaster catastrophe",
        "жахів": "horror scary",
        "комеді": "comedy funny",
        "фантастик": "sci-fi fantasy",
        "бойовик": "action adventure",
        "драм": "drama emotional",
        "мелодрам": "romance romantic",
        "трилер": "thriller suspense",
        "детектив": "detective mystery",
        "аніме": "anime japanese"
    }
    
    enhanced_query = query
    for ukr_keyword, eng_keyword in genre_keywords.items():
        if ukr_keyword in query.lower():
            enhanced_query = f"{query} {eng_keyword}"
            break
    
    # Формуємо запит з конкретними сайтами
    sites_query = " OR ".join([f"site:{site}" for site in sites_to_use])
    final_query = f"{enhanced_query} ({sites_query})"
    
    # Для преміум-користувачів збільшуємо кількість результатів
    num_results = 8 if is_premium else 5
    
    url = f"https://www.googleapis.com/customsearch/v1?q={final_query}&key={GOOGLE_API_KEY}&cx={SEARCH_ENGINE_ID}&num={num_results}"
    
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        results = []
        
        if "items" in data:
            for item in data["items"]:
                # Блокуємо російські сайти
                if is_russian_site(item.get('link', '')):
                    continue
                    
                # Перевіряємо чи це кіно-сайт
                if any(site in item['link'] for site in sites_to_use):
                    # Для преміум-користувачів додаємо більше інформації
                    if is_premium:
                        snippet = item.get('snippet', '')
                        if snippet:
                            snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
                            results.append(f"🎬 {item['title']}\n📝 {snippet}\n🔗 {item['link']}")
                        else:
                            results.append(f"🎬 {item['title']}\n🔗 {item['link']}")
                    else:
                        results.append(f"🎬 {item['title']}\n🔗 {item['link']}")
        
        if results:
            # Сортуємо результати - спочатку українські сайти
            def sort_key(result):
                if "kinoukr.com" in result: return 0
                if "film.ua" in result: return 1
                if "kino-teatr.ua" in result: return 2
                if "imdb.com" in result: return 3
                if "themoviedb.org" in result: return 4
                return 5
            
            results.sort(key=sort_key)
            
            # Обмежуємо кількість результатів
            max_results = 6 if is_premium else 4
            results = results[:max_results]
            
            return "\n\n".join(results)
        else:
            return "🔍 Нічого не знайдено на кіно-сайтах 😔"
            
    except Exception as e:
        print(f"❌ Помилка пошуку: {e}")
        return f"❌ Помилка пошуку: {e}"

def ask_gemini(user_id, question, context_messages=None):
    if context_messages is None:
        context_messages = []
    
    context_text = "\n".join(context_messages[-3:])
    
    question_lower = question.lower()
    is_movie_query = any(word in question_lower for word in movie_keywords) and not any(word in question_lower for word in code_keywords)
    is_code_query = any(word in question_lower for word in code_keywords) and not any(word in question_lower for word in movie_keywords)
    
    search_results = ""
    current_year = datetime.datetime.now().year
    
    if is_movie_query:
        search_results = google_search(question, user_id)
        
        # Отримуємо статус преміуму
        is_premium = False
        if user_id in user_data:
            user = user_data[user_id]
            is_premium = user.get('premium', {}).get('active', False) or user_id == ADMIN_ID
        
        if is_premium:
            prompt = f"""Ти експерт по фільмах, серіалах та аніме. Відповідай ДЕТАЛЬНО та ПРОФЕСІЙНО.

Поточний рік: {current_year}
Запит: {question}

Результати пошуку:
{search_results if search_results else "Нічого не знайдено"}

ВАЖЛИВО: Якщо запитують про майбутні фільми ({current_year+1}+ рік) - покажи анонсовані фільми, трейлери, очікувані прем'єри.

Вкажи ДЕТАЛЬНУ інформацію у форматі:
🎬 **Назва**: 
📅 **Рік випуску**: 
🌍 **Країна**: 
🎭 **Жанр**: 
⭐ **Рейтинг**: 
⏱️ **Тривалість**: 
🎥 **Режисер**: 
👥 **Актори**: 
📖 **Опис сюжету** (3-5 речень):
💡 **Цікаві факти**:
🎯 **Для кого підійде**:

Використовуй дані з надійних джерел."""
        else:
            prompt = f"""Ти експерт по фільмах, серіалах та аніме. Відповідай ТОЧНО та КОНКРЕТНО.

Поточний рік: {current_year}
Запит: {question}

Результати пошуку:
{search_results if search_results else "Нічого не знайдено"}

ВАЖЛИВО: Якщо запитують про майбутні фільми ({current_year+1}+ рік) - покажи анонсовані фільми, трейлери, очікувані прем'єри.

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
            "maxOutputTokens": 2048 if is_movie_query and is_premium else 1024,
            "temperature": 0.7
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=25)
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
        "• Пріоритетна обробка\n"
        "• Розширена база кіносайтів\n"
        "• Детальніші описи фільмів\n"
        "• Більше результатів пошуку\n\n"
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
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name
        }
    else:
        user_data[user_id]["username"] = message.from_user.username
        user_data[user_id]["first_name"] = message.from_user.first_name
        user_data[user_id]["last_name"] = message.from_user.last_name
    
    save_data()
    bot.reply_to(message, "👋 Вітаю! Я твій AI-помічник! Можу:\n• 🎬 Шукати фільми/серіали/аніме\n• 💻 Писати код\n• 💬 Вільно спілкуватись\n\nПросто напиши що потрібно! 😊", reply_markup=main_menu())

# ... (решта функцій залишаються аналогічними попередньому коду)

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
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name
        }
        save_data()
    else:
        user_data[user_id]["username"] = message.from_user.username
        user_data[user_id]["first_name"] = message.from_user.first_name
        user_data[user_id]["last_name"] = message.from_user.last_name
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
        search_results = google_search(message.text, user_id)
        if "🔍 Нічого не знайдено" not in search_results:
            premium_status = " (преміум пошук)" if is_premium else ""
            bot.reply_to(message, f"🔍 <b>Результати пошуку{premium_status}:</b>\n\n{search_results}\n\n📝 <b>А ось детальна інформація:</b>", parse_mode="HTML")
    
    bot.send_chat_action(message.chat.id, "typing")
    response = ask_gemini(user_id, message.text, user["history"])
    
    if is_code_query and "```" in response:
        user["last_code"] = response
        bot.reply_to(message, response, parse_mode="Markdown", reply_markup=create_copy_button(response))
    else:
        bot.reply_to(message, response)

if __name__ == "__main__":
    print("✅ Бот запущено з українськими сайтами та розумним пошуком!")
    print(f"📊 Користувачів у пам'яті: {len(user_data)}")
    
    threading.Timer(AUTOSAVE_INTERVAL, auto_save).start()
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"❌ Критична помилка: {e}")
        exit_handler()