import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
import json
from flask import Flask, request, jsonify
import anthropic
import threading

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
BOT_TOKEN = os.getenv('BOT_TOKEN')
GROUP_ID = int(os.getenv('GROUP_ID', '-1003951214564'))
GENERATOR_URL = os.getenv('GENERATOR_URL', 'https://fussreels.netlify.app/')
INITIAL_PASSWORD = os.getenv('INITIAL_PASSWORD', 'Reelslegko')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Хранилище паролей (в продакшене использовать БД)
PASSWORD_FILE = 'password_data.json'

def load_password_data():
    """Загружает данные о пароле из файла"""
    if os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE, 'r') as f:
            return json.load(f)
    return {
        'password': INITIAL_PASSWORD,
        'created_date': datetime.now().isoformat(),
        'next_change': (datetime.now() + timedelta(days=30)).isoformat()
    }

def save_password_data(data):
    """Сохраняет данные о пароле в файл"""
    with open(PASSWORD_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def generate_new_password():
    """Генерирует новый пароль"""
    import random
    import string
    
    # Формат: ReelsXXXX (буквы + цифры)
    random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    return f"Reels{random_part}"

async def check_password_expiry(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневная проверка необходимости смены пароля"""
    password_data = load_password_data()
    next_change = datetime.fromisoformat(password_data['next_change'])
    
    if datetime.now() >= next_change:
        # Время менять пароль
        new_password = generate_new_password()
        password_data['password'] = new_password
        password_data['created_date'] = datetime.now().isoformat()
        password_data['next_change'] = (datetime.now() + timedelta(days=30)).isoformat()
        save_password_data(password_data)
        
        logger.info(f"✅ Пароль изменён на: {new_password}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} (@{user.username}) начал диалог")
    
    welcome_text = (
        "👋 Привет! Я **Подо Рилс Генератор**\n\n"
        "Я помогу тебе генерировать идеи для Reels о подологии и ортопедии.\n\n"
        "Нажми /access чтобы получить доступ к генератору!"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /access - проверка подписки и выдача доступа"""
    user = update.effective_user
    user_id = user.id
    
    logger.info(f"Пользователь {user_id} запросил доступ")
    
    try:
        # Проверяем, подписан ли пользователь на группу
        member = await context.bot.get_chat_member(GROUP_ID, user_id)
        
        # Статусы "подписчика": 'member', 'restricted', 'creator', 'administrator'
        if member.status in ['member', 'restricted', 'creator', 'administrator']:
            # Пользователь подписан ✅
            password_data = load_password_data()
            current_password = password_data['password']
            
            success_text = (
                "✅ **Спасибо за подписку!**\n\n"
                "🎬 **Вот твой доступ к Генератору Рилс:**\n\n"
                f"🔗 Ссылка: {GENERATOR_URL}\n"
                f"🔑 Пароль: `{current_password}`\n\n"
                "📝 Пароль меняется автоматически раз в месяц.\n\n"
                "💡 **Как использовать:**\n"
                "1. Открой ссылку выше\n"
                "2. Введи пароль\n"
                "3. Выбери аудиторию (новички/педикюры/подологи)\n"
                "4. Нажми 'Сгенерировать 5 идей'\n"
                "5. Готовые идеи для Reels в руках! 🎉"
            )
            
            # Кнопка "Открыть генератор"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 Открыть генератор", url=GENERATOR_URL)]
            ])
            
            await update.message.reply_text(
                success_text,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            logger.info(f"✅ Доступ выдан пользователю {user_id}")
            
        else:
            # Пользователь не подписан ❌
            denied_text = (
                "❌ **Ты ещё не подписан на группу!**\n\n"
                "Чтобы получить доступ к Генератору Рилс, "
                "сначала подпишись на нашу группу СТОГ.\n\n"
                "После подписки вернись и напиши /access"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Перейти в группу СТОГ", url="https://t.me/+N5Ihg4P01xozZGQy")]
            ])
            
            await update.message.reply_text(
                denied_text,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            logger.warning(f"❌ Пользователь {user_id} не подписан на группу")
    
    except Exception as e:
        error_text = (
            f"⚠️ Ошибка: {str(e)}\n\n"
            "Попробуй позже или напиши администратору."
        )
        await update.message.reply_text(error_text)
        logger.error(f"Ошибка при проверке подписки: {e}")

async def password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /password - показать текущий пароль (для проверки)"""
    password_data = load_password_data()
    current_password = password_data['password']
    
    info_text = (
        f"🔑 **Текущий пароль:** `{current_password}`\n\n"
        f"📅 Создан: {password_data['created_date'][:10]}\n"
        f"🔄 Следующая смена: {password_data['next_change'][:10]}"
    )
    
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    help_text = (
        "📖 **Доступные команды:**\n\n"
        "/start - Начать\n"
        "/access - Получить доступ к генератору (нужна подписка)\n"
        "/password - Показать текущий пароль\n"
        "/help - Эта справка"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ── Flask приложение для генератора ──
app = Flask(__name__)

SYSTEM_PROMPT = """Ты — помощник по созданию идей для Reels про подологию и ортопедию.

АУДИТОРИЯ А — Новички-Свежачки (люди меняющие профессию):
- Страхи: слишком сложная теория, не смогу применить на практике
- Боли: не знаю с чего начать, много информации
- Желания: стать специалистом, зарабатывать больше

АУДИТОРИЯ Б — Мастера Педикюра (углубляющиеся):
- Страхи: слишком сложно, коллеги уже учатся
- Боли: вижу патологии но не знаю что с ними делать
- Желания: работать системно, повысить чек, стать специалистом

АУДИТОРИЯ В — Подологи (опытные):
- Страхи: потрачу деньги впустую, уже поздно менять подход
- Боли: работаю по старым протоколам, нет системы в лечении
- Желания: стать редким специалистом, давать результат, вырасти в доходе

Генерируй ТОЛЬКО JSON массив из 5 объектов, без markdown:
[{"hook":"...","idea":"...","trigger":"...","audience":"А" или "Б" или "В","format":"...","cta":"..."}]"""

@app.route('/api/generate', methods=['POST'])
def generate_ideas():
    """API endpoint для генератора рилс"""
    try:
        data = request.json
        user_prompt = data.get('prompt', '')
        
        if not user_prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        
        if not ANTHROPIC_API_KEY:
            return jsonify({'error': 'API key not configured'}), 500
        
        # Отправляем запрос к Claude
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-opus-4-1",
            max_tokens=2500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )
        
        # Парсим ответ
        response_text = message.content[0].text
        
        # Ищем JSON в ответе
        import re
        match = re.search(r'\[[\s\S]*\]', response_text)
        if not match:
            return jsonify({'error': 'Invalid response format'}), 500
        
        ideas = json.loads(match.group(0))
        
        return jsonify({'cards': ideas}), 200
    
    except Exception as e:
        logger.error(f"Generate API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({'status': 'ok'}), 200

def run_flask():
    """Запуск Flask в отдельном потоке"""
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

def main() -> None:
    """Запуск бота"""
    
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не установлен в переменных окружения!")
    
    logger.info("🤖 Запуск бота Подо Рилс Генератор...")
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask API запущен")
    
    # Создаём приложение Telegram
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("access", access))
    application.add_handler(CommandHandler("password", password))
    application.add_handler(CommandHandler("help", help_command))
    
    # Добавляем задачу проверки пароля каждый день
    application.job_queue.run_daily(
        check_password_expiry,
        time=None,
        days=tuple(range(7))
    )
    
    logger.info("✅ Бот готов к работе!")
    logger.info(f"📱 Telegram бот: t.me/podo_reels_bot")
    logger.info(f"🌐 API генератора: https://podo-reels-bot.up.railway.app/api/generate")
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
