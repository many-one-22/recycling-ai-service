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


# 폴더 자동 분할

# pip install split-folders 실행 필수
import splitfolders
# 사진을 모아둔 원본 폴더 경로
input_folder = "./data/processed"
# input_folder = "/content/drive/MyDrive/AICOSS 2026 WE-Meet/data/raw" 
# 코드가 자동으로 train과 val로 나누어서 저장할 새로운 폴더 이름
output_folder = "./dataset"
# output_folder = "/content/dataset" 
# 원본 데이터를 80%(train)와 20%(val) 비율로 무작위로 섞어서 나눔.
splitfolders.ratio(input_folder, output=output_folder, seed=42, ratio=(0.8, 0.2))
print("데이터 분할 완료")

# GPU 사용 가능 여부 확인 (코랩에서는 런타임 유형을 T4 GPU로 설정해야함!)
# device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
# GPU가 있으면 쓰고, 맥북(M칩)이면 mps를 쓰고, 둘 다 없으면 cpu를 쓴다.
if torch.cuda.is_available():
    device = torch.device("cuda:0")
elif torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print(f"현재 사용하는 디바이스: {device}")


# 데이터 전처리 및 로더 준비

# 1. 이미지 전처리 규칙 설정
data_transforms = {
    'train': transforms.Compose([
        transforms.Resize((224, 224)), # MobileNet의 적정 사이즈로 통일
        transforms.RandomHorizontalFlip(), # 데이터 증강: 사진 좌우 반전
        transforms.ToTensor(), # 이미지를 파이토치 텐서(숫자 배열)로 변환
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]) # ImageNet 표준 색상 정규화
    ]),
    'val': transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
}

# 2. 데이터 폴더 경로 설정
# 폴더 구조는 data_dir/train/페트병, data_dir/train/캔, data_dir/train/종이팩, data_dir/train/유리병
# data_dir = './dataset' 
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

# 2. 가중치 동결 (Feature Extractor 방식: 기존 지식은 잊어버리지 않게 얼려둠)
for param in model.parameters():
    param.requires_grad = False

# 3. 마지막 출력층(Classifier) 수정하기
# 우리의 클래스 개수 (투명 페트병, 캔, 종이팩, 유리병 = 총 4개)
num_classes = len(class_names) 

# MobileNetV2의 classifier[1]이 원래 1000개를 분류하던 것을 4개로 수정
num_ftrs = model.classifier[1].in_features
model.classifier[1] = nn.Linear(num_ftrs, num_classes)

# 모델을 GPU로 보냄.
model = model.to(device)

# 4. 오차 함수(Loss)와 최적화 도구(Optimizer) 설정
criterion = nn.CrossEntropyLoss()

# 모델 전체가 아니라, 우리가 방금 바꾼 마지막 층(classifier[1])만 학습시킴.
optimizer = optim.Adam(model.classifier[1].parameters(), lr=0.001)
# 파인 튜닝 후 아래 코드 사용
# optimizer = optim.Adam(model.parameters(), lr=0.0001)


# 학습 루프 함수 및 실행

def train_model(model, criterion, optimizer, num_epochs=10):
    since = time.time()

    # 가장 성능이 좋았던 모델의 가중치를 복사해둘 변수
    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    for epoch in range(num_epochs):
        print(f'Epoch {epoch+1}/{num_epochs}')
        print('-' * 10)

        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()  # 모델을 학습 모드로 설정
            else:
                model.eval()   # 모델을 평가 모드로 설정

            running_loss = 0.0
            running_corrects = 0

            # 데이터를 배치(32장) 단위로 가져와서 반복
            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)

                optimizer.zero_grad() # 기울기 초기화

                # 순전파 (Forward)
                # 학습 시에만 연산 기록을 추적
                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    # 학습(train) 단계일 때만 역전파 및 가중치 업데이트
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                # 통계 계산
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc = running_corrects.float() / dataset_sizes[phase]

            print(f'{phase} Loss: {epoch_loss:.4f} Acc: {epoch_acc:.4f}')

            # 검증(val) 단계에서 정확도가 기존 최고 기록보다 높으면 저장
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())

        print()

    time_elapsed = time.time() - since
    print(f'학습 완료! 걸린 시간: {time_elapsed // 60:.0f}분 {time_elapsed % 60:.0f}초')
    print(f'가장 높았던 검증 정확도(Best val Acc): {best_acc:4f}')

    # 가장 성능이 좋았던 가중치를 모델에 씌워서 반환
    model.load_state_dict(best_model_wts)
    return model

# 위 함수를 이용해 실제로 학습을 시작
model_ft = train_model(model, criterion, optimizer, num_epochs=10)

# 최고 성능의 모델을 파일로 저장
torch.save(model_ft.state_dict(), 'best_recycling_model.pth')
print("모델이 'best_recycling_model.pth'로 안전하게 저장되었습니다.")
# save_path = '/content/drive/MyDrive/AICOSS 2026 WE-Meet/best_recycling_model.pth'
# torch.save(model_ft.state_dict(), save_path)
# print("모델이 구글 드라이브에 안전하게 저장되었습니다.")