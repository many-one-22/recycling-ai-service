"""Recycling API routes. Put this file in be-api/recycling_api_routes.py.

The production authentication dependency must be connected to the verified
Google-login session/token before protected endpoints can be used.
"""
import importlib.util
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
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


def current_user():
    """Replace with verified Google-login session/token lookup.

    Never trust an email or user_id provided directly by the client.
    """
    raise HTTPException(status_code=503, detail='로그인 인증 연결이 아직 설정되지 않았습니다.')


def admin_user(user: Annotated[dict, Depends(current_user)]):
    if not user.get('is_admin'):
        raise HTTPException(status_code=403, detail='관리자만 접근할 수 있습니다.')
    return user


class RecycleRequest(BaseModel):
    item_type: str = Field(min_length=1, max_length=50)
    count: int = Field(default=1, ge=1, le=100)


class ReportRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class ReportStatusRequest(BaseModel):
    status: str = Field(pattern='^(대기중|확인중|처리완료)$')


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


@router.get('/admin/users')
def get_users(_admin: Annotated[dict, Depends(admin_user)]):
    return db.get_all_users()


@router.get('/admin/reports')
def get_reports(_admin: Annotated[dict, Depends(admin_user)]):
    return db.get_all_reports()


@router.post('/recycle', status_code=201)
def save_recycle(data: RecycleRequest, user: Annotated[dict, Depends(current_user)]):
    if not data.item_type.strip():
        raise HTTPException(status_code=422, detail='품목을 입력하세요.')
    if not db.add_recycle_record(user['id'], data.item_type.strip(), data.count):
        raise HTTPException(status_code=400, detail='재활용 기록 저장 실패')
    return {'message': '재활용 기록 저장 완료', 'added_count': data.count}


@router.post('/reports', status_code=201)
def save_report(data: ReportRequest, user: Annotated[dict, Depends(current_user)]):
    if not data.content.strip():
        raise HTTPException(status_code=422, detail='제보 내용을 입력하세요.')
    if not db.create_report(user['id'], data.content.strip()):
        raise HTTPException(status_code=400, detail='오류 제보 저장 실패')
    return {'message': '오류 제보 저장 완료'}


@router.patch('/admin/reports/{report_id}')
def change_report_status(report_id: int, data: ReportStatusRequest, _admin: Annotated[dict, Depends(admin_user)]):
    if not db.update_report_status(report_id, data.status):
        raise HTTPException(status_code=404, detail='제보를 찾을 수 없습니다.')
    return {'message': '제보 상태 변경 완료', 'report_id': report_id, 'status': data.status}
