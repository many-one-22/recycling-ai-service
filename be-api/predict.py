import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'be-db'))
from db import get_guide  # be-db/db.py의 get_guide 함수 임포트

app = Flask(__name__)
app.json.ensure_ascii = False #한글
CORS(app) #접근 허용

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/predict', methods=['GET', 'POST'])
def predict():
    if request.method == 'GET':
            return '''
            <h1>테스트 페이지</h1>
            <form action = '/predict' method='POST' enctype="multipart/form-data">
                <p><input name="title" type='text' placeholder='title'></p>
                <p><textarea name="text" placeholder="text"></textarea></p>
                <p><input name='image_file' type='file' accept='image/*'></p>
                <p><input type='submit' value='print'></p>
            </form>
            '''
    
    file = request.files.get('image_file')

    filename_result = "없음"
    if file and file.filename != '':
        save_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(save_path)  #이미지 서버에 저장
        filename_result = file.filename

    target_category = "페트병" #추후 AI 모델 예측값

    disposal_guide = get_guide(target_category)
    if not disposal_guide:
         disposal_guide = "깨끗이 씻어서 재질별로 배출해 주세요."

    response_data = {
        "status": "success",
        "saved_filename": filename_result,
        #응답 예시
        "prediction": {
            "category": target_category,
            "item_name": target_category,
            "disposal_method": disposal_guide
        }
    }

    return jsonify(response_data)

app.run(debug=True)
