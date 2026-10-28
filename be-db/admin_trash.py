import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "recycling.db")

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
            recycled_count INTEGER DEFAULT 0,
            is_admin BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

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

        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            # 여기에 실제 구글 로그인을 할 팀원의 진짜 이메일을 적기.
            admin_email = '팀원의진짜구글이메일@gmail.com' 
            
            cursor.execute("INSERT INTO users (email, is_admin) VALUES (?, ?)", (admin_email, 1))
            cursor.execute("INSERT INTO users (email, recycled_count, is_admin) VALUES (?, ?, ?)", ('user1@test.com', 15, 0))
            cursor.execute("INSERT INTO users (email, recycled_count, is_admin) VALUES (?, ?, ?)", ('user2@test.com', 5, 0))
            
            cursor.execute("INSERT INTO reports (user_id, content) VALUES (?, ?)", (2, "페트병 라벨 인식이 가끔 안 됩니다. 확인 부탁드려요."))
            conn.commit()
            print(f"DB 세팅 완료! (관리자 계정: {admin_email})")
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

def create_user(email: str) -> bool:
    email = email.strip().lower()
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (email) VALUES (?)", (email,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

#로그인 요청 시, 이미 가입된 사람인지 확인하고, 없으면 가입시키는 함수
def get_or_create_user(email: str):
    email = email.strip().lower()
    user = get_user_by_email(email)
    if user:
        return user # 이미 가입된 사람이면 정보 반환
    
    # 처음 온 사람이면 가입 시키고 정보 반환
    create_user(email)
    return get_user_by_email(email)

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