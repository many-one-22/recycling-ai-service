import math, sqlite3
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


def haversine(lat1, lng1, lat2, lng2):  # km 단위 거리
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@app.get("/")
def root():
    return {"message": "수거함 API 서버 동작 중"}


@app.get("/api/centers")
def get_centers(item: Optional[str] = None,
                lat: Optional[float] = None,
                lng: Optional[float] = None,
                limit: int = 10):
    conn = sqlite3.connect("centers.db")
    conn.row_factory = sqlite3.Row
    if item:
        rows = conn.execute(
            "SELECT c.* FROM centers c JOIN center_items ci ON ci.center_id=c.id WHERE ci.item=?",
            (item,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM centers").fetchall()

    result = []
    for r in rows:
        items = [x[0] for x in conn.execute(
            "SELECT item FROM center_items WHERE center_id=?", (r["id"],))]
        d = dict(r, items=items)
        if lat is not None and lng is not None:
            d["distance_km"] = round(haversine(lat, lng, r["lat"], r["lng"]), 2)
        result.append(d)

    if lat is not None and lng is not None:
        result.sort(key=lambda x: x["distance_km"])
    return result[:limit]