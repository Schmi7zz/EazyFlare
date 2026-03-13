"""
EazyFlare — Telegram Bot + Mini App
"""

import os
import logging
import socket
import requests
from functools import wraps
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
# توکن خود را اینجا قرار دهید یا از Environment Variables استفاده کنید
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-webapp-url.com")
CF_API = "https://api.cloudflare.com/client/v4"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━ FORCE IPv4 GLOBALLY ━━━━━━━━━━
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = _ipv4_getaddrinfo

# ━━━━━━━━━━ STATES ━━━━━━━━━━
CONNECT_METHOD, CONNECT_EMAIL, CONNECT_KEY = 0, 1, 2
ADD_TYPE, ADD_NAME, ADD_CONTENT, ADD_PROXY = 10, 11, 12, 13
EDIT_VALUE = 50

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
    logged = bool(get_s(uid).get("key"))

    text = f"👋 سلام <b>{name}</b>!\n\n🔸 <b>EazyFlare</b> — مدیریت DNS کلادفلر از تلگرام\n\n"

    if logged:
        text += "✅ حساب شما متصل است.\n"
        btns = [
            [InlineKeyboardButton("🌐 دامنه‌های من", callback_data="do_domains")],
            [InlineKeyboardButton("📊 داشبورد", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("📖 راهنما", callback_data="do_help"),
             InlineKeyboardButton("🔌 قطع", callback_data="do_disconnect")],
        ]
    else:
        text += "برای شروع، حساب Cloudflare خود را متصل کنید:\n"
        btns = [
            [InlineKeyboardButton("🔐 اتصال به Cloudflare", callback_data="do_connect")],
            [InlineKeyboardButton("📖 راهنما", callback_data="do_help")],
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
        "🔹 <b>دریافت API Token:</b>\n"
        "1. dash.cloudflare.com\n"
        "2. My Profile → API Tokens\n"
        "3. Create Token → Edit zone DNS\n"
        "4. Zone DNS = Edit, All zones\n"
        "5. IP Filtering را خالی بگذارید\n"
        "6. Token را کپی کنید\n"
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

        await wait.edit_text(
            "✅ <b>اتصال برقرار شد!</b>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 دامنه‌ها", callback_data="do_domains")],
                [InlineKeyboardButton("📊 داشبورد", web_app=WebAppInfo(url=WEBAPP_URL))],
            ]))
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
        btns.append([
            InlineKeyboardButton("🔄 بروزرسانی", callback_data="do_domains"),
            InlineKeyboardButton("📊 داشبورد", web_app=WebAppInfo(url=WEBAPP_URL)),
        ])
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
        [InlineKeyboardButton("📊 داشبورد", web_app=WebAppInfo(url=f"{WEBAPP_URL}?zone={zid}"))],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="do_domains")],
    ]
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
        fbtns.append([InlineKeyboardButton("📊 داشبورد", web_app=WebAppInfo(url=f"{WEBAPP_URL}?zone={zid}"))])
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
        fallbacks=[CommandHandler("cancel", connect_cancel_msg)],
        per_message=False,
    )

    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_start, pattern=r"^add_")],
        states={
            ADD_TYPE: [CallbackQueryHandler(add_type, pattern="^at_")],
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_content)],
            ADD_PROXY: [CallbackQueryHandler(add_proxy, pattern="^px_")],
        },
        fallbacks=[CommandHandler("cancel", connect_cancel_msg)],
        per_message=False,
    )

    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_content_entry, pattern=r"^ec_")],
        states={EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_content_value)]},
        fallbacks=[CommandHandler("cancel", connect_cancel_msg)],
        per_message=False,
    )

    app.add_handler(connect_conv)
    app.add_handler(add_conv)
    app.add_handler(edit_conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", send_help))
    app.add_handler(CommandHandler("domains", cmd_domains))
    app.add_handler(CommandHandler("dns", cmd_domains))
    app.add_handler(CommandHandler("disconnect", cmd_disconnect))
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
