<![CDATA[<p align="center">
  <img src="web/logo.png" alt="EazyFlare" width="120">
</p>

# EazyFlare

**Manage your entire Cloudflare from Telegram**

[![Telegram](https://img.shields.io/badge/Telegram-Channel-blue?logo=telegram)](https://t.me/SchmitzWS)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)

[English](#english) · [فارسی](#فارسی)

---

## English

### What is EazyFlare?

EazyFlare lets you manage your Cloudflare account directly from Telegram — through both a **chat bot** and a **Mini App dashboard**.

### Features

| Category | Capabilities |
|----------|-------------|
| 🔐 **Authentication** | API Token or Global API Key + Email |
| 📋 **DNS** | View, add, edit, delete records (A, AAAA, CNAME, MX, TXT, NS, SRV, CAA), toggle proxy, filter by type |
| 🔒 **SSL/TLS** | View and change encryption mode (Off / Flexible / Full / Full Strict) |
| 📛 **Nameservers** | View Cloudflare NS and original registrar NS |
| 🌐 **Zone Settings** | Toggle: Always HTTPS, Auto HTTPS Rewrites, TLS 1.3, HTTP/3, 0-RTT, Brotli, Minify (JS/CSS/HTML), Early Hints, WebSockets, Opportunistic Encryption |
| 🔀 **Page Rules** | List, create, toggle, delete rules (redirects, cache, SSL, always HTTPS) |
| 👷 **Workers** | List scripts & routes, view code, edit & publish, upload new, delete |
| 📧 **Email Routing** | View status, enable/disable, list routing rules |
| 📊 **Mini App** | Full dashboard with all features above, Cloudflare-like UI |
| 🌍 **Bilingual** | English and Persian (Farsi) with instant switching |
| 🛡️ **Security** | Auto-delete token messages, forced IPv4 |

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
curl -fsSL https://raw.githubusercontent.com/Schmi7zz/EazyFlare/main/install.sh | bash
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

1. Edit `webapp.html` — set the `PROXY` variable to your Worker URL:
   ```javascript
   var PROXY = "https://cf-api-proxy.xxx.workers.dev";
   ```
2. Host the file on your web server or Cloudflare Pages
3. Set up SSL (required for Telegram Mini Apps)

#### Step 3: Run the Bot

```bash
pip install -r requirements.txt
export BOT_TOKEN="your-telegram-bot-token"
export WEBAPP_URL="https://eazyflare.yourdomain.com"
python3 bot.py
```

#### Step 4: Run as a Service

```bash
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
3. Select **"Create Custom Token"**
4. Set the following permissions:

   **Zone permissions:**
   | Permission | Access |
   |-----------|--------|
   | Zone | Read |
   | Zone Settings | Edit |
   | DNS | Edit |
   | SSL and Certificates | Edit |
   | Page Rules | Edit |
   | Workers Routes | Edit |
   | Email Routing Rules | Edit |

   **Account permissions:**
   | Permission | Access |
   |-----------|--------|
   | Workers Scripts | Edit |

5. Zone Resources: **Include → All zones**
6. **Leave IP Address Filtering empty**
7. Create Token → Copy it

> ⚠️ **Important:** Leave the IP Filtering section empty, otherwise the token may not work from your server.

---

## فارسی

### EazyFlare چیست؟

EazyFlare ابزاری برای مدیریت کامل حساب کلادفلر مستقیماً از تلگرام — هم از طریق **ربات چت** و هم **مینی‌اپ داشبورد**.

### امکانات

| دسته | قابلیت‌ها |
|------|----------|
| 🔐 **احراز هویت** | ورود با API Token یا Global API Key + ایمیل |
| 📋 **DNS** | مشاهده، افزودن، ویرایش، حذف رکوردها، تغییر پروکسی، فیلتر بر اساس نوع |
| 🔒 **SSL/TLS** | مشاهده و تغییر حالت رمزنگاری (Off / Flexible / Full / Full Strict) |
| 📛 **نیم‌سرورها** | نمایش NS‌های کلادفلر و رجیسترار |
| 🌐 **تنظیمات دامنه** | تغییر: Always HTTPS، TLS 1.3، HTTP/3، Brotli، Minify، Early Hints، WebSockets و ... |
| 🔀 **Page Rules** | لیست، ایجاد، تغییر وضعیت، حذف قوانین (ریدایرکت، کش، SSL) |
| 👷 **Workers** | لیست اسکریپت‌ها و Route‌ها، مشاهده کد، ادیت و پابلیش، آپلود جدید، حذف |
| 📧 **مسیریابی ایمیل** | مشاهده وضعیت، فعال/غیرفعال، لیست قوانین |
| 📊 **مینی‌اپ** | داشبورد کامل با تمام امکانات بالا |
| 🌍 **دوزبانه** | انگلیسی و فارسی با تغییر آنی |
| 🛡️ **امنیت** | حذف خودکار پیام‌های حاوی توکن، اجبار IPv4 |

### نصب سریع

```bash
curl -fsSL https://raw.githubusercontent.com/Schmi7zz/EazyFlare/main/install.sh | bash
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

1. در `webapp.html` متغیر `PROXY` رو تنظیم کنید:
   ```javascript
   var PROXY = "https://cf-api-proxy.xxx.workers.dev";
   ```
2. فایل رو روی سرور وب یا Cloudflare Pages آپلود کنید
3. SSL تنظیم کنید

#### مرحله ۳: اجرای ربات

```bash
pip install -r requirements.txt
export BOT_TOKEN="توکن-ربات-تلگرام"
export WEBAPP_URL="https://eazyflare.yourdomain.com"
python3 bot.py
```

### دستورات ربات

| دستور | توضیح |
|-------|-------|
| `/start` | منوی اصلی |
| `/connect` | اتصال به Cloudflare |
| `/domains` | لیست دامنه‌ها |
| `/dns` | مدیریت DNS |
| `/disconnect` | قطع اتصال |
| `/help` | راهنما |

### ساخت API Token کلادفلر

1. وارد `dash.cloudflare.com` شوید
2. **My Profile** → **API Tokens** → **Create Token**
3. **"Create Custom Token"** را انتخاب کنید
4. Permission‌های زیر را تنظیم کنید:

   **دسترسی‌های Zone:**
   | دسترسی | سطح |
   |--------|------|
   | Zone | Read |
   | Zone Settings | Edit |
   | DNS | Edit |
   | SSL and Certificates | Edit |
   | Page Rules | Edit |
   | Workers Routes | Edit |
   | Email Routing Rules | Edit |

   **دسترسی‌های Account:**
   | دسترسی | سطح |
   |--------|------|
   | Workers Scripts | Edit |

5. Zone Resources: **Include → All zones**
6. **بخش IP Address Filtering را خالی بگذارید**
7. Token را کپی کنید

> ⚠️ **مهم:** بخش IP Filtering را خالی بگذارید، در غیر این صورت توکن از سرور کار نمی‌کند.

---

Made with ♡ by [Schmitz](https://t.me/SchmitzWS)
]]>