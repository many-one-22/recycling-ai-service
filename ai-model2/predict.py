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


def load_model(checkpoint_path):
    checkpoint = torch.load(checkpoint_path, map_location=device)
    class_names = checkpoint['classes']
    num_classes = len(class_names)

    model = models.mobilenet_v2(weights=None)
    num_ftrs = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(num_ftrs, num_classes)

    model.load_state_dict(checkpoint['model_state_dict'])
    model = model.to(device)
    model.eval()

    return model, class_names


predict_transform = transforms.Compose([
    transforms.Lambda(pad_to_square),
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])


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


def predict_image(image_path, model, class_names, use_tta=True):
    image = Image.open(image_path).convert('RGB')

    if not use_tta:
        # 기존 방식 (TTA 없이 한 번만 예측)
        input_tensor = predict_transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            outputs = model(input_tensor)
            probabilities = torch.softmax(outputs, dim=1)[0]
    else:
        # [신규] 여러 버전을 만들어서 예측 후 확률을 평균
        views = get_tta_views(image)
        all_probs = []
        with torch.no_grad():
            for view in views:
                input_tensor = predict_transform(view).unsqueeze(0).to(device)
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

    model, class_names = _model_cache[checkpoint_path]
    predicted_class, confidence, _ = predict_image(image_path, model, class_names, use_tta=True)

    return {
        "predicted_class": predicted_class,
        "confidence": confidence / 100,
    }


if __name__ == "__main__":
    MODEL_PATH = 'best_recycling_model.pth'
    TEST_IMAGE_PATH = 'dataset_new_new/pet/7.jpg'

    if os.path.exists(MODEL_PATH) and os.path.exists(TEST_IMAGE_PATH):
        model, class_names = load_model(MODEL_PATH)

        pred_class, confidence, probs = predict_image(TEST_IMAGE_PATH, model, class_names, use_tta=True)

        print("\n" + "="*30)
        print(f"테스트 이미지: {TEST_IMAGE_PATH}")
        print(f"AI의 예측 결과 (TTA 적용): [{pred_class}]")
        print(f"확신도(확률): {confidence:.2f}%")
        print("="*30)

        print("\n[전체 클래스별 확률]")
        for idx, name in enumerate(class_names):
            print(f"- {name}: {probs[idx].item()*100:.2f}%")

    else:
        print("'best_recycling_model.pth' 파일이나 테스트용 이미지 경로를 다시 확인해주세요!")