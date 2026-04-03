# 🤖 FinBot Pro — деплой на Railway

## Шаг 1 — Получи токен бота
1. Telegram → @BotFather → /newbot
2. Скопируй токен вида `7521234567:AAF...`

## Шаг 2 — Залей на GitHub
1. github.com → New repository → назови `finbot`
2. Загрузи 3 файла: bot.py, requirements.txt, Procfile

## Шаг 3 — Railway + PostgreSQL
1. railway.app → Login with GitHub
2. New Project → Deploy from GitHub repo → выбери `finbot`
3. В проекте нажми **"+ New"** → **"Database"** → **"PostgreSQL"**
4. Зайди в сервис бота → **Variables** → добавь:
   - `BOT_TOKEN` = твой токен от BotFather
   - `DATABASE_URL` = скопируй из вкладки PostgreSQL → Connect → `DATABASE_URL`
5. Нажми **Deploy** → готово!

## Что хранится в БД
- `users` — кто запускал бота (user_id, язык, дата)
- `payments` — все платежи (сумма, месяц, год, детали по услугам)
