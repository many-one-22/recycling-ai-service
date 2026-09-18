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
from PIL import Image
from sklearn.metrics import f1_score


# -------------------------------------------------------------
# [신규] 정사각형 패딩 (letterbox)
#   - Resize((224,224))가 원본 비율을 무시하고 강제로 찌그러뜨리는 문제를 막기 위함
#   - 스마트폰으로 세로로 길게(또는 극단적으로 클로즈업) 찍은 사진일수록
#     이 왜곡이 커져서, 병이 옆으로 눌린 것처럼 학습/인식되는 문제가 있었음
#   - (114,114,114)는 letterbox padding에 관례적으로 쓰는 중립 회색
#   - predict.py에도 반드시 동일하게 적용해야 함 (학습/추론 전처리 불일치 방지)
# -------------------------------------------------------------
def pad_to_square(image, fill_color=(114, 114, 114)):
    width, height = image.size
    max_side = max(width, height)
    new_image = Image.new("RGB", (max_side, max_side), fill_color)
    new_image.paste(image, ((max_side - width) // 2, (max_side - height) // 2))
    return new_image


# 폴더 자동 분할

# pip install split-folders 실행 필수
import splitfolders
# 사진을 모아둔 원본 폴더 경로
input_folder = "./data/processed_200"
# input_folder = "/content/drive/MyDrive/AICOSS 2026 WE-Meet/data/raw"
# 코드가 자동으로 train과 val로 나누어서 저장할 새로운 폴더 이름
output_folder = "./dataset"
# output_folder = "/content/dataset"

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
# [수정] pad_to_square를 Resize 앞에 추가 (train/val 둘 다 동일하게 적용)
#   - train 쪽 증강은 대폭 강화된 상태 유지
#     (유리병/페트병처럼 시각적으로 유사한 재질을 구분하려면,
#      다양한 각도/조명/구도에서도 같은 재질로 인식하도록 훈련시켜야 함)
#   - val 쪽은 패딩 외에 다른 증강 없음 (평가는 항상 "있는 그대로"로 해야 정확함)
data_transforms = {
    'train': transforms.Compose([
        transforms.Lambda(pad_to_square),                      # [신규] 비율 왜곡 방지
        transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),  # 확대/축소 + 크롭 (구도 다양화)
        transforms.RandomHorizontalFlip(),                      # 좌우 반전
        transforms.RandomRotation(20),                          # 회전 (촬영 각도 다양화)
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3),  # 조명/색감 다양화
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
    'val': transforms.Compose([
        transforms.Lambda(pad_to_square),                      # [신규] 비율 왜곡 방지
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


# MobileNet 모델 불러오기 및 수정

# 1. 사전 학습된 MobileNet V2 모델 불러오기
model = models.mobilenet_v2(weights='IMAGENET1K_V1')

# 2. 파인튜닝: 전체 레이어를 학습 가능하게 풀어줌
#   - Feature Extractor 방식(마지막 레이어만 학습)은 사전학습된 특징을 그대로 쓰기 때문에,
#     유리병 vs 페트병처럼 미세한 질감 차이를 구분하는 데 한계가 있었음
#   - 전체를 풀어서 재학습하면, 하위 레이어까지 우리 데이터에 맞게 조정됨
for param in model.parameters():
    param.requires_grad = True

# 3. 마지막 출력층(Classifier) 수정하기
# 우리의 클래스 개수 (페트병, 캔, 종이, 유리병 = 총 4개)
num_classes = len(class_names)

num_ftrs = model.classifier[1].in_features
model.classifier[1] = nn.Linear(num_ftrs, num_classes)

# 모델을 GPU로 보냄.
model = model.to(device)

# 4. 오차 함수(Loss)와 최적화 도구(Optimizer) 설정
criterion = nn.CrossEntropyLoss()

# 파인튜닝이므로 전체 파라미터를 학습 대상으로 하되,
#   이미 학습된 특징이 무너지지 않도록 학습률을 훨씬 낮춤 (0.0001 -> 0.00001)
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


# 파인튜닝은 처음부터 많은 에폭까지 필요 없음.
#   이미 어느 정도 학습된 특징을 "미세 조정"하는 것이므로 적은 에폭으로 충분하고,
#   너무 많이 돌리면 오히려 소량 데이터(200장)에 과적합될 위험이 커짐
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