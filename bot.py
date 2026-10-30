# ================= bot.py | FULL + LIVE PRICE FEATURE =================
import os, sqlite3, random, time, re, requests
from flask import Flask, request
import telebot
from telebot import types

TOKEN = os.environ.get("TOKEN", "9083948930:AAHKKPdwzYbfIiG9HVZl4yyiQ2al4H0lwWE")
ADMIN_ID = 5323764088
BOT_DISPLAY_NAME = "جک اسپارو"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

group_admins_cache = {}
user_state = {}

# ================= DATABASE =================
def db():
    return sqlite3.connect("airdrop_bot.db", check_same_thread=False)

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, language TEXT DEFAULT "fa", referrer_id INTEGER, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK (id = 1), welcome_text TEXT, channel_id TEXT, channel_link TEXT, donate_wallet TEXT, donate_text TEXT, what_is_airdrop TEXT, support_id TEXT, ad_price TEXT DEFAULT "5", ref_price TEXT DEFAULT "2.5", force_join INTEGER DEFAULT 0, menu_airdrop INTEGER DEFAULT 1, menu_whatis INTEGER DEFAULT 1, menu_donate INTEGER DEFAULT 1, menu_ref INTEGER DEFAULT 1, menu_ads INTEGER DEFAULT 1, menu_support INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS airdrops (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, value TEXT, capital TEXT, tutorial TEXT, link TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS pending_payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount TEXT, status TEXT DEFAULT "pending", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS user_spam (user_id INTEGER PRIMARY KEY, last_msg TEXT, count INTEGER DEFAULT 0, last_time REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS group_settings (chat_id INTEGER PRIMARY KEY, fun_enabled INTEGER DEFAULT 1, antilink INTEGER DEFAULT 1, antihyper INTEGER DEFAULT 1, lock_sticker INTEGER DEFAULT 0, lock_media INTEGER DEFAULT 0, welcome INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS group_vips (chat_id INTEGER, user_id INTEGER, PRIMARY KEY (chat_id, user_id))')
    c.execute("SELECT COUNT(*) FROM settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO settings (id, welcome_text, donate_wallet, donate_text, what_is_airdrop, support_id, force_join) VALUES (1,?,?,?,?,?,0)", ("به ربات مسیر پول خوش آمدید! 💰", "UQ................................", "اگر از ربات خوشت اومده حمایت کن ❤️", "🚀 ایردراپ چیست؟\n✅ Notcoin\n❌ Hamster\n\nاینجا فقط پروژه‌های معتبر + آموزش می‌ذاریم.", "@support"))
    conn.commit()
    conn.close()

init_db()

ALLOWED_SETTINGS = {
    "welcome_text","channel_id","channel_link","donate_wallet","donate_text",
    "what_is_airdrop","support_id","ad_price","ref_price","force_join",
    "menu_airdrop","menu_whatis","menu_donate","menu_ref","menu_ads","menu_support"
}

def get_setting(key):
    if key not in ALLOWED_SETTINGS: return None
    conn = db(); c = conn.cursor()
    c.execute(f"SELECT {key} FROM settings WHERE id=1")
    row = c.fetchone(); conn.close()
    return row[0] if row else None

def set_setting(key, value):
    if key not in ALLOWED_SETTINGS: return
    conn = db(); c = conn.cursor()
    c.execute(f"UPDATE settings SET {key}=? WHERE id=1", (value,))
    conn.commit(); conn.close()

def get_ref_count(uid):
    conn = db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (uid,))
    n = c.fetchone()[0]; conn.close(); return n

def ensure_group_row(chat_id):
    conn = db(); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO group_settings (chat_id) VALUES (?)", (chat_id,))
    conn.commit(); conn.close()

def get_group_flags(chat_id):
    ensure_group_row(chat_id)
    conn = db(); c = conn.cursor()
    c.execute("SELECT fun_enabled, antilink, antihyper, lock_sticker, lock_media, welcome FROM group_settings WHERE chat_id=?", (chat_id,))
    row = c.fetchone(); conn.close()
    return {"fun": bool(row[0]), "antilink": bool(row[1]), "antihyper": bool(row[2]), "lock_sticker": bool(row[3]), "lock_media": bool(row[4]), "welcome": bool(row[5])}

def set_group_flag(chat_id, field, value):
    ensure_group_row(chat_id)
    conn = db(); c = conn.cursor()
    c.execute(f"UPDATE group_settings SET {field}=? WHERE chat_id=?", (1 if value else 0, chat_id))
    conn.commit(); conn.close()

def is_vip(chat_id, uid):
    conn = db(); c = conn.cursor()
    c.execute("SELECT 1 FROM group_vips WHERE chat_id=? AND user_id=?", (chat_id, uid))
    r = c.fetchone(); conn.close(); return bool(r)

def add_vip(chat_id, uid):
    conn = db(); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO group_vips (chat_id, user_id) VALUES (?,?)", (chat_id, uid))
    conn.commit(); conn.close()

def remove_vip(chat_id, uid):
    conn = db(); c = conn.cursor()
    c.execute("DELETE FROM group_vips WHERE chat_id=? AND user_id=?", (chat_id, uid))
    conn.commit(); conn.close()

def is_joined(uid):
    ch = get_setting("channel_id")
    if not ch or str(get_setting("force_join")) == "0": return True
    try:
        return bot.get_chat_member(ch, uid).status in ("member", "administrator", "creator")
    except: return True

def force_join_msg(uid):
    ch = get_setting("channel_id") or ""
    link = get_setting("channel_link")
    if not link and ch: link = f"https://t.me/{ch.replace('@','')}"
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("✅ جوین شدم", callback_data="check_join"))
    if link: mk.add(types.InlineKeyboardButton("📢 ورود به کانال", url=link))
    bot.send_message(uid, "🔒 برای استفاده از ربات اول عضو کانال شو:", reply_markup=mk)

def refresh_group_admins(chat_id):
    try:
        ids = {a.user.id for a in bot.get_chat_administrators(chat_id)}
        group_admins_cache[chat_id] = ids
        return ids
    except: return group_admins_cache.get(chat_id, set())

def is_group_admin(chat_id, uid):
    if uid == ADMIN_ID: return True
    if chat_id not in group_admins_cache: refresh_group_admins(chat_id)
    return uid in group_admins_cache.get(chat_id, set())

def mute_user(chat_id, uid, minutes=None):
    try:
        until = int(time.time()) + (60*60*24*365*10) if minutes is None else int(time.time()) + int(minutes)*60
        bot.restrict_chat_member(chat_id, uid, until_date=until, permissions=types.ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_send_other_messages=False, can_add_web_page_previews=False))
        return True, "دائمی" if minutes is None else f"{minutes} دقیقه"
    except Exception as e: return False, str(e)

def unmute_user(chat_id, uid):
    try:
        bot.restrict_chat_member(chat_id, uid, permissions=types.ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True, can_send_polls=True, can_invite_users=True))
        return True, "OK"
    except Exception as e: return False, str(e)

def ban_user(chat_id, uid):
    try: bot.ban_chat_member(chat_id, uid); return True, "OK"
    except Exception as e: return False, str(e)

def kick_user(chat_id, uid):
    try:
        bot.ban_chat_member(chat_id, uid); time.sleep(0.7)
        for _ in range(3):
            try:
                bot.unban_chat_member(chat_id, uid, only_if_banned=True); return True, "OK"
            except TypeError:
                bot.unban_chat_member(chat_id, uid); return True, "OK"
            except: time.sleep(0.7)
        return False, "خطا"
    except Exception as e: return False, str(e)

# ================= LIVE PRICE FUNCTION =================
def fetch_prices():
    try:
        # Crypto prices in USD (CoinGecko - free, no key)
        crypto_ids = "bitcoin,ethereum,tether,the-open-network,tron,tether-gold"
        cg_url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_ids}&vs_currencies=usd"
        cg_resp = requests.get(cg_url, timeout=8)
        cg_data = cg_resp.json() if cg_resp.status_code == 200 else {}

        # USD to IRR rate (ExchangeRate-API - free)
        rate_resp = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=8)
        rate_data = rate_resp.json() if rate_resp.status_code == 200 else {}
        irr_rate = rate_data.get("rates", {}).get("IRR", 0)

        if not irr_rate or irr_rate == 0:
            irr_rate = 850000  # fallback approximate Toman base (~85k toman per USD historically approximate, adjust if needed)

        # Helper to format Toman
        def fmt(num):
            if not num: return "نامشخص"
            val = float(num) * irr_rate / 10  # USD -> Toman
            return f"{int(val):,}"

        out = "📊 <b>قیمت لحظه‌ای (تومان)</b>\n\n"
        # Bitcoin
        btc = cg_data.get("bitcoin", {}).get("usd")
        out += f"₿ بیت‌کوین: <b>{fmt(btc)}</b> تومان\n"
        # Ethereum
        eth = cg_data.get("ethereum", {}).get("usd")
        out += f"♦ اتریوم: <b>{fmt(eth)}</b> تومان\n"
        # TON (The Open Network)
        ton = cg_data.get("the-open-network", {}).get("usd")
        out += f"💎 تون‌کوین: <b>{fmt(ton)}</b> تومان\n"
        # Tron
        trx = cg_data.get("tron", {}).get("usd")
        out += f"🔺 ترون: <b>{fmt(trx)}</b> تومان\n"
        # Tether
        usdt = cg_data.get("tether", {}).get("usd")
        out += f"💵 تتر: <b>{fmt(usdt)}</b> تومان\n"
        # Gold (Tether Gold XAUT)
        gold = cg_data.get("tether-gold", {}).get("usd")
        out += f"🟡 طلا (هر اونس): <b>{fmt(gold)}</b> تومان\n"
        out += "\n⚡ منبع: CoinGecko + نرخ آزاد"
        return out
    except Exception as e:
        return f"❌ خطا در دریافت قیمت: {str(e)}\nلطفاً دوباره تلاش کنید."

# ================= FUN REPLIES =================
RUDE = ["بازم؟ خسته‌ام کردی 😒","مغزت کجاست؟","اسپم نکن ","دیگه بسه 😂","سوال تکراری=بی‌جواب","دوباره؟ جدی؟","اعصابم خرد شد","غلام تو نیستم","یه بار دیگه جواب نمی‌دم 😈","شلوغ نکن"]
LAUGH = ["آروم‌تر بخند، کشتی داره سوراخ می‌شه 😂","این‌قدر نخند؛ همستر فکر می‌کنه لیست شده 🤣","خنده‌ات ثبت شد؛ مالیاتش یک TON می‌شه 😌","کی جوک گفت؟ منم بخندم یا قیمت‌ها؟ 😂","صدای خنده‌ات تا بلاک‌چین رفت 🤣","بخند؛ فعلاً بازار موجودی ولتت رو ندیده 😂","این خنده بوی سود خیالی می‌ده 😏","آروم‌تر! نهنگ‌های بازار از خواب بیدار می‌شن 😂","تو بخند، من می‌رم ببینم چرا ولت هنوز خالیه 😂","خنده آزاده؛ ولی اسپم مالیات داره 😎"]
GREET_SALAM = ["سلام‌سلام 😎","علیک سلام","سلام رفیق","هی سلام!","سلام قشنگ","سلام جک اسپارو ☠️","سلام علیکم 😂","سلام جنگجو","بفرما","سلام چه خبر؟"]
GREET_KHOBI = ["تو خوبی من عالی‌ام","بدک نیستم","قوی مثل شیر 🦁","مثل ساعت","بهتر از تو 😌","در اوج","خوبم شکر","فوق‌العاده","می‌ترکونم","اوکیم"]
GREET_CHETORI = ["مثل پنبه","عالی تو چطوری؟","می‌ترکونم","بهترین حالت","خوبم تو بگو","روی کشتی ☠️","درجه یک","اوکی","بد نیست","عالی‌ام"]
GREET_CHEKHABAR = ["سلامتی تو بگو","دارم می‌ترکونم","خبر=ایردراپ","آروم 😎","خبرت چیه؟","پول و ایردراپ","زنده‌ایم","خبر خوب در راهه","گروه فعاله","جک اسپارو آنلاین"]
GREET_HAL = ["حالم طلاست","از تو بهتره 😎","در اوج","آماده جنگ","آروم خطرناک","ساعت سوئیسی","خوبم شکر","نپرس 😂","می‌چرخم","تیک‌تاک"]
GREET_SOBH = ["صبح بخیر جنگجو ☀️","صبح بخیر بترکون","صبح بخیر قهرمان","روزت پرپول","از جک اسپارو ☀️","بیدار شو","صبح بخیر رفیق","روز بزرگه","نگه‌دار","صبح بخیر"]
GREET_SHAB = ["شب بخیر 😴","شب خوش 🌙","برو بخواب","شب بخیر کاپیتان","رویاهات پول","فردا بترکون","شب آرام","شب بخیر رفیق","بای","شب خوش"]
GREET_ROOZ = ["روزت خوش","روز بخیر","بترکون امروز","روز پرپول","روز قشنگ","روز خوش رفیق","فتح امروز","روزت مبارک","یاعلی","بریم"]
NAME_R = ["جک اسپارو در خدمته ☠️","کاپیتان جک اسپارو","صدا زدی اومدم","اینجام","افسانه حاضر","کاپیتان!","دزد دریایی ایردراپ 😂","پیداشدم","من جک اسپارو‌ام","بله قربان"]
INTRO_R = [f"من <b>{BOT_DISPLAY_NAME}</b> هستم، ربات مسیر پول ☠️", f"اسمم {BOT_DISPLAY_NAME}؛ فان/ایردراپ/مدیریت", f"{BOT_DISPLAY_NAME} در خدمته 😎", "رباتم اسمم جک اسپارو", "معرفی تموم، بگو چی می‌خوای", "نیمه‌وقت دزد دریایی تمام‌وقت ربات", "بپر تو کشتی", "رسمی مسیر پول", "من جک اسپارو‌ام", "ربات مسیر پول"]
SLEEP_R = ["برو بخواب 😴","لالایی ایردراپ؟","مواظبه","قبل سایلنت بخواب 😂","اسپم نکن","فردا بیدار شو","ززیی...","قهوه بزن","شب بخیر 😈","بالش"]
LOVE_R = ["به ایردراپ بگو ","قلب نرم‌افزاری","عشق=هولد تون 💀","فالش","زیرمجموعه بهتر","فقط ولت","عاشق ربات 😂","منطق رفت","عاشق توکن","ربات بهتر"]
HATE_R = ["صف متنفرا 😎","حقوق ثابت","لاگ شد","بلاک احساسی","اسپم نکن","توجهه 😂","از اسپمر متنفرم","خنک شدی؟","دشمن رسمی","باشه"]
DOING_R = ["ایردراپ می‌پاشم","مواظب گروه","کاپیتانی ☠️","منتظر کی فلانه","لاگ","کار رباتی","پول","آنلاین خطرناک","پنل","خواب"]
MUSIC_R = ["با این بالا نمیای 😂","آهنگ قشنگ ایردراپ قشنگ‌تر","دیسکو تموم","مغز کرخ","پامپ نیست","نمی‌رقصم","صدا بده","ولت پر نمیشه","اسپم نکن","قطع ️"]
POOP_R = ["بهداشت 🤢","تاریخچه ننگ ","شخصی ببر","شوکه","یه جا دیگه","گند نزن","ادب","افتضاح","پاک کن","حد دارم 😷"]
WHO_F = ["خودتی 😂","مظنونید 🔫","۱۰٪ تو","دوربین","پیدا کنید","نمیدونم","ساکت‌ها","برو","قطعا تو","نمی‌گم"]
WHO_G = ["تو نیستی ","من قشنگم","متوسطید","هیچکس","سخت","آینه","ادمین","ربات","مدلینگ نیست","بعدا"]
WHO_B = ["فقط من","تو پیام دادی","من و تو","بقیه خواب","جک اسپارو","شب‌زنده‌دار","آنلاین‌ها","ادمین","بیداری؟","قهوه"]
WHO_K = ["تقریبا همه 😴","تو بیداری","من نمی‌خوابم","ساکت‌ها","لیست ندارم","جواب نمیده","شب‌خیر","نمیگم","حدس بزن","ززی"]

def check_spam(uid, text):
    now = time.time()
    conn = db(); c = conn.cursor()
    c.execute("SELECT last_msg, count, last_time FROM user_spam WHERE user_id=?", (uid,))
    row = c.fetchone()
    if row:
        last_msg, count, last_time = row
        if text == last_msg and now - last_time < 90:
            count += 1
            c.execute("UPDATE user_spam SET count=?, last_time=? WHERE user_id=?", (count, now, uid))
            conn.commit(); conn.close()
            if count >= 2: return random.choice(RUDE)
            return None
        c.execute("UPDATE user_spam SET last_msg=?, count=1, last_time=? WHERE user_id=?", (text, now, uid))
    else:
        c.execute("INSERT OR REPLACE INTO user_spam (user_id, last_msg, count, last_time) VALUES (?,?,1,?)", (uid, text, now))
    conn.commit(); conn.close()
    return None

# ================= MENUS =================
def show_main_menu(uid):
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # ✅ دکمه قیمت لحظه‌ای اضافه شد
    if get_setting("menu_airdrop"): mk.add("🎁 لیست ایردراپ‌ها")
    if get_setting("menu_whatis"): mk.add("❓ ایردراپ چیست؟")
    if get_setting("menu_donate"): mk.add("💰 حمایت مالی")
    if get_setting("menu_ref"): mk.add("🤝 زیرمجموعه‌گیری")
    if get_setting("menu_ads"): mk.add("💎 تبلیغات / ارتقا لینک")
    # ✅ دکمه جدید قیمت لحظه‌ای
    mk.add("💲 قیمت لحظه‌ای")
    if get_setting("menu_support"): mk.add("💬 پشتیبانی")
    if uid == ADMIN_ID: mk.add("⚙️ پنل مدیریت")
    bot.send_message(uid, get_setting("welcome_text") or "خوش آمدید", reply_markup=mk)

def cancel_kb():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True)
    mk.add("❌ کنسل")
    return mk

# ================= HANDLERS =================
@bot.message_handler(commands=["start"])
def start(m):
    if m.chat.type != "private":
        return bot.reply_to(m, f"پیوی استارت بزن. من {BOT_DISPLAY_NAME} هستم.")
    uid = m.chat.id
    args = m.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != uid else None
    conn = db(); c = conn.cursor()
    c.execute("SELECT language FROM users WHERE user_id=?", (uid,))
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, referrer_id) VALUES (?,?)", (uid, ref))
        conn.commit()
        mk = types.InlineKeyboardMarkup()
        mk.row(types.InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa"), types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"))
        bot.send_message(uid, "زبان را انتخاب کنید:", reply_markup=mk)
    else:
        if not is_joined(uid): force_join_msg(uid)
        else: show_main_menu(uid)
    conn.close()

@bot.callback_query_handler(func=lambda c: c.data.startswith("lang_"))
def lang_cb(c):
    lang = "fa" if c.data == "lang_fa" else "en"
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE users SET language=? WHERE user_id=?", (lang, c.message.chat.id))
    conn.commit(); conn.close()
    try: bot.delete_message(c.message.chat.id, c.message.message_id)
    except: pass
    if not is_joined(c.message.chat.id): force_join_msg(c.message.chat.id)
    else: show_main_menu(c.message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def join_cb(c):
    if is_joined(c.message.chat.id):
        bot.answer_callback_query(c.id, "✅ تأیید شد")
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass
        show_main_menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id, "❌ هنوز عضو نشدی", show_alert=True)

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "❓ ایردراپ چیست؟")
def p_what(m):
    if not is_joined(m.chat.id): return force_join_msg(m.chat.id)
    bot.send_message(m.chat.id, get_setting("what_is_airdrop") or "-")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "💰 حمایت مالی")
def p_don(m):
    if not is_joined(m.chat.id): return force_join_msg(m.chat.id)
    bot.send_message(m.chat.id, f"{get_setting('donate_text')}\n\n💳 <code>{get_setting('donate_wallet')}</code>")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "💬 پشتیبانی" and m.chat.id != ADMIN_ID)
def p_sup(m):
    bot.send_message(m.chat.id, f"پشتیبانی: {get_setting('support_id')}")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "🤝 زیرمجموعه‌گیری")
def p_ref(m):
    if not is_joined(m.chat.id): return force_join_msg(m.chat.id)
    try: bot_user = bot.get_me().username
    except: bot_user = "Bot"
    link = f"https://t.me/{bot_user}?start={m.chat.id}"
    bot.send_message(m.chat.id, f"🔗 لینک شما:\n<code>{link}</code>\n\n👥 زیرمجموعه: <b>{get_ref_count(m.chat.id)}</b>")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "🎁 لیست ایردراپ‌ها")
def p_air(m):
    if not is_joined(m.chat.id): return force_join_msg(m.chat.id)
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, title, value FROM airdrops ORDER BY id DESC")
    rows = c.fetchall(); conn.close()
    if not rows: return bot.send_message(m.chat.id, "ایردراپی نیست.")
    mk = types.InlineKeyboardMarkup()
    for r in rows: mk.add(types.InlineKeyboardButton(f"{r[1]} | {r[2]}", callback_data=f"air_{r[0]}"))
    bot.send_message(m.chat.id, "📋 لیست ایردراپ‌ها:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("air_"))
def air_cb(c):
    aid = int(c.data.split("_")[1])
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT title, value, capital, tutorial, link FROM airdrops WHERE id=?", (aid,))
    r = cur.fetchone(); conn.close()
    if r: bot.send_message(c.message.chat.id, f"🎯 <b>{r[0]}</b>\n\n💰 {r[1]}\n💵 سرمایه: {r[2]}\n\n📚 {r[3]}\n\n🔗 {r[4]}")

# ✅ هندلر جدید قیمت لحظه‌ای
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "💲 قیمت لحظه‌ای")
def p_price(m):
    # کاربر باید عضو کانال باشه؟ (اختیاری) اینجا بدون اجبار می‌فرستیم
    bot.send_chat_action(m.chat.id, "typing")
    msg = fetch_prices()
    bot.send_message(m.chat.id, msg, parse_mode="HTML")

# ✅ وقتی تو گروه "ارز" نوشته می‌شه، قیمت بده
@bot.message_handler(func=lambda m: m.chat.type in ["group","supergroup"], content_types=["text"])
def group_text(m):
    chat_id, uid = m.chat.id, m.from_user.id
    raw = m.text or ""; text = raw.lower().strip()
    flags = get_group_flags(chat_id)

    # ✅ اگر کاربر "ارز" نوشت در گروه -> قیمت لحظه‌ای بده
    if "ارز" in text:
        bot.send_chat_action(chat_id, "typing")
        bot.send_message(chat_id, fetch_prices(), parse_mode="HTML")

    # بقیه منطق گروه (فان، ادمین و غیره)
    vip = is_vip(chat_id, uid)
    if text in ["پنل","panel","/panel"]:
        if not is_group_admin(chat_id, uid): return bot.reply_to(m, "⛔ فقط ادمین")
        refresh_group_admins(chat_id)
        return bot.reply_to(m, f"️ <b>پنل {BOT_DISPLAY_NAME}</b>", reply_markup=panel_kb(chat_id))

    admin_cmds = ["سکوت","/mute","حذف سکوت","/unmute","بن","/ban","حذف","/kick","افزودن ویژه","حذف ویژه"]
    if any(text.startswith(x) for x in admin_cmds) or text in ["بن","حذف","افزودن ویژه","حذف ویژه"]:
        if not is_group_admin(chat_id, uid): return bot.reply_to(m, "⛔ فقط ادمین بات/گروه")
        if not m.reply_to_message: return bot.reply_to(m, "روی پیام کاربر <b>ریپلای</b> کن.")
        target = m.reply_to_message.from_user.id
        tname = m.reply_to_message.from_user.first_name or "کاربر"
        if is_group_admin(chat_id, target) and not text.startswith("حذف ویژه"):
            if any(text.startswith(x) for x in ["سکوت","بن","حذف","/mute","/ban","/kick"]): return bot.reply_to(m, "ادمین را نمی‌شود بن/سکوت/حذف کرد.")
        if text.startswith("حذف سکوت") or text.startswith("/unmute"):
            ok, info = unmute_user(chat_id, target)
            return bot.reply_to(m, f"🔊 حذف سکوت <b>{tname}</b>" if ok else f"خطا: <code>{info}</code>")
        if text.startswith("سکوت") or text.startswith("/mute"):
            minutes = None
            parts = text.replace("/mute","سکوت").split()
            if len(parts) >= 2 and parts[1].isdigit(): minutes = max(1, min(int(parts[1]), 10080))
            ok, info = mute_user(chat_id, target, minutes)
            return bot.reply_to(m, f"🔇 سکوت {info} برای <b>{tname}</b>" if ok else f"خطا:\n<code>{info}</code>")
        if text in ["بن","/ban"] or text.startswith("بن ") or text.startswith("/ban"):
            ok, info = ban_user(chat_id, target)
            return bot.reply_to(m, f" <b>{tname}</b> بن شد." if ok else f"خطا:\n<code>{info}</code>")
        if text in ["حذف","/kick"] or text.startswith("/kick"):
            ok, info = kick_user(chat_id, target)
            return bot.reply_to(m, f"🗑 <b>{tname}</b> حذف شد." if ok else f"خطا:\n<code>{info}</code>")
        if text.startswith("افزودن ویژه"):
            add_vip(chat_id, target)
            return bot.reply_to(m, f"⭐ <b>{tname}</b> ویژه شد.")
        if text.startswith("حذف ویژه"):
            remove_vip(chat_id, target)
            return bot.reply_to(m, f"☆ ویژه <b>{tname}</b> برداشته شد.")

    if not vip and not is_group_admin(chat_id, uid):
        if flags["antilink"] and re.search(r"(t\.me/|telegram\.me/|https?://|www\.)", raw, re.I):
            try: bot.delete_message(chat_id, m.message_id)
            except: pass
            return bot.send_message(chat_id, f"🔗 لینک مجاز نیست | {m.from_user.first_name}")
        if flags["antihyper"] and m.entities:
            for e in m.entities:
                if e.type in ["url","text_link"]:
                    try: bot.delete_message(chat_id, m.message_id)
                    except: pass
                    return bot.send_message(chat_id, f"🚫 هایپرلینک حذف شد | {m.from_user.first_name}")

    if not flags["fun"]:
        return

    # Fun logic
    if any(e in raw for e in ["😂","🤣","😆","😄","😅","😁"]): return bot.reply_to(m, random.choice(LAUGH))
    rude = check_spam(uid, text)
    if rude: return bot.reply_to(m, rude)
    if any(x in text for x in ["اسمت چیه","اسمت چیست","اسمت","your name"]): return bot.reply_to(m, random.choice(NAME_R + INTRO_R))
    if "جک اسپارو" in text or "jack sparrow" in text: return bot.reply_to(m, random.choice(NAME_R))
    if any(x in text for x in ["تو کی هستی","کی هستی","با منی","خودتو معرفی"]): return bot.reply_to(m, random.choice(INTRO_R))
    if text in ["ربات","bot"] or text.startswith("ربات"): return bot.reply_to(m, random.choice(["جانم؟","بله جک اسپارو","چیکار داری؟","در خدمته ☠️","بگو"]))
    if any(k in text for k in ["سلام","salam","hi","hello"]): return bot.reply_to(m, random.choice(GREET_SALAM))
    if any(k in text for k in ["خوبی","خوب هستی","خوبی؟"]): return bot.reply_to(m, random.choice(GREET_KHOBI))
    if any(k in text for k in ["چطوری","چطوره","چطوری؟"]): return bot.reply_to(m, random.choice(GREET_CHETORI))
    if any(k in text for k in ["چه خبر","چخبر","چهخبرا","چه خبرا"]): return bot.reply_to(m, random.choice(GREET_CHEKHABAR))
    if "حالت چطوره" in text or "حالت خوبه" in text: return bot.reply_to(m, random.choice(GREET_HAL))
    if "صبح بخیر" in text: return bot.reply_to(m, random.choice(GREET_SOBH))
    if "شب بخیر" in text or "شب خوش" in text: return bot.reply_to(m, random.choice(GREET_SHAB))
    if "روز خوش" in text or "روز بخیر" in text: return bot.reply_to(m, random.choice(GREET_ROOZ))
    if "خوابم میاد" in text or "خوابمه" in text: return bot.reply_to(m, random.choice(SLEEP_R))
    if "عاشق شدم" in text or "عاشقتم" in text: return bot.reply_to(m, random.choice(LOVE_R))
    if "ازت متنفرم" in text or ("متنفرم" in text and "از" in text): return bot.reply_to(m, random.choice(HATE_R))
    if any(k in text for k in ["چیکار میکنید","چیکار می‌کنید","چکار میکنید"]): return bot.reply_to(m, random.choice(DOING_R))
    if any(k in text for k in ["ریدم","ترکیدم","گوزیدم","پاشیدم"]): return bot.reply_to(m, random.choice(POOP_R))
    if any(k in text for k in ["خندیدم","خندیدن","می‌خندم","ميخندم","خنده"]): return bot.reply_to(m, random.choice(LAUGH))
    if "کی انلاینه" in text or "کی آنلاین" in text:
        try: me_id = bot.get_me().id
        except: me_id = None
        ads = [a for a in refresh_group_admins(chat_id) if a != me_id]
        if not ads: return bot.reply_to(m, "لیست اعضا کامل در دسترس نیست.")
        pick = random.choice(list(ads))
        try:
            u = bot.get_chat_member(chat_id, pick).user
            return bot.reply_to(m, f"آنلاینِ احتمالی: <a href=\"tg://user?id={pick}\">{u.first_name or 'یکی'}</a>")
        except: return bot.reply_to(m, "یکی از ادمینا آنلاینه 😂")
    if "کی خوابه" in text: return bot.reply_to(m, random.choice(WHO_K))
    if "کی بیداره" in text: return bot.reply_to(m, random.choice(WHO_B))
    if "کی قشنگه" in text: return bot.reply_to(m, random.choice(WHO_G))
    if "کی فلانه" in text or ("کی" in text and any(x in text for x in ["ه؟","هست","بود"])): return bot.reply_to(m, random.choice(WHO_F))

@bot.message_handler(func=lambda m: m.chat.type in ["group","supergroup"], content_types=["sticker"])
def g_sticker(m):
    flags = get_group_flags(m.chat.id)
    if flags["lock_sticker"] and not is_group_admin(m.chat.id, m.from_user.id) and not is_vip(m.chat.id, m.from_user.id):
        try: bot.delete_message(m.chat.id, m.message_id)
        except: pass

@bot.message_handler(func=lambda m: m.chat.type in ["group","supergroup"], content_types=["photo","video","animation","document","voice","audio","video_note"])
def g_media(m):
    flags = get_group_flags(m.chat.id)
    if flags["lock_media"] and not is_group_admin(m.chat.id, m.from_user.id) and not is_vip(m.chat.id, m.from_user.id):
        try: bot.delete_message(m.chat.id, m.message_id)
        except: pass
        return
    if flags["fun"] and m.content_type in ["voice","audio"] and random.random() < 0.7:
        bot.reply_to(m, random.choice(MUSIC_R))

# -------------------- ADMIN PANEL --------------------
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "⚙️ پنل مدیریت" and m.chat.id == ADMIN_ID)
def admin_panel(m):
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    mk.add("➕ افزودن ایردراپ","🗑 حذف ایردراپ")
    mk.add(" پیام همگانی","📊 آمار ربات")
    mk.add("🔒 قفل جوین","🔘 روشن/خاموش دکمه‌ها")
    mk.add(" ولت","✏️ خوش‌آمد")
    mk.add("📝 ایردراپ چیست","💬 پشتیبانی")
    mk.add("📢 کانال اجباری"," لینک کانال")
    mk.add("💰 قیمت تبلیغ","💎 قیمت ارتقا")
    mk.add("🔙 منوی اصلی")
    bot.send_message(m.chat.id, "️ پنل مدیریت:", reply_markup=mk)

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "❌ کنسل" and m.chat.id == ADMIN_ID)
def cancel(m):
    user_state.pop(m.chat.id, None)
    admin_panel(m)

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "🔙 منوی اصلی" and m.chat.id == ADMIN_ID)
def back_main(m):
    user_state.pop(m.chat.id, None)
    show_main_menu(m.chat.id)

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "📊 آمار ربات" and m.chat.id == ADMIN_ID)
def stats(m):
    conn = db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); u = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM airdrops"); a = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM pending_payments WHERE status='pending'"); p = c.fetchone()[0]
    conn.close()
    bot.send_message(m.chat.id, f"📊 کاربران: {u}\n📋 ایردراپ‌ها: {a}\n⏳ انتظار پرداخت: {p}")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "➕ افزودن ایردراپ" and m.chat.id == ADMIN_ID)
def add_air(m):
    user_state[m.chat.id] = {"step":"title"}
    bot.send_message(m.chat.id, "نام ایردراپ:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.chat.id == ADMIN_ID and m.chat.id in user_state)
def admin_flow(m):
    if m.text == "❌ کنسل": return cancel(m)
    st = user_state[m.chat.id]; step = st.get("step")
    if step == "title": st["title"] = m.text; st["step"] = "value"; bot.send_message(m.chat.id, "ارزش:")
    elif step == "value": st["value"] = m.text; st["step"] = "capital"; bot.send_message(m.chat.id, "سرمایه:")
    elif step == "capital": st["capital"] = m.text; st["step"] = "tutorial"; bot.send_message(m.chat.id, "آموزش:")
    elif step == "tutorial": st["tutorial"] = m.text; st["step"] = "link"; bot.send_message(m.chat.id, "لینک:")
    elif step == "link":
        conn = db(); c = conn.cursor()
        c.execute("INSERT INTO airdrops (title,value,capital,tutorial,link) VALUES (?,?,?,?,?)", (st["title"],st["value"],st["capital"],st["tutorial"],m.text))
        conn.commit(); conn.close(); user_state.pop(m.chat.id, None)
        bot.send_message(m.chat.id, "✅ اضافه شد"); admin_panel(m)
    elif step == "broadcast":
        conn = db(); c = conn.cursor(); c.execute("SELECT user_id FROM users"); users = c.fetchall(); conn.close()
        ok = fail = 0
        for u in users:
            try: bot.send_message(u[0], m.text); ok += 1
            except: fail += 1
        user_state.pop(m.chat.id, None)
        bot.send_message(m.chat.id, f"✅ موفق: {ok} | ناموفق: {fail}"); admin_panel(m)
    elif step == "setting":
        set_setting(st["key"], m.text); user_state.pop(m.chat.id, None)
        bot.send_message(m.chat.id, "✅ ذخیره شد"); admin_panel(m)

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "🗑 حذف ایردراپ" and m.chat.id == ADMIN_ID)
def del_air(m):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id,title FROM airdrops ORDER BY id DESC")
    rows = c.fetchall(); conn.close()
    if not rows: return bot.send_message(m.chat.id, "خالی است.")
    mk = types.InlineKeyboardMarkup()
    for r in rows: mk.add(types.InlineKeyboardButton(f"❌ {r[1]}", callback_data=f"delair_{r[0]}"))
    bot.send_message(m.chat.id, "کدام را حذف می‌کنی؟", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("delair_"))
def delair_cb(c):
    if c.from_user.id != ADMIN_ID: return
    aid = int(c.data.split("_")[1])
    conn = db(); cur = conn.cursor(); cur.execute("DELETE FROM airdrops WHERE id=?", (aid,))
    conn.commit(); conn.close()
    bot.answer_callback_query(c.id, "✅ حذف شد")
    bot.edit_message_text("✅ ایردراپ حذف شد.", c.message.chat.id, c.message.message_id)

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == " پیام همگانی" and m.chat.id == ADMIN_ID)
def bcast(m):
    user_state[m.chat.id] = {"step":"broadcast"}
    bot.send_message(m.chat.id, "پیام همگانی را بنویس:", reply_markup=cancel_kb())

def ask(m, key, prompt):
    user_state[m.chat.id] = {"step":"setting","key":key}
    bot.send_message(m.chat.id, prompt, reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="💳 ولت" and m.chat.id==ADMIN_ID) def s1(m): ask(m,"donate_wallet","ولت جدید:")
@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="✏️ خوش‌آمد" and m.chat.id==ADMIN_ID) def s2(m): ask(m,"welcome_text","متن خوش‌آمد:")
@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="📝 ایردراپ چیست" and m.chat.id==ADMIN_ID) def s3(m): ask(m,"what_is_airdrop","متن:")
@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="💬 پشتیبانی" and m.chat.id==ADMIN_ID) def s4(m): ask(m,"support_id","پشتیبانی:")
@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="📢 کانال اجباری" and m.chat.id==ADMIN_ID) def s5(m): ask(m,"channel_id","آیدی کانال:")
@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="🔗 لینک کانال" and m.chat.id==ADMIN_ID) def s6(m): ask(m,"channel_link","لینک کانال:")
@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="💰 قیمت تبلیغ" and m.chat.id==ADMIN_ID) def s7(m): ask(m,"ad_price","قیمت تبلیغ:")
@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="💎 قیمت ارتقا" and m.chat.id==ADMIN_ID) def s8(m): ask(m,"ref_price","قیمت ارتقا:")

@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="🔒 قفل جوین" and m.chat.id==ADMIN_ID)
def force_t(m):
    cur = str(get_setting("force_join")); new = 0 if cur == "1" else 1
    set_setting("force_join", new)
    bot.send_message(m.chat.id, "قفل جوین " + ("فعال ✅" if new else "خاموش ❌"))

@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="🔘 روشن/خاموش دکمه‌ها" and m.chat.id==ADMIN_ID)
def menus_t_cmd(m): menus_t_logic(m.chat.id)

def menus_t_logic(chat_id):
    mk = types.InlineKeyboardMarkup()
    items = [("menu_airdrop","ایردراپ"),("menu_whatis","ایردراپ چیست"),("menu_donate","حمایت"),("menu_ref","زیرمجموعه"),("menu_ads","تبلیغات"),("menu_support","پشتیبانی")]
    for k,n in items:
        st = "✅" if get_setting(k) else "❌"
        mk.add(types.InlineKeyboardButton(f"{st} {n}", callback_data=f"tg_{k}"))
    bot.send_message(chat_id, "دکمه‌های منو:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("tg_"))
def tg_cb(c):
    if c.from_user.id != ADMIN_ID: return
    key = c.data[3:]
    set_setting(key, 0 if get_setting(key) else 1)
    bot.answer_callback_query(c.id, "OK")
    mk = types.InlineKeyboardMarkup()
    items = [("menu_airdrop","ایردراپ"),("menu_whatis","ایردراپ چیست"),("menu_donate","حمایت"),("menu_ref","زیرمجموعه"),("menu_ads","تبلیغات"),("menu_support","پشتیبانی")]
    for k,n in items:
        st = "✅" if get_setting(k) else "❌"
        mk.add(types.InlineKeyboardButton(f"{st} {n}", callback_data=f"tg_{k}"))
    try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=mk)
    except: pass

# ================= RENDER WEBHOOK (SAFE) =================
@app.route(f"/{TOKEN}/", methods=["POST"])
def webhook():
    try:
        if request.is_json:
            body = request.get_json()
            bot.process_new_updates([telebot.types.Update.de_json(body)])
            return "OK", 200
        return "Fail", 400
    except Exception as e:
        return f"Webhook error: {e}", 500

@app.route("/")
def home():
    return "🤖 ربات جک اسپارو آنلاین است ☠️", 200

@app.route("/setup")
def setup_webhook():
    try:
        bot.remove_webhook()
        url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'YOUR-APP.onrender.com')}/{TOKEN}/"
        bot.set_webhook(url=url, drop_pending_updates=True)
        return f"✅ Webhook Set! <br>URL: {url}", 200
    except Exception as e:
        msg = str(e)
        if "429" in msg or "Too Many Requests" in msg:
            return "⛔ تلگرام گفت: خیلی رفرش کردی! <b>۲ تا ۵ دقیقه صبر کن</b> و بعد فقط یک بار از مرورگر خودت لینک وبهوک رو باز کن.", 429
        if "503" in msg or "Proxy" in msg:
            return "❌ خطای اتصال به تلگرام از سرور رندر دریافت شد؛ لطفاً از مرورگر خودت لینک زیر رو برای ست کردن وبهوک استفاده کن.", 503
        return f"❌ ارور ست وبهوک: {msg}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)