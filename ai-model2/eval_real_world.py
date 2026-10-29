"""
eval_real_world_test.py - 팀원들이 직접 찍은 실전 테스트셋을 한 번에 평가
[수정] TTA(Test-Time Augmentation) 반영: predict.py와 동일한 방식으로
       원본/좌우반전/±10도 회전 4개 버전을 평균내서 예측

폴더 구조 전제 (클래스별로 폴더가 나뉘어 있어야 함):
    dataset_new/
        유리병/
        캔/
        종이/
        페트병/

사용 예시:
    python eval_real_world_test.py --checkpoint best_recycling_model.pth --test_dir ./dataset_new
    python eval_real_world_test.py --checkpoint best_recycling_model.pth --test_dir ./dataset_new --no_tta   (TTA 끄고 비교용)
"""

import argparse
import unicodedata
from pathlib import Path

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image


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


# [신규] predict.py와 동일한 TTA 뷰 생성
# [실험 결과] 회전 제거 시 유리병은 개선되나(50%->62.5%) 종이/캔이 더 크게 하락(100%->62.5%, 87.5%->75%)
#            전체 정확도 기준 회전 포함이 더 나음(78.1% vs 68.8%) -> 회전 포함으로 확정
def get_tta_views(image: Image.Image):
    return [
        image,
        image.transpose(Image.FLIP_LEFT_RIGHT),
        image.rotate(10, fillcolor=(114, 114, 114)),
        image.rotate(-10, fillcolor=(114, 114, 114)),
    ]


def predict_one(image_path, model, class_names, transform, device, use_tta=True):
    image = Image.open(image_path).convert("RGB")

    if not use_tta:
        tensor = transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            outputs = model(tensor)
            probs = torch.softmax(outputs, dim=1)[0]
    else:
        views = get_tta_views(image)
        all_probs = []
        with torch.no_grad():
            for view in views:
                tensor = transform(view).unsqueeze(0).to(device)
                outputs = model(tensor)
                all_probs.append(torch.softmax(outputs, dim=1)[0])
        probs = torch.stack(all_probs).mean(dim=0)

    top_idx = torch.argmax(probs).item()
    pred_class = unicodedata.normalize("NFC", class_names[top_idx])
    return pred_class, probs[top_idx].item(), probs.cpu().numpy()


FOLDER_NAME_MAP = {
    "can": "캔",
    "glass": "유리병",
    "paper": "종이",
    "pet": "페트병",
    "plastic": "페트병",
}


def normalize_class_name(name: str) -> str:
    mapped = FOLDER_NAME_MAP.get(name.lower(), name)
    return unicodedata.normalize("NFC", mapped)


def main():
    parser = argparse.ArgumentParser(description="실전 테스트셋 일괄 평가 (TTA 적용)")
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--test_dir", type=str, required=True)
    parser.add_argument("--no_tta", action="store_true", help="TTA 끄고 기존 방식으로 비교 평가")
    args = parser.parse_args()

    use_tta = not args.no_tta
    print(f"TTA 사용: {use_tta}")

    device = torch.device(
        "cuda:0" if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available()
        else "cpu"
    )

    model, class_names = load_model(args.checkpoint, device)

    transform = transforms.Compose([
        transforms.Lambda(pad_to_square),
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    test_dir = Path(args.test_dir)
    class_folders = [d for d in test_dir.iterdir() if d.is_dir()]

    results = []
    for folder in class_folders:
        true_class = normalize_class_name(folder.name)
        images = sorted(list(folder.glob("*.jpg")) + list(folder.glob("*.jpeg")) + list(folder.glob("*.png")))
        for img_path in images:
            pred_class, confidence, _ = predict_one(img_path, model, class_names, transform, device, use_tta)
            results.append((true_class, pred_class, confidence, img_path.name))

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

    print("\n[클래스별 정확도]")
    for cls_raw in class_names:
        cls = unicodedata.normalize("NFC", cls_raw)
        cls_results = [r for r in results if r[0] == cls]
        if not cls_results:
            continue
        cls_correct = sum(1 for r in cls_results if r[0] == r[1])
        print(f"  {cls}: {cls_correct}/{len(cls_results)} ({cls_correct/len(cls_results)*100:.1f}%)")

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