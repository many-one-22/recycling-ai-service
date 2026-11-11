# 코랩 설정
# from google.colab import drive
# 실행하면 '구글 드라이브에 연결하시겠습니까?' 팝업이 뜨고 허용을 누르면 됨.
# drive.mount('/content/drive')

# 라이브러리 불러오기 및 환경 설정

import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, models, transforms
from torch.utils.data import DataLoader
import time
import copy
import os
from pathlib import Path
from PIL import Image, ImageFilter, ImageOps
from sklearn.metrics import f1_score


# -------------------------------------------------------------
# 정사각형 패딩 (letterbox)
#   - Resize((224,224))가 원본 비율을 무시하고 강제로 찌그러뜨리는 문제를 막기 위함
#   - predict.py에도 반드시 동일하게 적용해야 함 (학습/추론 전처리 불일치 방지)
# -------------------------------------------------------------
def pad_to_square(image, fill_color=(114, 114, 114)):
    width, height = image.size
    max_side = max(width, height)
    new_image = Image.new("RGB", (max_side, max_side), fill_color)
    new_image.paste(image, ((max_side - width) // 2, (max_side - height) // 2))
    return new_image


# -------------------------------------------------------------
# 가우시안 노이즈 (ToTensor 이후, Normalize 이전에 적용)
# -------------------------------------------------------------
def add_gaussian_noise(tensor, mean=0.0, std=0.03):
    noise = torch.randn(tensor.size()) * std + mean
    noisy_tensor = tensor + noise
    return torch.clamp(noisy_tensor, 0.0, 1.0)


# ===============================================================
# [신규] 멘토님 피드백: 배율별 이미지 + 윤곽선 이미지를 미리 생성해서
#        데이터셋 개수 자체를 늘리는 기능을 train.py에 통합
# ===============================================================

def zoom_image(image: Image.Image, scale: float, fill_color=(114, 114, 114)) -> Image.Image:
    """
    scale > 1.0  -> 확대(줌인): 가운데를 크롭 후 원래 크기로 리사이즈
    scale < 1.0  -> 축소(줌아웃): 이미지를 줄인 후 회색 여백을 채워 원래 크기로 복원
    scale == 1.0 -> 원본 그대로
    """
    width, height = image.size

    if scale == 1.0:
        return image.copy()

    if scale > 1.0:
        crop_w = int(width / scale)
        crop_h = int(height / scale)
        left = (width - crop_w) // 2
        top = (height - crop_h) // 2
        cropped = image.crop((left, top, left + crop_w, top + crop_h))
        return cropped.resize((width, height), Image.LANCZOS)
    else:
        new_w = int(width * scale)
        new_h = int(height * scale)
        shrunk = image.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGB", (width, height), fill_color)
        paste_x = (width - new_w) // 2
        paste_y = (height - new_h) // 2
        canvas.paste(shrunk, (paste_x, paste_y))
        return canvas


def extract_edges(image: Image.Image) -> Image.Image:
    """
    윤곽선만 추출: 흑백 변환 -> 대비 강화 -> FIND_EDGES -> 다시 3채널(RGB)로 복원
    (기존 모델 입력 파이프라인과 채널 수가 맞아야 하므로 RGB로 되돌림)
    """
    grayscale = image.convert("L")
    grayscale = ImageOps.autocontrast(grayscale)
    edges = grayscale.filter(ImageFilter.FIND_EDGES)
    return edges.convert("RGB")


def generate_expanded_dataset(src_dir: str, dest_dir: str, scales, include_edges: bool):
    """
    src_dir(클래스별 폴더)의 원본 이미지들로부터, 배율별 이미지(+윤곽선 이미지)를
    dest_dir에 생성함. 이미 dest_dir에 결과가 있으면 다시 만들지 않고 건너뜀
    (매번 학습 돌릴 때마다 새로 생성하면 시간 낭비이므로).
    """
    dest = Path(dest_dir)
    if dest.exists() and any(dest.iterdir()):
        print(f"[데이터 확장] '{dest_dir}'가 이미 존재해서 생성을 건너뜁니다. "
              f"다시 만들고 싶으면 이 폴더를 지우고 재실행하세요.")
        return

    src = Path(src_dir)
    class_folders = [d for d in src.iterdir() if d.is_dir()]
    print(f"[데이터 확장] 발견된 카테고리: {[c.name for c in class_folders]}")
    print(f"[데이터 확장] 적용할 배율: {scales} / 윤곽선 포함: {include_edges}")

    total_generated = 0
    for class_folder in class_folders:
        out_class_dir = dest / class_folder.name
        out_class_dir.mkdir(parents=True, exist_ok=True)

        images = sorted(list(class_folder.glob("*.jpg")) + list(class_folder.glob("*.jpeg")))
        for img_path in images:
            image = Image.open(img_path).convert("RGB")
            stem = img_path.stem

            for scale in scales:
                scaled = zoom_image(image, scale)
                scale_label = f"{int(scale * 100)}"
                out_name = f"{stem}_s{scale_label}.jpg"
                scaled.save(out_class_dir / out_name, quality=92)
                total_generated += 1

            if include_edges:
                edge_image = extract_edges(image)
                edge_name = f"{stem}_edge.jpg"
                edge_image.save(out_class_dir / edge_name, quality=92)
                total_generated += 1

        extra_per_image = len(scales) + (1 if include_edges else 0)
        print(f"[데이터 확장]   {class_folder.name}: 원본 {len(images)}장 -> {len(images) * extra_per_image}장")

    print(f"[데이터 확장] 완료. 총 {total_generated}장 생성됨 -> {dest_dir}")


# -------------------------------------------------------------
# [설정] 데이터 확장 옵션 (여기서 켜고 끌 수 있음)
# -------------------------------------------------------------
RAW_DATA_DIR = "./data/processed_200"          # 원본 데이터 (직접 모은 200장짜리)
EXPANDED_DATA_DIR = "./data/processed_scaled"  # 배율/윤곽선 적용해서 생성될 폴더
SCALES = [0.7, 0.8, 0.9, 1.0, 1.1]
INCLUDE_EDGES = True


# 데이터 확장 실행 (이미 생성되어 있으면 자동으로 건너뜀)
generate_expanded_dataset(RAW_DATA_DIR, EXPANDED_DATA_DIR, SCALES, INCLUDE_EDGES)


# 폴더 자동 분할

# pip install split-folders 실행 필수
import splitfolders

# [수정] 원본(200장) 대신, 위에서 확장한 데이터셋을 사용
input_folder = EXPANDED_DATA_DIR
output_folder = "./dataset"

# 주의: dataset 폴더가 이미 있으면 splitfolders가 에러를 내거나 파일이 섞일 수 있음
# 재학습 전에는 항상 지우고 새로 만드는 걸 권장 (터미널에서: rm -rf dataset)
splitfolders.ratio(input_folder, output=output_folder, seed=42, ratio=(0.8, 0.2))
print("데이터 분할 완료")

# GPU 사용 가능 여부 확인 (코랩에서는 런타임 유형을 T4 GPU로 설정해야함!)
if torch.cuda.is_available():
    device = torch.device("cuda:0")
elif torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print(f"현재 사용하는 디바이스: {device}")


# 데이터 전처리 및 로더 준비

# 1. 이미지 전처리 규칙 설정
#   - train 쪽 증강은 대폭 강화된 상태 유지
#   - val 쪽은 패딩 외에 다른 증강 없음 (평가는 항상 "있는 그대로"로 해야 정확함)
data_transforms = {
    'train': transforms.Compose([
        transforms.Lambda(pad_to_square),
        transforms.RandomResizedCrop(224, scale=(0.6, 1.0)),
        transforms.RandomAffine(degrees=0, scale=(0.9, 1.1)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(20),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3),
        transforms.RandomGrayscale(p=0.2),
        transforms.ToTensor(),
        transforms.Lambda(add_gaussian_noise),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
    'val': transforms.Compose([
        transforms.Lambda(pad_to_square),
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
}

# 2. 데이터 폴더 경로 설정
data_dir = output_folder

# 3. 데이터셋 불러오기
image_datasets = {x: datasets.ImageFolder(os.path.join(data_dir, x), data_transforms[x])
                  for x in ['train', 'val']}

# 4. 데이터로더 생성 (데이터를 한 번에 32장씩(batch_size) 모델에 던져줌)
dataloaders = {x: DataLoader(image_datasets[x], batch_size=32, shuffle=True, num_workers=0)
              for x in ['train', 'val']}

dataset_sizes = {x: len(image_datasets[x]) for x in ['train', 'val']}
class_names = image_datasets['train'].classes
print(f"우리가 분류할 클래스들: {class_names}")
print(f"학습 데이터 수: {dataset_sizes['train']}장 / 검증 데이터 수: {dataset_sizes['val']}장")


# MobileNet 모델 불러오기 및 수정

# 1. 사전 학습된 MobileNet V2 모델 불러오기
model = models.mobilenet_v2(weights='IMAGENET1K_V1')

# 2. 파인튜닝: 전체 레이어를 학습 가능하게 풀어줌
for param in model.parameters():
    param.requires_grad = True

# 3. 마지막 출력층(Classifier) 수정하기
num_classes = len(class_names)
num_ftrs = model.classifier[1].in_features
model.classifier[1] = nn.Linear(num_ftrs, num_classes)

model = model.to(device)

# 4. 오차 함수(Loss)와 최적화 도구(Optimizer) 설정
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.00001)


# 학습 루프 함수 및 실행

def train_model(model, criterion, optimizer, num_epochs=50):
    since = time.time()

    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    for epoch in range(num_epochs):
        print(f'Epoch {epoch+1}/{num_epochs}')
        print('-' * 10)

        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()
            else:
                model.eval()

            running_loss = 0.0
            running_corrects = 0

            all_preds = []
            all_labels = []

            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)

                optimizer.zero_grad()

                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())

            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc = running_corrects.float() / dataset_sizes[phase]
            epoch_f1 = f1_score(all_labels, all_preds, average='macro')

            print(f'{phase} Loss: {epoch_loss:.4f} Acc: {epoch_acc:.4f} F1: {epoch_f1:.4f}')

            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())

        print()

    time_elapsed = time.time() - since
    print(f'학습 완료! 걸린 시간: {time_elapsed // 60:.0f}분 {time_elapsed % 60:.0f}초')
    print(f'가장 높았던 검증 정확도(Best val Acc): {best_acc:4f}')

    model.load_state_dict(best_model_wts)
    return model


# 데이터가 5~6배(배율+윤곽선) 늘어났으므로 한 에폭에 걸리는 시간도 그만큼 늘어남
# 필요하면 에폭 수를 줄여서 먼저 짧게 테스트해보는 것도 방법
model_ft = train_model(model, criterion, optimizer, num_epochs=20)

# 최고 성능의 모델을 파일로 저장
torch.save({
    "model_state_dict": model_ft.state_dict(),
    "classes": class_names,
}, 'best_recycling_model.pth')
print("모델이 'best_recycling_model.pth'로 안전하게 저장되었습니다.")
# save_path = '/content/drive/MyDrive/AICOSS 2026 WE-Meet/best_recycling_model.pth'
# torch.save(model_ft.state_dict(), save_path)
# print("모델이 구글 드라이브에 안전하게 저장되었습니다.")