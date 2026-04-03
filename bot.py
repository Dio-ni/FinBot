import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "2120083228:AAEorTnGXuMdTiby7h5UhsecG56oxKxFDA4")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ──────────────────────────────────────────
# KEYBOARDS
# ──────────────────────────────────────────

def kb_language():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="lang_kz")],
    ])

def kb_main(lang: str):
    if lang == "ru":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🪪 Оплатить коммуналку", callback_data="pay_utility")],
            [InlineKeyboardButton(text="📊 История", callback_data="history")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🪪 Коммуналды төлеу", callback_data="pay_utility")],
            [InlineKeyboardButton(text="📊 Тарих", callback_data="history")],
            [InlineKeyboardButton(text="⚙️ Баптаулар", callback_data="settings")],
        ])

def kb_confirm(lang: str):
    if lang == "ru":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_pay")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_pay")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Растау", callback_data="confirm_pay")],
            [InlineKeyboardButton(text="❌ Бас тарту", callback_data="cancel_pay")],
        ])

def kb_after_pay(lang: str):
    if lang == "ru":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🪪 Оплатить ещё", callback_data="pay_utility")],
            [InlineKeyboardButton(text="📊 История", callback_data="history")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🪪 Тағы төлеу", callback_data="pay_utility")],
            [InlineKeyboardButton(text="📊 Тарих", callback_data="history")],
            [InlineKeyboardButton(text="⚙️ Баптаулар", callback_data="settings")],
        ])

# ──────────────────────────────────────────
# USER STATE (простое хранилище в памяти)
# ──────────────────────────────────────────

user_lang = {}      # user_id -> "ru" | "kz"
user_history = {}   # user_id -> list of dicts

BILLS = [
    {"name_ru": "Казахтелеком", "name_kz": "Қазақтелеком", "amount": 8450},
    {"name_ru": "Электроэнергия", "name_kz": "Электр энергиясы", "amount": 6000},
    {"name_ru": "Вода", "name_kz": "Су", "amount": 4000},
]
TOTAL = sum(b["amount"] for b in BILLS)

def fmt_money(n):
    return f"{n:,}".replace(",", " ") + " ₸"

def today():
    return datetime.now().strftime("%d.%m.%Y")

# ──────────────────────────────────────────
# HANDLERS
# ──────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Добро пожаловать!\n\nПожалуйста, выберите язык:\nТілді таңдаңыз:",
        reply_markup=kb_language()
    )


@dp.callback_query(F.data.in_(["lang_ru", "lang_kz"]))
async def choose_language(cb: CallbackQuery):
    lang = "ru" if cb.data == "lang_ru" else "kz"
    user_lang[cb.from_user.id] = lang

    if lang == "ru":
        text = "✅ Язык выбран: Русский\n\nЯ ваш персональный AI-ассистент 🤖\n\nЧем могу помочь?"
    else:
        text = "✅ Тіл таңдалды: Қазақша\n\nМен сіздің жеке AI-көмекшіңізбін 🤖\n\nҚалай көмектесе аламын?"

    await cb.message.edit_text(text, reply_markup=kb_main(lang))
    await cb.answer()


@dp.callback_query(F.data == "pay_utility")
async def pay_utility(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = user_lang.get(uid, "ru")

    if lang == "ru":
        msg = await cb.message.answer("🤖 Анализирую ваши платежи...")
    else:
        msg = await cb.message.answer("🤖 Төлемдеріңізді талдап жатырмын...")
    await cb.answer()
    await asyncio.sleep(1.5)

    if lang == "ru":
        await msg.edit_text("🔍 Найдены начисления:")
    else:
        await msg.edit_text("🔍 Төлемдер табылды:")
    await asyncio.sleep(1.5)

    # Build bill list
    if lang == "ru":
        lines = "\n".join(f"• {b['name_ru']} — {fmt_money(b['amount'])}" for b in BILLS)
        bill_text = f"{lines}\n\n{'─'*28}\n💰 Итого: {fmt_money(TOTAL)}"
    else:
        lines = "\n".join(f"• {b['name_kz']} — {fmt_money(b['amount'])}" for b in BILLS)
        bill_text = f"{lines}\n\n{'─'*28}\n💰 Барлығы: {fmt_money(TOTAL)}"

    await msg.edit_text(bill_text)
    await asyncio.sleep(1.0)

    if lang == "ru":
        confirm_text = "Подтвердить оплату?"
    else:
        confirm_text = "Төлеуді растайсыз ба?"

    await cb.message.answer(confirm_text, reply_markup=kb_confirm(lang))


@dp.callback_query(F.data == "confirm_pay")
async def confirm_payment(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = user_lang.get(uid, "ru")
    await cb.answer()

    if lang == "ru":
        msg = await cb.message.answer("⏳ Выполняю операцию...")
    else:
        msg = await cb.message.answer("⏳ Операция орындалуда...")
    await asyncio.sleep(2.0)

    if lang == "ru":
        await msg.edit_text("🔄 Обработка платежа...")
    else:
        await msg.edit_text("🔄 Төлем өңделуде...")
    await asyncio.sleep(1.5)

    if lang == "ru":
        await msg.edit_text("✅ Төлем сәтті орындалды" if lang == "kz" else "✅ Оплата успешно выполнена")
    else:
        await msg.edit_text("✅ Төлем сәтті орындалды")
    await asyncio.sleep(0.5)

    # Receipt
    date = today()
    if lang == "ru":
        receipt = f"📄 Квитанция:\n\nСумма: {fmt_money(TOTAL)}\nДата: {date}\nСтатус: Выполнено"
    else:
        receipt = f"📄 Чек:\n\nСома: {fmt_money(TOTAL)}\nКүні: {date}\nМәртебе: Орындалды"

    await cb.message.answer(receipt)
    await asyncio.sleep(0.3)

    # Save to history
    if uid not in user_history:
        user_history[uid] = []
    user_history[uid].insert(0, {"date": date, "amount": TOTAL, "type": "utility"})

    if lang == "ru":
        final_text = "🤖 Готов помочь с другими задачами"
    else:
        final_text = "🤖 Басқа тапсырмаларға көмектесуге дайынмын"

    await cb.message.answer(final_text, reply_markup=kb_after_pay(lang))


@dp.callback_query(F.data == "cancel_pay")
async def cancel_payment(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = user_lang.get(uid, "ru")
    await cb.answer()

    if lang == "ru":
        text = "❌ Операция отменена\n\nЕсли понадобится — я всегда готов помочь 🤖"
    else:
        text = "❌ Операция болдырылмады\n\nҚажет болса — мен әрқашан көмектесуге дайынмын 🤖"

    await cb.message.answer(text, reply_markup=kb_main(lang))


@dp.callback_query(F.data == "history")
async def show_history(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = user_lang.get(uid, "ru")
    await cb.answer()

    records = user_history.get(uid, [])
    if not records:
        if lang == "ru":
            await cb.message.answer("📊 История операций пуста", reply_markup=kb_main(lang))
        else:
            await cb.message.answer("📊 Операциялар тарихы бос", reply_markup=kb_main(lang))
        return

    if lang == "ru":
        lines = "\n".join(f"• {r['date']} — Коммуналка — {fmt_money(r['amount'])} ✅" for r in records[:5])
        text = f"📊 История операций:\n\n{lines}"
    else:
        lines = "\n".join(f"• {r['date']} — Коммуналка — {fmt_money(r['amount'])} ✅" for r in records[:5])
        text = f"📊 Операциялар тарихы:\n\n{lines}"

    await cb.message.answer(text, reply_markup=kb_main(lang))


@dp.callback_query(F.data == "settings")
async def show_settings(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = user_lang.get(uid, "ru")
    await cb.answer()

    if lang == "ru":
        text = "⚙️ Настройки\n\n🌐 Язык: Русский\n📱 Уведомления: Включены\n\n(Демо-режим)"
    else:
        text = "⚙️ Баптаулар\n\n🌐 Тіл: Қазақша\n📱 Хабарландырулар: Қосылған\n\n(Демо-режим)"

    await cb.message.answer(text, reply_markup=kb_main(lang))


# ──────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
