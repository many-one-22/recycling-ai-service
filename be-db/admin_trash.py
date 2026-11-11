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
# 1. 초기화 및 가짜 데이터 삽입, 관리자 계정 지정
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

        # 환경 퀴즈 풀이 기록 (문항 자체는 be-db/quiz.db에 있음)
        # UNIQUE(user_id, quiz_date) 로 하루에 한 번만 기록되게 막는다.
        cursor.execute('''CREATE TABLE IF NOT EXISTS quiz_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            quiz_date TEXT NOT NULL,
            question_id INTEGER NOT NULL,
            choice TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, quiz_date),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )''')
        conn.commit()

        # NEW : 제보에 사진/분류 결과/관리자 판정/ 정지 추가 (이미 있으면 무시)
        for ddl in [
            "ALTER TABLE reports ADD COLUMN image_path TEXT", #제보 사진 저장경로
            "ALTER TABLE reports ADD COLUMN ai_label TEXT", #AI가 분류한 품목
            "ALTER TABLE reports ADD COLUMN admin_label TEXT", # 관리자가 판정한 품목
            "ALTER TABLE reports ADD COLUMN handled_at TIMESTAMP", # 관리자가 제보 처리한 시각
            "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0", # 정지 여부
            "ALTER TABLE users ADD COLUMN banned_reason TEXT", # 정지 사유
            "ALTER TABLE users ADD COLUMN banned_at TIMESTAMP", # 정지한 시각
        ]:
            try:
                cursor.execute(ddl)
            except sqlite3.OperationalError:
                pass
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
def get_user_by_email(email: str): #사용자 한 명 조회
    email = email.strip().lower()
    conn = get_db_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()

def get_user_by_id(user_id: int): #사용자 한 명 조회
    conn = get_db_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()

def create_user(email: str, name: str = None, picture: str = None) -> bool: #사용자 생성
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

def set_notify_enabled(user_id: int, enabled: bool) -> bool: #알림 설정
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
        cursor.execute("DELETE FROM quiz_logs WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

# NEW 사용자 정지/해제. 계정과 기록은 남기고 로그인만 막음. 해제 가능 (관리자 계정은 정지 불가)
def set_banned(user_id: int, banned: bool, reason: str = None) -> bool:
    conn = get_db_connection()
    try:
        user = conn.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["is_admin"]:
            return False
        if banned:
            conn.execute(
                "UPDATE users SET is_banned = 1, banned_reason = ?, banned_at = CURRENT_TIMESTAMP WHERE id = ?",
                (reason, user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET is_banned = 0, banned_reason = NULL, banned_at = NULL WHERE id = ?",
                (user_id,),
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"[set_banned 실패] user_id={user_id}, error={e}")
        return False
    finally:
        conn.close()

# ==========================================
# 3. CRUD 함수 (관리자)
# ==========================================
def get_all_users():
    conn = get_db_connection()
    try:
        users = conn.execute(
            "SELECT id, email, name, picture, recycled_count, is_admin, is_banned, banned_reason, created_at FROM users"
        ).fetchall()
        return [dict(u) for u in users]
    finally:
        conn.close()

def get_all_reports():
    conn = get_db_connection()
    try: # query: 제보 목록 조회 (관리자용)
        query = '''
            SELECT r.id, r.content, r.status, r.created_at,
                   r.image_path, r.ai_label, r.admin_label, r.handled_at,
                   u.email
            FROM reports r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.created_at DESC, r.id DESC
        '''
        reports = conn.execute(query).fetchall()
        return [dict(r) for r in reports]
    finally:
        conn.close()

# 카운트 안되는 이유 알 수 있도록 print 추가 
def add_recycle_record(user_id: int, item_type: str, count: int) -> bool:
    if count <= 0:
        print(f"[add_recycle_record] count가 0 이하라 저장 안 함: {count}")
        return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO recycle_logs (user_id, item_type, count) VALUES (?, ?, ?)", (user_id, item_type, count))
        cursor.execute("UPDATE users SET recycled_count = recycled_count + ? WHERE id = ?", (count, user_id))

        if cursor.rowcount == 0:
            print(f"[add_recycle_record] user_id={user_id} 사용자를 못 찾음")
            conn.rollback()
            return False

        conn.commit()
        return True
    except Exception as e:
        print(f"[add_recycle_record] 실패: user_id={user_id}, item_type={item_type}, error={e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# NEW create_report 함수: 제보 생성 (사진/AI 분류 결과 포함)
def create_report(user_id: int, content: str, image_path: str = None,
                  ai_label: str = None) -> bool:
    if not (content or "").strip():
        return False
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO reports (user_id, content, image_path, ai_label) VALUES (?, ?, ?, ?)",
            (user_id, content, image_path, ai_label),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[create_report 실패] user_id={user_id}, error={e}")
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


# 관리자 페이지에서 제보 처리 시, 처리 완료/반려 상태를 선택할 수 있도록 수정.
# update_report_status와 다른 점은, 처리 완료 시 관리자가 최종 품목(admin_label)을 지정할 수 있다는 점.
def resolve_report(report_id: int, admin_label: str = None, status: str = '처리완료') -> bool:
    """관리자가 제보를 확인하고 최종 품목을 정해 처리"""
    if status not in ['대기중', '처리완료', '반려']:
        return False
    conn = get_db_connection()
    try:
        cur = conn.execute(
            """UPDATE reports
               SET status = ?,
                   admin_label = COALESCE(?, admin_label),
                   handled_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (status, admin_label, report_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
# ==========================================
# 4. 통계 함수 (관리자 페이지 통계)
# ==========================================
# 최근 N일 일별 분리배출 개수 (꺾은선 그래프)
def get_daily_recycle_stats(days: int = 7):
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT date(created_at, 'localtime') AS day, SUM(count) AS total
               FROM recycle_logs
               WHERE date(created_at, 'localtime') >= date('now', 'localtime', ?)
               GROUP BY day ORDER BY day""",
            (f'-{days - 1} days',),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# 품목별 총 개수 (원그래프용)
def get_item_type_stats():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT item_type, SUM(count) AS total FROM recycle_logs GROUP BY item_type ORDER BY total DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# 분리배출 많이 한 사용자 TOP N (막대그래프용)
def get_user_ranking(limit: int = 5):
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT email, name, recycled_count FROM users ORDER BY recycled_count DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# 제보 상태별 개수 (대기중/처리완료/반려)
def get_report_status_counts():
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT status, COUNT(*) AS cnt FROM reports GROUP BY status").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# 관리자 화면 상단 요약 카드용
def get_summary_stats():
    conn = get_db_connection()
    try:
        return {
            "total_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "active_users_7d": conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM recycle_logs "
                "WHERE date(created_at, 'localtime') >= date('now', 'localtime', '-6 days')"
            ).fetchone()[0],
            "total_recycled": conn.execute("SELECT COALESCE(SUM(count), 0) FROM recycle_logs").fetchone()[0],
            "pending_reports": conn.execute("SELECT COUNT(*) FROM reports WHERE status = '대기중'").fetchone()[0],
            "banned_users": conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1").fetchone()[0],
        }
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()

