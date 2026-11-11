"""
centers_api.py - 수거함(행정복지센터) 지도용 API

ai-model2/backend/main.py 를 별도 서버로 띄우지 않고,
postEx.py(localhost:8080) 한 서버에서 같이 서빙하기 위한 라우터.
프론트(map_script.js)가 상대경로 /api/centers 로 호출하므로
반드시 같은 포트에서 응답해야 한다.

DB: ai-model2/backend/centers.db  (팀원이 seed.py로 만든 파일)
"""

import math
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENTERS_DB = os.path.join(BASE_DIR, "ai-model2", "backend", "centers.db")

# seed.py가 넣어둔 영문 코드 -> 지도 필터 칩에 쓰는 한글 품목명
ITEM_LABEL = {
    "pet": "투명페트병",
    "can": "캔",
    "paper": "종이팩",
    "plastic": "플라스틱",
    "glass": "유리병",
    "battery": "폐건전지",
    "medicine": "폐의약품",
    "lamp": "폐형광등",
    "appliance": "소형가전",
    "icepack": "아이스팩",
}


def _connect():
    conn = sqlite3.connect(CENTERS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn, table: str):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def haversine(lat1, lng1, lat2, lng2):
    """두 좌표 사이 거리 (km)"""
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@router.get("/api/centers")
def get_centers(
    item: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    limit: int = 100,
):
    """
    수거함 목록 조회.
    - item: 품목 필터 (한글/영문 모두 허용)
    - lat, lng: 주면 거리(distance_km) 계산 후 가까운 순 정렬
    """
    if not os.path.exists(CENTERS_DB):
        return []

    conn = _connect()
    try:
        if not _table_exists(conn, "centers"):
            return []

        cols = _columns(conn, "centers")
        has_items_table = _table_exists(conn, "center_items")

        rows = conn.execute("SELECT * FROM centers").fetchall()

        result = []
        for r in rows:
            d = dict(r)

            # 품목: center_items 테이블 또는 centers.items 컬럼 중 있는 쪽 사용
            if has_items_table:
                raw_items = [
                    x[0]
                    for x in conn.execute(
                        "SELECT item FROM center_items WHERE center_id=?", (d["id"],)
                    )
                ]
            elif "items" in cols and d.get("items"):
                raw_items = [s.strip() for s in str(d["items"]).split(";") if s.strip()]
            else:
                raw_items = []

            labels = [ITEM_LABEL.get(str(x).strip().lower(), str(x).strip()) for x in raw_items]

            # 프론트(map_script.js)는 세미콜론 구분 문자열을 기대함
            d["items"] = ";".join(labels)
            d.setdefault("gu", d.get("gu"))
            d.setdefault("phone", d.get("phone"))
            d.setdefault("items_unverified", d.get("items_unverified") or "")

            # 품목 필터
            if item:
                key = ITEM_LABEL.get(item.strip().lower(), item.strip())
                if key not in labels:
                    continue

            if lat is not None and lng is not None and d.get("lat") and d.get("lng"):
                d["distance_km"] = round(haversine(lat, lng, d["lat"], d["lng"]), 2)

            result.append(d)

        if lat is not None and lng is not None:
            result.sort(key=lambda x: x.get("distance_km", 1e9))

        return result[:limit]
    finally:
        conn.close()


@router.get("/api/exchange-rules")
def get_exchange_rules():
    """구별 보상 교환 기준. 아직 테이블이 없으면 빈 배열."""
    if not os.path.exists(CENTERS_DB):
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "exchange_rules"):
            return []
        return [dict(r) for r in conn.execute("SELECT * FROM exchange_rules")]
    finally:
        conn.close()


@router.get("/api/sources")
def get_sources():
    """출처(구청 안내 페이지) 목록. 아직 테이블이 없으면 빈 배열."""
    if not os.path.exists(CENTERS_DB):
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "sources"):
            return []
        return [dict(r) for r in conn.execute("SELECT * FROM sources")]
    finally:
        conn.close()
