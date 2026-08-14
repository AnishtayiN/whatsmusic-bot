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
from locales import get_text
from playlist_manager import PlaylistManager
from quality_manager import QualityManager
from extra_commands import set_quality_command, set_lang_command, playlist_command, tag_command, convert_command
from plugin_manager import PluginManager

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
            if update.callback_query:
                await update.callback_query.answer("⛔ این دستور فقط برای ادمین‌هاست.", show_alert=True)
            elif update.message:
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

    keyboard = [
        [InlineKeyboardButton("🔍 جستجوی آهنگ", callback_data="cmd_search")],
        [InlineKeyboardButton("⬇️ دانلود از لینک", callback_data="cmd_download")],
        [InlineKeyboardButton("🎵 شناسایی آهنگ", callback_data="cmd_recognize")],
        [InlineKeyboardButton("📝 متن ترانه", callback_data="cmd_lyrics")],
        [InlineKeyboardButton("🎬 تبدیل ویدیو", callback_data="cmd_convert")],
        [InlineKeyboardButton("📋 اطلاعات ویدیو", callback_data="cmd_info")],
        [InlineKeyboardButton("📊 آمار من", callback_data="cmd_stats")],
        [InlineKeyboardButton("📂 پلی‌لیست", callback_data="cmd_playlist")],
        [InlineKeyboardButton("🏷️ برچسب‌ها", callback_data="cmd_tag")],
    ]
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("👑 پنل ادمین", callback_data="cmd_admin")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome = (
        f"🎵 سلام {user.first_name}!\n\n"
        "به ربات تشخیص و دانلود موزیک خوش آمدید.\n\n"
        "💡 فقط کافیه نام آهنگ رو تایپ کنید!\n"
        "یا از دکمه‌های زیر استفاده کنید:"
    )
    await update.message.reply_text(welcome, reply_markup=reply_markup)

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
                await update.message.reply_audio(audio=open(r['filename'], 'rb'), filename=Path(r['filename']).name)
            db.increment_download(user.id)
        else:
            await update.message.reply_audio(audio=open(result['filename'], 'rb'), filename=Path(result['filename']).name)
            db.increment_download(user.id)

            if update.message.text and '--recognize' in update.message.text:
                # trigger recognize automatically if flag present (optional)
                pass

    except Exception as e:
        logger.error(f"Download error: {e}")
        # ارسال لینک به عنوان fallback
        url = context.args[0] if context.args else ''
        if 'youtube.com' in url or 'youtu.be' in url:
            await update.message.reply_text(f"❌ خطا در دانلود.\n\n🔗 لینک مستقیم:\n{url}\n\n💡 لینک رو کپی کن و در مرورگر باز کن.")
        else:
            await update.message.reply_text(f"❌ خطا در دانلود: {str(e)}")

async def recognize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text("⛔ شما مسدود شده‌اید.")
        return
    if not await require_membership(update, context):
        return

    # پشتیبانی از: ریپلای به فایل صوتی + ویس مستقیم + ویدیوی صوتی
    target_msg = update.message
    file = None
    file_name = "audio.ogg"

    # حالت ۱: ریپلای به فایل صوتی
    if update.message.reply_to_message:
        replied = update.message.reply_to_message
        if replied.document:
            file = replied.document
            file_name = file.file_name or "audio.ogg"
        elif replied.audio:
            file = replied.audio
            file_name = file.file_name or f"audio_{replied.message_id}.mp3"
        elif replied.voice:
            file = replied.voice
            file_name = f"voice_{replied.message_id}.ogg"
        elif replied.video:
            file = replied.video
            file_name = f"video_{replied.message_id}.mp4"
    # حالت ۲: فایل صوتی مستقیم
    elif update.message.document:
        file = update.message.document
        file_name = file.file_name or "audio.ogg"
    elif update.message.audio:
        file = update.message.audio
        file_name = file.file_name or f"audio_{update.message.message_id}.mp3"
    elif update.message.voice:
        file = update.message.voice
        file_name = f"voice_{update.message.message_id}.ogg"
    elif update.message.video:
        file = update.message.video
        file_name = f"video_{update.message.message_id}.mp4"

    if not file:
        await update.message.reply_text(
            "❗ لطفاً یک فایل صوتی ارسال کنید یا به آن ریپلای کنید.\n\n"
            "🎯 روش‌ها:\n"
            "۱. فایل صوتی بفرست + روش /recognize بزن\n"
            "۲. ویس بفرست + روش /recognize بزن\n"
            "۳. ریپلای به فایل صوتی با /recognize"
        )
        return

    db.update_activity(user.id)
    await update.message.reply_text("🔍 در حال تشخیص موزیک با Shazam...")

    try:
        file_obj = await file.get_file()
        file_path = Path(DOWNLOAD_DIR) / f"temp_{user.id}_{file_name}"
        await file_obj.download_to_drive(file_path)

        recognizer = Recognizer()
        result = await recognizer.recognize_file(str(file_path))

        if file_path.exists():
            file_path.unlink()

        if result and 'error' not in result:
            db.increment_recognize(user.id)
            await update.message.reply_text(recognizer.format_result(result))
        else:
            err = result.get('error', 'خطای ناشناخته') if result else 'نتیجه‌ای یافت نشد'
            await update.message.reply_text(f"❌ تشخیص ناموفق: {err}")

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


async def lyrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن ترانه"""
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text("⛔ شما مسدود شده‌اید.")
        return
    if not await require_membership(update, context):
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❗ لطفاً نام خواننده و آهنگ را وارد کنید.\nمثال: /lyrics Eminem Lose Yourself")
        return

    text = ' '.join(context.args)
    parts = text.split(' - ', 1)
    if len(parts) == 2:
        artist, title = parts[0].strip(), parts[1].strip()
    else:
        parts = text.split(' ', 1)
        artist, title = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ''

    if not artist or not title:
        await update.message.reply_text("❗ هم نام خواننده و هم نام آهنگ لازمه.")
        return

    await update.message.reply_text(f"🔍 در حال جستجوی متن ترانه «{title}» از «{artist}»...")

    recognizer = Recognizer()
    lyrics = await recognizer.get_lyrics(artist, title)

    if lyrics:
        # Telegram max message length is 4096
        if len(lyrics) > 4000:
            lyrics = lyrics[:4000] + "\n\n... [ادامه متن]"
        await update.message.reply_text(f"📝 **{artist} - {title}**\n\n{lyrics}")
    else:
        await update.message.reply_text("❌ متن ترانه یافت نشد.\n\n💡 نکته: نام خواننده و آهنگ رو به انگلیسی وارد کنید.")

# ========== Command Callback Handler ==========
async def command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر دکمه‌های منوی اصلی"""
    query = update.callback_query
    await query.answer()
    data = query.data

    keyboard_back = [[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="cmd_back")]]

    if data == "cmd_back":
        # بازگشت به منوی اصلی
        context.user_data['state'] = None
        user = update.effective_user
        kb = [
            [InlineKeyboardButton("🔍 جستجوی آهنگ", callback_data="cmd_search")],
            [InlineKeyboardButton("⬇️ دانلود از لینک", callback_data="cmd_download")],
            [InlineKeyboardButton("🎵 شناسایی آهنگ", callback_data="cmd_recognize")],
            [InlineKeyboardButton("📝 متن ترانه", callback_data="cmd_lyrics")],
            [InlineKeyboardButton("🎬 تبدیل ویدیو", callback_data="cmd_convert")],
            [InlineKeyboardButton("📋 اطلاعات ویدیو", callback_data="cmd_info")],
            [InlineKeyboardButton("📊 آمار من", callback_data="cmd_stats")],
        ]
        if is_admin(user.id):
            kb.append([InlineKeyboardButton("👑 پنل ادمین", callback_data="cmd_admin")])
        await query.edit_message_text(
            f"🎵 سلام {user.first_name}!\n\n"
            "به ربات تشخیص و دانلود موزیک خوش آمدید.\n\n"
            "💡 فقط کافیه نام آهنگ رو تایپ کنید!\n"
            "یا از دکمه‌های زیر استفاده کنید:",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif data == "cmd_search":
        await query.edit_message_text(
            "🔍 **جستجوی آهنگ**\n\n"
            "نام آهنگ یا خواننده رو مستقیم تایپ کنید:\n\n"
            "💡 مثال:\n"
            "• eminem lose yourself\n"
            "• رضا بهرام گل بیته\n"
            "• Chester Bennington\n\n"
            "⚡ فقط کافیه اسم رو تایپ کنی، نتایج با دکمه اومده!",
            reply_markup=InlineKeyboardMarkup(keyboard_back)
        )

    elif data == "cmd_download":
        context.user_data['state'] = 'download'
        await query.edit_message_text(
            "⬇️ **دانلود از لینک**\n\n"
            "فقط کافیه **لینک** رو بفرستی! (بدون دستور)\n\n"
            "💡 مثال:\n"
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ\n\n"
            "📱 پشتیبانی:\n"
            "• YouTube\n• TikTok\n• Instagram\n• SoundCloud\n• Vimeo\n• + ۱۰۰۰ سایت دیگه",
            reply_markup=InlineKeyboardMarkup(keyboard_back)
        )

    elif data == "cmd_recognize":
        context.user_data['state'] = 'recognize'
        await query.edit_message_text(
            "🎵 **شناسایی آهنگ با Shazam**\n\n"
            "فقط کافیه **ویس یا فایل صوتی** بفرستی! (بدون دستور)\n\n"
            "💡 روش:\n"
            "۱. ویس بفرست\n"
            "۲. فایل صوتی بفرست\n"
            "۳. ویدیو بفرست\n\n"
            "🎯 نتیجه: نام آهنگ، خواننده، آلبوم، لینک",
            reply_markup=InlineKeyboardMarkup(keyboard_back)
        )

    elif data == "cmd_lyrics":
        context.user_data['state'] = 'lyrics'
        await query.edit_message_text(
            "📝 **متن ترانه**\n\n"
            "نام خواننده و آهنگ رو بفرست (بدون دستور):\n\n"
            "💡 مثال:\n"
            "Eminem Lose Yourself\n"
            "رضا بهرام گل بیته\n\n"
            "🌐 زبان‌ها: فارسی، انگلیسی، عربی",
            reply_markup=InlineKeyboardMarkup(keyboard_back)
        )

    elif data == "cmd_convert":
        context.user_data['state'] = 'convert'
        await query.edit_message_text(
            "🎬 **تبدیل ویدیو به صدا (MP3)**\n\n"
            "فقط کافیه **لینک ویدیو** رو بفرستی (بدون دستور):\n\n"
            "💡 مثال:\n"
            "https://www.youtube.com/watch?v=...\n\n"
            "🎵 خروجی: MP3 با کیفیت بالا",
            reply_markup=InlineKeyboardMarkup(keyboard_back)
        )

    elif data == "cmd_info":
        context.user_data['state'] = 'info'
        await query.edit_message_text(
            "📋 **اطلاعات ویدیو/صوت**\n\n"
            "فقط کافیه **لینک** رو بفرستی (بدون دستور):\n\n"
            "💡 مثال:\n"
            "https://www.youtube.com/watch?v=...\n\n"
            "📊 اطلاعات: عنوان، خواننده، مدت، بازدید، لایک",
            reply_markup=InlineKeyboardMarkup(keyboard_back)
        )

    elif data == "cmd_stats":
        user = update.effective_user
        user_data = db.get_user(user.id)
        if user_data:
            msg = (
                f"📊 **آمار شما**\n\n"
                f"📥 دانلودها: {user_data.get('download_count', 0)}\n"
                f"🎵 تشخیص‌ها: {user_data.get('recognize_count', 0)}\n"
                f"📅 عضویت: {user_data.get('joined_at', 'نامشخص')}\n"
                f"🕐 آخرین فعالیت: {user_data.get('last_active', 'نامشخص')}"
            )
        else:
            msg = "❌ آماری یافت نشد."
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard_back))

    elif data == "cmd_playlist":
        await query.edit_message_text(
            "📂 **مدیریت پلی‌لیست**\n\n"
            "💡 دستورات:\n\n"
            "`` /playlist create <نام> `` — ایجاد پلی‌لیست\n"
            "`` /playlist delete <نام> `` — حذف پلی‌لیست\n"
            "`` /playlist list `` — نمایش پلی‌لیست‌ها\n"
            "`` /playlist show <نام> `` — نمایش آهنگ‌ها",
            reply_markup=InlineKeyboardMarkup(keyboard_back)
        )

    elif data == "cmd_tag":
        await query.edit_message_text(
            "🏷️ **مدیریت برچسب‌ها**\n\n"
            "💡 دستورات:\n\n"
            "`` /tag add <song_id> <tag> `` — افزودن برچسب\n"
            "`` /tag remove <song_id> <tag> `` — حذف برچسب\n"
            "`` /tag list `` — نمایش برچسب‌ها\n"
            "`` /tag search <tag> `` — جستجو با برچسب",
            reply_markup=InlineKeyboardMarkup(keyboard_back)
        )

    elif data == "cmd_admin":
        user = update.effective_user
        if not is_admin(user.id):
            await query.edit_message_text("⛔ فقط ادمین‌ها دسترسی دارند.")
            return
        kb = [
            [InlineKeyboardButton("📊 آمار کلی", callback_data='admin_stats')],
            [InlineKeyboardButton("📢 ارسال همگانی", callback_data='admin_broadcast')],
            [InlineKeyboardButton("👥 لیست کاربران", callback_data='admin_users')],
            [InlineKeyboardButton("🚫 مسدود کردن", callback_data='admin_ban')],
            [InlineKeyboardButton("✅ رفع مسدودیت", callback_data='admin_unban')],
            [InlineKeyboardButton("📌 تنظیم کانال", callback_data='admin_set_channel')],
            [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="cmd_back")],
        ]
        await query.edit_message_text("👑 **پنل مدیریت**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

# ========== Voice/Audio Auto-Recognize Handler ==========
async def audio_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر ویس یا فایل صوتی می‌فرسته، خودکار تشخیص بده (اگر state=recognize)"""
    user = update.effective_user
    if db.is_banned(user.id):
        return

    # فقط وقتی کاربر دکمه شناسایی آهنگ زده باشه
    state = context.user_data.get('state')
    if state not in ('recognize', 'recognize_wait'):
        return

    file = None
    file_name = "audio.ogg"

    if update.message.voice:
        file = update.message.voice
        file_name = f"voice_{update.message.message_id}.ogg"
    elif update.message.audio:
        file = update.message.audio
        file_name = file.file_name or f"audio_{update.message.message_id}.mp3"
    elif update.message.document:
        # فقط فایل‌های صوتی
        fname = (update.message.document.file_name or "").lower()
        if fname.endswith(('.mp3', '.m4a', '.wav', '.flac', '.ogg', '.opus')):
            file = update.message.document
            file_name = update.message.document.file_name or "audio.ogg"
    elif update.message.video:
        file = update.message.video
        file_name = f"video_{update.message.message_id}.mp4"

    if not file:
        return

    context.user_data['state'] = None
    db.update_activity(user.id)
    await update.message.reply_text("🔍 در حال تشخیص موزیک با Shazam...")

    try:
        file_obj = await file.get_file()
        file_path = Path(DOWNLOAD_DIR) / f"temp_{user.id}_{file_name}"
        await file_obj.download_to_drive(file_path)

        recognizer = Recognizer()
        result = await recognizer.recognize_file(str(file_path))

        if file_path.exists():
            file_path.unlink()

        if result and 'error' not in result:
            db.increment_recognize(user.id)
            await update.message.reply_text(recognizer.format_result(result))
            # پیشنهاد دانلود
            kb = [[InlineKeyboardButton("⬇️ دانلود این آهنگ", callback_data="dl_search")]]
            await update.message.reply_text("🎵 می‌خوای دانلودش کنم؟", reply_markup=InlineKeyboardMarkup(kb))
        else:
            err = result.get('error', 'خطای ناشناخته') if result else 'نتیجه‌ای یافت نشد'
            await update.message.reply_text(f"❌ تشخیص ناموفق: {err}")
    except Exception as e:
        logger.error(f"Recognize error: {e}")
        await update.message.reply_text(f"❌ خطا در تشخیص: {str(e)}")

# ========== Search Callback ==========
async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith('search_'):
        idx = int(data.replace('search_', ''))
        results = context.user_data.get('search_results', [])
        if 0 <= idx < len(results):
            track = results[idx]
            title = track.get('title', 'نامشخص')
            artist = track.get('artist', {}).get('name', 'نامشخص') if isinstance(track.get('artist'), dict) else str(track.get('artist', ''))
            await query.edit_message_text(f"🎵 {title}\n👤 {artist}\n\n⬇️ در حال دانلود...")

            # دانلود از YouTube با جستجو
            import asyncio as _asyncio
            await _asyncio.sleep(5)  # وقفه برای جلوگیری از rate limiting
            search_query = f"{title} {artist} audio"
            downloader = Downloader(output_dir=DOWNLOAD_DIR)
            result = await downloader.download(search_query, extract_audio=True, playlist=False, is_search=True)
            if result and isinstance(result, list) and len(result) > 0:
                try:
                    await query.message.reply_audio(
                        audio=open(result[0]['filename'], 'rb'),
                        title=title,
                        performer=artist,
                        filename=Path(result[0]['filename']).name
                    )
                    await query.edit_message_text(f"✅ {title} - {artist}")
                except Exception as e:
                    await query.edit_message_text(f"❌ خطا در ارسال فایل: {str(e)}")
            else:
                url = track.get('url', '')
                if url:
                    await query.edit_message_text(f"❌ دانلود مستقیم ناموفق بود.\n\n🔗 لینک دستی:\n{url}\n\n💡 لینک رو کپی کن و در مرورگر باز کن.")
                else:
                    await query.edit_message_text("❌ دانلود ناموفق بود.")
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

async def unified_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler یکپارچه: state machine بدون دستورات اسلش"""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text.strip()

    # پشتیبانی از دستورات ادمین قدیمی برای سازگاری
    if text.startswith('/'):
        # لغو حالت فعلی
        if text == '/start':
            await start(update, context)
            return
        if text == '/cancel':
            context.user_data['state'] = None
            await update.message.reply_text("❌ لغو شد. روی دکمه زیر برگرد:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منوی اصلی", callback_data="cmd_back")]]))
            return
        # دستورات قدیمی هنوز کار می‌کنن
        if text.startswith('/download'):
            context.args = text.split()[1:]
            await download_command(update, context)
            return
        if text.startswith('/lyrics'):
            context.args = text.split()[1:]
            await lyrics_command(update, context)
            return
        if text.startswith('/convert'):
            context.args = text.split()[1:]
            await convert_command(update, context)
            return
        if text.startswith('/info'):
            context.args = text.split()[1:]
            await info_command(update, context)
            return
        if text.startswith('/recognize'):
            await recognize_command(update, context)
            return
        if text.startswith('/ban') and is_admin(user.id):
            try:
                uid = int(text.split()[1])
                db.ban_user(uid)
                await update.message.reply_text(f"✅ کاربر {uid} مسدود شد.")
            except:
                await update.message.reply_text("❗ شناسه نامعتبر.")
            return
        if text.startswith('/unban') and is_admin(user.id):
            try:
                uid = int(text.split()[1])
                db.unban_user(uid)
                await update.message.reply_text(f"✅ کاربر {uid} رفع مسدودیت شد.")
            except:
                await update.message.reply_text("❗ شناسه نامعتبر.")
            return
        if text.startswith('/set_channel') and is_admin(user.id):
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
            return
        return

    # ===== State Machine: بدون دستور =====
    state = context.user_data.get('state')

    if state == 'download':
        await download_command(update, context)
        context.user_data['state'] = None
        return
    elif state == 'lyrics':
        context.args = text.split()
        await lyrics_command(update, context)
        context.user_data['state'] = None
        return
    elif state == 'convert':
        await convert_command(update, context)
        context.user_data['state'] = None
        return
    elif state == 'info':
        await info_command(update, context)
        context.user_data['state'] = None
        return
    elif state == 'recognize':
        # کاربر باید فایل بفرسته نه متن
        await update.message.reply_text(
            "🎵 **حالا ویس یا فایل صوتی بفرست!**\n(بدون نیاز به دستور)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منوی اصلی", callback_data="cmd_back")]])
        )
        context.user_data['state'] = 'recognize_wait'
        return
    elif state == 'recognize_wait':
        await update.message.reply_text(
            "🎵 ویس یا فایل صوتی بفرست تا تشخیص بدم!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منوی اصلی", callback_data="cmd_back")]])
        )
        return

    # هر متن دیگه‌ای → جستجوی آهنگ
    await search_music_inline(update, context)

async def search_music_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جستجوی خودکار آهنگ با تایپ نام در چت"""
    from recognizer import Recognizer
    text = update.message.text.strip()
    if len(text) < 2:
        return

    await update.message.reply_text(f"🔍 در حال جستجوی «{text}»...")

    recognizer = Recognizer()
    results = await recognizer.search_track(text, limit=5)

    if not results:
        await update.message.reply_text("❌ آهنگی یافت نشد.")
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for i, track in enumerate(results):
        title = track.get('title', 'نامشخص')
        artist = track.get('artist', {}).get('name', 'نامشخص') if isinstance(track.get('artist'), dict) else str(track.get('artist', ''))
        buttons.append([InlineKeyboardButton(f"🎵 {title} - {artist}", callback_data=f"search_{i}")])

    # ذخیره نتایج برای استفاده در callback
    context.user_data['search_results'] = results

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(f"🎵 نتایج جستجوی «{text}»:", reply_markup=reply_markup)

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
    app.add_handler(CommandHandler("set_quality", set_quality_command))
    app.add_handler(CommandHandler("set_lang", set_lang_command))
    app.add_handler(CommandHandler("playlist", playlist_command))
    app.add_handler(CommandHandler("tag", tag_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("lyrics", lyrics_command))

    # Callback query (admin panel + search results + commands)
    app.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    app.add_handler(CallbackQueryHandler(search_callback, pattern='^search_'))
    app.add_handler(CallbackQueryHandler(command_callback, pattern='^cmd_'))

    # تشخیص خودکار ویس/فایل صوتی
    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO | filters.Document.AUDIO, audio_message_handler
    ), group=1)

    # Unified text handler (admin commands + broadcast + music search)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unified_text_handler), group=1)

    # Start bot
    logger.info("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()