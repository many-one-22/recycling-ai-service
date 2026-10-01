import sqlite3

conn = sqlite3.connect("centers.db")
conn.executescript("""
DROP TABLE IF EXISTS centers;
DROP TABLE IF EXISTS center_items;
CREATE TABLE centers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, address TEXT, lat REAL, lng REAL
);
CREATE TABLE center_items (
    center_id INTEGER, item TEXT
);
""")

# 샘플 데이터 (팀원 3의 실제 데이터로 교체 예정)
samples = [
    ("A행정복지센터", "광주 ...", 35.1595, 126.8526, ["pet", "can"]),
    ("B행정복지센터", "광주 ...", 35.1750, 126.9070, ["pet", "plastic"]),
    ("C행정복지센터", "광주 ...", 35.1400, 126.8000, ["can", "paper"]),
]
for name, addr, lat, lng, items in samples:
    cur = conn.execute("INSERT INTO centers (name,address,lat,lng) VALUES (?,?,?,?)",
                       (name, addr, lat, lng))
    for it in items:
        conn.execute("INSERT INTO center_items VALUES (?,?)", (cur.lastrowid, it))
conn.commit()