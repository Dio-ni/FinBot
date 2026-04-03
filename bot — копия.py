import time
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")

user_lang = {}
user_history = {}

BILLS = [
    {"ru": "Казахтелеком", "kz": "Қазақтелеком", "amount": 8450},
    {"ru": "Электроэнергия", "kz": "Электр энергиясы", "amount": 6000},
    {"ru": "Вода", "kz": "Су", "amount": 4000},
]
TOTAL = sum(b["amount"] for b in BILLS)


def money(n):
    return f"{n:,}".replace(",", " ") + " ₸"


def today():
    from datetime import datetime
    return datetime.now().strftime("%d.%m.%Y")


# ─── KEYBOARDS ───────────────────────────

def kb_lang():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇰🇿 Қазақша", callback_data="lang_kz")],
    ])


def kb_main(lang):
    if lang == "ru":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🪪 Оплатить коммуналку", callback_data="pay")],
            [InlineKeyboardButton("📊 История", callback_data="history")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪪 Коммуналды төлеу", callback_data="pay")],
        [InlineKeyboardButton("📊 Тарих", callback_data="history")],
        [InlineKeyboardButton("⚙️ Баптаулар", callback_data="settings")],
    ])


def kb_confirm(lang):
    if lang == "ru":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Растау", callback_data="confirm")],
        [InlineKeyboardButton("❌ Бас тарту", callback_data="cancel")],
    ])


# ─── HANDLERS ────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать!\n\nВыберите язык:\nТілді таңдаңыз:",
        reply_markup=kb_lang()
    )


async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = user_lang.get(uid, "ru")
    data = q.data

    # ── язык ──
    if data in ("lang_ru", "lang_kz"):
        lang = "ru" if data == "lang_ru" else "kz"
        user_lang[uid] = lang
        if lang == "ru":
            text = "✅ Язык выбран: Русский\n\nЯ ваш персональный AI-ассистент 🤖\n\nЧем могу помочь?"
        else:
            text = "✅ Тіл таңдалды: Қазақша\n\nМен сіздің жеке AI-көмекшіңізбін 🤖\n\nҚалай көмектесе аламын?"
        await q.edit_message_text(text, reply_markup=kb_main(lang))

    # ── оплата ──
    elif data == "pay":
        if lang == "ru":
            msg = await q.message.reply_text("🤖 Анализирую ваши платежи...")
        else:
            msg = await q.message.reply_text("🤖 Төлемдеріңізді талдап жатырмын...")
        time.sleep(1.5)

        if lang == "ru":
            await msg.edit_text("🔍 Найдены начисления:")
        else:
            await msg.edit_text("🔍 Төлемдер табылды:")
        time.sleep(1.5)

        if lang == "ru":
            lines = "\n".join(f"• {b['ru']} — {money(b['amount'])}" for b in BILLS)
            bill_text = f"{lines}\n\n{'─'*24}\n💰 Итого: {money(TOTAL)}"
        else:
            lines = "\n".join(f"• {b['kz']} — {money(b['amount'])}" for b in BILLS)
            bill_text = f"{lines}\n\n{'─'*24}\n💰 Барлығы: {money(TOTAL)}"

        await msg.edit_text(bill_text)
        time.sleep(1.0)

        confirm_text = "Подтвердить оплату?" if lang == "ru" else "Төлеуді растайсыз ба?"
        await q.message.reply_text(confirm_text, reply_markup=kb_confirm(lang))

    # ── подтверждение ──
    elif data == "confirm":
        if lang == "ru":
            msg = await q.message.reply_text("⏳ Выполняю операцию...")
        else:
            msg = await q.message.reply_text("⏳ Операция орындалуда...")
        time.sleep(2.0)

        if lang == "ru":
            await msg.edit_text("🔄 Обработка платежа...")
        else:
            await msg.edit_text("🔄 Төлем өңделуде...")
        time.sleep(1.5)

        if lang == "ru":
            await msg.edit_text("✅ Оплата успешно выполнена")
        else:
            await msg.edit_text("✅ Төлем сәтті орындалды")

        date = today()
        if lang == "ru":
            receipt = f"📄 Квитанция:\n\nСумма: {money(TOTAL)}\nДата: {date}\nСтатус: Выполнено"
        else:
            receipt = f"📄 Чек:\n\nСома: {money(TOTAL)}\nКүні: {date}\nМәртебе: Орындалды"

        await q.message.reply_text(receipt)

        if uid not in user_history:
            user_history[uid] = []
        user_history[uid].insert(0, {"date": date, "amount": TOTAL})

        final = "🤖 Готов помочь с другими задачами" if lang == "ru" else "🤖 Басқа тапсырмаларға дайынмын"
        await q.message.reply_text(final, reply_markup=kb_main(lang))

    # ── отмена ──
    elif data == "cancel":
        if lang == "ru":
            text = "❌ Операция отменена\n\nЕсли понадобится — я всегда готов помочь 🤖"
        else:
            text = "❌ Операция болдырылмады\n\nҚажет болса — әрқашан дайынмын 🤖"
        await q.message.reply_text(text, reply_markup=kb_main(lang))

    # ── история ──
    elif data == "history":
        records = user_history.get(uid, [])
        if not records:
            text = "📊 История пуста" if lang == "ru" else "📊 Тарих бос"
        else:
            lines = "\n".join(f"• {r['date']} — Коммуналка — {money(r['amount'])} ✅" for r in records[:5])
            text = f"📊 История операций:\n\n{lines}" if lang == "ru" else f"📊 Операциялар тарихы:\n\n{lines}"
        await q.message.reply_text(text, reply_markup=kb_main(lang))

    # ── настройки ──
    elif data == "settings":
        if lang == "ru":
            text = "⚙️ Настройки\n\n🌐 Язык: Русский\n📱 Уведомления: Включены\n\n(Демо-режим)"
        else:
            text = "⚙️ Баптаулар\n\n🌐 Тіл: Қазақша\n📱 Хабарландырулар: Қосылған\n\n(Демо-режим)"
        await q.message.reply_text(text, reply_markup=kb_main(lang))


# ─── MAIN ────────────────────────────────

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))

print("✅ Бот запущен!")
app.run_polling()
