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


# 가중치 및 클래스 이름이 저장된 모델 불러오기
state_dict = torch.load('best_recycling_model.pth')['model_state_dict']
class_names = torch.load('best_recycling_model.pth')['classes']

# MobileNet 모델 불러오기 및 수정

# 1. 사전 학습된 MobileNet V2 모델 불러오기
model = models.mobilenet_v2(weights=None)  # 사전 학습된 가중치 사용 안함 (None)
for param in model.parameters():
    param.requires_grad = False

# 2. 마지막 출력층(Classifier) 수정하기
# 우리의 클래스 개수 (페트병, 캔, 종이, 유리병, 비닐, 스티로폼, 플라스틱 = 총 7개)
num_classes = len(class_names)

# MobileNetV2의 classifier[1]이 원래 1000개를 분류하던 것을 7개로 수정
num_ftrs = model.classifier[1].in_features
model.classifier[1] = nn.Linear(num_ftrs, num_classes)

# 모델에 가중치 대입하기
model.load_state_dict(state_dict)
model = model.to(device)

model.eval()  # 평가 모드로 전환 (Dropout, BatchNorm 등 비활성화)


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

