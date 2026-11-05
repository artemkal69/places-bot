import asyncio
import sqlite3
import sys
import re
import random
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright

DB_PATH = Path(__file__).parent.parent / "data" / "places.db"
SOCIAL_DOMAINS = (
    "vk.com",
    "instagram.com",
    "facebook.com",
    "t.me",
    "ok.ru",
    "youtube.com",
    "wa.me",
    "whatsapp.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
)


def init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS places (
            id INTEGER PRIMARY KEY AUTOINCREMENT, yandex_id TEXT UNIQUE,
            name TEXT NOT NULL, category TEXT, address TEXT, lat REAL, lon REAL,
            website TEXT, has_social_only INTEGER DEFAULT 0, rating REAL,
            reviews_count INTEGER, yandex_url TEXT, photo_url TEXT,
            collected_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    return conn


async def parse_query(page, query, category, max_results, conn):
    saved = 0
    # bbox для всей Москвы (примерный прямоугольник)
    bbox = "37.3,55.5~37.9,55.9"
    url = f"https://yandex.ru/maps/?text={quote(query)}&bbox={bbox}"
    print(f"  Загружаю: {url}")

    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    print("  Жду загрузки списка (5 сек)...")
    await page.wait_for_timeout(5000)

    for i in range(20):
        if saved >= max_results:
            break

        links = await page.locator("a[href*='/maps/org/']").all()

        for link in links:
            if saved >= max_results:
                break

            try:
                href = await link.get_attribute("href")
                if not href:
                    continue

                match = re.search(r"/org/[^/]+/(\d+)", href)
                if not match:
                    continue
                yid = match.group(1)

                # Берем название
                card_text = await link.evaluate(
                    "el => { let p = el; for(let i=0; i<5; i++){ if(p.innerText && p.innerText.length > 5) return p.innerText; p = p.parentElement; } return ''; }"
                )
                if not card_text:
                    continue
                lines = [line.strip() for line in card_text.split("\n") if line.strip()]
                name = lines[0]
                if name in ["Реклама", "Без названия"]:
                    continue

                # Кликаем по карточке
                await link.click(timeout=3000)
                await page.wait_for_timeout(800)

                # Извлекаем адрес
                address = await page.evaluate("""() => {
                    let addrEl = document.querySelector('[class*="address"], [class*="addr"]');
                    return addrEl ? addrEl.innerText.trim() : "";
                }""")

                # Извлекаем сайт
                website = await page.evaluate("""() => {
                    let links = document.querySelectorAll('a[class*="website"], a[class*="link"], .card-phones-view a, .business-contacts-view a');
                    for(let a of links) {
                        let h = a.href;
                        if(h && h.startsWith('http') && !h.includes('yandex') && !h.match(/vk\\.com|instagram|t\\.me|ok\\.ru|youtube|wa\\.me|whatsapp|twitter|x\\.com|tiktok/)) {
                            return h;
                        }
                    }
                    return null;
                }""")

                # Координаты
                coord_str = await link.evaluate(
                    "el => { let p = el; for(let i=0; i<5; i++){ if(p.getAttribute && p.getAttribute('data-coordinates')) return p.getAttribute('data-coordinates'); p = p.parentElement; } return null; }"
                )
                if coord_str:
                    try:
                        lon, lat = map(float, coord_str.split(","))
                    except:
                        lon, lat = 37.6173, 55.7558
                else:
                    lon = 37.6173 + random.uniform(-0.05, 0.05)
                    lat = 55.7558 + random.uniform(-0.05, 0.05)

                # ГЛАВНОЕ: если сайт есть, пропускаем и не сохраняем
                if website:
                    print(f"  - Пропуск: {name} (есть сайт)")
                    continue

                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO places (yandex_id, name, category, address, lat, lon, website, has_social_only, rating, reviews_count, yandex_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        yid,
                        name,
                        category,
                        address,
                        lat,
                        lon,
                        None,
                        0,
                        None,
                        None,
                        f"https://yandex.ru/maps/org/{yid}/",
                    ),
                )
                conn.commit()

                if cur.rowcount > 0:
                    print(f"  + ДОБАВЛЕНО: {name} | Адрес: {address or 'Не указан'}")
                    saved += 1

            except Exception:
                pass

        await page.mouse.move(300, 500)
        await page.mouse.wheel(0, 1500)
        await page.wait_for_timeout(1500)

    return saved


async def main(city, categories, max_per_category):
    conn = init_db()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            locale="ru-RU", viewport={"width": 1400, "height": 900}
        )
        page = await context.new_page()

        total = 0
        for cat in categories:
            query = f"{cat} {city}"
            print(f"\n>>> Поиск: {query}")
            n = await parse_query(page, query, cat, max_per_category, conn)
            total += n
            await page.wait_for_timeout(3000)

        await browser.close()
    conn.close()
    print(f"\n=== ИТОГО найдено мест без сайтов: {total} ===")


if __name__ == "__main__":
    city_arg = sys.argv[1] if len(sys.argv) > 1 else "Москва"
    cats_arg = sys.argv[2].split(",") if len(sys.argv) > 2 else ["кафе"]
    max_arg = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    asyncio.run(main(city_arg, cats_arg, max_arg))
