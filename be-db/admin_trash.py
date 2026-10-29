import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "recycling.db")

# 관리자로 쓸 구글 계정. .env 의 ADMIN_EMAIL 로 덮어쓸 수 있음
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "dawon1703@gmail.com")

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ==========================================
# 1. 초기화 및 가짜 데이터 삽입
# ==========================================
def init_db():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            picture TEXT,
            recycled_count INTEGER DEFAULT 0,
            notify_enabled BOOLEAN DEFAULT 1,
            is_admin BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # 이미 만들어진 DB에도 새 컬럼을 추가 (이미 있으면 무시)
        for ddl in [
            "ALTER TABLE users ADD COLUMN name TEXT",
            "ALTER TABLE users ADD COLUMN picture TEXT",
            "ALTER TABLE users ADD COLUMN notify_enabled BOOLEAN DEFAULT 1",
        ]:
            try:
                cursor.execute(ddl)
            except sqlite3.OperationalError:
                pass

        cursor.execute('''CREATE TABLE IF NOT EXISTS recycle_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_type TEXT,
            count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT NOT NULL,
            status TEXT DEFAULT '대기중',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )''')
        conn.commit()

        # 관리자로 쓸 구글 계정 (이 이메일로 로그인하면 관리자 권한)
        admin_email = ADMIN_EMAIL

        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO users (email, is_admin) VALUES (?, ?)", (admin_email, 1))
            cursor.execute("INSERT INTO users (email, recycled_count, is_admin) VALUES (?, ?, ?)", ('user1@test.com', 15, 0))
            cursor.execute("INSERT INTO users (email, recycled_count, is_admin) VALUES (?, ?, ?)", ('user2@test.com', 5, 0))
            
            cursor.execute("INSERT INTO reports (user_id, content) VALUES (?, ?)", (2, "페트병 라벨 인식이 가끔 안 됩니다. 확인 부탁드려요."))
            conn.commit()
            print(f"DB 세팅 완료! (관리자 계정: {admin_email})")

        # 이미 DB가 만들어진 뒤여도 관리자 계정은 항상 관리자 권한을 갖도록 보정.
        # (구글 로그인으로 먼저 가입된 경우에도 관리자로 승격됨)
        cursor.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (admin_email,))
        conn.commit()
    finally:
        conn.close()

# ==========================================
# 2. CRUD 함수 (인증 및 사용자 관리)
# ==========================================
def get_user_by_email(email: str):
    email = email.strip().lower()
    conn = get_db_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()

def get_user_by_id(user_id: int):
    conn = get_db_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()

def create_user(email: str, name: str = None, picture: str = None) -> bool:
    email = email.strip().lower()
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO users (email, name, picture) VALUES (?, ?, ?)",
            (email, name, picture),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

#로그인 요청 시, 이미 가입된 사람인지 확인하고, 없으면 가입시키는 함수 (= 회원가입)
def get_or_create_user(email: str, name: str = None, picture: str = None):
    email = email.strip().lower()
    user = get_user_by_email(email)

    if user:
        # 이미 가입된 사람이면, 구글 프로필이 바뀌었을 수 있으니 최신값으로 갱신
        if name or picture:
            conn = get_db_connection()
            try:
                conn.execute(
                    "UPDATE users SET name = COALESCE(?, name), picture = COALESCE(?, picture) WHERE id = ?",
                    (name, picture, user["id"]),
                )
                conn.commit()
            finally:
                conn.close()
            user = get_user_by_email(email)
        return user

    # 처음 온 사람이면 가입 시키고 정보 반환
    create_user(email, name, picture)
    return get_user_by_email(email)

def set_notify_enabled(user_id: int, enabled: bool) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "UPDATE users SET notify_enabled = ? WHERE id = ?", (1 if enabled else 0, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_user(user_id: int) -> bool:
    """회원탈퇴: 해당 사용자의 기록(recycle_logs, reports)까지 모두 지운 뒤 계정 삭제.

    users를 먼저 지우면 외래키 제약(PRAGMA foreign_keys=ON) 때문에 실패하므로
    자식 테이블 -> 부모 테이블 순서로 지워야 함.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recycle_logs WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM reports WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

# ==========================================
# 3. CRUD 함수 (비즈니스 및 관리자)
# ==========================================
def get_all_users():
    conn = get_db_connection()
    try:
        users = conn.execute("SELECT id, email, recycled_count, is_admin, created_at FROM users").fetchall()
        return [dict(u) for u in users]
    finally:
        conn.close()

def get_all_reports():
    conn = get_db_connection()
    try:
        query = '''
            SELECT r.id, r.content, r.status, r.created_at, u.email 
            FROM reports r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.created_at DESC, r.id DESC
        '''
        reports = conn.execute(query).fetchall()
        return [dict(r) for r in reports]
    finally:
        conn.close()

def add_recycle_record(user_id: int, item_type: str, count: int) -> bool:
    if count <= 0: return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO recycle_logs (user_id, item_type, count) VALUES (?, ?, ?)", (user_id, item_type, count))
        cursor.execute("UPDATE users SET recycled_count = recycled_count + ? WHERE id = ?", (count, user_id))
        
        if cursor.rowcount == 0:
            conn.rollback()
            return False
            
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

def create_report(user_id: int, content: str) -> bool:
    if not content.strip(): return False
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO reports (user_id, content) VALUES (?, ?)", (user_id, content))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

# 대기중/처리완료 상태만 받도록 안전장치 추가
def update_report_status(report_id: int, new_status: str) -> bool:
    if new_status not in ['대기중', '처리완료']:
        return False
    conn = get_db_connection()
    try:
        cursor = conn.execute("UPDATE reports SET status = ? WHERE id = ?", (new_status, report_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()