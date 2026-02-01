# 🚀 Ultimate Media Downloader

**Lightweight, fast, and powerful Telegram bot for downloading media from YouTube, TikTok, and Instagram.**
Built with Python 3.12, Pyrogram, and yt-dlp.

## 🔥 Features

- **Any Link**: Supports YouTube (Video/Shorts/Live), TikTok (No Watermark), Instagram (Reels/Posts).
- **High Quality**: Auto-selects up to 1440p 60fps for video.
- **Crystal Clear Audio**: Converts extracted audio to **Opus** (OGG) for best quality/size ratio.
- **Smart TikTok**: Auto-detects TikTok links and downloads instantly (skipping menus).
- **Inline Mode**: Share videos directly in any chat (via direct stream URL).
- **Big Files**: Supports uploading files up to 2GB (4GB with local API).
- **Multi-language**: Auto-detects user language (EN, RU, UK, KK, etc.).

## 🛠 Installation

### 1. Clone & Setup
```bash
git clone https://github.com/caruno-git/downloader-bot.git
cd downloader-bot
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration (`.env`)
Create a `.env` file in the root directory:
```ini
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
API_ID=12345
API_HASH=0123456789abcdef0123456789abcdef
OWNER_ID=123456789
```

### 3. Cookies (Optional but Recommended)
To prevent "Sign in required" errors from YouTube/Instagram, place your `cookies.txt` file in the root directory.

### 4. Run
```bash
python main.py
```

## 🚀 Deployment (Systemd)

1. Create service file:
```bash
nano /etc/systemd/system/downloader_bot.service
```

2. Paste configuration (adjust paths):
```ini
[Unit]
Description=Downloader Bot
After=network.target

[Service]
User=root
WorkingDirectory=/root/downloader-bot
ExecStart=/root/downloader-bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Enable and start:
```bash
systemctl daemon-reload
systemctl enable downloader_bot
systemctl start downloader_bot
```

---
*Created by [Caruno](https://github.com/caruno-git)*
