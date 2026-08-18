# 🎵 What's Music Bot

ربات تلگرام برای دانلود و تشخیص موزیک از تیک‌تاک، یوتوب، اینستاگرام و ساندکلود با **yt-dlp** و **Shazamio** 🚀

## ✨ قابلیت‌ها

- ⬇️ دانلود از **TikTok, YouTube, Instagram, SoundCloud**
- 🔍 **جستجوی آهنگ** با نام خواننده/اثر (تایپ کنید در چت)
- 📝 **دریافت متن ترانه** با دستور `/lyrics`
- 🎵 تشخیص خودکار موزیک با **Shazam** (رایگان)
- 🤖 ربات تلگرام با **پنل ادمینی کامل**
- 🔒 **جوین اجباری** کانال (قابل تنظیم)
- 👑 **پنل ادمین** با دستورات: آمار، ارسال همگانی، لیست کاربران، مسدود/رفع مسدودیت، تنظیم کانال
- 📊 آمار کاربران و استفاده
- 🎬 **تبدیل ویدیو به صدا** با ffmpeg
- 🏷️ **برچسب‌ها و فیلترها** برای دسته‌بندی آهنگ‌ها
- 📂 **پلی‌لیست‌های شخصی** (ایجاد، حذف، افزودن آهنگ، نمایش)
- 🎛 **کیفیت انتخابی** (128/192/320 kbps)
- 🌐 **تغییر زبان** (فارسی/انگلیسی)
- 🧩 **ساختار پلاگین** (قابل گسترش)
- 📊 **داشبورد گرافیکی** با نمودارهای آماری
- 🐳 **داکر** (راه‌اندازی یک‌دقیقه‌ای)

## 📦 نصب و راه‌اندازی

### روش معمولی (بدون داکر)

```bash
# کلون پروژه
git clone https://github.com/AnishtayiN/whatsmusic-bot.git
cd whatsmusic-bot

# نصب وابستگی‌ها
pip install -r requirements.txt

# نصب ffmpeg (برای تبدیل ویدیو به صدا)
# Ubuntu/Debian: sudo apt install ffmpeg
# Mac: brew install ffmpeg
# Windows: دانلود از ffmpeg.org

# تنظیم متغیرهای محیطی
cp .env.example .env
# ویرایش .env با توکن ربات و تنظیمات دلخواه

# اجرای ربات
python bot.py
```

### روش داکر

```bash
# با docker-compose
docker-compose up -d

# یا با docker build
docker build -t whatsmusic-bot .
docker run -d --name whatsmusic-bot --env-file .env -v ./data:/app/data -v ./downloads:/app/downloads whatsmusic-bot
```

## 🔧 تنظیمات (.env)

| متغیر | توضیح |
|-------|--------|
| `BOT_TOKEN` | توکن ربات تلگرام (از @BotFather) |
| `ADMIN_IDS` | شناسه‌های ادمین (با کاما جدا شده) |
| `CHANNEL_USERNAME` | کانال اجباری (مثلاً @my_channel) |
| `DB_PATH` | مسیر دیتابیس SQLite |
| `DOWNLOAD_DIR` | پوشه ذخیره دانلودها |
| `COOKIES_FILE` | فایل کوکی (اختیاری) |

## 🤖 دستورات ربات

### کاربران:
- `/start` - شروع و راهنما
- `/help` - راهنما
- `/download <لینک>` - دانلود صدا
- `<نام آهنگ>` (تایپ در چت) - جستجو و دانلود
- `/lyrics <خواننده> <آهنگ>` - دریافت متن ترانه
- `/convert <لینک>` - تبدیل ویدیو به صدا
- `/recognize` (پاسخ به فایل صوتی) - تشخیص موزیک
- `/info <لینک>` - نمایش اطلاعات
- `/stats` - آمار استفاده شما
- `/set_quality 128|192|320` - تنظیم کیفیت
- `/set_lang fa|en` - تغییر زبان
- `/playlist` - مدیریت پلی‌لیست
- `/tag` - مدیریت برچسب‌ها

### ادمین‌ها:
- `/admin` - پنل مدیریت (دکمه‌ای)
- `/ban <user_id>` - مسدود کردن کاربر
- `/unban <user_id>` - رفع مسدودیت
- `/set_channel <@channel>` - تنظیم کانال اجباری

## 📁 ساختار پروژه

```
whatsmusic-bot/
├── bot.py              # ربات تلگرام + جوین اجباری + پنل ادمین
├── config.py           # بارگذاری متمرکز تنظیمات از .env
├── db.py               # لایه دیتابیس SQLite (WAL، کاربران، تنظیمات)
├── downloader.py       # دانلود با yt-dlp + سیستم retry هوشمند
├── recognizer.py       # تشخیص با shazamio + جستجو + متن ترانه
├── converter.py        # تبدیل ویدئو به صدا با ffmpeg + پاکسازی
├── playlist_manager.py # مدیریت پلی‌لیست‌ها (نوشتن اتمیک)
├── quality_manager.py  # مدیریت کیفیت
├── tag_manager.py      # مدیریت برچسب‌ها (SQLite + WAL)
├── plugin_manager.py   # سیستم پلاگین
├── locales.py          # ترجمه‌ها
├── extra_commands.py   # دستورات اضافی (کیفیت، زبان، پلی‌لیست، تگ، تبدیل)
├── dashboard.py        # داشبورد گرافیکی با Flask
├── main.py             # ورودی خط فرمان (CLI)
├── utils.py            # توابع کمکی (نام‌فایل، URL، پاکسازی)
├── tests/              # تست‌های واحد (unittest)
├── plugins/            # پلاگین‌های اختیاری
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 🧠 نحوه کار

ربات با استفاده از `python-telegram-bot` کار می‌کند و:
1. عضویت کاربر در کانال اجباری را چک می‌کند.
2. درخواست دانلود، تبدیل یا تشخیص را پردازش می‌کند.
3. از `yt-dlp` برای دانلود، `shazamio` برای تشخیص و `ffmpeg` برای تبدیل استفاده می‌کند.
4. آمار کاربران، پلی‌لیست‌ها و برچسب‌ها را در SQLite ذخیره می‌کند.

## 📄 لایسنس

MIT