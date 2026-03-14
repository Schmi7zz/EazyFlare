<div align="center">
  <img src="web/logo.png" alt="EazyFlare" width="120">
  <h1>EazyFlare</h1>
  <p><b>Manage Cloudflare DNS records from Telegram</b></p>
  <p>
    <a href="https://t.me/SchmitzWS"><img src="https://img.shields.io/badge/Telegram-Channel-blue?logo=telegram" alt="Telegram"></a>
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  </p>
  <p><a href="#english">English</a> · <a href="#فارسی">فارسی</a></p>
</div>

---

## English

### What is EazyFlare?

EazyFlare lets you manage your Cloudflare DNS records directly from Telegram — through both a **chat bot** and a **Mini App dashboard**.

### Features

- 🔐 Login with **API Token** or **Global API Key + Email**
- 🌐 List all domains with status and plan info
- 📋 View, add, edit, and delete DNS records (A, AAAA, CNAME, MX, TXT, NS, SRV, CAA)
- ☁️ Toggle Cloudflare proxy on/off
- 🔍 Filter records by type
- 📊 Full **Mini App dashboard** with Cloudflare-like UI
- 🌍 **Bilingual** — English and Persian (Farsi)
- 🔒 Sensitive messages (tokens) are auto-deleted
- 🛡️ Forces IPv4 to avoid token IP restrictions

### Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────────────┐
│  Telegram    │────▶│  Bot (Python)│────▶│  Cloudflare API    │
│  User        │     │  on server   │     │  (direct, IPv4)    │
└─────────────┘     └──────────────┘     └────────────────────┘
       │
       │ Mini App
       ▼
┌─────────────┐     ┌──────────────┐     ┌────────────────────┐
│  Web App    │────▶│  CF Worker   │────▶│  Cloudflare API    │
│  (browser)  │     │  (CORS proxy)│     │                    │
└─────────────┘     └──────────────┘     └────────────────────┘
```

### Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/SchmitzWS/eazyflare/main/install.sh | bash
```

### Manual Setup

#### Prerequisites
- A VPS with Ubuntu 20.04+
- A domain name pointed to your server
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Cloudflare account

#### Step 1: Deploy the CORS Proxy Worker

1. Go to `dash.cloudflare.com` → **Workers & Pages** → **Create** → **Create Worker**
2. Name it (e.g., `cf-api-proxy`) → Click **Deploy**
3. Click **Edit Code**
4. Delete everything → Paste contents of `worker.js` → **Deploy**
5. Copy your Worker URL (e.g., `https://cf-api-proxy.xxx.workers.dev`)

#### Step 2: Configure & Host the Web App

1. Edit `web/index.html` — set the `PROXY` variable to your Worker URL:
   ```javascript
   var PROXY = "https://cf-api-proxy.xxx.workers.dev";
   ```
2. Copy the `web/` folder to your web server (e.g., `/var/www/html/`)
3. Set up Nginx and SSL (or use Cloudflare Pages)

#### Step 3: Run the Bot

```bash
pip install -r requirements.txt
export BOT_TOKEN="your-telegram-bot-token"
export WEBAPP_URL="https://eazyflare.yourdomain.com"
python3 bot.py
```

#### Step 4: Run as a Service

```bash
# Create service
cat > /etc/systemd/system/eazyflare.service << 'EOF'
[Unit]
Description=EazyFlare Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/eazyflare
EnvironmentFile=/opt/eazyflare/.env
ExecStart=/usr/bin/python3 /opt/eazyflare/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable eazyflare
systemctl start eazyflare
```

### Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome menu |
| `/connect` | Connect Cloudflare account |
| `/domains` | List your domains |
| `/dns` | Manage DNS records |
| `/disconnect` | Disconnect account |
| `/help` | Help & guide |

### Getting a Cloudflare API Token

1. Go to `dash.cloudflare.com`
2. **My Profile** → **API Tokens** → **Create Token**
3. Use template **"Edit zone DNS"**
4. Set Zone DNS = **Edit**, All Zones
5. **Leave IP Address Filtering empty**
6. Create Token → Copy it

> ⚠️ **Important:** Leave the IP Filtering section empty, otherwise the token may not work from your server.

---

## فارسی

### EazyFlare چیست؟

EazyFlare ابزاری برای مدیریت رکوردهای DNS کلادفلر مستقیماً از تلگرام — هم از طریق **ربات چت** و هم **مینی‌اپ داشبورد**.

### امکانات

- 🔐 ورود با **API Token** یا **Global API Key + ایمیل**
- 🌐 لیست تمام دامنه‌ها با وضعیت و پلن
- 📋 مشاهده، افزودن، ویرایش و حذف رکوردهای DNS
- ☁️ فعال/غیرفعال کردن پروکسی Cloudflare
- 🔍 فیلتر رکوردها بر اساس نوع
- 📊 **داشبورد مینی‌اپ** با طراحی شبیه Cloudflare
- 🌍 **دوزبانه** — انگلیسی و فارسی
- 🔒 پیام‌های حاوی توکن خودکار حذف می‌شوند
- 🛡️ اجبار IPv4 برای جلوگیری از مشکل IP

### نصب سریع

```bash
curl -fsSL https://raw.githubusercontent.com/SchmitzWS/eazyflare/main/install.sh | bash
```

### نصب دستی

#### پیش‌نیازها
- سرور مجازی با Ubuntu 20.04+
- دامنه متصل به سرور
- توکن ربات تلگرام (از [@BotFather](https://t.me/BotFather))
- حساب Cloudflare

#### مرحله ۱: دیپلوی Worker پروکسی

1. وارد `dash.cloudflare.com` → **Workers & Pages** → **Create** → **Create Worker**
2. نام بگذارید → **Deploy**
3. **Edit Code** → همه رو پاک کنید → `worker.js` رو Paste → **Deploy**
4. آدرس Worker رو کپی کنید

#### مرحله ۲: تنظیم و آپلود وب‌اپ

1. در `web/index.html` متغیر `PROXY` رو تنظیم کنید:
   ```javascript
   var PROXY = "https://cf-api-proxy.xxx.workers.dev";
   ```
2. فولدر `web/` رو روی سرور وب کپی کنید
3. Nginx و SSL تنظیم کنید

#### مرحله ۳: اجرای ربات

```bash
pip install -r requirements.txt
export BOT_TOKEN="توکن-ربات-تلگرام"
export WEBAPP_URL="https://eazyflare.yourdomain.com"
python3 bot.py
```

### دستورات ربات

| دستور | توضیح |
|--------|--------|
| `/start` | منوی اصلی |
| `/connect` | اتصال به Cloudflare |
| `/domains` | لیست دامنه‌ها |
| `/dns` | مدیریت DNS |
| `/disconnect` | قطع اتصال |
| `/help` | راهنما |

### ساخت API Token کلادفلر

1. وارد `dash.cloudflare.com` شوید
2. **My Profile** → **API Tokens** → **Create Token**
3. قالب **"Edit zone DNS"** را انتخاب کنید
4. دسترسی Zone DNS = **Edit**، All Zones
5. **بخش IP Address Filtering را خالی بگذارید**
6. Token را کپی کنید

> ⚠️ **مهم:** بخش IP Filtering را خالی بگذارید، در غیر این صورت توکن از سرور کار نمی‌کند.

---

<div align="center">
  <p>Made with ♡ by <a href="https://t.me/SchmitzWS">Schmitz</a></p>
</div>
