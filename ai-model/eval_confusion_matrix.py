"""
eval_confusion_matrix.py - 검증셋(val) 전체에 대한 confusion matrix 계산

파인튜닝 전/후 성능을 "몇 장 감으로 보기"가 아니라 숫자로 비교하기 위한 스크립트.

사용 예시:
    python eval_confusion_matrix.py --checkpoint best_recycling_model.pth --data_dir ./dataset/val
"""

import argparse

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms
from sklearn.metrics import confusion_matrix, classification_report


def load_model(checkpoint_path, device):
    checkpoint = torch.load(checkpoint_path, map_location=device)
    class_names = checkpoint["classes"]

    model = models.mobilenet_v2(weights=None)
    num_ftrs = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(num_ftrs, len(class_names))
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device)
    model.eval()
    return model, class_names


def main():
    parser = argparse.ArgumentParser(description="검증셋 confusion matrix 계산")
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--data_dir", type=str, required=True, help="dataset/val 경로 (클래스별 하위 폴더)")
    args = parser.parse_args()

    device = torch.device(
        "cuda:0" if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available()
        else "cpu"
    )

    model, class_names = load_model(args.checkpoint, device)

    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    dataset = datasets.ImageFolder(args.data_dir, transform=transform)
    loader = DataLoader(dataset, batch_size=32, shuffle=False)

    all_preds, all_labels = [], []
    with torch.no_grad():
        for inputs, labels in loader:
            inputs = inputs.to(device)
            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.numpy())

    print("클래스 순서:", class_names)
    print("\n=== Confusion Matrix ===")
    cm = confusion_matrix(all_labels, all_preds)
    print("(행: 실제 정답, 열: 모델 예측)")
    header = "         " + "".join(f"{name:>10}" for name in class_names)
    print(header)
    for i, row in enumerate(cm):
        print(f"{class_names[i]:>8} " + "".join(f"{v:>10}" for v in row))

    print("\n=== Classification Report ===")
    print(classification_report(all_labels, all_preds, target_names=class_names))


if __name__ == "__main__":
    main()
