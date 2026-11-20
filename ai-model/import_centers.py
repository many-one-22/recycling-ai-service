# -*- coding: utf-8 -*-
"""
import_centers.py - 공공데이터포털 주민센터 CSV를 수거함 지도 DB에 넣는다.

입력:  공공데이터포털 "주민센터 현황" CSV
       https://www.data.go.kr/data/3082663/fileData.do
       (컬럼: 연번, 시도, 시군구, 읍면동, 우편번호, 소재지도로명주소, 전화번호, ...)

하는 일:
  1. CSV를 읽는다 (공공데이터 CSV는 보통 EUC-KR 이라 인코딩을 자동 판별)
  2. 도로명주소를 카카오 로컬 API로 좌표(위도/경도)로 바꾼다
  3. ai-model2/backend/centers.db 에 저장한다

카카오 REST API 키가 필요하다. 지도에 쓰는 JavaScript 키와 다른 키다.
  카카오 개발자 콘솔 > 내 애플리케이션 > 앱 키 > REST API 키

사용법:
    cd ai-model
    export KAKAO_REST_KEY=발급받은키
    python import_centers.py 주민센터현황.csv

    # 좌표 변환 없이 먼저 확인만
    python import_centers.py 주민센터현황.csv --dry-run
"""

import argparse
import csv
import io
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_DB = PROJECT_ROOT / "ai-model2" / "backend" / "centers.db"

KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

# ---------------------------------------------------------------------
# 주민센터에 어떤 수거함이 있는지는 이 CSV에 들어있지 않다.
# 구청마다 다르므로, 확인 전까지는 '확인 필요'로 두는 것이 정확하다.
#   - CONFIRMED : 지도 필터에 잡히고, 수거 가능 품목으로 표시된다
#   - UNVERIFIED: 바텀시트에 "센터 문의 후 방문하세요"로 표시된다
# 구청에 확인한 품목은 CONFIRMED 로 옮길 것.
# ---------------------------------------------------------------------
CONFIRMED_ITEMS = ["폐건전지", "폐형광등"]
UNVERIFIED_ITEMS = ["폐의약품", "종이팩", "아이스팩", "투명페트병"]


def read_csv_rows(path: Path):
    """공공데이터 CSV는 EUC-KR(cp949)인 경우가 많아서 인코딩을 차례로 시도한다."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            text = raw.decode(enc)
            rows = list(csv.DictReader(io.StringIO(text)))
            if rows and any(rows[0].keys()):
                print(f"[읽기] {path.name} ({enc}, {len(rows)}행)")
                return rows
        except (UnicodeDecodeError, csv.Error):
            continue
    sys.exit(f"[오류] CSV를 읽지 못했습니다: {path}")


def pick_column(fieldnames, *keywords):
    """컬럼명이 조금씩 달라도 찾을 수 있게, 키워드가 포함된 컬럼을 고른다."""
    for name in fieldnames:
        clean = (name or "").replace(" ", "")
        if any(k in clean for k in keywords):
            return name
    return None


def geocode(address: str, name: str, rest_key: str):
    """도로명주소 -> (위도, 경도). 주소로 못 찾으면 이름으로 한 번 더 시도."""
    headers = {"Authorization": f"KakaoAK {rest_key}"}

    def call(url, params):
        req = urllib.request.Request(
            url + "?" + urllib.parse.urlencode(params), headers=headers
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        data = call(KAKAO_ADDRESS_URL, {"query": address})
        docs = data.get("documents") or []
        if docs:
            return float(docs[0]["y"]), float(docs[0]["x"]), "주소"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("[오류] REST API 키가 올바르지 않습니다 (401). "
                     "JavaScript 키가 아니라 REST API 키인지 확인하세요.")
        print(f"  [경고] 주소 검색 실패({e.code}): {address}")
    except Exception as e:
        print(f"  [경고] 주소 검색 오류: {e}")

    # 주소로 못 찾으면 센터 이름으로 장소 검색
    try:
        data = call(KAKAO_KEYWORD_URL, {"query": name})
        docs = data.get("documents") or []
        if docs:
            return float(docs[0]["y"]), float(docs[0]["x"]), "이름"
    except Exception:
        pass

    return None, None, None


def build_db(db_path: Path, centers):
    """centers.db 를 새로 만든다. 지도 프론트가 기대하는 컬럼을 모두 포함."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            DROP TABLE IF EXISTS centers;
            DROP TABLE IF EXISTS center_items;
            CREATE TABLE centers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT,
                lat REAL,
                lng REAL,
                gu TEXT,
                phone TEXT,
                items_unverified TEXT
            );
            CREATE TABLE center_items (
                center_id INTEGER,
                item TEXT
            );
        """)
        for c in centers:
            cur = conn.execute(
                "INSERT INTO centers (name, address, lat, lng, gu, phone, items_unverified) "
                "VALUES (?,?,?,?,?,?,?)",
                (c["name"], c["address"], c["lat"], c["lng"], c["gu"], c["phone"],
                 ";".join(UNVERIFIED_ITEMS)),
            )
            for item in CONFIRMED_ITEMS:
                conn.execute("INSERT INTO center_items VALUES (?,?)", (cur.lastrowid, item))
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM centers").fetchone()[0]
        print(f"\n[저장] {db_path}  ({total}곳)")
        print("[저장] 구별 분포:")
        for gu, n in conn.execute(
            "SELECT COALESCE(gu,'(미상)'), COUNT(*) FROM centers GROUP BY gu ORDER BY COUNT(*) DESC"
        ):
            print(f"         {gu}: {n}곳")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="주민센터 CSV -> 수거함 지도 DB")
    parser.add_argument("csv_path", help="공공데이터포털에서 받은 CSV 파일")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="저장할 DB 경로")
    parser.add_argument("--key", default=os.getenv("KAKAO_REST_KEY"),
                        help="카카오 REST API 키 (환경변수 KAKAO_REST_KEY 로도 가능)")
    parser.add_argument("--dry-run", action="store_true",
                        help="좌표 변환 없이 CSV 읽기만 확인")
    parser.add_argument("--delay", type=float, default=0.1,
                        help="요청 간 대기 시간(초)")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.is_file():
        sys.exit(f"[오류] CSV 파일이 없습니다: {csv_path.resolve()}")

    rows = read_csv_rows(csv_path)
    fields = list(rows[0].keys())

    col_addr = pick_column(fields, "도로명주소", "소재지", "주소")
    col_dong = pick_column(fields, "읍면동", "행정동", "동명")
    col_gu = pick_column(fields, "시군구", "자치구")
    col_tel = pick_column(fields, "전화번호", "연락처")

    if not col_addr:
        sys.exit(f"[오류] 주소 컬럼을 찾지 못했습니다. 컬럼 목록: {fields}")
    print(f"[컬럼] 주소={col_addr} / 동={col_dong} / 구={col_gu} / 전화={col_tel}")

    centers = []
    for r in rows:
        addr = (r.get(col_addr) or "").strip()
        if not addr:
            continue
        dong = (r.get(col_dong) or "").strip() if col_dong else ""
        gu = (r.get(col_gu) or "").strip() if col_gu else ""
        name = f"{dong}행정복지센터" if dong and not dong.endswith("센터") else (dong or addr)
        centers.append({
            "name": name,
            "address": addr,
            "gu": gu or None,
            "phone": ((r.get(col_tel) or "").strip() or None) if col_tel else None,
            "lat": None, "lng": None,
        })

    print(f"[정리] 유효한 행 {len(centers)}곳")
    if args.dry_run:
        print("\n[미리보기]")
        for c in centers[:5]:
            print(f"   {c['gu']} | {c['name']} | {c['address']} | {c['phone']}")
        print("\n--dry-run 이므로 좌표 변환과 저장은 하지 않았습니다.")
        return

    if not args.key:
        sys.exit("[오류] 카카오 REST API 키가 필요합니다.\n"
                 "      export KAKAO_REST_KEY=발급받은키   또는   --key 발급받은키\n"
                 "      (지도에 쓰는 JavaScript 키가 아니라 REST API 키입니다)")

    print(f"\n[좌표 변환] {len(centers)}건 시작")
    ok, fail = 0, []
    for i, c in enumerate(centers, 1):
        lat, lng, how = geocode(c["address"], c["name"], args.key)
        if lat is None:
            fail.append(c["name"])
        else:
            c["lat"], c["lng"] = lat, lng
            ok += 1
        if i % 20 == 0 or i == len(centers):
            print(f"  {i}/{len(centers)} 처리 (성공 {ok})")
        time.sleep(args.delay)

    print(f"\n[좌표 변환] 성공 {ok}곳 / 실패 {len(fail)}곳")
    if fail:
        print(f"  실패 목록: {fail[:10]}{' ...' if len(fail) > 10 else ''}")
        print("  실패한 곳은 좌표가 비어 지도에 표시되지 않습니다. 주소를 확인하세요.")

    build_db(Path(args.db), [c for c in centers if c["lat"] is not None])

    print("\n확인: 서버를 켜고 http://localhost:8080/fe-map/map_index.html 에서")
    print("      마커가 광주 전역에 퍼져 보이면 성공입니다.")


if __name__ == "__main__":
    main()
