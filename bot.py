"""
EazyFlare — Telegram Bot + Mini App
"""

import os
import json
import logging
import socket
import requests
import asyncio
import io
from datetime import datetime
from functools import wraps
try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, BotCommand, MenuButtonWebApp
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler,
    filters
)

# ━━━━━━━━━━ CONFIG ━━━━━━━━━━
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
CF_API = "https://api.cloudflare.com/client/v4"
ADMIN_ID = 1028296561
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required. Set via environment variable or .env file.")

def webapp_btn(text, zid=None):
    """Return WebApp button only if WEBAPP_URL is set, else None."""
    if not WEBAPP_URL:
        return None
    url = f"{WEBAPP_URL}?zone={zid}" if zid else WEBAPP_URL
    return InlineKeyboardButton(text, web_app=WebAppInfo(url=url))

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━ FORCE IPv4 GLOBALLY ━━━━━━━━━━
# Monkey-patch socket to prefer IPv4
# This fixes "Cannot use access token from location" errors
# when the server connects via IPv6 but CF token doesn't allow it
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = _ipv4_getaddrinfo

# ━━━━━━━━━━ STATES ━━━━━━━━━━
CONNECT_METHOD, CONNECT_EMAIL, CONNECT_KEY = 0, 1, 2
ADD_TYPE, ADD_NAME, ADD_CONTENT, ADD_PROXY = 10, 11, 12, 13
EDIT_VALUE = 50
BROADCAST_MSG = 60
PR_URL, PR_ACTION = 70, 71
WK_CODE = 80
DEP_HOST, DEP_PORT, DEP_USER, DEP_AUTH, DEP_PASS, DEP_KEY, DEP_BOTTOKEN, DEP_WEBAPP = 90, 91, 92, 93, 94, 95, 96, 97

# ━━━━━━━━━━ USER DATABASE (persistent JSON) ━━━━━━━━━━
def load_db():
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {"users": {}, "cf_logins": {}}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def track_user(uid, name="", username=""):
    db = load_db()
    uid_str = str(uid)
    if uid_str not in db["users"]:
        db["users"][uid_str] = {
            "name": name, "username": username,
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat()
        }
    else:
        db["users"][uid_str]["last_seen"] = datetime.now().isoformat()
        if name: db["users"][uid_str]["name"] = name
        if username: db["users"][uid_str]["username"] = username
    save_db(db)

def track_cf_login(uid, name=""):
    db = load_db()
    uid_str = str(uid)
    db["cf_logins"][uid_str] = {
        "name": name,
        "last_login": datetime.now().isoformat()
    }
    save_db(db)

def is_admin(uid):
    return uid == ADMIN_ID

# ━━━━━━━━━━ SESSIONS ━━━━━━━━━━
sessions = {}
def get_s(uid): return sessions.get(uid, {})
def set_s(uid, data):
    if uid not in sessions: sessions[uid] = {}
    sessions[uid].update(data)
def del_s(uid): sessions.pop(uid, None)

# ━━━━━━━━━━ CLOUDFLARE API ━━━━━━━━━━
def cf_h(uid):
    s = get_s(uid)
    if s.get("auth") == "token":
        return {"Authorization": f"Bearer {s['key']}", "Content-Type": "application/json"}
    return {"X-Auth-Email": s.get("email",""), "X-Auth-Key": s.get("key",""), "Content-Type": "application/json"}

def cf_get(uid, path, params=None):
    r = requests.get(f"{CF_API}{path}", headers=cf_h(uid), params=params, timeout=15)
    d = r.json()
    if not d.get("success"):
        raise Exception(", ".join(e.get("message","") for e in d.get("errors",[])) or "Unknown error")
    return d

def cf_post(uid, path, body):
    r = requests.post(f"{CF_API}{path}", headers=cf_h(uid), json=body, timeout=15)
    d = r.json()
    if not d.get("success"):
        raise Exception(", ".join(e.get("message","") for e in d.get("errors",[])) or "Unknown error")
    return d

def cf_put(uid, path, body):
    r = requests.put(f"{CF_API}{path}", headers=cf_h(uid), json=body, timeout=15)
    d = r.json()
    if not d.get("success"):
        raise Exception(", ".join(e.get("message","") for e in d.get("errors",[])) or "Unknown error")
    return d

def cf_del(uid, path):
    r = requests.delete(f"{CF_API}{path}", headers=cf_h(uid), timeout=15)
    d = r.json()
    if not d.get("success"):
        raise Exception(", ".join(e.get("message","") for e in d.get("errors",[])) or "Unknown error")
    return d

def cf_patch(uid, path, body):
    r = requests.patch(f"{CF_API}{path}", headers=cf_h(uid), json=body, timeout=15)
    return r.json()

# ━━━━━━━━━━ AUTH CHECK ━━━━━━━━━━
def need_auth(func):
    @wraps(func)
    async def w(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not get_s(uid).get("key"):
            msg = update.message or update.callback_query.message
            await msg.reply_text(
                "⚠️ ابتدا به حساب Cloudflare وصل شوید.\n\n/connect",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔐 اتصال", callback_data="do_connect")
                ]])
            )
            return
        return await func(update, ctx)
    return w

# ━━━━━━━━━━ /start ━━━━━━━━━━
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name or "کاربر"
    username = update.effective_user.username or ""
    track_user(uid, name, username)
    logged = bool(get_s(uid).get("key"))

    text = f"👋 سلام <b>{name}</b>!\n\n🔸 <b>EazyFlare</b> — مدیریت DNS کلادفلر از تلگرام\n\n"

    if logged:
        text += "✅ حساب شما متصل است.\n"
        btns = [
            [InlineKeyboardButton("🌐 دامنه‌های من", callback_data="do_domains")],
        ]
        if WEBAPP_URL:
            btns.append([webapp_btn("📊 داشبورد")])
        btns.append([InlineKeyboardButton("📖 راهنما", callback_data="do_help"),
             InlineKeyboardButton("🔌 قطع", callback_data="do_disconnect")])
        btns.append([InlineKeyboardButton("🚀 نصب روی سرور", callback_data="do_deploy")])
    else:
        text += "برای شروع، حساب Cloudflare خود را متصل کنید:\n"
        btns = [
            [InlineKeyboardButton("🔐 اتصال به Cloudflare", callback_data="do_connect")],
            [InlineKeyboardButton("📖 راهنما", callback_data="do_help"),
             InlineKeyboardButton("🚀 نصب روی سرور", callback_data="do_deploy")],
        ]

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# ━━━━━━━━━━ /help ━━━━━━━━━━
async def send_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    if update.callback_query: await update.callback_query.answer()

    text = (
        "📖 <b>راهنمای EazyFlare</b>\n\n"
        "🔹 <b>دستورات:</b>\n"
        "/connect — اتصال به Cloudflare\n"
        "/domains — لیست دامنه‌ها\n"
        "/dns — مدیریت DNS\n"
        "/disconnect — قطع اتصال\n\n"
        "🔹 <b>امکانات:</b>\n"
        "📋 DNS — مشاهده/افزودن/ویرایش/حذف رکوردها\n"
        "🔒 SSL/TLS — تغییر حالت رمزنگاری\n"
        "📛 NS — نمایش نیم‌سرورها\n"
        "🌐 تنظیمات — Always HTTPS, TLS 1.3, HTTP/3, Brotli, Minify و ...\n"
        "🔀 Page Rules — ایجاد/ویرایش/حذف ریدایرکت و قوانین\n"
        "👷 Workers — مشاهده/ادیت/آپلود/حذف اسکریپت‌ها\n"
        "📧 Email — مدیریت مسیریابی ایمیل\n"
        "📊 داشبورد — مینی‌اپ با تمام امکانات بالا\n\n"
        "🔹 <b>دریافت API Token:</b>\n"
        "1. dash.cloudflare.com → My Profile → API Tokens\n"
        "2. Create Custom Token\n"
        "3. Permission‌های لازم:\n"
        "   <code>Zone — DNS → Edit</code>\n"
        "   <code>Zone — Zone Settings → Edit</code>\n"
        "   <code>Zone — SSL and Certificates → Edit</code>\n"
        "   <code>Zone — Page Rules → Edit</code>\n"
        "   <code>Zone — Workers Routes → Edit</code>\n"
        "   <code>Zone — Email Routing Rules → Edit</code>\n"
        "   <code>Account — Workers Scripts → Edit</code>\n"
        "4. Zone Resources: All zones\n"
        "5. Token را کپی کنید\n"
    )
    btns = [[InlineKeyboardButton("🔐 اتصال", callback_data="do_connect")]]
    if update.callback_query:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await msg.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# ━━━━━━━━━━ /connect ━━━━━━━━━━
async def connect_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message

    btns = [
        [InlineKeyboardButton("🛡 API Token (پیشنهادی)", callback_data="m_token")],
        [InlineKeyboardButton("🔑 Global API Key + Email", callback_data="m_apikey")],
        [InlineKeyboardButton("❌ انصراف", callback_data="m_cancel")],
    ]
    text = "🔐 <b>اتصال به Cloudflare</b>\n\nروش اتصال را انتخاب کنید:"

    if update.callback_query:
        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        except:
            await msg.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await msg.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    return CONNECT_METHOD

async def connect_method(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "m_cancel":
        await q.message.edit_text("❌ لغو شد.")
        return ConversationHandler.END
    if q.data == "m_token":
        ctx.user_data["auth"] = "token"
        await q.message.edit_text(
            "🛡 <b>API Token</b>\n\nلطفاً API Token را ارسال کنید:\n\n<i>⚠️ پیام بلافاصله حذف می‌شود.</i>",
            parse_mode="HTML")
        return CONNECT_KEY
    if q.data == "m_apikey":
        ctx.user_data["auth"] = "apikey"
        await q.message.edit_text(
            "🔑 <b>Global API Key</b>\n\n<b>ایمیل</b> Cloudflare را ارسال کنید:", parse_mode="HTML")
        return CONNECT_EMAIL
    return CONNECT_METHOD

async def connect_email(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["email"] = update.message.text.strip()
    await update.message.reply_text(
        f"📧 ایمیل: <code>{ctx.user_data['email']}</code>\n\n"
        "حالا <b>Global API Key</b> را ارسال کنید:\n\n<i>⚠️ پیام بلافاصله حذف می‌شود.</i>",
        parse_mode="HTML")
    return CONNECT_KEY

async def connect_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    key = update.message.text.strip()
    try: await update.message.delete()
    except: pass

    method = ctx.user_data.get("auth", "token")
    email = ctx.user_data.get("email", "")
    set_s(uid, {"key": key, "auth": method, "email": email})

    wait = await update.effective_chat.send_message("⏳ در حال بررسی...")
    try:
        if method == "token":
            cf_get(uid, "/user/tokens/verify")
        else:
            cf_get(uid, "/zones", {"per_page": 1})

        track_cf_login(uid, update.effective_user.first_name or "")
        _btns = [[InlineKeyboardButton("🌐 دامنه‌ها", callback_data="do_domains")]]
        if WEBAPP_URL:
            _btns.append([webapp_btn("📊 داشبورد")])
        await wait.edit_text(
            "✅ <b>اتصال برقرار شد!</b>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(_btns))
    except Exception as e:
        del_s(uid)
        await wait.edit_text(
            f"❌ <b>خطا</b>\n\n<code>{e}</code>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 تلاش مجدد", callback_data="do_connect")]
            ]))
    return ConversationHandler.END

async def connect_cancel_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ لغو شد.")
    return ConversationHandler.END

# ━━━━━━━━━━ /domains ━━━━━━━━━━
@need_auth
async def cmd_domains(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    uid = update.effective_user.id
    if update.callback_query: await update.callback_query.answer()

    wait = await msg.reply_text("⏳ دریافت دامنه‌ها...")
    try:
        zones = []
        page = 1
        while True:
            d = cf_get(uid, "/zones", {"per_page": 50, "page": page})
            zones.extend(d["result"])
            if page >= d.get("result_info", {}).get("total_pages", 1): break
            page += 1

        set_s(uid, {"zones": zones})
        if not zones:
            await wait.edit_text("📭 دامنه‌ای یافت نشد.")
            return

        ico = {"active": "🟢", "pending": "🟡", "moved": "🔴", "deactivated": "🔴"}
        text = f"🌐 <b>دامنه‌ها</b> — {len(zones)} عدد\n"
        btns = []
        for z in zones:
            i = ico.get(z["status"], "⚪")
            plan = z.get("plan", {}).get("name", "Free")
            btns.append([InlineKeyboardButton(f"{i} {z['name']}  •  {plan}", callback_data=f"zone_{z['id']}")])
        _last = [InlineKeyboardButton("🔄 بروزرسانی", callback_data="do_domains")]
        if WEBAPP_URL:
            _last.append(webapp_btn("📊 داشبورد"))
        btns.append(_last)
        await wait.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    except Exception as e:
        await wait.edit_text(f"❌ خطا: <code>{e}</code>", parse_mode="HTML")

# ━━━━━━━━━━ ZONE SELECTED ━━━━━━━━━━
async def zone_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    zid = q.data.replace("zone_", "")
    s = get_s(uid)
    zone = next((z for z in s.get("zones", []) if z["id"] == zid), None)
    if not zone:
        await q.message.edit_text("❌ دامنه یافت نشد.")
        return
    set_s(uid, {"cur_zone": zone})
    st = {"active": "🟢 فعال", "pending": "🟡 در انتظار", "moved": "🔴 منتقل شده"}
    ns = "\n".join(f"  <code>{n}</code>" for n in zone.get("name_servers", []))
    text = (f"📋 <b>{zone['name']}</b>\n\nوضعیت: {st.get(zone['status'], zone['status'])}\n"
            f"پلن: {zone.get('plan', {}).get('name', 'Free')}\nنیم‌سرورها:\n{ns}\n")
    btns = [
        [InlineKeyboardButton("📋 DNS", callback_data=f"dns_{zid}"),
         InlineKeyboardButton("➕ افزودن", callback_data=f"add_{zid}")],
        [InlineKeyboardButton("🔒 SSL/TLS", callback_data=f"ssl_{zid}"),
         InlineKeyboardButton("📛 NS", callback_data=f"ns_{zid}")],
        [InlineKeyboardButton("🌐 تنظیمات", callback_data=f"zs_{zid}"),
         InlineKeyboardButton("🔀 Page Rules", callback_data=f"pr_{zid}")],
        [InlineKeyboardButton("👷 Workers", callback_data=f"wk_{zid}"),
         InlineKeyboardButton("📧 Email", callback_data=f"em_{zid}")],
    ]
    if WEBAPP_URL:
        btns.append([webapp_btn("📊 داشبورد", zid)])
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data="do_domains")])
    await q.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# ━━━━━━━━━━ DNS LIST ━━━━━━━━━━
async def dns_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    zid = q.data.replace("dns_", "")
    s = get_s(uid)
    zone = s.get("cur_zone", {})
    try:
        recs = []
        page = 1
        while True:
            d = cf_get(uid, f"/zones/{zid}/dns_records", {"per_page": 100, "page": page})
            recs.extend(d["result"])
            if page >= d.get("result_info", {}).get("total_pages", 1): break
            page += 1
        set_s(uid, {"dns": recs})
        if not recs:
            await q.message.edit_text(f"📭 رکوردی برای <b>{zone.get('name','')}</b> یافت نشد.", parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ افزودن", callback_data=f"add_{zid}")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")],
                ]))
            return
        tc = {}
        for r in recs: tc[r["type"]] = tc.get(r["type"], 0) + 1
        ti = {"A":"🔵","AAAA":"🟣","CNAME":"🟢","MX":"🟡","TXT":"🩷","NS":"🔷","SRV":"🟠","CAA":"🟤"}
        text = f"📋 <b>DNS — {zone.get('name','')}</b>\n{len(recs)} رکورد\n\n"
        for t, c in sorted(tc.items()): text += f"{ti.get(t,'⚪')} <b>{t}</b>: {c}\n"
        text += "\n"
        for r in recs[:15]:
            px = "☁️" if r.get("proxied") else "🔘"
            nm = r["name"].replace(f".{zone.get('name','')}", "") or "@"
            ct = r["content"][:30] + ("…" if len(r["content"]) > 30 else "")
            text += f"<code>{r['type']:5}</code> {nm} → <code>{ct}</code> {px}\n"
        if len(recs) > 15: text += f"\n<i>… و {len(recs)-15} رکورد دیگر</i>\n"
        fbtns = []
        row = []
        for t in sorted(tc.keys()):
            row.append(InlineKeyboardButton(f"{ti.get(t,'')}{t}({tc[t]})", callback_data=f"ft_{zid}_{t}"))
            if len(row) >= 4: fbtns.append(row); row = []
        if row: fbtns.append(row)
        fbtns.append([InlineKeyboardButton("➕ افزودن", callback_data=f"add_{zid}"), InlineKeyboardButton("🔄", callback_data=f"dns_{zid}")])
        if WEBAPP_URL:
            fbtns.append([webapp_btn("📊 داشبورد", zid)])
        fbtns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")])
        await q.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(fbtns))
    except Exception as e:
        await q.message.edit_text(f"❌ خطا: <code>{e}</code>", parse_mode="HTML")

# ━━━━━━━━━━ DNS FILTER ━━━━━━━━━━
async def dns_filter(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    parts = q.data.split("_"); zid, rtype = parts[1], parts[2]
    s = get_s(uid); zone = s.get("cur_zone", {})
    recs = [r for r in s.get("dns", []) if r["type"] == rtype]
    ti = {"A":"🔵","AAAA":"🟣","CNAME":"🟢","MX":"🟡","TXT":"🩷","NS":"🔷","SRV":"🟠","CAA":"🟤"}
    text = f"{ti.get(rtype,'⚪')} <b>{rtype} — {zone.get('name','')}</b>\n{len(recs)} رکورد\n\n"
    btns = []
    for r in recs[:20]:
        nm = r["name"].replace(f".{zone.get('name','')}", "") or "@"
        ct = r["content"][:25] + ("…" if len(r["content"]) > 25 else "")
        px = "☁️" if r.get("proxied") else "🔘"
        text += f"<code>{nm}</code> → <code>{ct}</code> {px}\n"
        btns.append([InlineKeyboardButton(f"✏️ {nm} → {ct}", callback_data=f"ed_{r['id']}")])
    btns.append([InlineKeyboardButton("🔙 همه", callback_data=f"dns_{zid}"), InlineKeyboardButton("➕", callback_data=f"add_{zid}")])
    await q.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# ━━━━━━━━━━ ADD DNS ━━━━━━━━━━
async def add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    zid = q.data.replace("add_", ""); ctx.user_data["add_zid"] = zid
    types = ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA"]
    btns = []; row = []
    for t in types:
        row.append(InlineKeyboardButton(t, callback_data=f"at_{t}"))
        if len(row) >= 4: btns.append(row); row = []
    if row: btns.append(row)
    btns.append([InlineKeyboardButton("❌ انصراف", callback_data=f"zone_{zid}")])
    await q.message.edit_text("➕ <b>نوع رکورد:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    return ADD_TYPE

async def add_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["add_type"] = q.data.replace("at_", "")
    t = ctx.user_data["add_type"]
    ph = {"A":"@ یا www","AAAA":"@ یا www","CNAME":"www","MX":"@","TXT":"@ یا _dmarc","NS":"sub","SRV":"_sip._tcp","CAA":"@"}
    await q.message.edit_text(f"➕ <b>{t}</b>\n\n<b>نام</b> را بفرستید:\n<i>{ph.get(t,'')} — ریشه = @</i>", parse_mode="HTML")
    return ADD_NAME

async def add_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["add_name"] = update.message.text.strip()
    t = ctx.user_data["add_type"]
    hints = {"A":"<code>1.2.3.4</code>","AAAA":"<code>2001:db8::1</code>","CNAME":"<code>example.com</code>","MX":"<code>mail.example.com</code>","TXT":"<code>v=spf1 ...</code>","NS":"<code>ns1.example.com</code>","SRV":"<code>priority weight port target</code>","CAA":'<code>0 issue "letsencrypt.org"</code>'}
    await update.message.reply_text(f"✅ نام: <code>{ctx.user_data['add_name']}</code>\n\n<b>مقدار:</b>\n{hints.get(t,'')}", parse_mode="HTML")
    return ADD_CONTENT

async def add_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["add_content"] = update.message.text.strip()
    t = ctx.user_data["add_type"]
    if t in ("A", "AAAA", "CNAME"):
        await update.message.reply_text(f"✅ مقدار: <code>{ctx.user_data['add_content']}</code>\n\nپروکسی:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("☁️ فعال", callback_data="px_on"), InlineKeyboardButton("🔘 خاموش", callback_data="px_off")]]))
        return ADD_PROXY
    else:
        ctx.user_data["add_proxy"] = False
        return await do_add_submit(update, ctx)

async def add_proxy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["add_proxy"] = q.data == "px_on"
    return await do_add_submit(update, ctx)

async def do_add_submit(update, ctx):
    if update.callback_query: msg = update.callback_query.message; uid = update.callback_query.from_user.id
    else: msg = update.message; uid = update.effective_user.id
    zid = ctx.user_data["add_zid"]; t = ctx.user_data["add_type"]; name = ctx.user_data["add_name"]
    content = ctx.user_data["add_content"]; proxied = ctx.user_data.get("add_proxy", False)
    s = get_s(uid); zone = s.get("cur_zone", {})
    if name == "@": name = zone.get("name", name)
    elif not name.endswith(zone.get("name", "")): name = f"{name}.{zone.get('name', '')}"
    body = {"type": t, "name": name, "content": content, "ttl": 1}
    if t in ("A", "AAAA", "CNAME"): body["proxied"] = proxied
    wait = await msg.reply_text("⏳ ایجاد رکورد...")
    try:
        cf_post(uid, f"/zones/{zid}/dns_records", body)
        px_txt = "☁️" if proxied else "🔘"
        await wait.edit_text(f"✅ <b>ایجاد شد!</b>\n\n<code>{t}</code> | <code>{name}</code>\n→ <code>{content}</code> {px_txt}", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 رکوردها", callback_data=f"dns_{zid}"), InlineKeyboardButton("➕ دیگر", callback_data=f"add_{zid}")]]))
    except Exception as e:
        await wait.edit_text(f"❌ خطا: <code>{e}</code>", parse_mode="HTML")
    return ConversationHandler.END

# ━━━━━━━━━━ EDIT DNS ━━━━━━━━━━
async def edit_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id; rid = q.data.replace("ed_", "")
    s = get_s(uid); rec = next((r for r in s.get("dns", []) if r["id"] == rid), None)
    zid = s.get("cur_zone", {}).get("id", "")
    if not rec: await q.message.edit_text("❌ یافت نشد."); return
    ctx.user_data["edit_rec"] = rec
    px_txt = "☁️" if rec.get("proxied") else "🔘"
    ttl = "Auto" if rec.get("ttl") == 1 else f"{rec['ttl']}s"
    text = f"✏️ <b>ویرایش</b>\n\n<code>{rec['type']}</code> | <code>{rec['name']}</code>\n→ <code>{rec['content']}</code>\nTTL: {ttl} | پروکسی: {px_txt}"
    btns = [[InlineKeyboardButton("📝 تغییر مقدار", callback_data=f"ec_{rid}")]]
    if rec["type"] in ("A", "AAAA", "CNAME"):
        toggle = "غیرفعال" if rec.get("proxied") else "فعال"
        btns.append([InlineKeyboardButton(f"☁️ {toggle} کردن پروکسی", callback_data=f"ep_{rid}")])
    btns.append([InlineKeyboardButton("🗑 حذف", callback_data=f"dl_{rid}")])
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"dns_{zid}")])
    await q.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def toggle_proxy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id; rid = q.data.replace("ep_", "")
    s = get_s(uid); rec = next((r for r in s.get("dns", []) if r["id"] == rid), None)
    zid = s.get("cur_zone", {}).get("id", "")
    if not rec: return
    new_px = not rec.get("proxied", False)
    wait = await q.message.edit_text("⏳...")
    try:
        cf_put(uid, f"/zones/{zid}/dns_records/{rid}", {"type": rec["type"], "name": rec["name"], "content": rec["content"], "ttl": rec.get("ttl", 1), "proxied": new_px})
        st = "فعال ☁️" if new_px else "خاموش 🔘"
        await wait.edit_text(f"✅ پروکسی {st} شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 رکوردها", callback_data=f"dns_{zid}")]]))
    except Exception as e:
        await wait.edit_text(f"❌ خطا: <code>{e}</code>", parse_mode="HTML")

async def edit_content_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    rid = q.data.replace("ec_", "")
    s = get_s(q.from_user.id); rec = next((r for r in s.get("dns", []) if r["id"] == rid), None)
    if not rec: return ConversationHandler.END
    ctx.user_data["edit_rec"] = rec; ctx.user_data["edit_rid"] = rid
    await q.message.edit_text(f"📝 فعلی:\n<code>{rec['content']}</code>\n\nمقدار جدید:", parse_mode="HTML")
    return EDIT_VALUE

async def edit_content_value(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; val = update.message.text.strip()
    rec = ctx.user_data.get("edit_rec"); rid = ctx.user_data.get("edit_rid")
    s = get_s(uid); zid = s.get("cur_zone", {}).get("id", "")
    if not rec: await update.message.reply_text("❌ یافت نشد."); return ConversationHandler.END
    wait = await update.message.reply_text("⏳ بروزرسانی...")
    try:
        body = {"type": rec["type"], "name": rec["name"], "content": val, "ttl": rec.get("ttl", 1)}
        if rec["type"] in ("A", "AAAA", "CNAME"): body["proxied"] = rec.get("proxied", False)
        cf_put(uid, f"/zones/{zid}/dns_records/{rid}", body)
        await wait.edit_text(f"✅ شد!\n<code>{rec['name']}</code> → <code>{val}</code>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 رکوردها", callback_data=f"dns_{zid}")]]))
    except Exception as e:
        await wait.edit_text(f"❌ خطا: <code>{e}</code>", parse_mode="HTML")
    return ConversationHandler.END

# ━━━━━━━━━━ DELETE ━━━━━━━━━━
async def delete_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    rid = q.data.replace("dl_", ""); s = get_s(q.from_user.id)
    rec = next((r for r in s.get("dns", []) if r["id"] == rid), None)
    zid = s.get("cur_zone", {}).get("id", "")
    if not rec: return
    await q.message.edit_text(
        f"⚠️ <b>حذف؟</b>\n\n<code>{rec['type']}</code> | <code>{rec['name']}</code>\n→ <code>{rec['content']}</code>\n\n<b>قابل بازگشت نیست!</b>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑 حذف", callback_data=f"dx_{rid}"),
            InlineKeyboardButton("❌ انصراف", callback_data=f"dns_{zid}")]]))

async def delete_execute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id; rid = q.data.replace("dx_", "")
    zid = get_s(uid).get("cur_zone", {}).get("id", "")
    try:
        cf_del(uid, f"/zones/{zid}/dns_records/{rid}")
        await q.message.edit_text("✅ حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 رکوردها", callback_data=f"dns_{zid}")]]))
    except Exception as e:
        await q.message.edit_text(f"❌ خطا: <code>{e}</code>", parse_mode="HTML")

# ━━━━━━━━━━ /disconnect ━━━━━━━━━━
async def cmd_disconnect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    uid = update.effective_user.id
    if update.callback_query: await update.callback_query.answer()
    del_s(uid)
    await msg.reply_text("🔌 قطع شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔐 اتصال", callback_data="do_connect")]]))

# ━━━━━━━━━━ /stats (ADMIN ONLY) ━━━━━━━━━━
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Access denied.")
        return

    db = load_db()
    total_users = len(db.get("users", {}))
    total_cf = len(db.get("cf_logins", {}))
    active_sessions = len([u for u in sessions.values() if u.get("key")])

    # Recent users (last 5)
    users = db.get("users", {})
    sorted_users = sorted(users.items(), key=lambda x: x[1].get("last_seen", ""), reverse=True)

    recent = ""
    for uid_str, info in sorted_users[:10]:
        name = info.get("name", "?")
        uname = f"@{info['username']}" if info.get("username") else ""
        seen = info.get("last_seen", "?")[:10]
        cf = "✅" if uid_str in db.get("cf_logins", {}) else "❌"
        recent += f"  {cf} <code>{uid_str}</code> {name} {uname} — {seen}\n"

    text = (
        f"📊 <b>EazyFlare Stats</b>\n\n"
        f"👥 Total users: <b>{total_users}</b>\n"
        f"☁️ CF logins: <b>{total_cf}</b>\n"
        f"🟢 Active sessions: <b>{active_sessions}</b>\n\n"
        f"📋 <b>Recent users:</b>\n{recent or '  No users yet.'}\n"
        f"<i>✅ = connected to CF | ❌ = not connected</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# ━━━━━━━━━━ /broadcast (ADMIN ONLY) ━━━━━━━━━━
async def broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Access denied.")
        return ConversationHandler.END

    db = load_db()
    total = len(db.get("users", {}))
    await update.message.reply_text(
        f"📢 <b>Broadcast</b>\n\n"
        f"👥 Will be sent to <b>{total}</b> users.\n\n"
        f"Send the message you want to broadcast.\n"
        f"Supports text, photo, video, document.\n\n"
        f"/cancel to abort.",
        parse_mode="HTML"
    )
    return BROADCAST_MSG

async def broadcast_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return ConversationHandler.END

    db = load_db()
    users = db.get("users", {})
    total = len(users)
    sent, failed, blocked = 0, 0, 0

    wait = await update.message.reply_text(f"📢 Sending to {total} users...")

    for uid_str in users:
        try:
            chat_id = int(uid_str)
            if update.message.text:
                await ctx.bot.send_message(chat_id, update.message.text, parse_mode="HTML")
            elif update.message.photo:
                await ctx.bot.send_photo(chat_id, update.message.photo[-1].file_id,
                    caption=update.message.caption or "", parse_mode="HTML")
            elif update.message.video:
                await ctx.bot.send_video(chat_id, update.message.video.file_id,
                    caption=update.message.caption or "", parse_mode="HTML")
            elif update.message.document:
                await ctx.bot.send_document(chat_id, update.message.document.file_id,
                    caption=update.message.caption or "", parse_mode="HTML")
            else:
                await ctx.bot.copy_message(chat_id, update.message.chat_id, update.message.message_id)
            sent += 1
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "not found" in err:
                blocked += 1
            else:
                failed += 1
            logger.warning(f"Broadcast to {uid_str}: {e}")

        # Rate limit: 30 msgs/sec max
        if (sent + failed + blocked) % 25 == 0:
            await asyncio.sleep(1)

    await wait.edit_text(
        f"📢 <b>Broadcast Complete</b>\n\n"
        f"✅ Sent: <b>{sent}</b>\n"
        f"🚫 Blocked: <b>{blocked}</b>\n"
        f"❌ Failed: <b>{failed}</b>\n"
        f"📊 Total: <b>{total}</b>",
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def broadcast_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Broadcast cancelled.")
    return ConversationHandler.END

# ━━━━━━━━━━ SSL/TLS ━━━━━━━━━━
async def ssl_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    zid = q.data.replace("ssl_", "").replace("sslset_", "")
    s = get_s(uid)
    zone = s.get("cur_zone", {})

    if q.data.startswith("sslset_"):
        parts = zid.split("_", 1)
        zid, mode = parts[0], parts[1]
        wait = await q.message.edit_text("⏳ تغییر SSL...")
        r = cf_patch(uid, f"/zones/{zid}/settings/ssl", {"value": mode})
        if r.get("success"):
            await wait.edit_text(
                f"✅ SSL به <b>{mode}</b> تغییر کرد.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"ssl_{zid}")]])
            )
        else:
            err = r.get("errors", [{}])[0].get("message", "خطا")
            await wait.edit_text(f"❌ {err}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"ssl_{zid}")]]))
        return

    wait = await q.message.edit_text("⏳ دریافت SSL...")
    r = cf_get(uid, f"/zones/{zid}/settings/ssl")
    if not r.get("success"):
        await wait.edit_text("❌ خطا در دریافت SSL", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")]]))
        return

    current = r["result"]["value"]
    modes = {"off": "🔴 خاموش", "flexible": "🟡 Flexible", "full": "🟢 Full", "strict": "🔵 Full (Strict)"}
    text = f"🔒 <b>SSL/TLS — {zone.get('name', '')}</b>\n\nوضعیت فعلی: <b>{modes.get(current, current)}</b>\n\nیک حالت انتخاب کن:"

    btns = []
    for m, label in modes.items():
        if m == current:
            btns.append([InlineKeyboardButton(f"✅ {label}", callback_data="noop")])
        else:
            btns.append([InlineKeyboardButton(label, callback_data=f"sslset_{zid}_{m}")])
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")])

    await wait.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# ━━━━━━━━━━ NS INFO ━━━━━━━━━━
async def ns_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    zid = q.data.replace("ns_", "")
    s = get_s(uid)
    zone = s.get("cur_zone", {})

    wait = await q.message.edit_text("⏳ دریافت اطلاعات NS...")
    r = cf_get(uid, f"/zones/{zid}")
    if not r.get("success"):
        await wait.edit_text("❌ خطا", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")]]))
        return

    z = r["result"]
    ns_list = z.get("name_servers", [])
    orig_ns = z.get("original_name_servers", [])

    ns_txt = "\n".join(f"  <code>{n}</code>" for n in ns_list) or "—"
    orig_txt = "\n".join(f"  <code>{n}</code>" for n in orig_ns) or "—"

    text = (f"📛 <b>Nameservers — {z.get('name', '')}</b>\n\n"
            f"<b>نیم‌سرورهای کلادفلر:</b>\n{ns_txt}\n\n"
            f"<b>نیم‌سرورهای اصلی (رجیسترار):</b>\n{orig_txt}\n\n"
            f"وضعیت: <b>{z.get('status', '—')}</b>")

    btns = [[InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")]]
    await wait.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# ━━━━━━━━━━ ZONE SETTINGS ━━━━━━━━━━
ZONE_TOGGLES = [
    ("always_use_https", "🔗 Always HTTPS"),
    ("automatic_https_rewrites", "🔄 Auto HTTPS Rewrites"),
    ("min_tls_version", "🔐 Min TLS Version"),
    ("tls_1_3", "🔐 TLS 1.3"),
    ("http3", "🌐 HTTP/3"),
    ("0rtt", "⚡ 0-RTT"),
    ("minify", "📦 Minify"),
    ("brotli", "🗜 Brotli"),
    ("early_hints", "💡 Early Hints"),
    ("websockets", "🔌 WebSockets"),
    ("opportunistic_encryption", "🔒 Opportunistic Encryption"),
    ("browser_cache_ttl", "🕐 Browser Cache TTL"),
]

async def zone_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    d = q.data
    s = get_s(uid)
    zone = s.get("cur_zone", {})

    # Toggle a setting
    if d.startswith("zst_"):
        parts = d.replace("zst_", "").split("_", 1)
        zid, setting_val = parts[0], parts[1]
        # format: zst_{zid}_{setting}_{value}
        rest = setting_val
        # find last _ for value
        li = rest.rfind("_")
        setting = rest[:li]
        val = rest[li+1:]
        # convert
        if val in ("on", "off"):
            body = {"value": val}
        elif val.startswith("1."):
            body = {"value": val}
        else:
            try:
                body = {"value": int(val)}
            except:
                body = {"value": val}
        wait = await q.message.edit_text("⏳ ...")
        r = cf_patch(uid, f"/zones/{zid}/settings/{setting}", body)
        if r.get("success"):
            await wait.edit_text("✅ تغییر کرد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 تنظیمات", callback_data=f"zs_{zid}")]]))
        else:
            err = r.get("errors", [{}])[0].get("message", "خطا")
            await wait.edit_text(f"❌ {err}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"zs_{zid}")]]))
        return

    # Show settings list
    zid = d.replace("zs_", "")
    wait = await q.message.edit_text("⏳ دریافت تنظیمات...")

    settings = {}
    for key, _ in ZONE_TOGGLES:
        if key == "minify":
            r = cf_get(uid, f"/zones/{zid}/settings/minify")
        else:
            r = cf_get(uid, f"/zones/{zid}/settings/{key}")
        if r.get("success"):
            settings[key] = r["result"]["value"]

    text = f"🌐 <b>تنظیمات — {zone.get('name','')}</b>\n\n"
    btns = []
    for key, label in ZONE_TOGGLES:
        val = settings.get(key, "—")
        if key == "minify" and isinstance(val, dict):
            st = "JS:" + val.get("js","off") + " CSS:" + val.get("css","off") + " HTML:" + val.get("html","off")
            text += f"{label}: <code>{st}</code>\n"
            # toggle all on/off
            all_on = val.get("js") == "on" and val.get("css") == "on" and val.get("html") == "on"
            if all_on:
                btns.append([InlineKeyboardButton(f"📦 Minify: ✅ ON → OFF", callback_data=f"zsm_{zid}_off")])
            else:
                btns.append([InlineKeyboardButton(f"📦 Minify: ❌ OFF → ON", callback_data=f"zsm_{zid}_on")])
        elif key == "min_tls_version":
            text += f"{label}: <code>{val}</code>\n"
        elif key == "browser_cache_ttl":
            text += f"{label}: <code>{val}s</code>\n"
        else:
            icon = "✅" if val == "on" else "❌"
            text += f"{label}: {icon} {val}\n"
            new_val = "off" if val == "on" else "on"
            btns.append([InlineKeyboardButton(f"{label}: {icon} → {'❌' if val=='on' else '✅'}", callback_data=f"zst_{zid}_{key}_{new_val}")])

    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")])
    await wait.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def zone_minify_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    parts = q.data.replace("zsm_", "").split("_")
    zid, val = parts[0], parts[1]
    body = {"value": {"js": val, "css": val, "html": val}}
    wait = await q.message.edit_text("⏳ ...")
    r = cf_patch(uid, f"/zones/{zid}/settings/minify", body)
    if r.get("success"):
        await wait.edit_text("✅ Minify تغییر کرد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 تنظیمات", callback_data=f"zs_{zid}")]]))
    else:
        err = r.get("errors", [{}])[0].get("message", "خطا")
        await wait.edit_text(f"❌ {err}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"zs_{zid}")]]))

# ━━━━━━━━━━ PAGE RULES ━━━━━━━━━━
async def page_rules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    d = q.data

    # Delete page rule
    if d.startswith("prd_"):
        parts = d.replace("prd_", "").split("_", 1)
        zid, rid = parts[0], parts[1]
        wait = await q.message.edit_text("⏳ حذف...")
        try:
            cf_del(uid, f"/zones/{zid}/pagerules/{rid}")
            await wait.edit_text("✅ حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Page Rules", callback_data=f"pr_{zid}")]]))
        except Exception as e:
            await wait.edit_text(f"❌ {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"pr_{zid}")]]))
        return

    # Toggle page rule status
    if d.startswith("prt_"):
        parts = d.replace("prt_", "").split("_", 1)
        zid, rid = parts[0], parts[1]
        wait = await q.message.edit_text("⏳ ...")
        r = cf_get(uid, f"/zones/{zid}/pagerules/{rid}")
        if r.get("success"):
            cur = r["result"]["status"]
            new_st = "disabled" if cur == "active" else "active"
            r2 = cf_patch(uid, f"/zones/{zid}/pagerules/{rid}", {"status": new_st})
            if r2.get("success"):
                await wait.edit_text(f"✅ {new_st}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Page Rules", callback_data=f"pr_{zid}")]]))
            else:
                err = r2.get("errors", [{}])[0].get("message", "خطا")
                await wait.edit_text(f"❌ {err}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"pr_{zid}")]]))
        return

    # List page rules
    zid = d.replace("pr_", "")
    wait = await q.message.edit_text("⏳ دریافت Page Rules...")
    r = cf_get(uid, f"/zones/{zid}/pagerules", {"status": "active,disabled"})
    s = get_s(uid)
    zone = s.get("cur_zone", {})

    rules = r.get("result", []) if r.get("success") else []
    text = f"🔀 <b>Page Rules — {zone.get('name','')}</b>\n\n"
    btns = []

    if not rules:
        text += "📭 هیچ Page Rule ای وجود نداره.\n"
    else:
        for i, rule in enumerate(rules):
            st = "🟢" if rule["status"] == "active" else "🔴"
            targets = ", ".join(t["constraint"]["value"] for t in rule.get("targets", []))
            actions = ", ".join(a["id"] + (f":{a['value']}" if isinstance(a.get("value"), str) else "") for a in rule.get("actions", []))
            text += f"{i+1}. {st} <code>{targets}</code>\n   → {actions}\n\n"
            rid = rule["id"]
            btns.append([
                InlineKeyboardButton(f"{'⏸' if rule['status']=='active' else '▶️'} {i+1}", callback_data=f"prt_{zid}_{rid}"),
                InlineKeyboardButton(f"🗑 {i+1}", callback_data=f"prd_{zid}_{rid}"),
            ])

    btns.append([InlineKeyboardButton("➕ افزودن Page Rule", callback_data=f"pra_{zid}")])
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")])
    await wait.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# — Add Page Rule conversation —
async def pr_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    zid = q.data.replace("pra_", "")
    s = get_s(q.from_user.id)
    zone = s.get("cur_zone", {})
    ctx.user_data["pr_zid"] = zid
    ctx.user_data["pr_domain"] = zone.get("name", "")
    await q.message.edit_text(
        f"🔀 <b>افزودن Page Rule</b>\n\nURL الگو را ارسال کنید:\n"
        f"مثال: <code>{zone.get('name','')}/*</code> یا <code>*{zone.get('name','')}/*</code>",
        parse_mode="HTML"
    )
    return PR_URL

async def pr_add_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    ctx.user_data["pr_url"] = url
    await update.message.reply_text(
        "📋 اکشن را انتخاب کنید:\n\n"
        "یکی بفرست:\n"
        "<code>forwarding_url 301 https://example.com</code>\n"
        "<code>forwarding_url 302 https://example.com</code>\n"
        "<code>always_use_https</code>\n"
        "<code>cache_level aggressive</code>\n"
        "<code>cache_level bypass</code>\n"
        "<code>ssl flexible</code>\n"
        "<code>ssl full</code>\n"
        "<code>ssl strict</code>\n"
        "<code>browser_cache_ttl 3600</code>",
        parse_mode="HTML"
    )
    return PR_ACTION

async def pr_add_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    zid = ctx.user_data["pr_zid"]
    url = ctx.user_data["pr_url"]

    parts = text.split(None, 2)
    action_id = parts[0]

    # Build action
    if action_id == "forwarding_url" and len(parts) >= 3:
        action = {"id": "forwarding_url", "value": {"url": parts[2], "status_code": int(parts[1])}}
    elif action_id == "always_use_https":
        action = {"id": "always_use_https"}
    elif len(parts) >= 2:
        try:
            action = {"id": action_id, "value": int(parts[1])}
        except ValueError:
            action = {"id": action_id, "value": parts[1]}
    else:
        action = {"id": action_id}

    body = {
        "targets": [{"target": "url", "constraint": {"operator": "matches", "value": url}}],
        "actions": [action],
        "status": "active"
    }

    wait = await update.message.reply_text("⏳ ایجاد...")
    try:
        r = cf_post(uid, f"/zones/{zid}/pagerules", body)
        await wait.edit_text(
            "✅ Page Rule ایجاد شد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Page Rules", callback_data=f"pr_{zid}")]])
        )
    except Exception as e:
        await wait.edit_text(
            f"❌ {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"pr_{zid}")]])
        )
    return ConversationHandler.END

# ━━━━━━━━━━ WORKERS ━━━━━━━━━━
async def workers_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    d = q.data
    s = get_s(uid)
    zone = s.get("cur_zone", {})

    # Get account_id from zone
    def get_account_id():
        z = s.get("cur_zone", {})
        return z.get("account", {}).get("id", "")

    # Worker routes for zone
    if d.startswith("wk_"):
        zid = d.replace("wk_", "")
        wait = await q.message.edit_text("⏳ دریافت Workers...")

        acc_id = get_account_id()

        # Get scripts (account-level)
        scripts = []
        if acc_id:
            try:
                rs = cf_get(uid, f"/accounts/{acc_id}/workers/scripts")
                scripts = rs.get("result", []) if rs.get("success") else []
            except:
                pass

        # Get routes (zone-level)
        routes = []
        try:
            rr = cf_get(uid, f"/zones/{zid}/workers/routes")
            routes = rr.get("result", []) if rr.get("success") else []
        except:
            pass

        text = f"👷 <b>Workers — {zone.get('name','')}</b>\n\n"

        if scripts:
            text += f"<b>اسکریپت‌ها ({len(scripts)}):</b>\n"
            for i, sc in enumerate(scripts):
                text += f"  {i+1}. <code>{sc.get('id','')}</code>\n"
            text += "\n"

        if routes:
            text += f"<b>Route‌ها ({len(routes)}):</b>\n"
            for i, rt in enumerate(routes):
                text += f"  {i+1}. <code>{rt.get('pattern','')}</code> → {rt.get('script','—')}\n"
            text += "\n"

        if not scripts and not routes:
            text += "📭 هیچ Worker ای وجود نداره.\n"

        btns = []
        # Script actions
        for sc in scripts:
            name = sc.get("id", "")
            btns.append([
                InlineKeyboardButton(f"📄 {name[:20]}", callback_data=f"wkv_{zid}_{name[:40]}"),
                InlineKeyboardButton(f"🗑", callback_data=f"wks_{zid}_{name[:40]}"),
            ])
        # Route delete
        for rt in routes:
            btns.append([
                InlineKeyboardButton(f"🗑 route: {rt.get('pattern','')[:25]}", callback_data=f"wkd_{zid}_{rt['id']}")
            ])

        btns.append([InlineKeyboardButton("📝 آپلود/ادیت Worker", callback_data=f"wke_{zid}")])
        btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")])
        await wait.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        return

    # View worker code
    if d.startswith("wkv_"):
        parts = d.replace("wkv_", "").split("_", 1)
        zid, name = parts[0], parts[1]
        acc_id = get_account_id()
        wait = await q.message.edit_text("⏳ دریافت کد...")
        try:
            r = requests.get(f"{CF_API}/accounts/{acc_id}/workers/scripts/{name}", headers=cf_h(uid), timeout=15)
            code = r.text[:3500]  # Telegram limit
            await wait.edit_text(
                f"📄 <b>{name}</b>\n\n<pre>{code}</pre>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 ادیت", callback_data=f"wke_{zid}_{name}")],
                    [InlineKeyboardButton("🔙 Workers", callback_data=f"wk_{zid}")]
                ])
            )
        except Exception as e:
            await wait.edit_text(f"❌ {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"wk_{zid}")]]))
        return

    # Delete worker script
    if d.startswith("wks_"):
        parts = d.replace("wks_", "").split("_", 1)
        zid, name = parts[0], parts[1]
        acc_id = get_account_id()
        wait = await q.message.edit_text(f"⚠️ حذف Worker <b>{name}</b>؟", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ بله حذف کن", callback_data=f"wksx_{zid}_{name}"),
                 InlineKeyboardButton("❌ انصراف", callback_data=f"wk_{zid}")]
            ]))
        return

    # Confirm delete worker script
    if d.startswith("wksx_"):
        parts = d.replace("wksx_", "").split("_", 1)
        zid, name = parts[0], parts[1]
        acc_id = get_account_id()
        wait = await q.message.edit_text("⏳ حذف...")
        try:
            requests.delete(f"{CF_API}/accounts/{acc_id}/workers/scripts/{name}", headers=cf_h(uid), timeout=15)
            await wait.edit_text("✅ حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Workers", callback_data=f"wk_{zid}")]]))
        except Exception as e:
            await wait.edit_text(f"❌ {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"wk_{zid}")]]))
        return

    # Delete worker route
    if d.startswith("wkd_"):
        parts = d.replace("wkd_", "").split("_", 1)
        zid, rid = parts[0], parts[1]
        wait = await q.message.edit_text("⏳ حذف...")
        try:
            cf_del(uid, f"/zones/{zid}/workers/routes/{rid}")
            await wait.edit_text("✅ حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Workers", callback_data=f"wk_{zid}")]]))
        except Exception as e:
            await wait.edit_text(f"❌ {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"wk_{zid}")]]))
        return

# — Worker upload/edit conversation —
async def wk_edit_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    parts = q.data.replace("wke_", "").split("_", 1)
    zid = parts[0]
    name = parts[1] if len(parts) > 1 else ""
    s = get_s(uid)
    ctx.user_data["wk_zid"] = zid
    ctx.user_data["wk_name"] = name
    ctx.user_data["wk_acc"] = s.get("cur_zone", {}).get("account", {}).get("id", "")

    if name:
        await q.message.edit_text(
            f"📝 <b>ادیت Worker: {name}</b>\n\nکد جاوااسکریپت جدید رو بفرست.\nیا یه فایل <code>.js</code> آپلود کن.",
            parse_mode="HTML"
        )
    else:
        await q.message.edit_text(
            "📝 <b>آپلود Worker جدید</b>\n\nاول اسم Worker رو بفرست (مثلاً <code>my-worker</code>).\nبعد کد رو می‌فرستی.",
            parse_mode="HTML"
        )
        ctx.user_data["wk_need_name"] = True
    return WK_CODE

async def wk_edit_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    zid = ctx.user_data.get("wk_zid", "")
    acc_id = ctx.user_data.get("wk_acc", "")
    name = ctx.user_data.get("wk_name", "")

    # If we need name first
    if ctx.user_data.get("wk_need_name"):
        if update.message.document:
            # File sent without name
            await update.message.reply_text("اول اسم Worker رو بفرست:")
            return WK_CODE
        name = update.message.text.strip().replace(" ", "-").lower()
        ctx.user_data["wk_name"] = name
        ctx.user_data["wk_need_name"] = False
        await update.message.reply_text(
            f"نام: <code>{name}</code>\n\nحالا کد جاوااسکریپت رو بفرست یا فایل <code>.js</code> آپلود کن.",
            parse_mode="HTML"
        )
        return WK_CODE

    # Get code from text or file
    code = None
    if update.message.document:
        f = await update.message.document.get_file()
        ba = await f.download_as_bytearray()
        code = ba.decode("utf-8", errors="replace")
    elif update.message.text:
        code = update.message.text

    if not code:
        await update.message.reply_text("❌ کدی دریافت نشد.")
        return ConversationHandler.END

    wait = await update.message.reply_text("⏳ آپلود و پابلیش...")

    try:
        # Upload/update worker script
        h = cf_h(uid).copy()
        h["Content-Type"] = "application/javascript"
        r = requests.put(
            f"{CF_API}/accounts/{acc_id}/workers/scripts/{name}",
            headers=h, data=code.encode("utf-8"), timeout=30
        )
        rd = r.json()
        if rd.get("success"):
            await wait.edit_text(
                f"✅ Worker <b>{name}</b> آپلود و پابلیش شد!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Workers", callback_data=f"wk_{zid}")]])
            )
        else:
            err = rd.get("errors", [{}])[0].get("message", "خطای ناشناخته")
            await wait.edit_text(
                f"❌ {err}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"wk_{zid}")]])
            )
    except Exception as e:
        await wait.edit_text(
            f"❌ {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"wk_{zid}")]])
        )
    return ConversationHandler.END
# ━━━━━━━━━━ EMAIL ROUTING ━━━━━━━━━━
async def email_routing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    d = q.data

    # Toggle email routing enable/disable
    if d.startswith("emt_"):
        zid = d.replace("emt_", "").split("_")[0]
        val = d.split("_")[-1]  # enable or disable
        wait = await q.message.edit_text("⏳ ...")
        endpoint = "enable" if val == "enable" else "disable"
        r = cf_post(uid, f"/zones/{zid}/email/routing/{endpoint}", {})
        if r.get("success"):
            await wait.edit_text(f"✅ Email Routing {endpoint}d.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Email", callback_data=f"em_{zid}")]]))
        else:
            err = r.get("errors", [{}])[0].get("message", "خطا")
            await wait.edit_text(f"❌ {err}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"em_{zid}")]]))
        return

    # Delete email rule
    if d.startswith("emd_"):
        parts = d.replace("emd_", "").split("_", 1)
        zid, rid = parts[0], parts[1]
        wait = await q.message.edit_text("⏳ حذف...")
        try:
            cf_del(uid, f"/zones/{zid}/email/routing/rules/{rid}")
            await wait.edit_text("✅ حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Email", callback_data=f"em_{zid}")]]))
        except Exception as e:
            await wait.edit_text(f"❌ {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"em_{zid}")]]))
        return

    # List email routing rules
    zid = d.replace("em_", "")
    s = get_s(uid)
    zone = s.get("cur_zone", {})
    wait = await q.message.edit_text("⏳ دریافت Email Routing...")

    # Get email routing settings
    r_settings = cf_get(uid, f"/zones/{zid}/email/routing")
    # Get rules
    r_rules = cf_get(uid, f"/zones/{zid}/email/routing/rules")

    enabled = False
    if r_settings.get("success") and r_settings.get("result"):
        enabled = r_settings["result"].get("enabled", False)

    st = "🟢 فعال" if enabled else "🔴 غیرفعال"
    text = f"📧 <b>Email Routing — {zone.get('name','')}</b>\n\nوضعیت: {st}\n\n"

    btns = []
    if enabled:
        btns.append([InlineKeyboardButton("🔴 غیرفعال کردن", callback_data=f"emt_{zid}_disable")])
    else:
        btns.append([InlineKeyboardButton("🟢 فعال کردن", callback_data=f"emt_{zid}_enable")])

    rules = r_rules.get("result", []) if r_rules.get("success") else []
    if rules:
        text += "<b>قوانین:</b>\n"
        for i, rule in enumerate(rules):
            matchers = rule.get("matchers", [])
            actions = rule.get("actions", [])
            match_str = ", ".join(m.get("value", m.get("type", "")) for m in matchers)
            action_str = ", ".join(a.get("value", [a.get("type", "")])[0] if isinstance(a.get("value"), list) else str(a.get("value", a.get("type", ""))) for a in actions)
            st_r = "🟢" if rule.get("enabled") else "🔴"
            text += f"{i+1}. {st_r} <code>{match_str}</code> → {action_str}\n"
            btns.append([InlineKeyboardButton(f"🗑 {i+1}: {match_str[:25]}", callback_data=f"emd_{zid}_{rule['tag']}")])
    else:
        text += "📭 هیچ قانونی وجود نداره.\n"

    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"zone_{zid}")])
    await wait.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# ━━━━━━━━━━ DEPLOY VIA SSH ━━━━━━━━━━
DEPLOY_STEPS = [
    ("STEP_1", 10, "🔌 اتصال SSH برقرار شد"),
    ("STEP_2", 25, "🐳 نصب Docker"),
    ("STEP_3", 40, "📥 دانلود فایل‌ها از GitHub"),
    ("STEP_4", 55, "⚙️ ساخت فایل تنظیمات"),
    ("STEP_5", 75, "🔨 ساخت Docker image"),
    ("STEP_6", 90, "🚀 اجرای کانتینر"),
    ("DEPLOY_OK", 100, "✅ نصب کامل شد!"),
]

DEPLOY_SCRIPT = '''#!/bin/bash
set -e
echo "STEP_2"
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh >/dev/null 2>&1
fi
if ! docker compose version &>/dev/null 2>&1; then
  apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq docker-compose-plugin >/dev/null 2>&1 || true
fi
echo "STEP_3"
mkdir -p /opt/eazyflare && cd /opt/eazyflare
REPO="https://raw.githubusercontent.com/Schmi7zz/EazyFlare/main"
curl -fsSL "$REPO/bot.py" -o bot.py
curl -fsSL "$REPO/Dockerfile" -o Dockerfile
curl -fsSL "$REPO/docker-compose.yml" -o docker-compose.yml
# Create minimal requirements (no paramiko needed on target)
cat > requirements.txt << REQEOF
python-telegram-bot==21.5
requests>=2.31.0
REQEOF
echo "STEP_4"
cat > .env << ENVEOF
BOT_TOKEN={bot_token}
WEBAPP_URL={webapp_url}
ENVEOF
[ -f users.json ] || echo '{{"users":{{}},"cf_logins":{{}}}}' > users.json
echo "STEP_5"
docker compose down 2>/dev/null || true
docker compose build --no-cache 2>&1 | tail -1
echo "STEP_6"
docker compose up -d
echo "DEPLOY_OK"
'''

def _make_progress_bar(pct):
    filled = int(pct / 5)
    empty = 20 - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {pct}%"

def _ssh_connect(data):
    """Create and return SSH client."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_args = {
        "hostname": data["dep_host"],
        "port": data["dep_port"],
        "username": data["dep_user"],
        "timeout": 15,
    }
    if data.get("dep_auth_method") == "pass":
        connect_args["password"] = data["dep_password"]
    else:
        key_data = data.get("dep_key_data", "")
        key_file = io.StringIO(key_data)
        try:
            pkey = paramiko.RSAKey.from_private_key(key_file)
        except:
            key_file.seek(0)
            try:
                pkey = paramiko.Ed25519Key.from_private_key(key_file)
            except:
                key_file.seek(0)
                pkey = paramiko.ECDSAKey.from_private_key(key_file)
        connect_args["pkey"] = pkey
    client.connect(**connect_args)
    return client

async def deploy_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    if not HAS_PARAMIKO:
        await msg.reply_text("❌ پکیج paramiko نصب نیست.\n<code>pip install paramiko</code>", parse_mode="HTML")
        return ConversationHandler.END
    text = (
        "🚀 <b>نصب EazyFlare روی سرور شخصی</b>\n\n"
        "با این قابلیت می‌تونید ربات EazyFlare خودتون رو روی سرور شخصی‌تون نصب کنید.\n\n"
        "📋 <b>پیش‌نیازها:</b>\n"
        "• یک سرور لینوکسی (Ubuntu/Debian)\n"
        "• دسترسی SSH (IP + رمز یا کلید)\n"
        "• توکن ربات تلگرام (از @BotFather)\n\n"
        "آدرس IP سرور را بفرستید:"
    )
    if update.callback_query:
        await msg.edit_text(text, parse_mode="HTML")
    else:
        await msg.reply_text(text, parse_mode="HTML")
    logger.info(f"Deploy started, returning DEP_HOST={DEP_HOST}")
    return DEP_HOST

async def deploy_host(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    logger.info(f"deploy_host called with: {update.message.text}")
    ctx.user_data["dep_host"] = update.message.text.strip()
    await update.message.reply_text("پورت SSH (پیش‌فرض 22):\n\nاگه 22 هست فقط <code>22</code> بفرست.", parse_mode="HTML")
    return DEP_PORT

async def deploy_port(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["dep_port"] = int(update.message.text.strip())
    except:
        ctx.user_data["dep_port"] = 22
    await update.message.reply_text("یوزرنیم SSH (معمولاً <code>root</code>):", parse_mode="HTML")
    return DEP_USER

async def deploy_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["dep_user"] = update.message.text.strip()
    await update.message.reply_text(
        "روش احراز هویت؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 رمز عبور", callback_data="dauth_pass"),
             InlineKeyboardButton("🔐 کلید SSH", callback_data="dauth_key")]
        ])
    )
    return DEP_AUTH

async def deploy_auth_method(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    method = q.data.replace("dauth_", "")
    ctx.user_data["dep_auth_method"] = method
    if method == "pass":
        await q.message.edit_text("🔑 رمز عبور SSH:")
        return DEP_PASS
    else:
        await q.message.edit_text("🔐 فایل کلید SSH (private key) رو آپلود کنید یا محتواش رو بفرستید:")
        return DEP_KEY

async def deploy_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["dep_password"] = update.message.text.strip()
    # Auto-delete password message
    try:
        await update.message.delete()
    except:
        pass
    await update.message.reply_text("🤖 توکن ربات تلگرام مقصد (از @BotFather):")
    return DEP_BOTTOKEN

async def deploy_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        f = await update.message.document.get_file()
        ba = await f.download_as_bytearray()
        ctx.user_data["dep_key_data"] = ba.decode("utf-8", errors="replace")
    else:
        ctx.user_data["dep_key_data"] = update.message.text.strip()
    # Auto-delete key message
    try:
        await update.message.delete()
    except:
        pass
    await update.message.reply_text("🤖 توکن ربات تلگرام مقصد (از @BotFather):")
    return DEP_BOTTOKEN

async def deploy_bottoken(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["dep_bottoken"] = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    await update.message.reply_text(
        "🌐 آدرس وب‌اپ (URL مینی‌اپ):\n\n"
        "اگه نمی‌خوای مینی‌اپ داشته باشی، بنویس <code>skip</code>",
        parse_mode="HTML"
    )
    return DEP_WEBAPP

async def deploy_webapp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    webapp = update.message.text.strip()
    if webapp.lower() == "skip":
        webapp = ""
    ctx.user_data["dep_webapp"] = webapp

    host = ctx.user_data["dep_host"]
    port = ctx.user_data["dep_port"]

    wait = await update.message.reply_text(
        f"⏳ <b>در حال نصب...</b>\n🖥 سرور: <code>{host}:{port}</code>",
        parse_mode="HTML"
    )

    result = await asyncio.get_event_loop().run_in_executor(None, _ssh_deploy, ctx.user_data)

    if result["success"]:
        await wait.edit_text(
            f"✅ <b>نصب موفق!</b>\n\n"
            f"🖥 سرور: <code>{host}</code>\n"
            f"📁 مسیر: <code>/opt/eazyflare</code>\n"
            f"🐳 Docker: در حال اجرا\n\n"
            f"🔧 لاگ:\n<code>docker compose -f /opt/eazyflare/docker-compose.yml logs -f</code>",
            parse_mode="HTML"
        )
    else:
        err = result["error"][:1200]
        await wait.edit_text(f"❌ <b>خطا:</b>\n<pre>{err}</pre>", parse_mode="HTML")

    for k in ["dep_password", "dep_key_data", "dep_bottoken"]:
        ctx.user_data.pop(k, None)
    return ConversationHandler.END

def _ssh_deploy(data):
    """Legacy sync deploy (used by mini app handler)."""
    try:
        client = _ssh_connect(data)
        script = DEPLOY_SCRIPT.format(
            bot_token=data["dep_bottoken"],
            webapp_url=data.get("dep_webapp", ""),
        )
        stdin, stdout, stderr = client.exec_command("bash -s", timeout=300)
        stdin.write(script)
        stdin.channel.shutdown_write()
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        client.close()
        if exit_code == 0 and "DEPLOY_OK" in out:
            return {"success": True, "output": out}
        else:
            return {"success": False, "error": f"Exit code: {exit_code}\n{err}\n{out}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def deploy_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    for k in ["dep_password", "dep_key_data", "dep_bottoken"]:
        ctx.user_data.pop(k, None)
    await update.message.reply_text("❌ لغو شد.")
    return ConversationHandler.END

def _ssh_deploy_raw(host, port, user, auth, password, key_data, script):
    """Direct SSH deploy with raw script (used by mini app)."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_args = {"hostname": host, "port": port, "username": user, "timeout": 15}
        if auth == "pass":
            connect_args["password"] = password
        else:
            key_file = io.StringIO(key_data)
            try:
                pkey = paramiko.RSAKey.from_private_key(key_file)
            except:
                key_file.seek(0)
                try:
                    pkey = paramiko.Ed25519Key.from_private_key(key_file)
                except:
                    key_file.seek(0)
                    pkey = paramiko.ECDSAKey.from_private_key(key_file)
            connect_args["pkey"] = pkey
        client.connect(**connect_args)
        stdin, stdout, stderr = client.exec_command("bash -s", timeout=120)
        stdin.write(script)
        stdin.channel.shutdown_write()
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        client.close()
        if exit_code == 0:
            return {"success": True, "output": out}
        else:
            return {"success": False, "error": f"Exit {exit_code}\n{err}\n{out}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ━━━━━━━━━━ CALLBACK ROUTER ━━━━━━━━━━
async def cb_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = update.callback_query.data
    if d == "do_help":       return await send_help(update, ctx)
    if d == "do_domains":    return await cmd_domains(update, ctx)
    if d == "do_disconnect": return await cmd_disconnect(update, ctx)
    if d.startswith("zone_"): return await zone_selected(update, ctx)
    if d.startswith("dns_"):  return await dns_list(update, ctx)
    if d.startswith("ft_"):   return await dns_filter(update, ctx)
    if d.startswith("ed_"):   return await edit_start(update, ctx)
    if d.startswith("ep_"):   return await toggle_proxy(update, ctx)
    if d.startswith("dl_"):   return await delete_confirm(update, ctx)
    if d.startswith("dx_"):   return await delete_execute(update, ctx)
    if d.startswith("ssl_") or d.startswith("sslset_"): return await ssl_settings(update, ctx)
    if d.startswith("ns_"):   return await ns_info(update, ctx)
    if d.startswith("zs_") or d.startswith("zst_"): return await zone_settings(update, ctx)
    if d.startswith("zsm_"):  return await zone_minify_toggle(update, ctx)
    if d.startswith("pr_") or d.startswith("prt_") or d.startswith("prd_"): return await page_rules(update, ctx)
    if d.startswith("wk_") or d.startswith("wkd_") or d.startswith("wkv_") or d.startswith("wks_") or d.startswith("wksx_"): return await workers_list(update, ctx)
    if d.startswith("em_") or d.startswith("emt_") or d.startswith("emd_"): return await email_routing(update, ctx)
    if d == "noop":           return await update.callback_query.answer()
    # Unhandled
    logger.warning(f"Unhandled callback: {d}")
    await update.callback_query.answer()

# ━━━━━━━━━━ MAIN ━━━━━━━━━━
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    connect_conv = ConversationHandler(
        entry_points=[
            CommandHandler("connect", connect_entry),
            CallbackQueryHandler(connect_entry, pattern="^do_connect$"),
        ],
        states={
            CONNECT_METHOD: [CallbackQueryHandler(connect_method, pattern="^m_")],
            CONNECT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_email)],
            CONNECT_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_key)],
        },
        fallbacks=[CommandHandler("cancel", connect_cancel_msg), CommandHandler("start", cmd_start)],
        per_message=False,
        allow_reentry=True,
    )

    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_start, pattern=r"^add_")],
        states={
            ADD_TYPE: [CallbackQueryHandler(add_type, pattern="^at_")],
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_content)],
            ADD_PROXY: [CallbackQueryHandler(add_proxy, pattern="^px_")],
        },
        fallbacks=[CommandHandler("cancel", connect_cancel_msg), CommandHandler("start", cmd_start)],
        per_message=False,
        allow_reentry=True,
    )

    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_content_entry, pattern=r"^ec_")],
        states={EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_content_value)]},
        fallbacks=[CommandHandler("cancel", connect_cancel_msg), CommandHandler("start", cmd_start)],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(connect_conv)
    app.add_handler(add_conv)
    app.add_handler(edit_conv)

    # Page Rule add conversation
    pr_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(pr_add_start, pattern=r"^pra_")],
        states={
            PR_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, pr_add_url)],
            PR_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, pr_add_action)],
        },
        fallbacks=[CommandHandler("cancel", connect_cancel_msg), CommandHandler("start", cmd_start)],
        per_message=False,
        allow_reentry=True,
    )
    app.add_handler(pr_conv)

    # Worker edit/upload conversation
    wk_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(wk_edit_start, pattern=r"^wke_")],
        states={
            WK_CODE: [
                MessageHandler(filters.Document.ALL, wk_edit_code),
                MessageHandler(filters.TEXT & ~filters.COMMAND, wk_edit_code),
            ],
        },
        fallbacks=[CommandHandler("cancel", connect_cancel_msg), CommandHandler("start", cmd_start)],
        per_message=False,
        allow_reentry=True,
    )
    app.add_handler(wk_conv)

    # Deploy via SSH conversation
    deploy_conv = ConversationHandler(
        entry_points=[
            CommandHandler("deploy", deploy_start),
            CallbackQueryHandler(deploy_start, pattern="^do_deploy$"),
        ],
        states={
            DEP_HOST: [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_host)],
            DEP_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_port)],
            DEP_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_user)],
            DEP_AUTH: [CallbackQueryHandler(deploy_auth_method, pattern="^dauth_")],
            DEP_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_password)],
            DEP_KEY: [
                MessageHandler(filters.Document.ALL, deploy_key),
                MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_key),
            ],
            DEP_BOTTOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_bottoken)],
            DEP_WEBAPP: [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_webapp)],
        },
        fallbacks=[CommandHandler("cancel", deploy_cancel), CommandHandler("start", cmd_start)],
        per_message=False,
        allow_reentry=True,
    )
    app.add_handler(deploy_conv)

    # Broadcast conversation (admin only)
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_send)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel), CommandHandler("start", cmd_start)],
    )
    app.add_handler(broadcast_conv)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", send_help))
    app.add_handler(CommandHandler("domains", cmd_domains))
    app.add_handler(CommandHandler("dns", cmd_domains))
    app.add_handler(CommandHandler("disconnect", cmd_disconnect))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Standalone callback handlers (must work even during conversations)
    app.add_handler(CallbackQueryHandler(send_help, pattern="^do_help$"))
    app.add_handler(CallbackQueryHandler(cmd_disconnect, pattern="^do_disconnect$"))
    app.add_handler(CallbackQueryHandler(cmd_domains, pattern="^do_domains$"))

    # Handle deploy data from mini app
    async def handle_webapp_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        data = update.effective_message.web_app_data.data
        try:
            payload = json.loads(data)
            if payload.get("action") == "deploy":
                d = payload["data"]
                wait = await update.message.reply_text("⏳ در حال اتصال و نصب...")
                dep_data = {
                    "dep_host": d["host"],
                    "dep_port": d["port"],
                    "dep_user": d["user"],
                    "dep_auth_method": d["auth"],
                    "dep_password": d.get("pass", ""),
                    "dep_key_data": d.get("key", ""),
                    "dep_bottoken": "",
                    "dep_webapp": "",
                }
                # Script already has tokens embedded
                result = await asyncio.get_event_loop().run_in_executor(
                    None, _ssh_deploy_raw, d["host"], d["port"], d["user"], d["auth"], d.get("pass",""), d.get("key",""), d["script"]
                )
                if result["success"]:
                    await wait.edit_text(f"✅ <b>نصب موفق!</b>\n\n🖥 سرور: <code>{d['host']}</code>\n📁 مسیر: /opt/eazyflare", parse_mode="HTML")
                else:
                    await wait.edit_text(f"❌ <b>خطا:</b>\n<pre>{result['error'][:1500]}</pre>", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(CallbackQueryHandler(cb_router))

    async def post_init(application):
        await application.bot.set_my_commands([
            BotCommand("start", "شروع"),
            BotCommand("connect", "اتصال به Cloudflare"),
            BotCommand("domains", "لیست دامنه‌ها"),
            BotCommand("dns", "مدیریت DNS"),
            BotCommand("disconnect", "قطع اتصال"),
            BotCommand("help", "راهنما"),
        ])
        if WEBAPP_URL:
            try:
                await application.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="📊 Dashboard", web_app=WebAppInfo(url=WEBAPP_URL)))
            except Exception as e:
                logger.warning(f"Menu button: {e}")

    app.post_init = post_init
    logger.info("🚀 EazyFlare Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
