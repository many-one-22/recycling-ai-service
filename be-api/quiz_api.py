"""
quiz_api.py - 환경 O/X 데일리 퀴즈 API

하루에 한 문제씩 나온다. 날짜(한국 시간 기준)로 문항이 정해지므로
같은 날 접속한 사람은 모두 같은 문제를 본다.

DB 두 개를 쓴다.
  - be-db/quiz.db       : 문항 100개 (quiz_questions)   <- 팀에서 내용 수정하는 쪽
  - be-db/recycling.db  : 풀이 기록 (quiz_logs)          <- users 테이블과 외래키로 연결

엔드포인트
  GET  /api/quiz/today   오늘의 문제 (정답/해설은 숨김)
  POST /api/quiz/answer  O/X 제출 -> 정답 여부 + 해설 반환, 로그인 상태면 기록 저장
  GET  /api/quiz/stats   내 누적 성적 (마이페이지용, 로그인 필요)

정답을 /today 응답에 넣지 않는 이유: 개발자도구로 미리 볼 수 있기 때문.
제출(/answer) 시점에 서버가 채점해서 정답과 해설을 돌려준다.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import auth  # 같은 be-api 폴더의 auth.py (current_user 재사용)

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUIZ_DB = os.path.join(BASE_DIR, "be-db", "quiz.db")
USER_DB = os.path.join(BASE_DIR, "be-db", "recycling.db")

KST = timezone(timedelta(hours=9))


# ------------------------------------------------------------------
# DB 헬퍼
# ------------------------------------------------------------------
def _quiz_conn():
    if not os.path.exists(QUIZ_DB):
        raise HTTPException(
            status_code=503,
            detail="퀴즈 DB가 없습니다. be-db 폴더에서 python seed_quiz.py 를 실행하세요.",
        )
    conn = sqlite3.connect(QUIZ_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _user_conn():
    conn = sqlite3.connect(USER_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_quiz_log_table():
    """quiz_logs 테이블이 없으면 만든다.

    admin_trash.init_db()는 수동 실행이라, 서버만 켠 상태에서도
    퀴즈가 동작하도록 여기서 한 번 더 보장한다.
    """
    try:
        conn = _user_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                quiz_date TEXT NOT NULL,
                question_id INTEGER NOT NULL,
                choice TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, quiz_date),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.commit()
        conn.close()
    except Exception as e:  # DB가 아직 없을 수도 있으니 서버 기동은 막지 않는다
        print(f"[quiz] quiz_logs 테이블 준비 실패(무시하고 계속): {e}")


ensure_quiz_log_table()


# ------------------------------------------------------------------
# 오늘의 문항 고르기
# ------------------------------------------------------------------
def today_kst() -> str:
    """한국 시간 기준 오늘 날짜 (YYYY-MM-DD)."""
    return datetime.now(KST).strftime("%Y-%m-%d")


def pick_question_for_date(conn, date_str: str):
    """날짜로 문항을 결정한다.

    날짜의 일련번호를 전체 문항 수로 나눈 나머지를 쓰기 때문에
    - 같은 날이면 항상 같은 문제가 나오고
    - 100문항이면 100일 주기로 한 바퀴 돈다.
    """
    ids = [r[0] for r in conn.execute("SELECT id FROM quiz_questions ORDER BY id")]
    if not ids:
        raise HTTPException(status_code=503, detail="등록된 퀴즈 문항이 없습니다.")

    ordinal = datetime.strptime(date_str, "%Y-%m-%d").date().toordinal()
    qid = ids[ordinal % len(ids)]

    row = conn.execute(
        "SELECT * FROM quiz_questions WHERE id = ?", (qid,)
    ).fetchone()
    return row, len(ids)


# ------------------------------------------------------------------
# 로그인 여부가 선택인 사용자 조회
# ------------------------------------------------------------------
def optional_user(
    authorization: Annotated[Optional[str], Header()] = None
) -> Optional[dict]:
    """로그인했으면 사용자 정보, 아니면 None.

    퀴즈는 로그인 없이도 풀 수 있어야 하므로 401을 던지지 않는다.
    """
    if not authorization:
        return None
    try:
        return auth.current_user(authorization)
    except HTTPException:
        return None


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------
class AnswerRequest(BaseModel):
    choice: str  # "O" 또는 "X"


@router.get("/api/quiz/today")
def get_today_quiz(user: Annotated[Optional[dict], Depends(optional_user)] = None):
    """오늘의 문제. 이미 푼 사람에게는 정답과 해설까지 같이 준다."""
    date_str = today_kst()
    conn = _quiz_conn()
    try:
        q, total = pick_question_for_date(conn, date_str)
    finally:
        conn.close()

    result = {
        "date": date_str,
        "question_id": q["id"],
        "field": q["field"],
        "question": q["question"],
        "total_questions": total,
        "answered": False,
        "logged_in": user is not None,
    }

    # 로그인 상태면 오늘 이미 풀었는지 확인
    if user:
        conn = _user_conn()
        try:
            log = conn.execute(
                "SELECT * FROM quiz_logs WHERE user_id = ? AND quiz_date = ?",
                (user["id"], date_str),
            ).fetchone()
        finally:
            conn.close()

        if log:
            result.update(
                {
                    "answered": True,
                    "my_choice": log["choice"],
                    "is_correct": bool(log["is_correct"]),
                    "answer": q["answer"],
                    "explanation": q["explanation"],
                }
            )

    return result


@router.post("/api/quiz/answer")
def submit_answer(
    data: AnswerRequest,
    user: Annotated[Optional[dict], Depends(optional_user)] = None,
):
    """O/X를 제출하면 채점해서 정답과 해설을 돌려준다."""
    choice = (data.choice or "").strip().upper()
    if choice not in ("O", "X"):
        raise HTTPException(status_code=400, detail="O 또는 X만 제출할 수 있습니다.")

    date_str = today_kst()
    conn = _quiz_conn()
    try:
        q, _ = pick_question_for_date(conn, date_str)
    finally:
        conn.close()

    is_correct = choice == q["answer"]
    already_answered = False

    # 로그인 상태면 기록 저장 (하루 한 번)
    if user:
        conn = _user_conn()
        try:
            prev = conn.execute(
                "SELECT * FROM quiz_logs WHERE user_id = ? AND quiz_date = ?",
                (user["id"], date_str),
            ).fetchone()

            if prev:
                # 이미 푼 날이면 기록을 덮어쓰지 않는다 (정답 맞출 때까지 재시도 방지)
                already_answered = True
                choice = prev["choice"]
                is_correct = bool(prev["is_correct"])
            else:
                conn.execute(
                    "INSERT INTO quiz_logs (user_id, quiz_date, question_id, choice, is_correct) "
                    "VALUES (?,?,?,?,?)",
                    (user["id"], date_str, q["id"], choice, int(is_correct)),
                )
                conn.commit()
        finally:
            conn.close()

    return {
        "date": date_str,
        "question_id": q["id"],
        "my_choice": choice,
        "answer": q["answer"],
        "is_correct": is_correct,
        "explanation": q["explanation"],
        "already_answered": already_answered,
        "saved": user is not None and not already_answered,
        "logged_in": user is not None,
    }


@router.get("/api/quiz/stats")
def get_my_stats(user: Annotated[dict, Depends(auth.current_user)]):
    """마이페이지용 누적 성적."""
    conn = _user_conn()
    try:
        rows = conn.execute(
            "SELECT quiz_date, is_correct FROM quiz_logs WHERE user_id = ? "
            "ORDER BY quiz_date DESC",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()

    solved = len(rows)
    correct = sum(1 for r in rows if r["is_correct"])

    # 연속 참여일수: 오늘(또는 어제)부터 하루씩 거슬러 올라가며 센다
    dates = {r["quiz_date"] for r in rows}
    streak = 0
    cursor_date = datetime.now(KST).date()
    if cursor_date.strftime("%Y-%m-%d") not in dates:
        cursor_date -= timedelta(days=1)  # 오늘 아직 안 풀었으면 어제부터 센다
    while cursor_date.strftime("%Y-%m-%d") in dates:
        streak += 1
        cursor_date -= timedelta(days=1)

    return {
        "solved": solved,
        "correct": correct,
        "wrong": solved - correct,
        "accuracy": round(correct / solved * 100) if solved else 0,
        "streak": streak,
    }
