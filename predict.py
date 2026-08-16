import os
from flask import Flask, request, jsonify
from flask_cors import CORS

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

    #DB 조회 함수 위치

    response_data = {
        "status": "success",
        "saved_filename": filename_result,
        #응답 예시
        "prediction": {
            "category": "유리병",
            "item_name": "투명 유리병",
            "disposal_method": "깨끗한 유리병은 유리병 수거함으로 배출합니다."
        }
    }

    return jsonify(response_data)

app.run(debug=True)
