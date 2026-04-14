import asyncio
import os
import random
import logging
from datetime import datetime

import psycopg2
import psycopg2.extras
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN    = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]


# ─────────────────────────────────────────
# РЕАЛИСТИЧНЫЕ СУММЫ (сезонность)
# ─────────────────────────────────────────

SEASON_COEFF = {
    1: 1.35, 2: 1.30, 3: 1.10,
    4: 0.95, 5: 0.85, 6: 0.75,
    7: 0.70, 8: 0.75, 9: 0.90,
    10: 1.05, 11: 1.20, 12: 1.35,
}

BASE_BILLS = [
    {"key": "kaztel",   "ru": "АО Казахтелеком",  "kz": "АО Қазақтелеком",     "base": 8500, "vary": 0.05},
    {"key": "electric", "ru": "Электроэнергия", "kz": "Электр энергиясы", "base": 7200, "vary": 0.20},
    {"key": "water",    "ru": "Вода",           "kz": "Су",            "base": 5100, "vary": 0.30},
    {"key": "gas",      "ru": "Газ",            "kz": "Газ",                 "base": 3800, "vary": 0.15},
    {"key": "garbage",  "ru": "Вывоз мусора",   "kz": "Қоқыс шығару",    "base": 1200, "vary": 0.03},
]
def kb_start_entry():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Начать демо", callback_data="start_demo")],
        [InlineKeyboardButton("🔍 Проверить подписку", callback_data="check_sub")],
    ])

def kb_continue():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Продолжить", callback_data="continue")]
    ])
def generate_bills(month):
    coeff = SEASON_COEFF[month]
    bills = []
    for b in BASE_BILLS:
        vary   = b["vary"]
        amount = int(b["base"] * coeff * random.uniform(1 - vary, 1 + vary) / 10) * 10
        bills.append({**b, "amount": amount})
    return bills

def money(n):
    return f"{n:,}".replace(",", " ") + " ₸"

def today():
    return datetime.now().strftime("%d.%m.%Y")

# ─────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id       SERIAL PRIMARY KEY,
            user_id  BIGINT  NOT NULL,
            username TEXT,
            lang     TEXT    DEFAULT 'ru',
            paid_at  TEXT    NOT NULL,
            month    INTEGER NOT NULL,
            year     INTEGER NOT NULL,
            total    INTEGER NOT NULL,
            details  JSONB   NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id      BIGINT PRIMARY KEY,
            username     TEXT,
            lang         TEXT    DEFAULT 'ru',
            created_at   TEXT    NOT NULL,
            subscribed   BOOLEAN DEFAULT FALSE,
            trial_used   INTEGER DEFAULT 0
        )
    """)
    # Добавляем колонки если их нет (миграция для существующих баз)
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS subscribed BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS trial_used INTEGER DEFAULT 0
    """)
    conn.commit()
    conn.close()
    log.info("DB ready")

def upsert_user(uid, username, lang):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, username, lang, created_at, subscribed, trial_used)
        VALUES (%s, %s, %s, %s, FALSE, 0)
        ON CONFLICT (user_id) DO UPDATE SET username=%s, lang=%s
    """, (uid, username or "", lang, today(), username or "", lang))
    conn.commit()
    conn.close()

def get_user(uid):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = %s", (uid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def set_subscribed(uid):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE users SET subscribed = TRUE WHERE user_id = %s", (uid,))
    conn.commit()
    conn.close()

def save_payment(uid, username, lang, bills, total):
    import json
    conn = get_db()
    cur  = conn.cursor()
    now  = datetime.now()
    cur.execute("""
        INSERT INTO payments (user_id, username, lang, paid_at, month, year, total, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (uid, username or "", lang, today(), now.month, now.year, total,
          json.dumps([{"key": b["key"], "amount": b["amount"]} for b in bills])))
    conn.commit()
    conn.close()

def get_history(uid, limit=8):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        SELECT paid_at, total, month, year FROM payments
        WHERE user_id = %s ORDER BY id DESC LIMIT %s
    """, (uid, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_stats(uid):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) as cnt, SUM(total) as summa, AVG(total) as avg
        FROM payments WHERE user_id = %s
    """, (uid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}

# ─────────────────────────────────────────
# ACCESS CHECK
# ─────────────────────────────────────────

def has_access(user_row):
    return True
def is_demo(user_row):
    return not (user_row and user_row.get("subscribed", False))
def is_subscribed(user_row):
    return user_row and user_row.get("subscribed", False)

# ─────────────────────────────────────────
# KEYBOARDS
# ─────────────────────────────────────────

def kb_lang():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇰🇿 Қазақша", callback_data="lang_kz"),
    ]])

def kb_subscribe(lang, trial_left=None):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💎 Оформить подписку" if lang == "ru" else "💎 Жазылым рәсімдеу",
            callback_data="subscribe"
        )
    ]])
def kb_main(lang):
    if lang == "ru":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🪪 Оплатить коммуналку ✅", callback_data="pay")],
            [InlineKeyboardButton("🤖 AI-Автопилот",           callback_data="autopay")],
            [InlineKeyboardButton("💸 Оплатить кредит",        callback_data="wip_credit"),
             InlineKeyboardButton("🧾 Оплатить налоги",        callback_data="wip_tax")],
            [InlineKeyboardButton("🍔 Заказать еду",           callback_data="wip_food"),
             InlineKeyboardButton("✈️ Купить билеты",          callback_data="wip_tickets")],
            [InlineKeyboardButton("📊 История",                callback_data="history"),
             InlineKeyboardButton("📈 Статистика",             callback_data="stats")],
            [InlineKeyboardButton("⚙️ Настройки",             callback_data="settings")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪪 Коммуналды төлеу ✅",  callback_data="pay")],
        [InlineKeyboardButton("🤖 AI-Автопилот",          callback_data="autopay")],
        [InlineKeyboardButton("💸 Несие төлеу",          callback_data="wip_credit"),
         InlineKeyboardButton("🧾 Салық төлеу",          callback_data="wip_tax")],
        [InlineKeyboardButton("🍔 Тамақ тапсырыс",       callback_data="wip_food"),
         InlineKeyboardButton("✈️ Билет сатып алу",      callback_data="wip_tickets")],
        [InlineKeyboardButton("📊 Тарих",                callback_data="history"),
         InlineKeyboardButton("📈 Статистика",           callback_data="stats")],
        [InlineKeyboardButton("⚙️ Баптаулар",           callback_data="settings")],
    ])

def kb_confirm(lang):
    if lang == "ru":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
            InlineKeyboardButton("❌ Отмена",      callback_data="cancel"),
        ]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Растау",    callback_data="confirm"),
        InlineKeyboardButton("❌ Бас тарту", callback_data="cancel"),
    ]])

def kb_back(lang):
    label = "◀️ Назад" if lang == "ru" else "◀️ Артқа"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="back")]])

def kb_show_utility(lang):
    if lang == "ru":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🪪 Показать оплату коммуналки", callback_data="pay")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪪 Коммуналды көрсету", callback_data="pay")],
        [InlineKeyboardButton("◀️ Артқа", callback_data="back")],
    ])

def kb_paywall(lang):
    """Клавиатура после исчерпания пробного периода."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💎 Оформить подписку" if lang == "ru" else "💎 Жазылым рәсімдеу",
            callback_data="subscribe"
        )
    ]])

# ─────────────────────────────────────────
# WIP — ответы витрины
# ─────────────────────────────────────────

WIP_TEXTS = {
    "wip_credit": {
        "ru": "🤖 Я уже могу выполнять такие задачи,\nно сейчас демонстрирую финансовый модуль.\n\nХотите посмотреть оплату коммунальных услуг?",
        "kz": "🤖 Мен мұндай тапсырмаларды орындай аламын,\nбірақ қазір қаржы модулін көрсетіп жатырмын.\n\nКоммуналдық төлемді көргіңіз келе ме?",
    },
    "wip_tax": {
        "ru": "🤖 Я уже могу выполнять такие задачи,\nно сейчас демонстрирую финансовый модуль.\n\nХотите посмотреть оплату коммунальных услуг?",
        "kz": "🤖 Мен мұндай тапсырмаларды орындай аламын,\nбірақ қазір қаржы модулін көрсетіп жатырмын.\n\nКоммуналдық төлемді көргіңіз келе ме?",
    },
    "wip_food": {
        "ru": "🤖 Я уже могу выполнять такие задачи,\nно сейчас демонстрирую финансовый модуль.\n\nХотите посмотреть оплату коммунальных услуг?",
        "kz": "🤖 Мен мұндай тапсырмаларды орындай аламын,\nбірақ қазір қаржы модулін көрсетіп жатырмын.\n\nКоммуналдық төлемді көргіңіз келе ме?",
    },
    "wip_tickets": {
        "ru": "🤖 Я уже могу выполнять такие задачи,\nно сейчас демонстрирую финансовый модуль.\n\nХотите посмотреть оплату коммунальных услуг?",
        "kz": "🤖 Мен мұндай тапсырмаларды орындай аламын,\nбірақ қазір қаржы модулін көрсетіп жатырмын.\n\nКоммуналдық төлемді көргіңіз келе ме?",
    },
}

# ─────────────────────────────────────────
# STATE
# ─────────────────────────────────────────

pending = {}

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def subscribe_screen_text(lang, user_row=None):
    if lang == "ru":
        return (
            "🤖 Ваш персональный AI-ассистент\n\n"
            "Сейчас вы используете ДЕМО-версию\n\n"
            "⚠️ В демо режиме:\n"
            "• Симулируются платежи\n"
            "• Нет реальной интеграции с банком\n\n"
            "💎 Подписка открывает:\n"
            "• Реальные оплаты\n"
            "• Автоплатежи\n"
            "• Полный функционал\n"
        )
    else:
        return (
            "🤖 Сіздің AI-көмекшіңіз\n\n"
            "Сіз қазір DEMO-нұсқасын пайдаланып жатырсыз\n\n"
            "⚠️ DEMO режимінде:\n"
            "• Төлемдер тек симуляция\n"
            "• Банкпен нақты интеграция жоқ\n\n"
            "💎 Жазылым ашылады:\n"
            "• Нақты төлемдер\n"
            "• Автотөлем\n"
            "• Толық функционал\n"
        )
async def show_subscribe_screen(message, lang, user_row=None):
    """Отправляет экран подписки новым сообщением."""
    text = subscribe_screen_text(lang, user_row)
    await message.reply_text(text, reply_markup=kb_subscribe(lang))


# ─────────────────────────────────────────
# HANDLERS
# ─────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Добро пожаловать!\n\n"
        "Я ваш AI-ассистент для автоматических платежей\n\n"
        "Выберите действие:",
        reply_markup=kb_start_entry()
    )

async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q     = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    uname = q.from_user.username or q.from_user.first_name or ""
    lang  = ctx.user_data.get("lang", "ru")
    data  = q.data
    # ── СТАРТОВЫЙ ЭКРАН ─────────────────────

    if data == "start_demo":
        await q.message.reply_text(
            "🧪 Вы выбрали демо-режим\n\n"
            "Можно протестировать все функции в режиме симуляции",
            reply_markup=kb_continue()
        )

    elif data == "check_sub":
        await q.message.reply_text(
            "🔍 Проверяю подписку..."
        )
        await asyncio.sleep(1.5)

        await q.message.reply_text(
            "❌ Подписка не найдена\n\n"
            "Вы можете продолжить в демо-режиме",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Продолжить с демо", callback_data="start_demo")]
            ])
        )

    elif data == "continue":
        await q.message.reply_text(
            "🌐 Выберите язык:\nТілді таңдаңыз:",
            reply_markup=kb_lang()
        )
    # ── ЯЗЫК ──────────────────────────────
    if data in ("lang_ru", "lang_kz"):
        lang = "ru" if data == "lang_ru" else "kz"
        ctx.user_data["lang"] = lang
        upsert_user(uid, uname, lang)
        user_row = get_user(uid)

        if lang == "ru":
            greeting = "✅ Язык выбран: Русский\n\n"
        else:
            greeting = "✅ Тіл таңдалды: Қазақша\n\n"

        # Если уже подписан — сразу в главное меню
        if is_subscribed(user_row):
            text = greeting + ("Я ваш персональный AI-ассистент 🤖\nЧем могу помочь?"
                               if lang == "ru" else
                               "Мен сіздің жеке AI-көмекшіңізбін 🤖\nҚалай көмектесе аламын?")
            await q.edit_message_text(text, reply_markup=kb_main(lang))
        else:
            # Показываем экран подписки
            left = trials_left(user_row)
            text = greeting + subscribe_screen_text(lang, user_row)
            await q.edit_message_text(text, reply_markup=kb_subscribe(lang, left))

    # ── ПОДПИСКА (ЗАГЛУШКА) ───────────────
    elif data == "subscribe":
        if lang == "ru":
            text = (
                "💎 Оформление подписки\n\n"
                "Здесь будет интеграция с платёжной системой.\n\n"
                "✅ Подписка успешно оформлена!\n\n"
                "Теперь у вас есть полный доступ ко всем функциям 🤖"
            )
        else:
            text = (
                "💎 Жазылымды рәсімдеу\n\n"
                "Мұнда төлем жүйесімен интеграция болады.\n\n"
                "✅ Жазылым сәтті рәсімделді!\n\n"
                "Енді барлық функцияларға толық қолжетімділігіңіз бар 🤖"
            )
        set_subscribed(uid)
        await q.message.reply_text(text, reply_markup=kb_main(lang))

    
    # ── НАЗАД ─────────────────────────────
    elif data == "back":
        user_row = get_user(uid)
        if is_subscribed(user_row):
            text = "Чем могу помочь?" if lang == "ru" else "Қалай көмектесе аламын?"
            await q.message.reply_text(text, reply_markup=kb_main(lang))
        else:
            await show_subscribe_screen(q.message, lang, user_row)

    # ── ВИТРИНА WIP ───────────────────────
    elif data in WIP_TEXTS:
        text = WIP_TEXTS[data][lang]
        await q.message.reply_text(text, reply_markup=kb_show_utility(lang))

    # ── ОПЛАТА КОММУНАЛКИ ─────────────────
    elif data == "pay":
        user_row = get_user(uid)

        

        
        month = datetime.now().month
        bills = generate_bills(month)
        pending[uid] = bills
        total = sum(b["amount"] for b in bills)

        month_names_ru = ["","Январь","Февраль","Март","Апрель","Май","Июнь",
                          "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
        month_names_kz = ["","Қаңтар","Ақпан","Наурыз","Сәуір","Мамыр","Маусым",
                          "Шілде","Тамыз","Қыркүйек","Қазан","Қараша","Желтоқсан"]

        # Шаг 1 — получаю данные
        if lang == "ru":
            msg = await q.message.reply_text("🤖 Анализирую ваши начисления...")
        else:
            msg = await q.message.reply_text("📡 Деректерді алып жатырмын...")
        await asyncio.sleep(3.0)

        # Шаг 2 — актуальные данные
        if lang == "ru":
            await msg.edit_text("📡 Получаю актуальные данные...")
        else:
            await msg.edit_text("📡 Өзекті деректерді алып жатырмын...")
        await asyncio.sleep(2.0)

        # Шаг 3 — анализ
        if lang == "ru":
            await msg.reply_text(
                "📊 Я проанализировал ваши данные:\n\n"
                "Подготовил актуальные платежи 👇"
            )
        else:
            await msg.reply_text(
                "📊 Деректеріңізді талдадым:\n\n"
                "Өзекті төлемдерді дайындадым 👇"
            )
        await asyncio.sleep(1.5)
        if is_demo(user_row):
            if lang == "ru":
                await q.message.reply_text(
                    "🧪 ДЕМО режим\n\n"
                    "Сейчас я показываю симуляцию платежей\n"
                    "Реальные списания не выполняются"
                )
            else:
                await q.message.reply_text(
                    "🧪 DEMO режимі\n\n"
                    "Қазір төлемдер симуляция ретінде көрсетіледі\n"
                    "Нақты ақша алынбайды"
                )
        # Шаг 4 — список счетов
        if lang == "ru":
            lines     = "\n".join(f"• {b['ru']} — {money(b['amount'])}" for b in bills)
            header    = f"📋 {month_names_ru[month]} {datetime.now().year}"
            bill_text = f"{header}\n\n{lines}\n\n{'─'*26}\n💰 Итого: {money(total)}"
        else:
            lines     = "\n".join(f"• {b['kz']} — {money(b['amount'])}" for b in bills)
            header    = f"📋 {month_names_kz[month]} {datetime.now().year}"
            bill_text = f"{header}\n\n{lines}\n\n{'─'*26}\n💰 Барлығы: {money(total)}"

        await msg.edit_text(bill_text)
        await asyncio.sleep(0.8)

        confirm_q = "Подтвердить оплату?" if lang == "ru" else "Төлеуді растайсыз ба?"
        await q.message.reply_text(confirm_q, reply_markup=kb_confirm(lang))

    # ── ПОДТВЕРЖДЕНИЕ ─────────────────────
    elif data == "confirm":
        bills = pending.pop(uid, generate_bills(datetime.now().month))
        total = sum(b["amount"] for b in bills)

        msg = await q.message.reply_text(
            "⏳ Выполняю операцию..." if lang == "ru" else "⏳ Операция орындалуда..."
        )
        await asyncio.sleep(2.0)

        await msg.edit_text(
            "🔄 Обработка платежа..." if lang == "ru" else "🔄 Төлем өңделуде..."
        )
        await asyncio.sleep(1.5)

        save_payment(uid, uname, lang, bills, total)

        await msg.edit_text(
            "✅ Оплата успешно выполнена" if lang == "ru" else "✅ Төлем сәтті орындалды"
        )

        date = today()
        
        if lang == "ru":
            receipt = (
                        f"📄 Квитанция #{random.randint(100000,999999)}\n\n"
                        f"Сумма: {money(total)}\n"
                        f"Дата: {date}\n"
                        f"{status}\n\n"
                        f"Спасибо за оплату! 🤖"
                    )
        else:
            receipt = (f"📄 Түбіртек #{random.randint(100000,999999)}\n\n"
                       f"Сома: {money(total)}\nКүні: {date}\nМәртебе: Орындалды ✅\n\n"
                       f"Төлегеніңізге рахмет! 🤖")

        await q.message.reply_text(receipt)
        user_row = get_user(uid)
        if is_demo(user_row):
            if lang == "ru":
                text = (
                    "💎 Это была демо-операция\n\n"
                    "Хочешь, чтобы я реально оплачивал счета?\n\n"
                    "Подключи подписку:\n"
                    "• реальные списания\n"
                    "• автоплатеж\n"
                    "• полная автоматизация 🤖"
                )
            else:
                text = (
                    "💎 Бұл демо операция болды\n\n"
                    "Шынайы төлем жасағым келеді ме?\n\n"
                    "Жазылымды қос:\n"
                    "• нақты төлемдер\n"
                    "• автотөлем\n"
                    "• толық автоматтандыру 🤖"
                )

            await q.message.reply_text(text, reply_markup=kb_subscribe(lang))
        await asyncio.sleep(0.5)

        # Подписчик — стандартный оффер автопилота
        if lang == "ru":
            autopay_offer = (
                "🤖 Кстати, я могу делать это автоматически каждый месяц\n\n"
                "Включить AI-автопилот — и я буду сам:\n"
                "• проверять начисления\n"
                "• оплачивать в нужный день\n"
                "• присылать квитанцию вам 📲"
            )
        else:
            autopay_offer = (
                "🤖 Айтпақшы, мен мұны әр ай автоматты түрде жасай аламын\n\n"
                "AI-Автопилотты қосыңыз — мен өзім:\n"
                "• есептеулерді тексеремін\n"
                "• қажетті күні төлеймін\n"
                "• сізге түбіртек жіберемін 📲"
            )
        kb_autopay_offer = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🤖 Включить AI-автопилот" if lang == "ru" else "🤖 AI-Автопилотты қосу",
                callback_data="autopay"
            )],
            [InlineKeyboardButton(
                "Не сейчас" if lang == "ru" else "Қазір емес",
                callback_data="back"
            )],
        ])
        await q.message.reply_text(autopay_offer, reply_markup=kb_autopay_offer)

    # ── ОТМЕНА ────────────────────────────
    elif data == "cancel":
        pending.pop(uid, None)
        if lang == "ru":
            text = "❌ Операция отменена\n\nЕсли понадобится — я всегда готов помочь 🤖"
        else:
            text = "❌ Операция болдырылмады\n\nҚажет болса — әрқашан дайынмын 🤖"
        await q.message.reply_text(text, reply_markup=kb_main(lang))

    # ── ИСТОРИЯ ───────────────────────────
    elif data == "history":
        rows = get_history(uid)
        if not rows:
            text = ("📊 История платежей пуста\n\nОплатите коммуналку — и здесь появятся записи 🗂"
                    if lang == "ru" else
                    "📊 Төлемдер тарихы бос\n\nКоммуналды төлесеңіз — жазбалар пайда болады 🗂")
        else:
            month_short_ru = ["","Янв","Фев","Мар","Апр","Май","Июн",
                               "Июл","Авг","Сен","Окт","Ноя","Дек"]
            month_short_kz = ["","Қаң","Ақп","Нау","Сәу","Мам","Мау",
                               "Шіл","Там","Қыр","Қаз","Қар","Жел"]
            lines = []
            for r in rows:
                m = month_short_ru[r["month"]] if lang == "ru" else month_short_kz[r["month"]]
                lines.append(f"• {r['paid_at']} ({m}) — {money(r['total'])} ✅")
            header = "📊 История платежей:\n\n" if lang == "ru" else "📊 Төлемдер тарихы:\n\n"
            text   = header + "\n".join(lines)
        await q.message.reply_text(text, reply_markup=kb_back(lang))

    # ── AI-АВТОПИЛОТ ──────────────────────
    elif data == "autopay":
        if lang == "ru":
            msg = await q.message.reply_text("🤖 Настраиваю AI-автопилот...")
        else:
            msg = await q.message.reply_text("🤖 AI-Автопилотты баптап жатырмын...")
        await asyncio.sleep(1.5)

        if lang == "ru":
            await msg.edit_text("🔍 Анализирую ваши платежи за последние месяцы...")
        else:
            await msg.edit_text("🔍 Соңғы айлардағы төлемдеріңізді талдап жатырмын...")
        await asyncio.sleep(2.0)

        if lang == "ru":
            text = (
                "✅ AI-Автопилот активирован!\n\n"
                "Я беру это на себя:\n\n"
                "📅 Каждое 1-е число\n"
                "   └ проверяю новые начисления\n\n"
                "💳 После проверки\n"
                "   └ оплачиваю все счета за вас\n\n"
                "📲 Сразу после оплаты\n"
                "   └ отправляю квитанцию сюда\n\n"
                "─────────────────────────\n"
                "Первый запуск уже выполнен\n\n"
                "Теперь коммунальные платежи — моя задача\n"
                "Вы можете вообще об этом забыть\n\n"
                "🔔 Вы всегда можете отключить автопилот в любой момент"
            )
        else:
            text = (
                "✅ AI-Автопилот іске қосылды!\n\n"
                "Мен мұны өз мойныма аламын:\n\n"
                "📅 Әр айдың 1-і\n"
                "   └ жаңа есептеулерді тексеремін\n\n"
                "💳 Тексергеннен кейін\n"
                "   └ барлық төлемдерді сіздің орныңызға төлеймін\n\n"
                "📲 Төлемнен кейін бірден\n"
                "   └ түбіртекті осында жіберемін\n\n"
                "─────────────────────────\n"
                "Алғашқы іске қосу орындалды\n\n"
                "Енді коммуналдық төлемдер — менің міндетім\n"
                "Сіз бұл туралы мүлде ойламай-ақ қоя аласыз\n\n"
                "🔔 Автопилотты кез келген уақытта өшіре аласыз"
            )

        kb_autopay_active = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔴 Отключить автопилот" if lang == "ru" else "🔴 Автопилотты өшіру",
                callback_data="autopay_off"
            )],
            [InlineKeyboardButton(
                "◀️ Назад" if lang == "ru" else "◀️ Артқа",
                callback_data="back"
            )],
        ])
        await msg.edit_text(text, reply_markup=kb_autopay_active)

    elif data == "autopay_off":
        if lang == "ru":
            text = (
                "🔴 Автопилот отключён\n\n"
                "Вы всегда можете включить его снова — "
                "и я возьму рутину на себя 🤖"
            )
        else:
            text = (
                "🔴 Автопилот өшірілді\n\n"
                "Оны кез келген уақытта қайта қоса аласыз — "
                "мен күнделікті жұмысты өз мойныма аламын 🤖"
            )
        await q.message.reply_text(text, reply_markup=kb_main(lang))

    # ── СТАТИСТИКА ────────────────────────
    elif data == "stats":
        st    = get_stats(uid)
        cnt   = st.get("cnt") or 0
        summa = int(st.get("summa") or 0)
        avg   = int(st.get("avg") or 0)
        if cnt == 0:
            text = ("📈 Статистика пуста — ещё нет платежей" if lang == "ru"
                    else "📈 Статистика бос — әлі төлемдер жоқ")
        else:
            if lang == "ru":
                text = (f"📈 Ваша статистика:\n\n"
                        f"🔢 Всего платежей: {cnt}\n"
                        f"💸 Потрачено: {money(summa)}\n"
                        f"📊 Средний платёж: {money(avg)}")
            else:
                text = (f"📈 Сіздің статистикаңыз:\n\n"
                        f"🔢 Барлық төлемдер: {cnt}\n"
                        f"💸 Жұмсалды: {money(summa)}\n"
                        f"📊 Орташа төлем: {money(avg)}")
        await q.message.reply_text(text, reply_markup=kb_back(lang))

# ── НАСТРОЙКИ ─────────────────────────
    elif data == "settings":
        lang_label = "Русский 🇷🇺" if lang == "ru" else "Қазақша 🇰🇿"
        user_row = get_user(uid)

        if lang == "ru":
            sub_status = (
                "✅ Активна" if is_subscribed(user_row)
                else "🧪 Демо режим"
            )

            text = (
                f"⚙️ Настройки\n\n"
                f"🌐 Язык: {lang_label}\n"
                f"💎 Статус: {sub_status}\n"
                f"🆔 Ваш ID: {uid}\n\n"
                f"🧪 Вы используете демо-версию\n"
                f"Некоторые функции работают в режиме симуляции\n\n"
                f"Для смены языка напишите /start"
            )
        else:
            sub_status = (
                "✅ Белсенді" if is_subscribed(user_row)
                else "🧪 DEMO режимі"
            )

            text = (
                f"⚙️ Баптаулар\n\n"
                f"🌐 Тіл: {lang_label}\n"
                f"💎 Күйі: {sub_status}\n"
                f"🆔 Сіздің ID: {uid}\n\n"
                f"🧪 Сіз DEMO-нұсқасын пайдаланып жатырсыз\n"
                f"Кейбір функциялар симуляция режимінде жұмыс істейді\n\n"
                f"Тілді өзгерту үшін /start жазыңыз"
            )

        await q.message.reply_text(text, reply_markup=kb_back(lang))

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

async def post_init(app):
    init_db()

app = (ApplicationBuilder()
       .token(BOT_TOKEN)
       .post_init(post_init)
       .build())

app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CallbackQueryHandler(button))

log.info("Bot starting...")
app.run_polling()