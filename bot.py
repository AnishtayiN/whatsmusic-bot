import os
import logging
import sqlite3
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

from downloader import Downloader
from recognizer import Recognizer
from utils import sanitize_filename, extract_platform

# Load environment
load_dotenv()

# Config
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '').strip()
DB_PATH = os.getenv('DB_PATH', 'data/users.db')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
COOKIES_FILE = os.getenv('COOKIES_FILE', '')

# Ensure directories
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== Database ==========
class DB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_at TEXT,
                    last_active TEXT,
                    is_banned INTEGER DEFAULT 0,
                    is_admin INTEGER DEFAULT 0,
                    download_count INTEGER DEFAULT 0,
                    recognize_count INTEGER DEFAULT 0
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS blocked_users (
                    user_id INTEGER PRIMARY KEY
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            # Insert default settings if not exists
            conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("channel", ?)', (CHANNEL_USERNAME,))

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def add_user(self, user_id: int, username: str = '', first_name: str = '', last_name: str = ''):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, joined_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, now, now))

    def update_activity(self, user_id: int):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute('UPDATE users SET last_active = ? WHERE user_id = ?', (now, user_id))

    def increment_download(self, user_id: int):
        with sqlite3.connect(self.path) as conn:
            conn.execute('UPDATE users SET download_count = download_count + 1 WHERE user_id = ?', (user_id,))

    def increment_recognize(self, user_id: int):
        with sqlite3.connect(self.path) as conn:
            conn.execute('UPDATE users SET recognize_count = recognize_count + 1 WHERE user_id = ?', (user_id,))

    def ban_user(self, user_id: int):
        with sqlite3.connect(self.path) as conn:
            conn.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))

    def unban_user(self, user_id: int):
        with sqlite3.connect(self.path) as conn:
            conn.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))

    def is_banned(self, user_id: int) -> bool:
        with sqlite3.connect(self.path) as conn:
            cur = conn.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            return bool(row and row[0])

    def get_all_users(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute('SELECT * FROM users ORDER BY joined_at DESC')
            return [dict(row) for row in cur.fetchall()]

    def get_settings(self, key: str) -> Optional[str]:
        with sqlite3.connect(self.path) as conn:
            cur = conn.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = cur.fetchone()
            return row[0] if row else None

    def set_setting(self, key: str, value: str):
        with sqlite3.connect(self.path) as conn:
            conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))

db = DB()

# ========== Helpers ==========
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is member of required channel"""
    if not CHANNEL_USERNAME:
        return True
    try:
        chat_id = CHANNEL_USERNAME if CHANNEL_USERNAME.startswith('@') else '@' + CHANNEL_USERNAME
        member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
        return member.status in [ChatMember.OWNER, ChatMember.ADMINISTRATOR, ChatMember.MEMBER]
    except:
        return False

async def require_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if await check_membership(update, context):
        return True
    await update.message.reply_text(
        f"❗ برای استفاده از ربات ابتدا در کانال {CHANNEL_USERNAME} عضو شوید.\n"
        "پس از عضویت، دوباره امتحان کنید."
    )
    return False

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ این دستور فقط برای ادمین‌هاست.")
            return
        return await func(update, context)
    return wrapper

# ========== Bot Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)
    db.update_activity(user.id)

    if db.is_banned(user.id):
        await update.message.reply_text("⛔ شما توسط ادمین مسدود شده‌اید.")
        return

    if not await check_membership(update, context):
        await update.message.reply_text(
            f"❗ برای استفاده از ربات ابتدا در کانال {CHANNEL_USERNAME} عضو شوید.\n"
            "پس از عضویت، دوباره /start را بزنید."
        )
        return

    welcome = (
        f"🎵 سلام {user.first_name}!\n"
        "به ربات تشخیص و دانلود موزیک خوش آمدید.\n\n"
        "📌 دستورات:\n"
        "/start - نمایش این پیام\n"
        "/help - راهنما\n"
        "/download <لینک> - دانلود صدا از تیک‌تاک/یوتوب/اینستا/ساندکلود\n"
        "/recognize <فایل صوتی> - تشخیص موزیک با Shazam\n"
        "/info <لینک> - نمایش اطلاعات ویدیو/صوت\n"
        "/stats - آمار استفاده شما\n"
        "/admin - پنل ادمین (فقط ادمین‌ها)\n"
    )
    await update.message.reply_text(welcome)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text("⛔ شما مسدود شده‌اید.")
        return
    if not await require_membership(update, context):
        return

    if not context.args:
        await update.message.reply_text("❗ لطفاً یک لینک وارد کنید.\nمثال: /download https://www.tiktok.com/@user/video/123")
        return

    url = context.args[0]
    db.update_activity(user.id)

    await update.message.reply_text(f"⬇️ در حال دانلود از {extract_platform(url)}...")

    try:
        downloader = Downloader(output_dir=DOWNLOAD_DIR, cookies_file=COOKIES_FILE if Path(COOKIES_FILE).exists() else None)
        result = await downloader.download(url, extract_audio=True, playlist=False)

        if not result:
            await update.message.reply_text("❌ دانلود ناموفق بود.")
            return

        if isinstance(result, list):
            for r in result:
                await update.message.reply_document(document=open(r['filename'], 'rb'), filename=Path(r['filename']).name)
            db.increment_download(user.id)
            await update.message.reply_text(f"✅ {len(result)} فایل دانلود شد!")
        else:
            await update.message.reply_document(document=open(result['filename'], 'rb'), filename=Path(result['filename']).name)
            db.increment_download(user.id)
            await update.message.reply_text("✅ دانلود کامل شد!")

            if update.message.text and '--recognize' in update.message.text:
                # trigger recognize automatically if flag present (optional)
                pass

    except Exception as e:
        logger.error(f"Download error: {e}")
        await update.message.reply_text(f"❌ خطا در دانلود: {str(e)}")

async def recognize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text("⛔ شما مسدود شده‌اید.")
        return
    if not await require_membership(update, context):
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("❗ لطفاً به یک فایل صوتی پاسخ دهید.\nمثال: /recognize در پاسخ به فایل mp3")
        return

    file = update.message.reply_to_message.document
    if not file.file_name.lower().endswith(('.mp3', '.m4a', '.wav', '.flac', '.ogg')):
        await update.message.reply_text("❗ لطفاً یک فایل صوتی معتبر ارسال کنید.")
        return

    db.update_activity(user.id)

    await update.message.reply_text("🔍 در حال تشخیص موزیک با Shazam...")

    try:
        # Download file
        file_obj = await file.get_file()
        file_path = Path(DOWNLOAD_DIR) / f"temp_{user.id}_{file.file_name}"
        await file_obj.download_to_drive(file_path)

        # Recognize
        recognizer = Recognizer()
        result = await recognizer.recognize_file(str(file_path))

        # Cleanup
        if file_path.exists():
            file_path.unlink()

        if result and 'error' not in result:
            db.increment_recognize(user.id)
            await update.message.reply_text(recognizer.format_result(result))
        else:
            await update.message.reply_text(f"❌ تشخیص ناموفق: {result.get('error', 'خطای ناشناخته')}")

    except Exception as e:
        logger.error(f"Recognize error: {e}")
        await update.message.reply_text(f"❌ خطا در تشخیص: {str(e)}")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text("⛔ شما مسدود شده‌اید.")
        return
    if not await require_membership(update, context):
        return

    if not context.args:
        await update.message.reply_text("❗ لطفاً یک لینک وارد کنید.\nمثال: /info https://www.youtube.com/watch?v=abc")
        return

    url = context.args[0]
    db.update_activity(user.id)

    await update.message.reply_text("📋 در حال دریافت اطلاعات...")

    try:
        downloader = Downloader(output_dir=DOWNLOAD_DIR)
        info = await downloader.get_info(url)
        if info:
            msg = (
                f"📋 اطلاعات:\n"
                f"🎵 عنوان: {info.get('title', 'نامشخص')}\n"
                f"👤 کانال: {info.get('uploader', 'نامشخص')}\n"
                f"⏱ مدت: {info.get('duration', 0)} ثانیه\n"
                f"👁 بازدید: {info.get('view_count', 0):,}\n"
                f"❤️ لایک: {info.get('like_count', 0):,}\n"
                f"🖼 تصویر: {info.get('thumbnail', 'ندارد')}"
            )
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("❌ دریافت اطلاعات ناموفق.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {str(e)}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = db.get_user(user.id)
    if not data:
        await update.message.reply_text("❌ آماری یافت نشد.")
        return

    msg = (
        f"📊 آمار شما:\n"
        f"📥 دانلودها: {data.get('download_count', 0)}\n"
        f"🎵 تشخیص‌ها: {data.get('recognize_count', 0)}\n"
        f"📅 عضویت: {data.get('joined_at', 'نامشخص')}\n"
        f"🕐 آخرین فعالیت: {data.get('last_active', 'نامشخص')}"
    )
    await update.message.reply_text(msg)

# ========== Admin Panel ==========
@admin_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 آمار کلی", callback_data='admin_stats')],
        [InlineKeyboardButton("📢 ارسال همگانی", callback_data='admin_broadcast')],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data='admin_users')],
        [InlineKeyboardButton("🚫 مسدود کردن", callback_data='admin_ban')],
        [InlineKeyboardButton("✅ رفع مسدودیت", callback_data='admin_unban')],
        [InlineKeyboardButton("📌 تنظیم کانال", callback_data='admin_set_channel')],
        [InlineKeyboardButton("🔙 بستن", callback_data='admin_close')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👑 **پنل مدیریت**", reply_markup=reply_markup, parse_mode='Markdown')

@admin_only
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == 'admin_stats':
        users = db.get_all_users()
        total = len(users)
        banned = sum(1 for u in users if u.get('is_banned', 0))
        downloads = sum(u.get('download_count', 0) for u in users)
        recognizes = sum(u.get('recognize_count', 0) for u in users)

        msg = (
            f"📊 **آمار کلی ربات**\n"
            f"👥 کاربران: {total}\n"
            f"🚫 مسدود: {banned}\n"
            f"📥 دانلودها: {downloads}\n"
            f"🎵 تشخیص‌ها: {recognizes}"
        )
        await query.edit_message_text(msg, parse_mode='Markdown')

    elif data == 'admin_broadcast':
        await query.edit_message_text("📢 لطفاً پیام همگانی خود را ارسال کنید.\n(برای لغو /cancel)")
        context.user_data['broadcast_mode'] = True

    elif data == 'admin_users':
        users = db.get_all_users()
        if not users:
            await query.edit_message_text("❌ هیچ کاربری یافت نشد.")
            return
        # Show first 10
        lines = []
        for u in users[:10]:
            name = u.get('first_name', 'نامشخص')
            uname = u.get('username', '')
            status = '🚫' if u.get('is_banned') else '✅'
            lines.append(f"{status} {name} (@{uname}) - ID: {u['user_id']}")
        msg = "👥 **کاربران (۱۰ نفر اول)**\n" + "\n".join(lines)
        await query.edit_message_text(msg, parse_mode='Markdown')

    elif data == 'admin_ban':
        await query.edit_message_text("🚫 شناسه کاربری که می‌خواهید مسدود کنید را وارد کنید.\nمثال: 123456789")

    elif data == 'admin_unban':
        await query.edit_message_text("✅ شناسه کاربری که می‌خواهید رفع مسدودیت کنید را وارد کنید.\nمثال: 123456789")

    elif data == 'admin_set_channel':
        await query.edit_message_text("📌 کانال مورد نظر را وارد کنید (با @).\nمثال: @my_channel")

    elif data == 'admin_close':
        await query.edit_message_text("🔙 پنل بسته شد.")

async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('broadcast_mode'):
        return
    if update.message.text == '/cancel':
        context.user_data['broadcast_mode'] = False
        await update.message.reply_text("❌ ارسال همگانی لغو شد.")
        return

    users = db.get_all_users()
    success = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u['user_id'], text=update.message.text)
            success += 1
            await asyncio.sleep(0.05)  # avoid flood
        except:
            pass

    await update.message.reply_text(f"✅ پیام برای {success} کاربر ارسال شد.")
    context.user_data['broadcast_mode'] = False

async def handle_text_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle ban/unban/set_channel via text
    if not is_admin(update.effective_user.id):
        return

    text = update.message.text
    if 'broadcast_mode' in context.user_data and context.user_data['broadcast_mode']:
        return

    # Detect ban command pattern
    if text.startswith('/ban'):
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❗ شناسه کاربری را وارد کنید.")
            return
        try:
            user_id = int(parts[1])
            db.ban_user(user_id)
            await update.message.reply_text(f"✅ کاربر {user_id} مسدود شد.")
        except:
            await update.message.reply_text("❌ شناسه نامعتبر.")

    elif text.startswith('/unban'):
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❗ شناسه کاربری را وارد کنید.")
            return
        try:
            user_id = int(parts[1])
            db.unban_user(user_id)
            await update.message.reply_text(f"✅ کاربر {user_id} رفع مسدودیت شد.")
        except:
            await update.message.reply_text("❌ شناسه نامعتبر.")

    elif text.startswith('/set_channel'):
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❗ کانال را وارد کنید (با @).")
            return
        channel = parts[1]
        if not channel.startswith('@'):
            channel = '@' + channel
        db.set_setting('channel', channel)
        global CHANNEL_USERNAME
        CHANNEL_USERNAME = channel
        await update.message.reply_text(f"✅ کانال به {channel} تنظیم شد.")

# ========== Main ==========
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set in environment.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("download", download_command))
    app.add_handler(CommandHandler("recognize", recognize_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("admin", admin_panel))

    # Admin text commands
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_admin))

    # Callback query
    app.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))

    # Broadcast handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_handler))

    # Start bot
    logger.info("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()