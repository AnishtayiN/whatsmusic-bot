"""extra_commands.py - Quality, language, playlist, tag and convert commands."""
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from config import DB_PATH, DOWNLOAD_DIR, COOKIES_FILE, DEFAULT_LANG, DEFAULT_QUALITY
from db import DB
from locales import get_text
from playlist_manager import PlaylistManager
from quality_manager import QualityManager
from tag_manager import TagManager
from converter import AudioConverter
from utils import is_url

# Shared singletons (imported lazily to avoid import cycles at module load)
db = DB(DB_PATH)
playlist_mgr = PlaylistManager()
quality_mgr = QualityManager()
tag_mgr = TagManager()
converter = AudioConverter(output_dir=DOWNLOAD_DIR)


async def set_quality_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text('❗ کیفیت را وارد کنید: 128, 192, 320')
        return
    try:
        quality = int(context.args[0])
        if quality not in (128, 192, 320):
            raise ValueError
        quality_mgr.set_quality(user_id, quality)
        await update.message.reply_text(get_text('quality_set', 'fa', quality=quality))
    except (ValueError, IndexError):
        await update.message.reply_text(get_text('invalid_quality', 'fa'))


async def set_lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text('❗ زبان را وارد کنید: fa یا en')
        return
    lang = context.args[0].lower()
    if lang not in ('fa', 'en'):
        await update.message.reply_text(get_text('invalid_lang', 'fa'))
        return
    # Persist language preference on the user record
    db.set_language(user_id, lang)
    if context.user_data is not None:
        context.user_data['lang'] = lang
    await update.message.reply_text(get_text('lang_set', 'fa', lang=lang))


async def playlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            '📂 مدیریت پلی‌لیست:\n'
            '/playlist create <نام> - ایجاد پلی‌لیست جدید\n'
            '/playlist delete <نام> - حذف پلی‌لیست\n'
            '/playlist list - نمایش پلی‌لیست‌ها\n'
            '/playlist show <نام> - نمایش آهنگ‌ها\n'
            '/playlist add <نام> <عنوان> - افزودن آهنگ'
        )
        return

    action = context.args[0].lower()
    if action == 'create':
        if len(context.args) < 2:
            await update.message.reply_text('❗ نام پلی‌لیست را وارد کنید.')
            return
        name = ' '.join(context.args[1:])
        if playlist_mgr.create_playlist(user_id, name):
            await update.message.reply_text(get_text('playlist_created', 'fa', name=name))
        else:
            await update.message.reply_text('❌ پلی‌لیست قبلاً وجود دارد.')

    elif action == 'delete':
        if len(context.args) < 2:
            await update.message.reply_text('❗ نام پلی‌لیست را وارد کنید.')
            return
        name = ' '.join(context.args[1:])
        if playlist_mgr.delete_playlist(user_id, name):
            await update.message.reply_text(get_text('playlist_deleted', 'fa'))
        else:
            await update.message.reply_text('❌ پلی‌لیست پیدا نشد.')

    elif action == 'add':
        if len(context.args) < 3:
            await update.message.reply_text('❗ نام پلی‌لیست و عنوان آهنگ را وارد کنید.\nمثال: /playlist add mylist Song Title')
            return
        name = context.args[1]
        song_title = ' '.join(context.args[2:])
        if playlist_mgr.add_song(user_id, name, {'title': song_title}):
            await update.message.reply_text(get_text('playlist_added', 'fa'))
        else:
            await update.message.reply_text('❌ پلی‌لیست پیدا نشد.')

    elif action == 'list':
        playlists = playlist_mgr.list_playlists(user_id)
        if not playlists:
            await update.message.reply_text(get_text('no_playlist', 'fa'))
        else:
            await update.message.reply_text(get_text('playlist_list', 'fa', playlists='\n'.join(playlists)))

    elif action == 'show':
        if len(context.args) < 2:
            await update.message.reply_text('❗ نام پلی‌لیست را وارد کنید.')
            return
        name = ' '.join(context.args[1:])
        songs = playlist_mgr.get_songs(user_id, name)
        if not songs:
            await update.message.reply_text(get_text('no_songs', 'fa'))
        else:
            lines = [f"{i + 1}. {s.get('title', 'بدون نام')}" for i, s in enumerate(songs)]
            await update.message.reply_text(get_text('playlist_songs', 'fa', name=name, songs='\n'.join(lines)))

    else:
        await update.message.reply_text('❌ دستور نامعتبر.')


# ========== Tag commands ==========
async def tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            '🏷️ مدیریت برچسب‌ها:\n'
            '/tag add <song_id> <tag> - افزودن برچسب به آهنگ\n'
            '/tag remove <song_id> <tag> - حذف برچسب\n'
            '/tag list - نمایش همه برچسب‌های شما\n'
            '/tag search <tag> - جستجوی آهنگ‌ها با برچسب'
        )
        return

    action = context.args[0].lower()
    if action == 'add':
        if len(context.args) < 3:
            await update.message.reply_text('❗ شناسه آهنگ و برچسب را وارد کنید.')
            return
        song_id = context.args[1]
        tag = ' '.join(context.args[2:])
        tag_mgr.add_tag(user_id, song_id, tag)
        await update.message.reply_text(f"✅ برچسب '{tag}' به آهنگ {song_id} اضافه شد.")

    elif action == 'remove':
        if len(context.args) < 3:
            await update.message.reply_text('❗ شناسه آهنگ و برچسب را وارد کنید.')
            return
        song_id = context.args[1]
        tag = ' '.join(context.args[2:])
        tag_mgr.remove_tag(user_id, song_id, tag)
        await update.message.reply_text(f"✅ برچسب '{tag}' از آهنگ {song_id} حذف شد.")

    elif action == 'list':
        tags = tag_mgr.get_all_tags(user_id)
        if not tags:
            await update.message.reply_text('🏷️ شما هیچ برچسبی ندارید.')
        else:
            await update.message.reply_text('🏷️ برچسب‌های شما:\n' + '\n'.join(tags))

    elif action == 'search':
        if len(context.args) < 2:
            await update.message.reply_text('❗ برچسب را وارد کنید.')
            return
        tag = ' '.join(context.args[1:])
        songs = tag_mgr.get_songs_by_tag(user_id, tag)
        if not songs:
            await update.message.reply_text(f"❌ هیچ آهنگی با برچسب '{tag}' پیدا نشد.")
        else:
            lines = [f"{s['song_id']}: {s.get('title', 'بدون نام')} - {s.get('artist', '')}" for s in songs]
            await update.message.reply_text(f"🎵 آهنگ‌های با برچسب '{tag}':\n" + '\n'.join(lines))

    else:
        await update.message.reply_text('❌ دستور نامعتبر.')


# ========== Video to audio conversion ==========
async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or not is_url(context.args[0]):
        await update.message.reply_text('❗ لطفاً یک لینک ویدئو وارد کنید.\nمثال: /convert https://www.youtube.com/watch?v=abc')
        return

    url = context.args[0]
    await update.message.reply_text('🎬 در حال دانلود و تبدیل ویدئو به صدا...')

    try:
        quality = quality_mgr.get_quality(user_id)
        audio_path = await converter.convert_to_audio(url, quality=quality)
        if audio_path:
            p = Path(audio_path)
            with open(p, 'rb') as f:
                await update.message.reply_document(document=f, filename=p.name)
            await update.message.reply_text('✅ تبدیل ویدئو به صدا کامل شد!')
        else:
            await update.message.reply_text('❌ استخراج صدا با خطا مواجه شد.')
    except Exception as e:
        await update.message.reply_text(f'❌ خطا: {e}')
