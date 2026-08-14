# 🎵 What's Music Bot

دانلود و تشخیص خودکار موزیک از **تیک‌تاک، یوتوب، اینستاگرام و ساندکلود** با پایتون.

## ✨ قابلیت‌ها

- ⬇️ دانلود صدا/ویدئو با **yt-dlp**
- 🎵 تشخیص موزیک با **Shazamio** (رایگان)
- 🔗 پشتیبانی از لینک‌های تیک‌تاک، یوتوب، اینستاگرام، ساندکلود و هر سایت پشتیبانی‌شده توسط yt-dlp
- 🎧 استخراج خودکار صدا و تبدیل به MP3
- 📁 ذخیره‌سازی با نام تمیز و مدیریت تکراری‌ها
- ▶️ پخش خودکار فایل (اختیاری)
- 🍪 پشتیبانی از کوکی برای سایت‌های نیازمند ورود

## 📦 پیش‌نیازها

- Python 3.8+
- **yt-dlp** (نصب خودکار با requirements)
- **ffmpeg** (برای تبدیل صدا) — روی سیستم نصب باشد

نصب ffmpeg:
- Windows: دانلود از ffmpeg.org و اضافه به PATH
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

## 🚀 نصب و اجرا

```bash
# کلون یا دانلود پروژه
cd whatsmusic-bot

# نصب وابستگی‌ها
pip install -r requirements.txt

# اجرا
python main.py -u "لینک" -r
```

## 📖 راهنما

### دانلود صدا و تشخیص موزیک

```bash
python main.py -u "https://www.tiktok.com/@user/video/123456" -r
```

### دانلود ویدئو (بدون استخراج صدا)

```bash
python main.py -u "https://www.youtube.com/watch?v=abc" -v
```

### تشخیص موزیک از فایل محلی

```bash
python main.py -f song.mp3 -r
```

### دانلود و پخش خودکار

```bash
python main.py -u "لینک" -p
```

### استفاده از کوکی (برای سایت‌های نیازمند احراز)

```bash
python main.py -u "لینک" --cookies cookies.txt
```

### تنظیم پوشه خروجی

```bash
python main.py -u "لینک" -o ./my_music
```

## 📂 ساختار پروژه

```
whatsmusic-bot/
├── main.py           # ورودی خط فرمان
├── downloader.py     # دانلود با yt-dlp
├── recognizer.py     # تشخیص با shazamio
├── utils.py          # توابع کمکی
├── requirements.txt
└── README.md
```

## 🧠 نحوه کار

1. لینک را دریافت می‌کند
2. با yt-dlp فایل را دانلود می‌کند
3. در صورت درخواست، صدا را استخراج و به MP3 تبدیل می‌کند
4. با Shazamio تشخیص موزیک را انجام می‌دهد
5. نتیجه را نمایش می‌دهد

## 🔧 توسعه

برای اضافه کردن سرویس جدید، کافی است yt-dlp از آن پشتیبانی کند.

## 📄 لایسنس

MIT