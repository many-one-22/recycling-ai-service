"""Recycling API routes. Put this file in be-api/recycling_api_routes.py.

The production authentication dependency must be connected to the verified
Google-login session/token before protected endpoints can be used.
"""
import importlib.util
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter, Depends, HTTPException,
    UploadFile, File, Form, Query
)
from pydantic import BaseModel, Field

DB_MODULE_FILE = Path(__file__).resolve().parent.parent / 'be-db' / 'admin_trash.py'
if not DB_MODULE_FILE.is_file():
    raise RuntimeError(f'DB 모듈을 찾을 수 없습니다: {DB_MODULE_FILE}')
spec = importlib.util.spec_from_file_location('admin_trash_db', DB_MODULE_FILE)
if spec is None or spec.loader is None:
    raise RuntimeError('DB 모듈을 불러올 수 없습니다.')
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)

router = APIRouter()

# 오류 제보 사진 저장 폴더
UPLOAD_DIR = Path(__file__).resolve().parent.parent / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# 실제 구글 로그인 인증(auth.py)과 연결됨.
# Authorization: Bearer <토큰> 헤더를 검증해서 사용자 정보를 돌려준다.
from auth import current_user


def admin_user(user: Annotated[dict, Depends(current_user)]):
    if not user.get('is_admin'):
        raise HTTPException(status_code=403, detail='관리자만 접근할 수 있습니다.')
    return user


class RecycleRequest(BaseModel):
    item_type: str = Field(min_length=1, max_length=50)
    count: int = Field(default=1, ge=1, le=100)

#오류 제보
class ReportStatusRequest(BaseModel):
    status: str = Field(pattern='^(처리완료|반려)$')
    admin_label: str | None = Field(default=None, max_length=50)

#사용자 차단
class BanRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.get('/api/db-health', include_in_schema=True)
def db_health():
    """Safe connectivity check; does not expose user or report data."""
    try:
        with db.get_db_connection() as conn:
            conn.execute('SELECT 1').fetchone()
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'users', 'recycle_logs', 'reports'}
        return {'database': 'connected', 'tables_ready': required.issubset(tables)}
    except Exception:
        raise HTTPException(status_code=503, detail='DB 연결을 확인할 수 없습니다.')


@router.get('/api/admin/users')
def get_users(_admin: Annotated[dict, Depends(admin_user)]):
    return db.get_all_users()


@router.get('/api/admin/reports')
def get_reports(_admin: Annotated[dict, Depends(admin_user)]):
    return db.get_all_reports()


@router.post('/api/recycle', status_code=201)
def save_recycle(data: RecycleRequest, user: Annotated[dict, Depends(current_user)]):
    if not data.item_type.strip():
        raise HTTPException(status_code=422, detail='품목을 입력하세요.')
    if not db.add_recycle_record(user['id'], data.item_type.strip(), data.count):
        raise HTTPException(status_code=400, detail='재활용 기록 저장 실패')
    return {'message': '재활용 기록 저장 완료', 'added_count': data.count}


# 오류 제보: 사진, AI 예측 결과, 제보 내용 저장
@router.post('/api/reports', status_code=201)
async def save_report(
    user: Annotated[dict, Depends(current_user)],
    content: str = Form(...),
    ai_label: str | None = Form(None),
    image: UploadFile | None = File(None)
):
    content = content.strip()

    if not content or len(content) > 2000:
        raise HTTPException(
            status_code=422,
            detail='제보 내용을 확인하세요.'
        )

    image_path = None
    saved_file = None

    # 사진 저장
    if image is not None:
        allowed_types = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/webp': '.webp'
        }

        extension = allowed_types.get(image.content_type)

        if extension is None:
            raise HTTPException(
                status_code=400,
                detail='JPG, PNG, WEBP 이미지만 업로드할 수 있습니다.'
            )

        # 최대 5MB
        contents = await image.read(5 * 1024 * 1024 + 1)

        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail='사진은 5MB 이하만 업로드할 수 있습니다.'
            )

        # 확장자와 실제 파일 내용 확인
        valid_image = (
            (extension == '.jpg' and contents.startswith(b'\xff\xd8\xff'))
            or (extension == '.png' and contents.startswith(b'\x89PNG\r\n\x1a\n'))
            or (
                extension == '.webp'
                and contents[:4] == b'RIFF'
                and contents[8:12] == b'WEBP'
            )
        )

        if not valid_image:
            raise HTTPException(
                status_code=400,
                detail='올바른 이미지 파일이 아닙니다.'
            )

        # 파일명 중복 방지
        filename = f'{uuid.uuid4().hex}{extension}'

        saved_file = UPLOAD_DIR / filename
        saved_file.write_bytes(contents)

        image_path = f'/static/uploads/{filename}'

    # DB에 제보 저장
    try:
        success = db.create_report(
            user['id'],
            content,
            image_path=image_path,
            ai_label=ai_label
        )
    except Exception:
        if saved_file:
            saved_file.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail='오류 제보 저장 중 문제가 발생했습니다.'
        )

    if not success:
        if saved_file:
            saved_file.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail='오류 제보 저장 실패'
        )

    return {
        'message': '오류 제보 저장 완료',
        'image_path': image_path,
        'ai_label': ai_label
    }

# 관리자: 오류 제보 확인 후 재분류
@router.patch('/api/admin/reports/{report_id}')
def change_report_status(
    report_id: int,
    data: ReportStatusRequest,
    _admin: Annotated[dict, Depends(admin_user)]
):
    # 처리완료 시에는 관리자가 실제 품목을 지정해야 함
    if data.status == '처리완료':
        if not data.admin_label or not data.admin_label.strip():
            raise HTTPException(
                status_code=422,
                detail='최종 분류할 쓰레기 종류를 입력하세요.'
            )

    # DB 함수 호출
    success = db.resolve_report(
        report_id,
        admin_label=(
            data.admin_label.strip()
            if data.admin_label else None
        ),
        status=data.status
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail='제보를 찾을 수 없습니다.'
        )

    return {
        'message': '제보 처리 완료',
        'report_id': report_id,
        'status': data.status,
        'admin_label': data.admin_label
    }


# ==========================================
# 관리자 - 사용자 관리
# ==========================================

# 사용자 정지
@router.post('/api/admin/users/{user_id}/ban')
def ban_user(
    user_id: int,
    data: BanRequest,
    _admin: Annotated[dict, Depends(admin_user)]
):
    if not db.set_banned(user_id, True, data.reason):
        raise HTTPException(
            status_code=400,
            detail='사용자 정지 실패'
        )

    return {'message': '사용자 정지 완료'}


# 사용자 정지 해제
@router.post('/api/admin/users/{user_id}/unban')
def unban_user(
    user_id: int,
    _admin: Annotated[dict, Depends(admin_user)]
):
    if not db.set_banned(user_id, False):
        raise HTTPException(
            status_code=400,
            detail='사용자 정지 해제 실패'
        )

    return {'message': '사용자 정지 해제 완료'}


# 사용자 삭제
@router.delete('/api/admin/users/{user_id}')
def delete_user(
    user_id: int,
    admin: Annotated[dict, Depends(admin_user)]
):
    target = db.get_user_by_id(user_id)

    if not target:
        raise HTTPException(
            status_code=404,
            detail='사용자를 찾을 수 없습니다.'
        )

    # 관리자 계정과 본인 계정 삭제 방지
    if target.get('is_admin') or user_id == admin['id']:
        raise HTTPException(
            status_code=403,
            detail='관리자 또는 본인 계정은 삭제할 수 없습니다.'
        )

    if not db.delete_user(user_id):
        raise HTTPException(
            status_code=400,
            detail='사용자 삭제 실패'
        )

    return {'message': '사용자 삭제 완료'}

# ==========================================
# 관리자 - 통계
# ==========================================

# 전체 요약 통계
@router.get('/api/admin/stats/summary')
def stats_summary(
    _admin: Annotated[dict, Depends(admin_user)]
):
    return db.get_summary_stats()


# 최근 N일 분리배출 추이
@router.get('/api/admin/stats/daily')
def stats_daily(
    _admin: Annotated[dict, Depends(admin_user)],
    days: int = Query(default=7, ge=1, le=365)
):
    return db.get_daily_recycle_stats(days)


# 품목별 분리배출 비율
@router.get('/api/admin/stats/items')
def stats_items(
    _admin: Annotated[dict, Depends(admin_user)]
):
    return db.get_item_type_stats()


# 사용자 분리배출 순위
@router.get('/api/admin/stats/ranking')
def stats_ranking(
    _admin: Annotated[dict, Depends(admin_user)],
    limit: int = Query(default=5, ge=1, le=100)
):
    return db.get_user_ranking(limit)


# 제보 처리 상태별 개수
@router.get('/api/admin/stats/reports')
def stats_reports(
    _admin: Annotated[dict, Depends(admin_user)]
):
    return db.get_report_status_counts()