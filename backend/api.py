from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sqlite3
from pathlib import Path
import math
import os
import uvicorn
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
)

# --- НАСТРОЙКИ БОТА ---
# Токен будет браться из переменной окружения на Render (Environment)
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_СЮДА_ЕСЛИ_ТЕСТИРУЕШЬ_ЛОКАЛЬНО")
WEB_APP_URL = "https://places-bot-b1k8.onrender.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    # Создаем кнопку, которая открывает Mini App
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗺 Открыть карту", web_app=WebAppInfo(url=WEB_APP_URL)
                )
            ]
        ]
    )

    text = (
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я — гид по местам, которые прячутся от интернета. "
        "Здесь ты найдешь уютные кафе и барбершопы, у которых нет своих сайтов.\n\n"
        "Нажимай кнопку ниже и выбирай место!"
    )
    await message.answer(text, reply_markup=kb)


async def start_bot():
    try:
        # Удаляем вебхук, чтобы polling работал корректно
        await bot.delete_webhook(drop_pending_updates=True)
        # Ставим кнопку меню (слева внизу)
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть Гид", web_app=WebAppInfo(url=WEB_APP_URL)
            )
        )
        print("✅ Бот запущен и готов к работе!")
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА БОТА: {e}")


# --- FASTAPI ---
app = FastAPI(title="Local Guide API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Пути
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "local.db"
FRONTEND_DIR = BASE_DIR / "frontend"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@app.on_event("startup")
async def startup_event():
    # Запускаем бота в фоне при старте сервера
    asyncio.create_task(start_bot())


@app.on_event("shutdown")
async def shutdown_event():
    await bot.session.close()


@app.get("/places")
def get_places(lat: float = 56.8587, lon: float = 35.9006, radius: float = 100.0):
    try:
        conn = get_db()
        # Берем ВСЕ места из базы, так как OSM-парсер уже отфильтровал только те, у кого нет сайта
        rows = conn.execute(
            "SELECT id, name, category, address, lat, lon, rating, yandex_url FROM places"
        ).fetchall()
        conn.close()

        result = []
        for row in rows:
            if row["lat"] is None or row["lon"] is None:
                continue
            try:
                dist = haversine(lat, lon, float(row["lat"]), float(row["lon"]))
                if dist <= radius:
                    result.append(
                        {
                            "id": row["id"],
                            "name": row["name"],
                            "category": row["category"] or "Заведение",
                            "address": row["address"] or "Адрес не указан",
                            "lat": row["lat"],
                            "lon": row["lon"],
                            "rating": row["rating"],
                            "yandex_url": row["yandex_url"],
                        }
                    )
            except:
                continue
        return {"count": len(result), "places": result}
    except Exception as e:
        print(f"Ошибка БД: {e}")
        return {"count": 0, "places": []}


@app.get("/place/{place_id}")
def get_place(place_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Не найдено")
    return dict(row)


# Проверяем наличие папки frontend перед монтированием
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
else:
    print(f"⚠️ ВНИМАНИЕ: Папка {FRONTEND_DIR} не найдена!")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
