from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from pathlib import Path
import math
import uvicorn

app = FastAPI(title="Yandex Places Mini App API")

# Разрешаем запросы с любых доменов (чтобы фронтенд мог стучаться)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).parent.parent / "data" / "places.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def haversine(lat1, lon1, lat2, lon2):
    """Расстояние между двумя точками на карте в километрах."""
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


@app.get("/places")
def get_places(lat: float = 55.7558, lon: float = 37.6173, radius: float = 100.0):
    """
    Получить заведения на карте.
    По умолчанию: Москва, радиус 10 км.
    Возвращает только те, у кого нет сайта ИЛИ он устаревший (score >= 40).
    """
    conn = get_db()
    # Берем заведения без сайта или с плохим сайтом
    query = """
        SELECT id, name, category, lat, lon, website, outdated_score, audit_reasons, rating
        FROM places 
        WHERE (website IS NULL OR outdated_score >= 40)
    """
    rows = conn.execute(query).fetchall()
    conn.close()

    result = []
    for row in rows:
        if row["lat"] is None or row["lon"] is None:
            continue

        # Фильтруем по радиусу
        dist = haversine(lat, lon, row["lat"], row["lon"])
        if dist <= radius:
            result.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "category": row["category"],
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "has_website": row["website"] is not None,
                    "score": row["outdated_score"],
                    "reason": row["audit_reasons"],
                    "rating": row["rating"],
                }
            )

    return {"count": len(result), "places": result}


@app.get("/place/{place_id}")
def get_place(place_id: int):
    """Получить полную информацию о конкретном заведении для карточки."""
    conn = get_db()
    row = conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Заведение не найдено")

    return dict(row)


app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
if __name__ == "__main__":
    print("Запускаю API сервер...")
    print("Открой в браузере: http://127.0.0.1:8000/places")
    uvicorn.run(app, host="127.0.0.1", port=8000)
