"""bot.py - Telegram bot: music download, recognition, conversion and admin panel."""
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters,
)

from config import (
    BOT_TOKEN, ADMIN_IDS, CHANNEL_USERNAME, DB_PATH, DOWNLOAD_DIR,
    COOKIES_FILE, DEFAULT_LANG, MAX_SEARCH_RESULTS, TELEGRAM_MAX_MSG,
    SUPPORTED_AUDIO_EXTS,
)
from db import DB
from downloader import Downloader
from recognizer import Recognizer
from utils import sanitize_filename, extract_platform, is_url, cleanup_file
from locales import get_text
from playlist_manager import PlaylistManager
from quality_manager import QualityManager
from extra_commands import set_quality_command, set_lang_command, playlist_command, tag_command, convert_command

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Singletons
db = DB(DB_PATH, default_channel=CHANNEL_USERNAME)
playlist_mgr = PlaylistManager()
quality_mgr = QualityManager()
recognizer = Recognizer()


# ========== Helpers ==========
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def user_lang(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    """Get the user's preferred language, falling back to default."""
    lang = context.user_data.get('lang') if context.user_data else None
    if lang:
        return lang
    return db.get_language(user_id, DEFAULT_LANG)


async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the user is a member of the required channel."""
    channel = db.get_settings('channel') or CHANNEL_USERNAME
    if not channel:
        return True
    try:
        chat_id = channel if channel.startswith('@') else '@' + channel
        member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
        return member.status in (ChatMember.OWNER, ChatMember.ADMINISTRATOR, ChatMember.MEMBER)
    except Exception as e:
        logger.debug(f'Membership check failed: {e}')
        return False


async def require_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    channel = db.get_settings('channel') or CHANNEL_USERNAME
    if await check_membership(update, context):
        return True
    msg = (
        f'❗ برای استفاده از ربات ابتدا در کانال {channel} عضو شوید.\n'
        'پس از عضویت، دوباره امتحان کنید.'
    )
    if update.callback_query:
        await update.callback_query.answer(msg, show_alert=True)
    elif update.message:
        await update.message.reply_text(msg)
    return False


def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton('🔍 جستجوی آهنگ', callback_data='cmd_search')],
        [InlineKeyboardButton('⬇️ دانلود از لینک', callback_data='cmd_download')],
        [InlineKeyboardButton('🎵 شناسایی آهنگ', callback_data='cmd_recognize')],
        [InlineKeyboardButton('📝 متن ترانه', callback_data='cmd_lyrics')],
        [InlineKeyboardButton('🎬 تبدیل ویدئو', callback_data='cmd_convert')],
        [InlineKeyboardButton('ℹ️ اطلاعات ویدئو', callback_data='cmd_info')],
        [InlineKeyboardButton('📊 آمار من', callback_data='cmd_stats')],
        [InlineKeyboardButton('📂 پلی‌لیست', callback_data='cmd_playlist')],
        [InlineKeyboardButton('🏷️ برچسب‌ها', callback_data='cmd_tag')],
    ]
    if is_admin(user_id):
        kb.append([InlineKeyboardButton('👑 پنل ادمین', callback_data='cmd_admin')])
    return InlineKeyboardMarkup(kb)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton('🔙 بازگشت به منو', callback_data='cmd_back')]])


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            msg = '⛔ این دستور فقط برای ادمین‌هاست.'
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            elif update.message:
                await update.message.reply_text(msg)
            return
        return await func(update, context)
    return wrapper


# ========== Bot Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)
    db.update_activity(user.id)

    if db.is_banned(user.id):
        await update.message.reply_text('⛔ شما توسط ادمین مسدود شده‌اید.')
        return

    if not await check_membership(update, context):
        channel = db.get_settings('channel') or CHANNEL_USERNAME
        await update.message.reply_text(
            f'❗ برای استفاده از ربات ابتدا در کانال {channel} عضو شوید.\n'
            'پس از عضویت، دوباره /start را بزنید.'
        )
        return

    welcome = (
        f'🎵 سلام {user.first_name}!\n\n'
        'به ربات تشخیص و دانلود موسیقی خوش آمدید.\n\n'
        '💡 فقط کافیه نام آهنگ رو تایپ کنی!\n'
        'یا از دکمه‌های زیر استفاده کنی:'
    )
    await update.message.reply_text(welcome, reply_markup=main_menu_keyboard(user.id))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def _send_audio_file(message, file_path: Path, title: str = '', performer: str = '') -> bool:
    """Send an audio file with a context-managed handle. Returns True on success."""
    if not file_path.exists():
        return False
    try:
        with open(file_path, 'rb') as f:
            await message.reply_audio(audio=f, title=title or file_path.stem,
                                      performer=performer, filename=file_path.name)
        return True
    except Exception as e:
        logger.error(f'Failed to send audio {file_path}: {e}')
        return False


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text('⛔ شما مسدود شده‌اید.')
        return
    if not await require_membership(update, context):
        return

    if not context.args:
        await update.message.reply_text('❗ لطفاً یک لینک وارد کنید.\nمثال: /download https://www.tiktok.com/@user/video/123')
        return

    url = context.args[0]
    if not is_url(url):
        await update.message.reply_text('❗ لینک وارد شده معتبر نیست.')
        return

    db.update_activity(user.id)
    await update.message.reply_text(f'⬇️ در حال دانلود از {extract_platform(url)}...')

    downloader = Downloader(output_dir=DOWNLOAD_DIR, cookies_file=COOKIES_FILE or None)
    try:
        result = await downloader.download(url, extract_audio=True, playlist=False)
    except Exception as e:
        logger.error(f'Download error: {e}')
        await update.message.reply_text(f'❌ خطا در دانلود: {e}')
        return

    if not result:
        if 'youtu' in url:
            await update.message.reply_text(
                f'❌ دانلود ناموفق بود.\n\n🔗 لینک مستقیم:\n{url}\n\n💡 لینک رو کپی کن و در مرورگر باز کن.'
            )
        else:
            await update.message.reply_text('❌ دانلود ناموفق بود.')
        return

    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        items = [result]
    else:
        await update.message.reply_text('❌ دانلود ناموفق بود.')
        return

    sent = False
    for r in items:
        fpath = Path(r.get('filename', ''))
        title = r.get('title', '')
        if await _send_audio_file(update.message, fpath, title=title):
            sent = True
            db.increment_download(user.id)
    if not sent:
        await update.message.reply_text('❌ ارسال فایل ناموفق بود.')


async def recognize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text('⛔ شما مسدود شده‌اید.')
        return
    if not await require_membership(update, context):
        return

    file, file_name = _extract_audio_file_from_message(update.message)
    if not file:
        await update.message.reply_text(
            '❗ لطفاً یک فایل صوتی ارسال کنید یا به آن ریپلای کنید.\n\n'
            '🎬 روش‌ها:\n'
            '۱. فایل صوتی بفرست + روش /recognize بزن\n'
            '۲. ویس بفرست + روش /recognize بزن\n'
            '۳. ریپلای به فایل صوتی با /recognize'
        )
        return

    db.update_activity(user.id)
    await update.message.reply_text('🔍 در حال تشخیص موسیقی با Shazam...')

    file_path = None
    try:
        file_obj = await file.get_file()
        file_path = Path(DOWNLOAD_DIR) / f'temp_{user.id}_{file_name}'
        await file_obj.download_to_drive(file_path)

        result = await recognizer.recognize_file(str(file_path))
        if result and 'error' not in result:
            db.increment_recognize(user.id)
            await update.message.reply_text(recognizer.format_result(result))
            kb = InlineKeyboardMarkup([[InlineKeyboardButton('⬇️ دانلود این آهنگ', callback_data='dl_recognize')]])
            await update.message.reply_text('🎵 می‌خوای دانلودش کنم؟', reply_markup=kb)
        else:
            err = (result or {}).get('error', 'نتیجه‌ای پیدا نشد')
            await update.message.reply_text(f'❌ تشخیص ناموفق: {err}')
    except Exception as e:
        logger.error(f'Recognize error: {e}')
        await update.message.reply_text(f'❌ خطا در تشخیص: {e}')
    finally:
        if file_path:
            cleanup_file(file_path)


def _extract_audio_file_from_message(message):
    """Return (file_obj, file_name) for a voice/audio/video/document to recognize."""
    target = message.reply_to_message if message.reply_to_message else message
    if not target:
        return None, 'audio.ogg'
    if target.document:
        return target.document, target.document.file_name or 'audio.ogg'
    if target.audio:
        return target.audio, target.audio.file_name or f'audio_{target.message_id}.mp3'
    if target.voice:
        return target.voice, f'voice_{target.message_id}.ogg'
    if target.video:
        return target.video, f'video_{target.message_id}.mp4'
    return None, 'audio.ogg'


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text('⛔ شما مسدود شده‌اید.')
        return
    if not await require_membership(update, context):
        return

    if not context.args or not is_url(context.args[0]):
        await update.message.reply_text('❗ لطفاً یک لینک وارد کنید.\nمثال: /info https://www.youtube.com/watch?v=abc')
        return

    url = context.args[0]
    db.update_activity(user.id)
    await update.message.reply_text('ℹ️ در حال دریافت اطلاعات...')

    try:
        downloader = Downloader(output_dir=DOWNLOAD_DIR, cookies_file=COOKIES_FILE or None)
        info = await downloader.get_info(url)
        if info:
            msg = (
                f"ℹ️ اطلاعات:\n"
                f"🎵 عنوان: {info.get('title') or 'نامشخص'}\n"
                f"👤 کانال: {info.get('uploader') or 'نامشخص'}\n"
                f"⏱ مدت: {info.get('duration', 0)} ثانیه\n"
                f"👁 بازدید: {info.get('view_count', 0):,}\n"
                f"❤️ لایک: {info.get('like_count', 0):,}\n"
                f"🖼 تصویر: {info.get('thumbnail') or 'ندارد'}"
            )
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text('❌ دریافت اطلاعات ناموفق.')
    except Exception as e:
        logger.error(f'Info error: {e}')
        await update.message.reply_text(f'❌ خطا: {e}')


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = db.get_user(user.id)
    if not data:
        await update.message.reply_text('❌ آماری پیدا نشد.')
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
    """Fetch song lyrics."""
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text('⛔ شما مسدود شده‌اید.')
        return
    if not await require_membership(update, context):
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text('❗ لطفاً نام خواننده و آهنگ را وارد کنید.\nمثال: /lyrics Eminem Lose Yourself')
        return

    text = ' '.join(context.args)
    # Support "artist - title" or "artist title"
    if ' - ' in text:
        artist, title = text.split(' - ', 1)
    else:
        parts = text.split(' ', 1)
        artist = parts[0]
        title = parts[1] if len(parts) > 1 else ''
    artist, title = artist.strip(), title.strip()

    if not artist or not title:
        await update.message.reply_text('❗ هم نام خواننده و هم نام آهنگ لازمه.')
        return

    db.update_activity(user.id)
    await update.message.reply_text(f'🔍 در حال جستجوی متن ترانه «{title}» از «{artist}»...')

    try:
        lyrics = await recognizer.get_lyrics(artist, title)
    except Exception as e:
        logger.error(f'Lyrics error: {e}')
        lyrics = ''

    if lyrics:
        if len(lyrics) > TELEGRAM_MAX_MSG - 100:
            lyrics = lyrics[:TELEGRAM_MAX_MSG - 100] + '\n\n... [ادامه متن]'
        await update.message.reply_text(f'📝 **{artist} - {title}**\n\n{lyrics}')
    else:
        await update.message.reply_text('❌ متن ترانه پیدا نشد.\n\n💡 نکته: نام خواننده و آهنگ رو به انگلیسی وارد کنید.')


# ========== Command Callback Handler ==========
async def command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main-menu button callbacks."""
    query = update.callback_query
    await query.answer()
    data = query.data
    back = back_keyboard()

    if data == 'cmd_back':
        context.user_data['state'] = None
        user = update.effective_user
        await query.edit_message_text(
            f'🎵 سلام {user.first_name}!\n\n'
            'به ربات تشخیص و دانلود موسیقی خوش آمدید.\n\n'
            '💡 فقط کافیه نام آهنگ رو تایپ کنی!\n'
            'یا از دکمه‌های زیر استفاده کنی:',
            reply_markup=main_menu_keyboard(user.id),
        )
    elif data == 'cmd_search':
        await query.edit_message_text(
            '🔍 **جستجوی آهنگ**\n\n'
            'نام آهنگ یا خواننده رو مستقیم تایپ کن:\n\n'
            '💡 مثال:\n'
            '• eminem lose yourself\n'
            '• رضا بهرام گل بیته\n'
            '• Chester Bennington\n\n'
            '⚡ فقط کافیه اسم رو تایپ کنی، نتایج با دکمه اومده!',
            reply_markup=back,
        )
    elif data == 'cmd_download':
        context.user_data['state'] = 'download'
        await query.edit_message_text(
            '⬇️ **دانلود از لینک**\n\n'
            'فقط کافیه **لینک** رو بفرستی! (بدون دستور)\n\n'
            '💡 مثال:\n'
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ\n\n'
            '📱 پشتیبانی:\n'
            '• YouTube\n• TikTok\n• Instagram\n• SoundCloud\n• Vimeo\n• + ۱۰۰۰ سایت دیگه',
            reply_markup=back,
        )
    elif data == 'cmd_recognize':
        context.user_data['state'] = 'recognize'
        await query.edit_message_text(
            '🎵 **شناسایی آهنگ با Shazam**\n\n'
            'فقط کافیه **ویس یا فایل صوتی** بفرستی! (بدون دستور)\n\n'
            '💡 روش:\n'
            '۱. ویس بفرست\n'
            '۲. فایل صوتی بفرست\n'
            '۳. ویدئو بفرست\n\n'
            '🎯 نتیجه: نام آهنگ، خواننده، آلبوم، لینک',
            reply_markup=back,
        )
    elif data == 'cmd_lyrics':
        context.user_data['state'] = 'lyrics'
        await query.edit_message_text(
            '📝 **متن ترانه**\n\n'
            'نام خواننده و آهنگ رو بفرست (بدون دستور):\n\n'
            '💡 مثال:\n'
            'Eminem Lose Yourself\n'
            'رضا بهرام گل بیته\n\n'
            '🌐 زبان‌ها: فارسی، انگلیسی، عربی',
            reply_markup=back,
        )
    elif data == 'cmd_convert':
        context.user_data['state'] = 'convert'
        await query.edit_message_text(
            '🎬 **تبدیل ویدئو به صدا (MP3)**\n\n'
            'فقط کافیه **لینک ویدئو** رو بفرستی (بدون دستور)\n\n'
            '💡 مثال:\n'
            'https://www.youtube.com/watch?v=...\n\n'
            '🎵 خروجی: MP3 با کیفیت بالا',
            reply_markup=back,
        )
    elif data == 'cmd_info':
        context.user_data['state'] = 'info'
        await query.edit_message_text(
            'ℹ️ **اطلاعات ویدئو/صوت**\n\n'
            'فقط کافیه **لینک** رو بفرستی (بدون دستور)\n\n'
            '💡 مثال:\n'
            'https://www.youtube.com/watch?v=...\n\n'
            '📊 اطلاعات: عنوان، خواننده، مدت، بازدید، لایک',
            reply_markup=back,
        )
    elif data == 'cmd_stats':
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
            msg = '❌ آماری پیدا نشد.'
        await query.edit_message_text(msg, reply_markup=back)
    elif data == 'cmd_playlist':
        await query.edit_message_text(
            '📂 **مدیریت پلی‌لیست**\n\n'
            '💡 دستورات:\n\n'
            '`` /playlist create <نام> `` — ایجاد پلی‌لیست\n'
            '`` /playlist delete <نام> `` — حذف پلی‌لیست\n'
            '`` /playlist list `` — نمایش پلی‌لیست‌ها\n'
            '`` /playlist show <نام> `` — نمایش آهنگ‌ها',
            reply_markup=back,
        )
    elif data == 'cmd_tag':
        await query.edit_message_text(
            '🏷️ **مدیریت برچسب‌ها**\n\n'
            '💡 دستورات:\n\n'
            '`` /tag add <song_id> <tag> `` — افزودن برچسب\n'
            '`` /tag remove <song_id> <tag> `` — حذف برچسب\n'
            '`` /tag list `` — نمایش برچسب‌ها\n'
            '`` /tag search <tag> `` — جستجو با برچسب',
            reply_markup=back,
        )
    elif data == 'cmd_admin':
        user = update.effective_user
        if not is_admin(user.id):
            await query.edit_message_text('⛔ فقط ادمین‌ها دسترسی دارند.')
            return
        kb = [
            [InlineKeyboardButton('📊 آمار کلی', callback_data='admin_stats')],
            [InlineKeyboardButton('📢 ارسال همگانی', callback_data='admin_broadcast')],
            [InlineKeyboardButton('👥 لیست کاربران', callback_data='admin_users')],
            [InlineKeyboardButton('⛔ مسدود کردن', callback_data='admin_ban')],
            [InlineKeyboardButton('✅ رفع مسدودیت', callback_data='admin_unban')],
            [InlineKeyboardButton('📌 تنظیم کانال', callback_data='admin_set_channel')],
            [InlineKeyboardButton('🔙 بازگشت به منو', callback_data='cmd_back')],
        ]
        await query.edit_message_text('👑 **پنل مدیریت**', reply_markup=InlineKeyboardMarkup(kb),
                                      parse_mode='Markdown')


# ========== Voice/Audio Auto-Recognize Handler ==========
async def audio_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-recognize when a user sends a voice/audio file while in recognize state."""
    if not update.message:
        return
    user = update.effective_user
    if db.is_banned(user.id):
        return

    state = context.user_data.get('state')
    if state not in ('recognize', 'recognize_wait'):
        return

    file, file_name = _extract_audio_file_from_message(update.message)
    if not file:
        return

    context.user_data['state'] = None
    db.update_activity(user.id)
    await update.message.reply_text('🔍 در حال تشخیص موسیقی با Shazam...')

    file_path = None
    try:
        file_obj = await file.get_file()
        file_path = Path(DOWNLOAD_DIR) / f'temp_{user.id}_{file_name}'
        await file_obj.download_to_drive(file_path)

        result = await recognizer.recognize_file(str(file_path))
        if result and 'error' not in result:
            db.increment_recognize(user.id)
            await update.message.reply_text(recognizer.format_result(result))
            kb = InlineKeyboardMarkup([[InlineKeyboardButton('⬇️ دانلود این آهنگ', callback_data='dl_recognize')]])
            await update.message.reply_text('🎵 می‌خوای دانلودش کنم؟', reply_markup=kb)
        else:
            err = (result or {}).get('error', 'نتیجه‌ای پیدا نشد')
            await update.message.reply_text(f'❌ تشخیص ناموفق: {err}')
    except Exception as e:
        logger.error(f'Recognize error: {e}')
        await update.message.reply_text(f'❌ خطا در تشخیص: {e}')
    finally:
        if file_path:
            cleanup_file(file_path)


# ========== Search Callback ==========
async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if not data.startswith('search_'):
        return

    try:
        idx = int(data.replace('search_', ''))
    except ValueError:
        await query.answer('❌ خطا در انتخاب', show_alert=True)
        return

    results: List[Dict[str, Any]] = context.user_data.get('search_results', [])
    if not results or not (0 <= idx < len(results)):
        await query.answer('❌ نتیجه پیدا نشد', show_alert=True)
        return

    track = results[idx]
    title = track.get('title', 'نامشخص')
    artist = track.get('artist', {}).get('name', '') if isinstance(track.get('artist'), dict) else str(track.get('artist', ''))
    await query.edit_message_text(f'🎵 {title}\n👤 {artist}\n\n⬇️ در حال دانلود...')

    search_query = f'{title} {artist} audio'.strip()
    downloader = Downloader(output_dir=DOWNLOAD_DIR)
    try:
        dl_result = await downloader.download(search_query, extract_audio=True, playlist=False, is_search=True)
    except Exception as e:
        logger.error(f'Search download error: {e}')
        dl_result = None

    if dl_result and isinstance(dl_result, list) and dl_result:
        fpath = Path(dl_result[0]['filename'])
        if await _send_audio_file(query.message, fpath, title=title, performer=artist):
            await query.edit_message_text(f'✅ {title} - {artist}')
            return
        await query.edit_message_text('❌ خطا در ارسال فایل.')
    else:
        url = track.get('url', '')
        if url:
            await query.edit_message_text(
                f'❌ دانلود مستقیم ناموفق بود.\n\n🔗 لینک دستی:\n{url}\n\n💡 لینک رو کپی کن و در مرورگر باز کن.'
            )
        else:
            await query.edit_message_text('❌ دانلود ناموفق بود.')


# ========== Recognition Download Callback ==========
async def recognition_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download a track that was recognized via Shazam."""
    query = update.callback_query
    await query.answer()

    msg = query.message.text or ''
    title_line = msg.split('\n')[0] if msg else ''
    title = title_line.replace('🎵', '').replace('🎶', '').strip().split(' - ')[0] or 'unknown'

    await query.edit_message_text(f'🔍 در حال دانلود «{title}»...')

    try:
        results = await recognizer.search_track(title, limit=1)
        if not results:
            await query.edit_message_text(
                f'❌ دانلود ناموفق بود.\n\n🔗 لینک دستی:\n'
                f'https://www.youtube.com/results?search_query={title.replace(" ", "+")}\n\n'
                '💡 لینک رو کپی کن و در مرورگر باز کن.'
            )
            return

        track = results[0]
        search_title = track.get('title', title)
        artist = track.get('artist', {}).get('name', '') if isinstance(track.get('artist'), dict) else str(track.get('artist', ''))
        search_query = f'{search_title} {artist} audio'.strip()

        downloader = Downloader(output_dir=DOWNLOAD_DIR)
        try:
            dl_result = await downloader.download(search_query, extract_audio=True, playlist=False, is_search=True)
        except Exception as e:
            logger.error(f'Recognition download error: {e}')
            dl_result = None

        if dl_result and isinstance(dl_result, list) and dl_result:
            fpath = Path(dl_result[0]['filename'])
            if await _send_audio_file(query.message, fpath, title=search_title, performer=artist):
                await query.edit_message_text(f'✅ {search_title} - {artist}')
                return

        await query.edit_message_text(
            f'❌ دانلود ناموفق بود.\n\n🔗 لینک دستی:\n'
            f'https://www.youtube.com/results?search_query={title.replace(" ", "+")}\n\n'
            '💡 لینک رو کپی کن و در مرورگر باز کن.'
        )
    except Exception as e:
        logger.error(f'Recognition download callback error: {e}')
        await query.edit_message_text('❌ خطا در دانلود.')


# ========== Admin Panel ==========
@admin_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton('📊 آمار کلی', callback_data='admin_stats')],
        [InlineKeyboardButton('📢 ارسال همگانی', callback_data='admin_broadcast')],
        [InlineKeyboardButton('👥 لیست کاربران', callback_data='admin_users')],
        [InlineKeyboardButton('⛔ مسدود کردن', callback_data='admin_ban')],
        [InlineKeyboardButton('✅ رفع مسدودیت', callback_data='admin_unban')],
        [InlineKeyboardButton('📌 تنظیم کانال', callback_data='admin_set_channel')],
        [InlineKeyboardButton('🔙 بستن', callback_data='admin_close')],
    ]
    await update.message.reply_text('👑 **پنل مدیریت**', reply_markup=InlineKeyboardMarkup(keyboard),
                                    parse_mode='Markdown')


@admin_only
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'admin_stats':
        stats = db.get_stats()
        msg = (
            f"📊 **آمار کلی ربات**\n"
            f"👥 کاربران: {stats['total']}\n"
            f"⛔ مسدود: {stats['banned']}\n"
            f"📥 دانلودها: {stats['downloads']}\n"
            f"🎵 تشخیص‌ها: {stats['recognizes']}"
        )
        await query.edit_message_text(msg, parse_mode='Markdown')
    elif data == 'admin_broadcast':
        await query.edit_message_text('📢 لطفاً پیام همگانی خود را ارسال کنید.\n(برای لغو /cancel)')
        context.user_data['broadcast_mode'] = True
    elif data == 'admin_users':
        users = db.get_all_users()
        if not users:
            await query.edit_message_text('❌ هیچ کاربری پیدا نشد.')
            return
        lines = []
        for u in users[:10]:
            name = u.get('first_name', 'نامشخص')
            uname = u.get('username', '')
            status = '⛔' if u.get('is_banned') else '✅'
            lines.append(f"{status} {name} (@{uname}) - ID: {u['user_id']}")
        msg = '👥 **کاربران (۱۰ نفر اول)**\n' + '\n'.join(lines)
        await query.edit_message_text(msg, parse_mode='Markdown')
    elif data == 'admin_ban':
        await query.edit_message_text('⛔ شناسه کاربری که می‌خواهید مسدود کنید را وارد کنید.\nمثال: 123456789')
        context.user_data['await_ban'] = True
    elif data == 'admin_unban':
        await query.edit_message_text('✅ شناسه کاربری که می‌خواهید رفع مسدودیت کنید را وارد کنید.\nمثال: 123456789')
        context.user_data['await_unban'] = True
    elif data == 'admin_set_channel':
        await query.edit_message_text('📌 کانال مورد نظر را وارد کنید (با @).\nمثال: @my_channel')
        context.user_data['await_channel'] = True
    elif data == 'admin_close':
        await query.edit_message_text('🔙 پنل بسته شد.')


async def _handle_admin_text_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle admin text-input states (broadcast, ban, unban, channel). Returns True if handled."""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if context.user_data.get('broadcast_mode'):
        context.user_data['broadcast_mode'] = False
        await _broadcast_message(update, context, text)
        return True
    if context.user_data.get('await_ban'):
        context.user_data['await_ban'] = False
        await _ban_by_text(update, text)
        return True
    if context.user_data.get('await_unban'):
        context.user_data['await_unban'] = False
        await _unban_by_text(update, text)
        return True
    if context.user_data.get('await_channel'):
        context.user_data['await_channel'] = False
        await _set_channel_by_text(update, context, text)
        return True
    return False


async def _broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    users = db.get_all_users()
    sent, failed = 0, 0
    status = await update.message.reply_text(f'📢 در حال ارسال به {len(users)} کاربر...')
    for u in users:
        if u.get('is_banned'):
            continue
        try:
            await context.bot.send_message(u['user_id'], text)
            sent += 1
        except Exception:
            failed += 1
    await status.edit_text(f'✅ ارسال شد به {sent} کاربر.\n❌ ناموفق: {failed}')


async def _ban_by_text(update: Update, text: str):
    try:
        uid = int(text.split()[0])
        db.ban_user(uid)
        await update.message.reply_text(f'✅ کاربر {uid} مسدود شد.')
    except (ValueError, IndexError):
        await update.message.reply_text('❗ شناسه نامعتبر.')


async def _unban_by_text(update: Update, text: str):
    try:
        uid = int(text.split()[0])
        db.unban_user(uid)
        await update.message.reply_text(f'✅ کاربر {uid} رفع مسدودیت شد.')
    except (ValueError, IndexError):
        await update.message.reply_text('❗ شناسه نامعتبر.')


async def _set_channel_by_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    channel = text.split()[0]
    if not channel.startswith('@'):
        channel = '@' + channel
    db.set_setting('channel', channel)
    await update.message.reply_text(f'✅ کانال به {channel} تنظیم شد.')


async def unified_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified handler: admin text states, slash commands, and the state machine for music search."""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text.strip()

    # Admin text-input states (broadcast, ban, etc.) — only for admins
    if is_admin(user.id) and await _handle_admin_text_state(update, context):
        return

    # Slash commands
    if text.startswith('/'):
        if text == '/start':
            await start(update, context)
            return
        if text == '/cancel':
            context.user_data.clear()
            await update.message.reply_text(
                '❌ لغو شد.', reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton('🔙 منوی اصلی', callback_data='cmd_back')]]
                )
            )
            return
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
            await _ban_by_text(update, text.replace('/ban', '', 1).strip())
            return
        if text.startswith('/unban') and is_admin(user.id):
            await _unban_by_text(update, text.replace('/unban', '', 1).strip())
            return
        if text.startswith('/set_channel') and is_admin(user.id):
            await _set_channel_by_text(update, context, text.replace('/set_channel', '', 1).strip())
            return
        return

    if db.is_banned(user.id):
        return

    # State machine: commandless interactions
    state = context.user_data.get('state')

    if state == 'download':
        if is_url(text):
            context.args = [text]
            context.user_data['state'] = None
            await download_command(update, context)
        else:
            context.user_data['state'] = None
            await update.message.reply_text('🔍 به نظر لینک نیست! دارم جستجو می‌کنم...')
            await search_music_inline(update, context)
        return
    if state == 'lyrics':
        context.args = text.split()
        context.user_data['state'] = None
        await lyrics_command(update, context)
        return
    if state == 'convert':
        if is_url(text):
            context.args = [text]
            context.user_data['state'] = None
            await convert_command(update, context)
        else:
            context.user_data['state'] = None
            await update.message.reply_text('🎬 لطفاً یک لینک ویدئو بفرستی.')
        return
    if state == 'info':
        if is_url(text):
            context.args = [text]
            context.user_data['state'] = None
            await info_command(update, context)
        else:
            context.user_data['state'] = None
            await update.message.reply_text('ℹ️ لطفاً یک لینک بفرستی.')
        return
    if state in ('recognize', 'recognize_wait'):
        await update.message.reply_text(
            '🎵 حالا ویس یا فایل صوتی بفرست! (بدون نیاز به دستور)',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 منوی اصلی', callback_data='cmd_back')]]),
        )
        context.user_data['state'] = 'recognize_wait'
        return

    # Any other text → music search
    await search_music_inline(update, context)


async def search_music_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for tracks when the user types a song name in chat."""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if len(text) < 2:
        return

    await update.message.reply_text(f'🔍 در حال جستجوی «{text}»...')

    try:
        results = await recognizer.search_track(text, limit=MAX_SEARCH_RESULTS)
    except Exception as e:
        logger.error(f'Search error: {e}')
        results = []

    if not results:
        await update.message.reply_text('❌ آهنگی پیدا نشد.')
        return

    buttons = []
    for i, track in enumerate(results):
        title = track.get('title', 'نامشخص')
        artist = track.get('artist', {}).get('name', '') if isinstance(track.get('artist'), dict) else str(track.get('artist', ''))
        buttons.append([InlineKeyboardButton(f'🎵 {title} - {artist}', callback_data=f'search_{i}')])

    context.user_data['search_results'] = results
    await update.message.reply_text(f'🎵 نتایج جستجوی «{text}»:', reply_markup=InlineKeyboardMarkup(buttons))


# ========== Main ==========
def main():
    if not BOT_TOKEN:
        logger.error('BOT_TOKEN not set in environment.')
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('download', download_command))
    app.add_handler(CommandHandler('recognize', recognize_command))
    app.add_handler(CommandHandler('info', info_command))
    app.add_handler(CommandHandler('stats', stats_command))
    app.add_handler(CommandHandler('admin', admin_panel))
    app.add_handler(CommandHandler('set_quality', set_quality_command))
    app.add_handler(CommandHandler('set_lang', set_lang_command))
    app.add_handler(CommandHandler('playlist', playlist_command))
    app.add_handler(CommandHandler('tag', tag_command))
    app.add_handler(CommandHandler('convert', convert_command))
    app.add_handler(CommandHandler('lyrics', lyrics_command))

    app.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    app.add_handler(CallbackQueryHandler(search_callback, pattern='^search_'))
    app.add_handler(CallbackQueryHandler(recognition_download_callback, pattern='^dl_recognize$'))
    app.add_handler(CallbackQueryHandler(command_callback, pattern='^cmd_'))

    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.Document.AUDIO,
                                   audio_message_handler), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unified_text_handler), group=1)

    logger.info('Bot started...')
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
