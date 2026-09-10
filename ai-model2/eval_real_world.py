"""
eval_real_world_test.py - 팀원들이 직접 찍은 실전 테스트셋을 한 번에 평가

[수정] train.py/predict.py와 동일하게 pad_to_square 전처리 반영
       (비율 왜곡 방지를 위해 Resize 전에 정사각형 패딩 적용)

폴더 구조 전제 (클래스별로 폴더가 나뉘어 있어야 함):
    dataset_new/
        유리병/
            xxx.jpg
            ...
        캔/
            can4-1.jpg
            can4-2.jpg
            ...
        종이/
        페트병/

사용 예시:
    python eval_real_world.py --checkpoint best_recycling_model.pth --test_dir ./dataset_new
"""

import argparse
import unicodedata
from pathlib import Path

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image


# -------------------------------------------------------------
# train.py / predict.py와 완전히 동일한 패딩 함수
# -------------------------------------------------------------
def pad_to_square(image, fill_color=(114, 114, 114)):
    width, height = image.size
    max_side = max(width, height)
    new_image = Image.new("RGB", (max_side, max_side), fill_color)
    new_image.paste(image, ((max_side - width) // 2, (max_side - height) // 2))
    return new_image


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


def predict_one(image_path, model, class_names, transform, device):
    image = Image.open(image_path).convert("RGB")
    tensor = transform(image).unsqueeze(0).to(device)
    with torch.no_grad():
        outputs = model(tensor)
        probs = torch.softmax(outputs, dim=1)[0]
        top_idx = torch.argmax(probs).item()
    pred_class = unicodedata.normalize("NFC", class_names[top_idx])  # [수정] 예측값도 NFC로 정규화
    return pred_class, probs[top_idx].item(), probs.cpu().numpy()


# [신규] 영어 폴더명 -> 한글 클래스명 매핑
# 폴더명이 can/glass/paper/pet처럼 영어여도, 모델의 클래스명(한글)과 비교할 수 있게 변환
FOLDER_NAME_MAP = {
    "can": "캔",
    "glass": "유리병",
    "paper": "종이",
    "pet": "페트병",
    "plastic": "페트병",  # 혹시 다른 이름으로 저장했을 경우 대비
}


def normalize_class_name(name: str) -> str:
    """폴더명을 한글 클래스명으로 정규화.
    영어 폴더명(can 등)은 한글로 매핑하고,
    macOS가 한글 파일명을 분리형(NFD)으로 저장하는 문제를 막기 위해
    항상 완성형(NFC)으로 정규화함 (눈으로는 같아 보여도 == 비교가 실패하는 문제 방지)
    """
    mapped = FOLDER_NAME_MAP.get(name.lower(), name)
    return unicodedata.normalize("NFC", mapped)


def main():
    parser = argparse.ArgumentParser(description="실전 테스트셋 일괄 평가")
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--test_dir", type=str, required=True, help="클래스별 하위 폴더가 있는 테스트 이미지 루트")
    args = parser.parse_args()

    device = torch.device(
        "cuda:0" if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available()
        else "cpu"
    )

    model, class_names = load_model(args.checkpoint, device)

    # [수정] pad_to_square를 Resize 앞에 추가 (train.py의 val 전처리와 동일해야 함)
    transform = transforms.Compose([
        transforms.Lambda(pad_to_square),
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    test_dir = Path(args.test_dir)
    class_folders = [d for d in test_dir.iterdir() if d.is_dir()]

    results = []  # (실제클래스, 예측클래스, 확신도, 파일명)
    for folder in class_folders:
        true_class = normalize_class_name(folder.name)  # [수정] 영어 폴더명 -> 한글로 변환
        images = sorted(list(folder.glob("*.jpg")) + list(folder.glob("*.jpeg")) + list(folder.glob("*.png")))
        for img_path in images:
            pred_class, confidence, all_probs = predict_one(img_path, model, class_names, transform, device)
            results.append((true_class, pred_class, confidence, img_path.name))

    # 전체 결과 표 출력
    print(f"{'파일명':<25}{'실제':<8}{'예측':<8}{'확신도':<10}{'정답여부'}")
    print("-" * 65)
    correct = 0
    for true_class, pred_class, confidence, filename in results:
        is_correct = "O" if true_class == pred_class else "X"
        if true_class == pred_class:
            correct += 1
        print(f"{filename:<25}{true_class:<8}{pred_class:<8}{confidence*100:>6.2f}%    {is_correct}")

    print("-" * 65)
    print(f"전체 정확도: {correct}/{len(results)} ({correct/len(results)*100:.1f}%)")

    # 클래스별 정확도
    # [수정] class_names도 NFC로 정규화해서 results 안의 이름과 매칭되게 함
    print("\n[클래스별 정확도]")
    for cls_raw in class_names:
        cls = unicodedata.normalize("NFC", cls_raw)
        cls_results = [r for r in results if r[0] == cls]
        if not cls_results:
            continue
        cls_correct = sum(1 for r in cls_results if r[0] == r[1])
        print(f"  {cls}: {cls_correct}/{len(cls_results)} ({cls_correct/len(cls_results)*100:.1f}%)")

    # 오분류 패턴 (실제 -> 예측 방향으로 몇 번 틀렸는지)
    print("\n[오분류 패턴 (실제 → 예측)]")
    mistake_counts = {}
    for true_class, pred_class, _, _ in results:
        if true_class != pred_class:
            key = f"{true_class} → {pred_class}"
            mistake_counts[key] = mistake_counts.get(key, 0) + 1
    if mistake_counts:
        for pattern, count in sorted(mistake_counts.items(), key=lambda x: -x[1]):
            print(f"  {pattern}: {count}회")
    else:
        print("  오분류 없음")


if __name__ == "__main__":
    main()