from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sqlite3
from pathlib import Path
import math
import os
import uvicorn

app = FastAPI(title="Local Guide API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Путь к новой базе от OpenStreetMap
DB_PATH = Path(__file__).parent.parent / "data" / "local.db"


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


@app.get("/places")
def get_places(lat: float = 56.8587, lon: float = 35.9006, radius: float = 50.0):
    conn = get_db()
    # Выбираем все места из новой базы.
    # Если хочешь фильтровать по отсутствию сайта, используй website_status
    query = """
        SELECT id, name, category, address, lat, lon, rating, yandex_url
        FROM places 
        WHERE website_status = 'not_listed'
    """
    rows = conn.execute(query).fetchall()
    conn.close()

    result = []
    for row in rows:
        if row["lat"] is None or row["lon"] is None:
            continue
        dist = haversine(lat, lon, row["lat"], row["lon"])
        if dist <= radius:
            result.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "category": row["category"],
                    "address": row["address"],
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "rating": row["rating"],
                    "yandex_url": row["yandex_url"],
                }
            )
    return {"count": len(result), "places": result}


@app.get("/place/{place_id}")
def get_place(place_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Заведение не найдено")
    return dict(row)


# Подключаем статику (HTML/JS)
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
