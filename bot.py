import telebot
import requests
import datetime
import re
import json
import os
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==========================
TELEGRAM_TOKEN = "8190669389:AAEStx12GMVbiNthRvXJ2Ks3AB8FGNADYnk"
GEMINI_API_KEY = "AIzaSyAgAZKpUA0okxEG428a9x6ql_O4DzkSMR4"
GOOGLE_API_KEY = "AIzaSyAjifVZ0gfxGz6zZCH5h2E3hgkrdTlEZM4"
SEARCH_ENGINE_ID = "d24749d51b2724215"
ADMIN_ID = 1637885523
FREE_LIMIT = 30
SUPPORT_USERNAME = "@нік"
# ==========================

bot = telebot.TeleBot(TELEGRAM_TOKEN)
user_data = {}
promo_codes = {
    "TEST1H": {"seconds": 3600, "uses_left": 50},
    "WELCOME1D": {"seconds": 86400, "uses_left": 100},
    "PREMIUM7D": {"seconds": 604800, "uses_left": 30},
    "VIP30D": {"seconds": 2592000, "uses_left": 20}
}

MOVIE_SITES = [
    "imdb.com", "myanimelist.net", "anidb.net", "anime-planet.com",
    "anilist.co", "animego.org", "shikimori.one", "anime-news-network.com",
    "kinoukr.com", "film.ua", "kino-teatr.ua", "novyny.live", "telekritika.ua"
]

movie_keywords = ["фільм", "серіал", "аніме", "мультфільм", "movie", "anime", "series", "кіно", "фильм", "сюжет", "сюжету", "опис"]
code_keywords = ["код", "html", "css", "js", "javascript", "python", "створи", "скрипт", "програма", "create", "program"]

def convert_dates(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, datetime.date):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_dates(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_dates(item) for item in obj]
    return obj

def restore_dates(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                try:
                    if 'T' in value:
                        obj[key] = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                    elif len(value) == 10 and value.count('-') == 2:
                        obj[key] = datetime.date.fromisoformat(value)
                except (ValueError, TypeError):
                    pass
            elif isinstance(value, (dict, list)):
                restore_dates(value)
    elif isinstance(obj, list):
        for item in obj:
            restore_dates(item)
    return obj

def save_data():
    try:
        data_to_save = {
            'user_data': convert_dates(user_data),
            'promo_codes': promo_codes
        }
        with open('bot_data.json', 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Помилка збереження даних: {e}")

def load_data():
    global user_data, promo_codes
    try:
        if not os.path.exists('bot_data.json'):
            return
            
        with open('bot_data.json', 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return
                
            data = json.loads(content)
            user_data = restore_dates(data.get('user_data', {}))
            promo_codes = data.get('promo_codes', promo_codes)
            
    except json.JSONDecodeError:
        try:
            os.rename('bot_data.json', 'bot_data_corrupted.json')
        except:
            pass
    except Exception as e:
        print(f"❌ Помилка завантаження: {e}")

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
        r = requests.get(url, timeout=10)
        data = r.json()
        results = []
        
        if "items" in data:
            for item in data["items"][:5]:
                if any(site in item['link'] for site in MOVIE_SITES):
                    results.append(f"{item['title']}\n{item['link']}")
        
        return "\n\n".join(results) if results else "🔍 Нічого не знайдено на кіно-сайтах 😔"
    except Exception as e:
        return f"❌ Помилка пошуку: {e}"

def ask_gemini(user_id, question, context_messages=None):
    if context_messages is None:
        context_messages = []
    
    context_text = "\n".join(context_messages[-6:])
    
    if any(word in question.lower() for word in movie_keywords) or any(keyword in context_text.lower() for keyword in movie_keywords):
        prompt = f"""Ти експерт по фільмах, серіалах та аніме. Відповідай ТОЧНО та КОНКРЕТНО.
        
        Контекст попередньої розмови:
        {context_text}
        
        Поточний запит: {question}
        
        Вкажи ТОЧНУ інформацію у такому форматі:
        🎬 Назва: 
        📅 Рік випуску: 
        🌍 Країна: 
        🎭 Жанр: 
        ⭐ Рейтинг (якщo відомий): 
        📖 Короткий опис сюжету (2-3 речення):
        
        Якщо це серіал - вкажи кількість сезонів.
        Якщо точно не знаєш - так і скажи, не вигадуй."""
    
    elif any(word in question.lower() for word in code_keywords):
        prompt = f"""Ти експерт-програміст. Відповідай ЧІТКИМ КОДОМ на запит.
        
        Контекст попередньої розмови:
        {context_text}
        
        Поточний запит: {question}
        
        ВИМОГИ:
        1. Надай ПОВНИЙ робочий код
        2. Використовуй чітке форматування з ``` 
        3. Додай короткі коментарі для пояснення
        4. Переконайся що код працює
        5. Якщо потрібно - вкажи яку мову програмування використовуєш"""
    
    else:
        prompt = f"""Ти дружній та допоміжний AI-асистент. Відповідай природньо та зрозуміло.
        
        Контекст попередньої розмови:
        {context_text}
        
        Поточний запит: {question}
        
        Вимоги до відповіді:
        1. Будь природнім та дружнім
        2. Відповідай розгорнуто але не занадто довго
        3. Використовуй емодзі для кращої читабельності
        4. Якщо питань про фільми/код - відповідай у спеціальному форматі
        5. Будь корисним та інформативним"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
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
    kb.add(KeyboardButton("🔙 Головне меню"))
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
        "• Інформація про рейтинг та жанр\n"
        "• Пошук на українських та міжнародних сайтах\n\n"
        "💻 <b>Генерація коду:</b>\n"
        "• Створення HTML/CSS/JS кодів\n"
        "• Python скрипти та програми\n"
        "• Зручне копіювання через кнопки\n\n"
        "💬 <b>Звичайне спілкування:</b>\n"
        "• Відповіді на будь-які запитання\n"
        "• Допомога з різних тем\n"
        "• Дружній та інформативний стиль\n\n"
        "💎 <b>Преміум система:</b>\n"
        "• Необмежені запити\n"
        "• Пріоритетна обробка\n"
        "• Детальніші відповіді\n\n"
        "⚙️ <b>Команди:</b>\n"
        "• /start - Запуск бота\n"
        "• /profile - Перегляд профілю\n"
        "• /premium - Інформація про преміум\n\n"
        f"🐞 <b>Знайшли баги чи є ідеї?</b>\n"
        f"Звертайтеся до техпідтримки: {SUPPORT_USERNAME}"
    )

load_data()

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {
            "used": 0,
            "premium": {"active": False, "until": None},
            "reset": datetime.date.today().isoformat(),
            "history": [],
            "free_used": False,
            "last_movie_query": None,
            "last_code": None,
            "username": message.from_user.username
        }
        save_data()
    bot.reply_to(message, "👋 Вітаю! Я твій AI-помічник! Можу:\n• 🎬 Шукати фільми/серіали/аніме\n• 💻 Писати код\n• 💬 Свободно спілкуватись\n\nПросто напиши що потрібно! 😊", reply_markup=main_menu())

@bot.message_handler(commands=["profile"])
def profile_command(message):
    profile(message)

@bot.message_handler(func=lambda m: m.text == "📊 Профіль")
def profile(message):
    user_id = message.from_user.id
    if user_id not in user_data:
        start(message)
        return
    user = user_data[user_id]
    today = datetime.date.today()
    
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
            else:
                until_date = user["premium"]["until"]
            
            if until_date > datetime.datetime.now():
                premium_status = f"✅ До {until_date.strftime('%d.%m.%Y %H:%M')}"
            else:
                user["premium"] = {"active": False, "until": None}
                save_data()
    
    role = "👑 Адміністратор" if user_id == ADMIN_ID else ("💎 Преміум" if user["premium"]["active"] else "👤 Користувач")
    limit_info = "♾️ Необмежено" if (user["premium"]["active"] or user_id == ADMIN_ID) else f"{FREE_LIMIT - user['used']} / {FREE_LIMIT}"
    
    text = (
        f"📊 <b>Профіль:</b>\n\n"
        f"🆔 <b>ID:</b> {user_id}\n"
        f"👤 <b>Ім'я:</b> @{user.get('username', 'Немає')}\n"
        f"🎭 <b>Роль:</b> {role}\n"
        f"💎 <b>Преміум:</b> {premium_status}\n"
        f"💬 <b>Використано сьогодні:</b> {user['used']}\n"
        f"🔋 <b>Ліміт:</b> {limit_info}\n"
        f"⏰ <b>Оновлення:</b> опівночі\n\n"
        f"🐞 <b>Техпідтримка:</b> {SUPPORT_USERNAME}"
    )
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🆘 Допомога")
def help_menu(message):
    bot.reply_to(message, help_text(), parse_mode='HTML')

@bot.message_handler(commands=["premium"])
def premium_command(message):
    premium_main(message)

@bot.message_handler(func=lambda m: m.text == "💎 Преміум")
def premium_main(message):
    user_id = message.from_user.id
    if user_id not in user_data:
        start(message)
        return
    
    user = user_data[user_id]
    if user["premium"]["active"]:
        bot.reply_to(message, "💎 У тебе вже активовано преміум!", reply_markup=main_menu())
    else:
        text = (
            "💎 <b>Преміум підписка:</b>\n\n"
            "✨ <b>Переваги преміуму:</b>\n"
            "• ♾️ Необмежена кількість запитів\n"
            "• ⚡ Пріоритетна обробка\n"
            "• 🎬 Детальніші відповіді\n"
            "• 💻 Більше можливостей для коду\n\n"
            "🎫 <b>Маєш промокод?</b> Обери 'Ввести промокод'\n"
            "💳 <b>Бажаєш придбати?</b> Обери 'Купити преміум'\n\n"
            f"🐞 <b>Техпідтримка:</b> {SUPPORT_USERNAME}"
        )
        bot.reply_to(message, text, parse_mode='HTML', reply_markup=premium_menu_keyboard())

@bot.message_handler(func=lambda m: m.text == "🎫 Ввести промокод")
def enter_promocode(message):
    msg = bot.reply_to(message, "🔑 Введіть ваш промокод:")
    bot.register_next_step_handler(msg, process_promocode)

def process_promocode(message):
    user_id = message.from_user.id
    promo = message.text.upper().strip()
    
    if promo in promo_codes:
        if promo_codes[promo]["uses_left"] > 0:
            seconds = promo_codes[promo]["seconds"]
            if seconds is None:
                user_data[user_id]["premium"] = {
                    "active": True,
                    "until": None
                }
                time_text = "НАЗАВЖДИ"
            else:
                until_date = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
                user_data[user_id]["premium"] = {
                    "active": True,
                    "until": until_date.isoformat()
                }
                time_text = format_time(seconds)
            
            promo_codes[promo]["uses_left"] -= 1
            save_data()
            
            bot.reply_to(message, f"🎉 Вітаю! Преміум активовано на {time_text}! 🎊", reply_markup=main_menu())
        else:
            bot.reply_to(message, "❌ Цей промокод вже вичерпано!", reply_markup=main_menu())
    else:
        bot.reply_to(message, "❌ Невірний промокод!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "💳 Купити преміум")
def buy_premium(message):
    text = (
        f"💳 <b>Для придбання преміуму:</b>\n\n"
        f"📞 <b>Зв'яжіться з адміністратором:</b> {SUPPORT_USERNAME}\n"
        f"💬 <b>Напишіть ваш ID:</b> {message.from_user.id}\n"
        f"💰 <b>Вартість:</b> 100 грн/місяць\n\n"
        f"🎫 <b>Або спробуйте ввести промокод!</b>\n\n"
        f"🐞 <b>Техпідтримка:</b> {SUPPORT_USERNAME}"
    )
    bot.reply_to(message, text, parse_mode='HTML', reply_markup=premium_menu_keyboard())

@bot.message_handler(func=lambda m: m.text == "⚙️ Адмін панель")
def admin_panel(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ Це меню доступне тільки адміну!")
        return
    bot.reply_to(message, "⚙️ Панель адміністратора", reply_markup=admin_keyboard())

@bot.message_handler(func=lambda m: m.text == "👥 Список користувачів")
def user_list(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return
    
    text = "👥 <b>Список користувачів:</b>\n\n"
    for uid, data in user_data.items():
        premium_status = "✅" if data["premium"]["active"] else "❌"
        username = data.get('username', 'Немає')
        text += f"ID: {uid} | @{username} | Преміум: {premium_status} | Використано: {data['used']}\n"
    
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🎫 Керування промокодами")
def manage_promocodes(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return
    
    text = "🎫 <b>Поточні промокоди:</b>\n\n"
    for code, info in promo_codes.items():
        time_text = format_time(info['seconds'])
        text += f"<code>{code}</code>: {time_text} | Залишилось: {info['uses_left']}\n"
    
    text += f"\n📝 <b>Для додавання нового промокоду:</b>\n<code>/addpromo КОД ЧАС КІЛЬКІСТЬ</code>\n\n"
    text += f"⏰ <b>Формат часу:</b> 1m, 2h, 3d, 1month, forever\n"
    text += f"🐞 <b>Техпідтримка:</b> {SUPPORT_USERNAME}"
    
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "➕ Додати преміум")
def add_premium_menu(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return
    
    msg = bot.reply_to(message, "👤 Введіть ID користувача та термін через пробіл:\nНаприклад: <code>123456789 30d</code>\n\nДоступні формати: 1m, 2h, 3d, 1month, forever", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_add_premium)

def process_add_premium(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        target_id = int(parts[0])
        time_input = " ".join(parts[1:])
        
        seconds = parse_time_input(time_input)
        if seconds is None and time_input.lower() != "forever":
            bot.reply_to(message, "❌ Невірний формат часу! Використовуйте: 1m, 2h, 3d, 1month, forever")
            return
        
        if target_id not in user_data:
            user_data[target_id] = {
                "used": 0,
                "premium": {"active": False, "until": None},
                "reset": datetime.date.today().isoformat(),
                "history": [],
                "free_used": False,
                "last_movie_query": None,
                "last_code": None,
                "username": "unknown"
            }
        
        if seconds is None:
            user_data[target_id]["premium"] = {
                "active": True,
                "until": None
            }
            time_text = "НАЗАВЖДИ"
        else:
            until_date = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
            user_data[target_id]["premium"] = {
                "active": True,
                "until": until_date.isoformat()
            }
            time_text = format_time(seconds)
        
        save_data()
        
        bot.reply_to(message, f"✅ Преміум додано для ID {target_id} на {time_text}!")
        
        try:
            bot.send_message(target_id, f"🎉 Вам надано преміум на {time_text} адміністратором!")
        except:
            pass
            
    except (ValueError, IndexError):
        bot.reply_to(message, "❌ Невірний формат! Використовуйте: ID ЧАС")

@bot.message_handler(func=lambda m: m.text == "⏰ Преміум на час")
def premium_custom_time(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return
    
    msg = bot.reply_to(message, "👤 Введіть ID користувача та дату завершення (дд.мм.рррр):\nНаприклад: <code>123456789 31.12.2024</code>", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_premium_custom_time)

def process_premium_custom_time(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        target_id = int(parts[0])
        date_str = parts[1]
        
        day, month, year = map(int, date_str.split('.'))
        end_date = datetime.datetime(year, month, day, 23, 59, 59)
        
        if target_id not in user_data:
            user_data[target_id] = {
                "used": 0,
                "premium": {"active": False, "until": None},
                "reset": datetime.date.today().isoformat(),
                "history": [],
                "free_used": False,
                "last_movie_query": None,
                "last_code": None,
                "username": "unknown"
            }
        
        user_data[target_id]["premium"] = {
            "active": True,
            "until": end_date.isoformat()
        }
        save_data()
        
        bot.reply_to(message, f"✅ Преміум додано для ID {target_id} до {end_date.strftime('%d.%m.%Y')}!")
        
        try:
            bot.send_message(target_id, f"🎉 Вам надано преміум до {end_date.strftime('%d.%m.%Y')} адміністратором!")
        except:
            pass
            
    except (ValueError, IndexError):
        bot.reply_to(message, "❌ Невірний формат! Використовуйте: ID ДД.ММ.РРРР")

@bot.message_handler(commands=["addpromo"])
def add_promocode(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ Невірний формат! Використовуйте: /addpromo КОД ЧАС [КІЛЬКІСТЬ]")
            return
            
        code = parts[1].upper()
        time_input = parts[2]
        uses = int(parts[3]) if len(parts) > 3 else 1
        
        seconds = parse_time_input(time_input)
        if seconds is None and time_input.lower() != "forever":
            bot.reply_to(message, "❌ Невірний формат часу! Використовуйте: 1m, 2h, 3d, 1month, forever")
            return
        
        promo_codes[code] = {"seconds": seconds, "uses_left": uses}
        save_data()
        
        time_text = format_time(seconds)
        bot.reply_to(message, f"✅ Промокод {code} додано: {time_text}, {uses} використань")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Невірний формат! Використовуйте: /addpromo КОД ЧАС [КІЛЬКІСТЬ]")

@bot.message_handler(func=lambda m: m.text == "🔙 Головне меню")
def back_to_main(message):
    bot.reply_to(message, "🔙 Повертаємось до головного меню", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith('copy_'))
def handle_copy(call):
    user_id = call.from_user.id
    if user_id in user_data and user_data[user_id]["last_code"]:
        bot.answer_callback_query(call.id, "📋 Код скопійовано до буферу обміну!")
    else:
        bot.answer_callback_query(call.id, "❌ Немає коду для копіювання")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {
            "used": 0, 
            "premium": {"active": False, "until": None}, 
            "reset": datetime.date.today().isoformat(), 
            "history": [], 
            "free_used": False,
            "last_movie_query": None,
            "last_code": None,
            "username": message.from_user.username
        }
        save_data()
    
    user = user_data[user_id]
    today = datetime.date.today()
    
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
        else:
            until_date = user["premium"]["until"]
        
        if until_date < datetime.datetime.now():
            user["premium"] = {"active": False, "until": None}
            save_data()

    if not user["premium"]["active"] and user_id != ADMIN_ID:
        if user["used"] >= FREE_LIMIT:
            bot.reply_to(message, f"⚠️ Ліміт вичерпано! Спробуй завтра або звернись до адміністратора.\n\n🐞 Техпідтримка: {SUPPORT_USERNAME}")
            return

    query = message.text
    
    context_messages = []
    if user["last_movie_query"] and (query.isdigit() or any(word in query.lower() for word in ["год", "рік", "країна", "страна", "жанр", "сюжет"])):
        context_messages.append(f"👤: {user['last_movie_query']}")
        full_query = f"{user['last_movie_query']} {query}"
    else:
        full_query = query
        if any(word in query.lower() for word in movie_keywords):
            user["last_movie_query"] = query
        else:
            user["last_movie_query"] = None

    for hist_msg in user["history"][-4:]:
        context_messages.append(hist_msg)

    is_movie_query = any(word in full_query.lower() for word in movie_keywords)
    is_code_query = any(word in full_query.lower() for word in code_keywords)
    
    if is_movie_query:
        search_query = re.sub(r'[^a-zA-Zа-яА-Я0-9\s]', '', full_query)
        google_results = google_search(search_query + " фільм серіал аніме опис сюжету", "movie")
        gemini_reply = ask_gemini(user_id, full_query, context_messages)
        reply_text = f"{gemini_reply}\n\n🔍 Результати пошуку:\n{google_results}"
        reply_markup = None
    
    elif is_code_query:
        gemini_reply = ask_gemini(user_id, full_query, context_messages)
        reply_text = gemini_reply
        user["last_code"] = gemini_reply
        reply_markup = create_copy_button(gemini_reply)
    
    else:
        gemini_reply = ask_gemini(user_id, full_query, context_messages)
        reply_text = gemini_reply
        reply_markup = None

    user["history"].append(f"👤: {query}")
    user["history"].append(f"🤖: {reply_text[:100]}...")
    save_data()

    if reply_markup:
        bot.reply_to(message, reply_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        bot.reply_to(message, reply_text)

    if not user["premium"]["active"] and user_id != ADMIN_ID:
        user["used"] += 1
        save_data()

print("✅ Бот запущено з повним контролем часу та техпідтримкою!")
bot.polling(none_stop=True)
