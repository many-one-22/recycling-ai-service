# -*- coding: utf-8 -*-
"""predict.py - 회색 패딩(letterbox) + TTA(Test-Time Augmentation) 적용 버전

train.py와 반드시 동일한 기본 전처리(pad_to_square + Resize + Normalize)를 사용해야 함.
"""

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import os

if torch.cuda.is_available():
    device = torch.device("cuda:0")
elif torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print(f"현재 예측에 사용하는 디바이스: {device}")


def pad_to_square(image, fill_color=(114, 114, 114)):
    width, height = image.size
    max_side = max(width, height)
    new_image = Image.new("RGB", (max_side, max_side), fill_color)
    new_image.paste(image, ((max_side - width) // 2, (max_side - height) // 2))
    return new_image


def build_model(name, num_classes):
    """train.py 의 build_model 과 반드시 같은 구조여야 한다.
    (train.py 에서 모델을 바꿔 학습했다면 여기서도 같은 모델로 만들어야 가중치가 들어감)
    사전학습 가중치는 불러오지 않는다 - 어차피 우리가 학습시킨 가중치로 덮어쓰기 때문."""
    if name == "mobilenet_v2":
        model = models.mobilenet_v2(weights=None)
        model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    elif name == "resnet18":
        model = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    elif name == "resnet50":
        model = models.resnet50(weights=None)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    elif name == "efficientnet_b0":
        model = models.efficientnet_b0(weights=None)
        model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    elif name == "convnext_tiny":
        model = models.convnext_tiny(weights=None)
        model.classifier[2] = nn.Linear(model.classifier[2].in_features, num_classes)
    else:
        raise ValueError(
            "모르는 모델 이름: {}\n"
            "train.py 와 predict.py 의 build_model 을 함께 수정해야 합니다.".format(name)
        )
    return model


def load_model(checkpoint_path):
    checkpoint = torch.load(checkpoint_path, map_location=device)
    class_names = checkpoint['classes']
    num_classes = len(class_names)

    # train.py 가 체크포인트에 어떤 모델로 학습했는지 적어둔다.
    # 예전에 만든 체크포인트에는 이 값이 없으므로 mobilenet_v2 로 간주.
    model_name = checkpoint.get('model_name', 'mobilenet_v2')
    img_size = checkpoint.get('img_size', DEFAULT_IMG_SIZE)
    print("불러온 모델: {} / 입력 {}px / 클래스 {}개".format(model_name, img_size, num_classes))

    model = build_model(model_name, num_classes)
    model.load_state_dict(checkpoint['model_state_dict'])
    model = model.to(device)
    model.eval()

    return model, class_names, build_transform(img_size)


def build_transform(img_size):
    """train.py 의 val 전처리와 반드시 같아야 한다.

    크기를 여기에 숫자로 박아두면, train.py 에서 IMG_SIZE 를 바꿨을 때
    학습 320 / 추론 224 처럼 몰래 어긋나서 정확도가 조용히 떨어진다.
    그래서 체크포인트에 저장된 img_size 를 읽어서 만든다."""
    return transforms.Compose([
        transforms.Lambda(pad_to_square),
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])


# 예전 체크포인트(img_size 없음)용 기본값
DEFAULT_IMG_SIZE = 224


# -------------------------------------------------------------
# [신규] TTA용: 원본 이미지를 여러 버전(원본/좌우반전/약간 회전)으로 만들어서
#        각각 예측한 확률을 평균냄. 재학습 없이 추론 단계에서만 적용하는 방식.
# -------------------------------------------------------------
def get_tta_views(image: Image.Image):
    views = [
        image,                                  # 원본
        image.transpose(Image.FLIP_LEFT_RIGHT), # 좌우 반전
        image.rotate(10, fillcolor=(114, 114, 114)),   # 시계 방향 10도
        image.rotate(-10, fillcolor=(114, 114, 114)),  # 반시계 방향 10도
    ]
    return views


def predict_image(image_path, model, class_names, transform, use_tta=True):
    image = Image.open(image_path).convert('RGB')

    if not use_tta:
        # 기존 방식 (TTA 없이 한 번만 예측)
        input_tensor = transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            outputs = model(input_tensor)
            probabilities = torch.softmax(outputs, dim=1)[0]
    else:
        # [신규] 여러 버전을 만들어서 예측 후 확률을 평균
        views = get_tta_views(image)
        all_probs = []
        with torch.no_grad():
            for view in views:
                input_tensor = transform(view).unsqueeze(0).to(device)
                outputs = model(input_tensor)
                probs = torch.softmax(outputs, dim=1)[0]
                all_probs.append(probs)
        probabilities = torch.stack(all_probs).mean(dim=0)

    _, pred_idx = torch.max(probabilities, 0)
    predicted_class = class_names[pred_idx.item()]
    confidence = probabilities[pred_idx.item()].item() * 100

    return predicted_class, confidence, probabilities


_model_cache = {}


def predict(image_path, checkpoint_path):
    if checkpoint_path not in _model_cache:
        _model_cache[checkpoint_path] = load_model(checkpoint_path)

    model, class_names, transform = _model_cache[checkpoint_path]
    predicted_class, confidence, _ = predict_image(
        image_path, model, class_names, transform, use_tta=True)

    return {
        "predicted_class": predicted_class,
        "confidence": confidence / 100,
    }


if __name__ == "__main__":
    # 사용법:  python predict.py [이미지경로] [모델경로]
    import sys

    TEST_IMAGE_PATH = sys.argv[1] if len(sys.argv) > 1 else 'test.jpg'
    MODEL_PATH = sys.argv[2] if len(sys.argv) > 2 else 'best_recycling_model.pth'

    if os.path.exists(MODEL_PATH) and os.path.exists(TEST_IMAGE_PATH):
        model, class_names, transform = load_model(MODEL_PATH)

        pred_class, confidence, probs = predict_image(
            TEST_IMAGE_PATH, model, class_names, transform, use_tta=True)

        print("\n" + "="*30)
        print(f"테스트 이미지: {TEST_IMAGE_PATH}")
        print(f"AI의 예측 결과 (TTA 적용): [{pred_class}]")
        print(f"확신도(확률): {confidence:.2f}%")
        print("="*30)

        print("\n[전체 클래스별 확률]")
        for idx, name in enumerate(class_names):
            print(f"- {name}: {probs[idx].item()*100:.2f}%")

    else:
        print("파일을 찾을 수 없습니다.")
        print(f"  모델:   {MODEL_PATH}  ({'있음' if os.path.exists(MODEL_PATH) else '없음'})")
        print(f"  이미지: {TEST_IMAGE_PATH}  ({'있음' if os.path.exists(TEST_IMAGE_PATH) else '없음'})")
        print("사용법: python predict.py [이미지경로] [모델경로]")