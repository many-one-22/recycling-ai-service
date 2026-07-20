import os
from flask import Flask, request

app = Flask(__name__)

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/testtext/', methods=['GET', 'POST'])
def print_text_image():
    if request.method == 'GET':
        return '''
        <h1>텍스트 + 사진 받아서 출력하기</h1>
        <form action = '/testtext/' method='POST' enctype="multipart/form-data">
            <p><input name="title" type='text' placeholder='title'></p>
            <p><textarea name="text" placeholder="text"></textarea></p>
            <p><input name='image_file' type='file' accept='image/*'></p>
            <p><input type='submit' value='print'></p>
        </form>
        '''
    
    elif request.method == 'POST':
        received_title = request.form.get('title', '제목없음')
        received_text = request.form.get('text', '내용없음')
        file = request.files.get('image_file')

        img_html = ""
        if file and file.filename != '':
            save_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(save_path) 

            img_html = f'<p><strong>받아온 사진 :</strong><br><img src="/static/uploads/{file.filename}" style="max-width:300px;"></p>'
        else:
            img_html = '<p><strong>받아온 사진 :</strong> 없음</p>'


        return f'''
        <h2>받아온 텍스트 출력</h2>
        <p><strong>받아온 제목 : </strong> {received_title} </p>
        <p><strong>받아온 본문 : </strong> {received_text} </p>
        {img_html}
        <a href='/testtext/'> 다시 </a>
        '''

app.run(debug=True)