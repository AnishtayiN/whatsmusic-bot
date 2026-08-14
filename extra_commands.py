from telegram import Update
from telegram.ext import ContextTypes
from locales import get_text
from playlist_manager import PlaylistManager
from quality_manager import QualityManager

playlist_mgr = PlaylistManager()
quality_mgr = QualityManager()

async def set_quality_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❗ کیفیت را وارد کنید: 128, 192, 320")
        return
    try:
        quality = int(context.args[0])
        if quality not in [128, 192, 320]:
            raise ValueError
        quality_mgr.set_quality(user_id, quality)
        await update.message.reply_text(get_text('quality_set', 'fa', quality=quality))
    except:
        await update.message.reply_text(get_text('invalid_quality', 'fa'))

async def set_lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ زبان را وارد کنید: fa یا en")
        return
    lang = context.args[0].lower()
    if lang not in ['fa', 'en']:
        await update.message.reply_text(get_text('invalid_lang', 'fa'))
        return
    # ذخیره در دیتابیس (فعلاً فرض می‌کنیم)
    await update.message.reply_text(get_text('lang_set', 'fa', lang=lang))

async def playlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "📂 مدیریت پلی‌لیست:\n"
            "/playlist create <نام> - ایجاد پلی‌لیست جدید\n"
            "/playlist delete <نام> - حذف پلی‌لیست\n"
            "/playlist add <نام> - افزودن آهنگ فعلی به پلی‌لیست (بعد از دانلود)\n"
            "/playlist remove <نام> <شماره> - حذف آهنگ از پلی‌لیست\n"
            "/playlist list - نمایش پلی‌لیست‌ها\n"
            "/playlist show <نام> - نمایش آهنگ‌های پلی‌لیست"
        )
        return

    action = context.args[0].lower()
    if action == "create":
        if len(context.args) < 2:
            await update.message.reply_text("❗ نام پلی‌لیست را وارد کنید.")
            return
        name = " ".join(context.args[1:])
        if playlist_mgr.create_playlist(user_id, name):
            await update.message.reply_text(get_text('playlist_created', 'fa', name=name))
        else:
            await update.message.reply_text("❌ پلی‌لیست قبلاً وجود دارد یا خطا.")

    elif action == "delete":
        if len(context.args) < 2:
            await update.message.reply_text("❗ نام پلی‌لیست را وارد کنید.")
            return
        name = " ".join(context.args[1:])
        if playlist_mgr.delete_playlist(user_id, name):
            await update.message.reply_text(get_text('playlist_deleted', 'fa'))
        else:
            await update.message.reply_text("❌ پلی‌لیست یافت نشد.")

    elif action == "list":
        playlists = playlist_mgr.list_playlists(user_id)
        if not playlists:
            await update.message.reply_text(get_text('no_playlist', 'fa'))
        else:
            await update.message.reply_text(get_text('playlist_list', 'fa', playlists="\n".join(playlists)))

    elif action == "show":
        if len(context.args) < 2:
            await update.message.reply_text("❗ نام پلی‌لیست را وارد کنید.")
            return
        name = " ".join(context.args[1:])
        songs = playlist_mgr.get_songs(user_id, name)
        if not songs:
            await update.message.reply_text(get_text('no_songs', 'fa'))
        else:
            lines = [f"{i+1}. {s.get('title', 'بدون نام')}" for i, s in enumerate(songs)]
            await update.message.reply_text(get_text('playlist_songs', 'fa', name=name, songs="\n".join(lines)))

    else:
        await update.message.reply_text("❌ دستور نامعتبر.")