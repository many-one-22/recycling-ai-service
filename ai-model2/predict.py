# -*- coding: utf-8 -*-
"""predict.py - 회색 패딩(letterbox) 적용 버전

train.py와 반드시 동일한 전처리(pad_to_square + Resize + Normalize)를 사용해야 함.
학습 때와 추론 때 전처리가 다르면 모델 성능이 왜곡됨.
"""

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import os

# 디바이스 설정 (Mac, CUDA GPU, CPU 자동 판별)

if torch.cuda.is_available():
    device = torch.device("cuda:0")
elif torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print(f"현재 예측에 사용하는 디바이스: {device}")


# -------------------------------------------------------------
# [신규] 정사각형 패딩 (letterbox) - train.py와 완전히 동일한 함수
# -------------------------------------------------------------
def pad_to_square(image, fill_color=(114, 114, 114)):
    width, height = image.size
    max_side = max(width, height)
    new_image = Image.new("RGB", (max_side, max_side), fill_color)
    new_image.paste(image, ((max_side - width) // 2, (max_side - height) // 2))
    return new_image


# -------------------------------------------------------------
# 저장된 모델 및 클래스 정보
# -------------------------------------------------------------
def load_model(checkpoint_path):
    # checkpoint 파일 불러오기
    checkpoint = torch.load(checkpoint_path, map_location=device)
    class_names = checkpoint['classes']
    num_classes = len(class_names)

    # train.py와 똑같은 구조로 MobileNetV2 뼈대생성
    model = models.mobilenet_v2(weights=None) # 새로 학습할 게 아니므로 None
    num_ftrs = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(num_ftrs, num_classes)

    # train.py에서 공부해서 저장했던 가중치 덮어씌우기
    model.load_state_dict(checkpoint['model_state_dict'])
    model = model.to(device)

    # 평가 모드로 변경
    model.eval()

    return model, class_names


# -------------------------------------------------------------
# 테스트할 새 이미지 전처리
# [수정] pad_to_square를 Resize 앞에 추가 (train.py의 val 전처리와 반드시 동일해야 함)
# -------------------------------------------------------------
predict_transform = transforms.Compose([
    transforms.Lambda(pad_to_square),   # [신규] 비율 왜곡 방지
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])


# -------------------------------------------------------------
# 이미지 한 장 받아서 예측하는 함수
# -------------------------------------------------------------
def predict_image(image_path, model, class_names):
    # 이미지 파일 열기
    image = Image.open(image_path).convert('RGB')

    # 전처리 적용 및 모델에 넣기 위한 차원 맞춰주기 (1, C, H, W)
    input_tensor = predict_transform(image).unsqueeze(0).to(device)

    # 기울기 계산 안함 (추론 속도 향상, 메모리 절약)
    with torch.no_grad():
        outputs = model(input_tensor)

        # 점수를 확률(0~100%)로 변환
        probabilities = torch.softmax(outputs, dim=1)[0]

        # 가장 높은 점수를 얻은 클래스의 번호 추출
        _, pred_idx = torch.max(outputs, 1)

        predicted_class = class_names[pred_idx.item()]
        confidence = probabilities[pred_idx.item()].item() * 100

    return predicted_class, confidence, probabilities


# -------------------------------------------------------------
#  !! 실제 실행 !!
# -------------------------------------------------------------
if __name__ == "__main__":
    MODEL_PATH = 'best_recycling_model.pth' # train.py가 만들어준 최종 파일

    # 테스트해보고 싶은 이미지 파일 경로를 넣기
    # [참고] 이제 pad_to_square가 자동으로 적용되므로, 미리 패딩한 파일을 안 넣어도 됨
    #        (glass4-2_padded_gray.jpg 대신 원본 glass4-2.jpg를 그대로 넣으면 됨)
    TEST_IMAGE_PATH = 'dataset_new/paper/paper4-2.jpg'

    if os.path.exists(MODEL_PATH) and os.path.exists(TEST_IMAGE_PATH):
        # 모델 로드
        model, class_names = load_model(MODEL_PATH)

        # 예측 실행
        pred_class, confidence, probs = predict_image(TEST_IMAGE_PATH, model, class_names)

        print("\n" + "="*30)
        print(f"테스트 이미지: {TEST_IMAGE_PATH}")
        print(f"AI의 예측 결과: [{pred_class}]")
        print(f"확신도(확률): {confidence:.2f}%")
        print("="*30)

        # 클래스별 상세 확률 확인하기
        print("\n[전체 클래스별 확률]")
        for idx, name in enumerate(class_names):
            print(f"- {name}: {probs[idx].item()*100:.2f}%")

    else:
        print("'best_recycling_model.pth' 파일이나 테스트용 이미지 경로를 다시 확인해주세요!")