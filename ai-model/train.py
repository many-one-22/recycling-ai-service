"""
train.py - 재활용품(유리병 등) 이미지 분류 모델 학습 스크립트

사용 예시:
    python train.py --data_dir ../data/processed --epochs 20 --model mobilenet_v2

전처리 규격은 PREPROCESSING.md 참고 (팀 공통 규칙, 임의로 바꾸지 말 것)

TODO(다원): 팀 회의 후 아래 항목 확정
    - YOLO(탐지) vs Classification(분류) 최종 구조 결정
    - 클래스 목록 (유리병 외 나머지 8종 포함 여부)
    - 하이퍼파라미터 (epochs, lr, batch_size) 튜닝
"""

import argparse
import os

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms


def get_transforms(img_size=224):
    """
    전처리 규격 (PREPROCESSING.md와 반드시 동일하게 유지)
    - 리사이즈: img_size x img_size (기본 224x224)
    - 정규화: ImageNet mean/std 기준 (pretrained 모델 사용 전제)
    """
    return transforms.Compose(
        [
            transforms.Resize((img_size, img_size)),
            transforms.RandomHorizontalFlip(),  # TODO: 증강 기법 추가 논의 (회전/밝기 등)
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ]
    )


def build_model(model_name: str, num_classes: int):
    """분류 기반 transfer learning 모델 생성.

    TODO(다원): 탐지(YOLO) 구조로 최종 결정될 경우 이 함수 전체 교체 필요
    """
    if model_name == "mobilenet_v2":
        model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
        model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    elif model_name == "resnet18":
        model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    else:
        raise ValueError(f"지원하지 않는 모델: {model_name}")
    return model


def train_one_epoch(model, loader, optimizer, criterion, device) -> float:
    model.train()
    running_loss = 0.0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        running_loss += loss.item() * images.size(0)
    return running_loss / len(loader.dataset)


def main():
    parser = argparse.ArgumentParser(description="재활용품 분류 모델 학습")
    parser.add_argument(
        "--data_dir",
        type=str,
        default="../data/processed",
        help="ImageFolder 구조 데이터 경로 (data_dir/클래스명/이미지.jpg)",
    )
    parser.add_argument(
        "--model", type=str, default="mobilenet_v2", choices=["mobilenet_v2", "resnet18"]
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--img_size", type=int, default=224)
    parser.add_argument("--save_path", type=str, default="../checkpoints/best_model.pt")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    # TODO(다원/다언): AI Hub에서 받은 유리병 등 이미지로 data_dir 구성 필요
    dataset = datasets.ImageFolder(args.data_dir, transform=get_transforms(args.img_size))
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=2)
    print(f"클래스: {dataset.classes} / 총 {len(dataset)}장")

    model = build_model(args.model, num_classes=len(dataset.classes)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    for epoch in range(args.epochs):
        loss = train_one_epoch(model, loader, optimizer, criterion, device)
        print(f"[Epoch {epoch + 1}/{args.epochs}] loss={loss:.4f}")

    os.makedirs(os.path.dirname(args.save_path), exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "classes": dataset.classes,
            "model_name": args.model,
            "img_size": args.img_size,
        },
        args.save_path,
    )
    print(f"모델 저장 완료: {args.save_path}")


if __name__ == "__main__":
    main()
