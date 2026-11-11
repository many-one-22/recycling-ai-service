import os
import sys
import importlib
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from recycling_api_routes import router as recycling_router
from auth import router as auth_router
from centers_api import router as centers_router
from quiz_api import router as quiz_router

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# DB 및 모델 모듈 임포트
db_module = importlib.import_module("be-db.db")
get_guide = db_module.get_guide

import predict as predict_module
predict = predict_module.predict


# 개발 중에는 브라우저가 옛날 HTML/CSS/JS를 계속 쓰는 일이 잦아서
# 정적 파일마다 "항상 서버에 바뀐 게 있는지 물어보라"고 알려준다.
# (파일이 그대로면 304만 오가므로 느려지지 않는다)
class NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app = FastAPI()
app.include_router(auth_router)
app.include_router(recycling_router)
app.include_router(centers_router)
app.include_router(quiz_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

UI_DIR = os.path.join(BASE_DIR, "ai-model/Frontend2/fe-ui")
app.mount("/fe-ui", NoCacheStaticFiles(directory=UI_DIR), name="fe-ui")

CAM_DIR = os.path.join(BASE_DIR, "ai-model/Frontend2/fe-camera")
if os.path.exists(CAM_DIR):
    app.mount("/fe-camera", NoCacheStaticFiles(directory=CAM_DIR), name="fe-camera")

MAP_DIR = os.path.join(BASE_DIR, "ai-model/Frontend2/fe-map")
if os.path.exists(MAP_DIR):
    app.mount("/fe-map", NoCacheStaticFiles(directory=MAP_DIR), name="fe-map")

QUIZ_DIR = os.path.join(BASE_DIR, "ai-model/Frontend2/fe-quiz")
if os.path.exists(QUIZ_DIR):
    app.mount("/fe-quiz", NoCacheStaticFiles(directory=QUIZ_DIR), name="fe-quiz")

# be-api 폴더
CHECKPOINT_PATH = os.path.join(BASE_DIR, "be-api", "best_recycling_model.pth")

# 홈 화면 연결 (/)
@app.get("/")
async def serve_home():
    return FileResponse(os.path.join(UI_DIR, "index.html"), headers={"Cache-Control": "no-cache, must-revalidate"})

# index.html의 상대경로 href="style.css" 지원용
@app.get("/style.css")
async def serve_style():
    return FileResponse(os.path.join(UI_DIR, "style.css"), headers={"Cache-Control": "no-cache, must-revalidate"})

# 결과 화면 연결 (/result)
@app.get("/result")
async def serve_result():
    return FileResponse(os.path.join(UI_DIR, "result.html"), headers={"Cache-Control": "no-cache, must-revalidate"})

# 카메라 화면 연결
@app.get("/camera")
async def serve_camera():
    return RedirectResponse(url="/fe-camera/camera.html")

# 수거함 지도 화면 연결
@app.get("/map")
async def serve_map():
    return RedirectResponse(url="/fe-map/map_index.html")

# 환경 퀴즈 화면 연결
@app.get("/quiz")
async def serve_quiz():
    return RedirectResponse(url="/fe-quiz/quiz_index.html")

@app.post("/predict")
async def predict_waste(image_file: UploadFile = File(...)):
    # 1. 업로드된 파일 저장
    file_path = os.path.join(UPLOAD_FOLDER, image_file.filename)
    contents = await image_file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    # 2. predict.py 실행 (가중치 파일 없을 시 목업 데이터로 안전하게 처리)
    if os.path.exists(CHECKPOINT_PATH):
        result = predict(file_path, CHECKPOINT_PATH)
        category = result["predicted_class"]
        confidence = result["confidence"]
    else:
        category = "페트병"
        confidence = 0.954

    # 3. DB에서 분리배출 방법 조회 (get_guide)
    raw_guide = get_guide(category)

    # 4. DB 긴 문장을 체크리스트 3단계 배열(steps)로 파싱
    steps = []
    if raw_guide:
        if "," in raw_guide:
            steps = [s.strip() for s in raw_guide.split(",") if s.strip()]
        else:
            parts = re.split(r"(?<=[고|후])\s+", raw_guide)
            steps = [p.strip() for p in parts if p.strip()]

    # 5. 프론트엔드로 JSON 응답 전달
    return {
        "category": category,
        "title": f"{category}으로 분류돼요",
        "sub_title": "올바른 분리배출을 실천해주세요",
        "confidence": confidence,
        "guide": raw_guide,
        "steps": steps,
        "image_url": f"/static/uploads/{image_file.filename}"
    }