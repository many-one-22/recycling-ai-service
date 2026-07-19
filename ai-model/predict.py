"""
predict.py - 학습된 모델로 단일 이미지 추론

사용 예시:
    python predict.py --image ./sample.jpg --checkpoint ../checkpoints/best_model.pt

TODO(현서 - be-api): predict() 함수를 API 엔드포인트에서 그대로 호출해서 연동하면 됨
"""

import argparse

import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms


def load_model(checkpoint_path: str, device):
    checkpoint = torch.load(checkpoint_path, map_location=device)
    model_name = checkpoint["model_name"]
    classes = checkpoint["classes"]

    if model_name == "mobilenet_v2":
        model = models.mobilenet_v2()
        model.classifier[1] = nn.Linear(model.last_channel, len(classes))
    elif model_name == "resnet18":
        model = models.resnet18()
        model.fc = nn.Linear(model.fc.in_features, len(classes))
    else:
        raise ValueError(f"지원하지 않는 모델: {model_name}")

    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()
    return model, classes, checkpoint["img_size"]


def preprocess_image(image_path: str, img_size: int):
    # 학습 때와 반드시 동일한 전처리 (PREPROCESSING.md 참고)
    transform = transforms.Compose(
        [
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ]
    )
    image = Image.open(image_path).convert("RGB")
    return transform(image).unsqueeze(0)


def predict(image_path: str, checkpoint_path: str) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, classes, img_size = load_model(checkpoint_path, device)
    tensor = preprocess_image(image_path, img_size).to(device)

    with torch.no_grad():
        outputs = model(tensor)
        probs = torch.softmax(outputs, dim=1)[0]
        top_idx = torch.argmax(probs).item()

    return {
        "predicted_class": classes[top_idx],
        "confidence": round(probs[top_idx].item(), 4),
        "all_probs": {c: round(p.item(), 4) for c, p in zip(classes, probs)},
    }


def main():
    parser = argparse.ArgumentParser(description="재활용품 이미지 추론")
    parser.add_argument("--image", type=str, required=True, help="추론할 이미지 경로")
    parser.add_argument("--checkpoint", type=str, default="../checkpoints/best_model.pt")
    args = parser.parse_args()

    result = predict(args.image, args.checkpoint)
    print(f"예측 클래스: {result['predicted_class']} (신뢰도: {result['confidence']})")
    print("전체 확률:", result["all_probs"])


if __name__ == "__main__":
    main()
