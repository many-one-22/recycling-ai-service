"""auth.py - 구글 로그인 기반 인증 (로그인 / 회원가입 / 회원탈퇴)

흐름
  1) 프론트(sign_in.html)에서 구글 로그인 -> 구글이 ID 토큰 발급
  2) 그 토큰을 POST /auth/google 로 보냄
  3) 서버가 구글에 토큰이 진짜인지 검증 -> 이메일 확인
  4) DB에 없으면 자동 가입(= 회원가입), 있으면 로그인
  5) 우리 서비스 전용 토큰(JWT)을 발급해서 프론트에 전달
  6) 이후 요청은 Authorization: Bearer <토큰> 헤더로 인증

중요: 클라이언트가 보낸 이메일은 절대 그대로 믿지 않는다.
      반드시 구글이 서명한 ID 토큰을 검증해서 얻은 이메일만 사용한다.
"""
import importlib.util
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel

# ------------------------------------------------------------------
# DB 모듈 불러오기 (be-db 폴더 이름에 하이픈이 있어서 일반 import가 안 됨)
# ------------------------------------------------------------------
DB_MODULE_FILE = Path(__file__).resolve().parent.parent / "be-db" / "admin_trash.py"
if not DB_MODULE_FILE.is_file():
    raise RuntimeError(f"DB 모듈을 찾을 수 없습니다: {DB_MODULE_FILE}")
_spec = importlib.util.spec_from_file_location("admin_trash_db", DB_MODULE_FILE)
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)

# ------------------------------------------------------------------
# 설정값 (.env 파일이나 환경변수로 덮어쓸 수 있음)
# ------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# sign_in.html 에 적혀 있는 것과 반드시 같아야 함
GOOGLE_CLIENT_ID = os.getenv(
    "GOOGLE_CLIENT_ID",
    "172339746930-7bfqmf7ahj79cvhdmomativigmqsagmi.apps.googleusercontent.com",
)

# 우리 서비스 토큰(JWT)에 서명할 비밀키. 배포 시에는 반드시 .env로 바꿔야 함
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    JWT_SECRET = "dev-only-insecure-secret-change-me"
    print("[auth] 경고: JWT_SECRET이 설정되지 않아 개발용 기본값을 사용합니다. "
          "배포 전에 .env 파일에 JWT_SECRET을 지정하세요.")

JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 14  # 로그인 유지 기간

router = APIRouter()


# ------------------------------------------------------------------
# 1. 구글 ID 토큰 검증
# ------------------------------------------------------------------
def verify_google_token(token: str) -> dict:
    """구글 ID 토큰을 검증하고 사용자 정보(dict)를 반환.

    google-auth 라이브러리가 설치돼 있으면 그걸로 검증(권장, 네트워크 왕복 없음),
    없으면 구글의 tokeninfo 엔드포인트로 검증한다.
    """
    claims = None

    # (권장) google-auth 라이브러리로 서명 검증
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ImportError:
        # (대체) 구글 tokeninfo 엔드포인트로 검증 - 추가 설치 없이 동작
        try:
            url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode(
                {"id_token": token}
            )
            with urllib.request.urlopen(url, timeout=10) as resp:
                claims = json.loads(resp.read().decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=401, detail="구글 토큰 검증에 실패했습니다.")
    except ValueError:
        raise HTTPException(status_code=401, detail="유효하지 않은 구글 토큰입니다.")

    if not claims:
        raise HTTPException(status_code=401, detail="구글 토큰을 확인할 수 없습니다.")

    # 이 토큰이 "우리 서비스"를 위해 발급된 게 맞는지 확인 (다른 앱 토큰 재사용 차단)
    if claims.get("aud") != GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="다른 앱에서 발급된 토큰입니다.")

    # 발급자가 진짜 구글인지 확인
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status_code=401, detail="구글이 발급한 토큰이 아닙니다.")

    # tokeninfo 응답은 email_verified가 문자열 "true"로 올 수 있음
    email_verified = str(claims.get("email_verified", "")).lower() == "true"
    if not email_verified:
        raise HTTPException(status_code=401, detail="이메일 인증이 완료되지 않은 구글 계정입니다.")

    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="구글 계정에서 이메일을 가져오지 못했습니다.")

    return {
        "email": email,
        "name": claims.get("name"),
        "picture": claims.get("picture"),
    }


# ------------------------------------------------------------------
# 2. 우리 서비스 토큰(JWT) 발급 / 검증
# ------------------------------------------------------------------
def create_access_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),          # 사용자 식별자
        "email": user["email"],
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def current_user(authorization: Annotated[Optional[str], Header()] = None) -> dict:
    """보호된 API에서 쓰는 로그인 확인 함수.

    요청 헤더의 Authorization: Bearer <토큰> 을 검증해서 사용자 정보를 돌려준다.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    token = authorization.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="로그인이 만료되었거나 유효하지 않습니다.")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="토큰 정보가 올바르지 않습니다.")

    # 토큰이 유효해도 그 사이 탈퇴했을 수 있으므로 DB에서 매번 확인
    user = db.get_user_by_id(int(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="탈퇴했거나 존재하지 않는 계정입니다.")

    return user


# ------------------------------------------------------------------
# 3. API 엔드포인트
# ------------------------------------------------------------------
class GoogleLoginRequest(BaseModel):
    token: str


class NotifyRequest(BaseModel):
    enabled: bool


@router.post("/auth/google")
def login_with_google(data: GoogleLoginRequest):
    """로그인 + 회원가입(처음이면 자동 가입)."""
    profile = verify_google_token(data.token)

    user = db.get_or_create_user(
        email=profile["email"],
        name=profile.get("name"),
        picture=profile.get("picture"),
    )
    if not user:
        raise HTTPException(status_code=500, detail="계정 생성에 실패했습니다.")

    access_token = create_access_token(user)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user.get("name") or user["email"].split("@")[0],
            "picture": user.get("picture"),
            "is_admin": bool(user.get("is_admin")),
            "recycled_count": user.get("recycled_count", 0),
        },
    }


@router.get("/api/user/me")
def read_me(user: Annotated[dict, Depends(current_user)]):
    """현재 로그인한 사용자 정보."""
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name") or user["email"].split("@")[0],
        "picture": user.get("picture"),
        "is_admin": bool(user.get("is_admin")),
        "recycled_count": user.get("recycled_count", 0),
        "notify_enabled": bool(user.get("notify_enabled", 1)),
    }


@router.get("/api/user/recycle-count")
def read_recycle_count(user: Annotated[dict, Depends(current_user)]):
    """마이페이지의 '재활용한 쓰레기 개수'."""
    return {"count": user.get("recycled_count", 0)}


@router.patch("/api/user/notify")
def update_notify(data: NotifyRequest, user: Annotated[dict, Depends(current_user)]):
    """알림 켜기/끄기."""
    if not db.set_notify_enabled(user["id"], data.enabled):
        raise HTTPException(status_code=400, detail="알림 설정 변경에 실패했습니다.")
    return {"message": "알림 설정이 변경되었습니다.", "enabled": data.enabled}


@router.delete("/api/user/withdraw")
def withdraw(user: Annotated[dict, Depends(current_user)]):
    """회원탈퇴: 계정과 관련 기록(재활용 로그, 제보)을 모두 삭제."""
    if not db.delete_user(user["id"]):
        raise HTTPException(status_code=400, detail="회원탈퇴 처리에 실패했습니다.")
    return {"message": "회원탈퇴가 완료되었습니다."}
