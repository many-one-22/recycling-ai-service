"""
seed_quiz.py - 환경 O/X 퀴즈 100문항을 quiz.db에 넣는 스크립트

사용법:
    cd be-db
    python seed_quiz.py

quiz_data.tsv 를 읽어서 quiz.db의 quiz_questions 테이블을 새로 만든다.
문항을 고치고 싶으면 quiz_data.tsv 를 수정한 뒤 이 스크립트를 다시 돌리거나,
DB Browser for SQLite로 quiz.db를 직접 열어서 수정해도 된다.

주의: 사용자의 풀이 기록(quiz_logs)은 recycling.db에 저장된다.
      users 테이블과 외래키로 묶여 있어야 해서 DB를 분리했다.
      이 스크립트는 quiz.db만 건드리므로 풀이 기록은 지워지지 않는다.
"""

import csv
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUIZ_DB = os.path.join(BASE_DIR, "quiz.db")
TSV_PATH = os.path.join(BASE_DIR, "quiz_data.tsv")


def load_rows(tsv_path):
    """TSV를 읽어서 (no, field, question, answer, explanation) 목록으로 반환"""
    rows = []
    with open(tsv_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)  # 번호 / 분야 / 문제 / 정답 / 해설
        if header[0].strip() != "번호":
            raise ValueError(f"첫 줄이 헤더가 아닙니다: {header}")

        for line_no, row in enumerate(reader, start=2):
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != 5:
                raise ValueError(f"{line_no}번째 줄의 칸 수가 5개가 아닙니다: {row}")

            no, field, question, answer, explanation = (c.strip() for c in row)
            answer = answer.upper()
            if answer not in ("O", "X"):
                raise ValueError(f"{line_no}번째 줄의 정답이 O/X가 아닙니다: {answer!r}")

            rows.append((int(no), field, question, answer, explanation))

    return rows


def main():
    rows = load_rows(TSV_PATH)
    print(f"TSV에서 {len(rows)}문항을 읽었습니다.")

    conn = sqlite3.connect(QUIZ_DB)
    try:
        conn.executescript(
            """
            DROP TABLE IF EXISTS quiz_questions;
            CREATE TABLE quiz_questions (
                id          INTEGER PRIMARY KEY,   -- TSV의 '번호'를 그대로 사용
                field       TEXT NOT NULL,         -- 분야 (기후변화, 에너지 ...)
                question    TEXT NOT NULL,         -- 문제 문장
                answer      TEXT NOT NULL CHECK (answer IN ('O','X')),
                explanation TEXT NOT NULL          -- 해설
            );
            CREATE INDEX idx_quiz_field ON quiz_questions(field);
            """
        )
        conn.executemany(
            "INSERT INTO quiz_questions (id, field, question, answer, explanation) "
            "VALUES (?,?,?,?,?)",
            rows,
        )
        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM quiz_questions").fetchone()[0]
        print(f"quiz.db 저장 완료: {total}문항")
        print("분야별 문항 수:")
        for field, cnt in conn.execute(
            "SELECT field, COUNT(*) FROM quiz_questions GROUP BY field ORDER BY MIN(id)"
        ):
            print(f"  - {field}: {cnt}문항")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
