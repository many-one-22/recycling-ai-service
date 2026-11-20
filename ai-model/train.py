# -*- coding: utf-8 -*-
"""
train.py - 재활용품 4종(유리병/종이/캔/페트병) 분류 모델 학습

멘토님 피드백 반영 내역
  1) 20에폭 중 가장 좋은 에폭 저장        -> macro F1 기준으로 best 에폭 선택 + 몇 번째였는지 기록
  2) 회전/확대/축소/노이즈/반전 증강       -> 학습 증강으로 적용 (오프라인 배율 생성은 선택)
  3) 틀린 데이터를 전부 보고 원인 분석     -> 오분류 이미지 그리드 PNG + 혼동행렬 + CSV 자동 생성
  4) 모델 교체                            -> MODEL_NAME 한 줄로 교체 (mobilenet/resnet/efficientnet/convnext)

★ 가장 중요한 수정: 데이터 누수(leakage) 제거
  기존 코드는 "배율 변형본을 먼저 만들고 -> 그걸 통째로 train/val 분할" 하는 순서였다.
  그러면 같은 사진의 s70 은 train, s100 은 val 로 갈라져서
  검증 정확도가 "이미 본 사진을 배율만 바꿔 다시 맞히는 점수"가 되어버린다.
  (실제로 확인해보니 val 원본 604장이 100% train 에도 들어있었음 -> val 95% 인데 실사 62.5%)

  이 파일은 순서를 뒤집었다.
      원본을 먼저 train/val 로 나눈다  ->  그 다음 train 쪽에만 변형본을 만든다
  val 에는 한 번도 본 적 없는 사진만 남으므로, 이제 검증 점수를 믿을 수 있다.

실행
    python train.py                              # 학습 + 오류 분석
    python train.py --analyze-only best_recycling_model.pth   # 학습 없이 기존 모델만 분석
"""

import argparse
import copy
import csv
import os
import random
import shutil
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.transforms.functional as TF
from PIL import Image, ImageFilter, ImageOps
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

# =====================================================================
# 1. 설정  — 여기만 고치면 됨
# =====================================================================

# 이 파일이 있는 위치를 기준으로 경로를 잡는다.
# (어느 폴더에서 python train.py 를 실행하든 똑같이 동작하게 하기 위함.
#  예전처럼 "./data/..." 상대경로를 쓰면 ai-model 안에서 실행할 때 데이터를 못 찾음)
SCRIPT_DIR = Path(__file__).resolve().parent      # .../recycling-ai-service/ai-model
PROJECT_ROOT = SCRIPT_DIR.parent                  # .../recycling-ai-service

# --- 데이터 ---
RAW_DATA_DIR = "data/processed_200"     # 클래스별 원본 사진 폴더 (레포 루트 기준)
DATASET_DIR = SCRIPT_DIR / "dataset"    # 분할 결과가 만들어질 폴더 (매번 새로 만듦)
VAL_RATIO = 0.2
SEED = 42

# --- 오프라인 데이터 확장 (train 에만 적용됨) ---
# 주의: 이전 실험에서 이걸 켰을 때 실사 정확도가 62.5% -> 53.1% 로 떨어졌다.
#       다만 그때는 위의 누수 문제 때문에 "어떤 에폭이 좋은지" 판단 자체가 틀렸을 수 있다.
#       이제 val 을 믿을 수 있으니, False 로 한 번 / True 로 한 번 돌려서 직접 비교해볼 것.
USE_OFFLINE_EXPANSION = False
SCALES = [0.8, 1.0, 1.2]     # 축소/원본/확대
INCLUDE_EDGES = False
# 윤곽선(edge) 이미지는 기본 꺼둠. 실제 서비스에서는 사용자가 윤곽선 사진을 올릴 일이 없어서,
# 학습에만 존재하는 가짜 분포를 외우게 될 수 있음. 멘토님 제안이라 기능은 남겨둠.

# --- 모델 ---
# "mobilenet_v2" | "resnet18" | "resnet50" | "efficientnet_b0" | "convnext_tiny"
MODEL_NAME = "mobilenet_v2"

# --- 백본 동결 (과적합 방지) ---
# 사진이 640장뿐인데 2.2M 파라미터를 전부 풀어놓으면 2에폭 만에 통째로 외워버린다.
# 실제로 320 학습에서 train 100% / val 48% 까지 벌어졌고, 최고 에폭이 1번째였다.
# (= 2에폭 이후 학습이 전부 손해)
# 몸통을 얼려두면 외울 수 있는 자리가 없어서 일반화가 강제된다.
#   "none"    : 전부 학습 (지금까지 방식. 데이터가 수천 장 모이면 이걸로)
#   "partial" : 뒤쪽 2블록 + 출력층만 학습  <- 640장에는 이게 기본
#   "head"    : 출력층만 학습 (가장 강한 제약. partial 도 과적합이면 이걸로)
FREEZE_MODE = "partial"

# --- 학습 ---
NUM_EPOCHS = 20
BATCH_SIZE = 32
BACKBONE_LR = 1e-4   # 사전학습된 몸통: 조심스럽게
HEAD_LR = 1e-3       # 새로 만든 출력층: 좀 더 과감하게
WEIGHT_DECAY = 1e-4
LABEL_SMOOTHING = 0.05
# 입력 해상도.
# 224 -> 320 으로 올린 이유:
#   캔/페트병 원본이 4000x2400 급이라 224 로 줄이면 18배 축소된다.
#   그러면 캔 표면의 금속 질감/따개가 사라져서 실루엣만 남고,
#   '눕힌 원통'인 캔과 유리병을 구별할 단서가 없어진다.
#   재학습 없이 추론 해상도만 320 으로 올려본 실험에서
#   val macro F1 0.693 -> 0.785, 캔 재현율 30% -> 50% 로 올라갔다.
#   (384 는 오히려 떨어졌으므로 320 이 적당)
# 주의: 메모리를 약 2배 쓰고 학습 시간도 약 2배 늘어난다.
#       메모리가 부족하면 BATCH_SIZE 를 16 으로 낮출 것.
IMG_SIZE = 320

# --- 저장 ---
CHECKPOINT_PATH = SCRIPT_DIR / "best_recycling_model.pth"
REPORT_DIR = SCRIPT_DIR / "report"   # 혼동행렬, 오분류 그리드, CSV 가 여기 쌓임
SERVER_MODEL_PATH = PROJECT_ROOT / "be-api" / "best_recycling_model.pth"  # 서버가 읽는 위치

# --- 평가 ---
USE_TTA_FOR_FINAL_EVAL = True   # predict.py 와 동일한 조건으로 최종 점수 확인

MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
PAD_COLOR = (114, 114, 114)


# =====================================================================
# 2. 공통 유틸
# =====================================================================

def set_seed(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def nfc(text: str) -> str:
    """macOS 는 한글 파일명을 자소 분리(NFD)로 저장해서 '캔' != '캔' 이 되는 일이 있음.
    화면 출력/CSV 저장 전에 전부 NFC 로 맞춰준다."""
    return unicodedata.normalize("NFC", text)


def pad_to_square(image, fill_color=PAD_COLOR):
    """정사각형 letterbox 패딩.
    Resize((224,224)) 만 쓰면 세로로 긴 병이 찌그러져서 캔처럼 보이게 된다.
    predict.py 에도 똑같이 들어가 있어야 함 (학습/추론 전처리 불일치 방지)."""
    width, height = image.size
    max_side = max(width, height)
    new_image = Image.new("RGB", (max_side, max_side), fill_color)
    new_image.paste(image, ((max_side - width) // 2, (max_side - height) // 2))
    return new_image


def add_gaussian_noise(tensor, mean=0.0, std=0.03):
    """ToTensor 이후 ~ Normalize 이전에 적용"""
    noisy = tensor + torch.randn_like(tensor) * std + mean
    return torch.clamp(noisy, 0.0, 1.0)


def pick_device():
    if torch.cuda.is_available():
        return torch.device("cuda:0")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def get_pyplot():
    """matplotlib 이 설치돼 있으면 pyplot 을, 없으면 None 을 돌려준다.

    matplotlib 이 없다고 해서 20분 걸린 학습 결과를 날리면 안 되므로,
    그림만 건너뛰고 CSV/콘솔 출력은 그대로 나가도록 한다."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        return None


_FONT_READY = False


def setup_korean_font():
    """matplotlib 에서 한글 클래스명이 네모로 깨지지 않게 폰트를 잡아준다."""
    global _FONT_READY
    if _FONT_READY:
        return True
    try:
        import matplotlib
        from matplotlib import font_manager
    except ImportError:
        return False

    candidates = ["AppleGothic", "Malgun Gothic", "NanumGothic",
                  "NanumBarunGothic", "Noto Sans CJK KR", "Noto Sans KR"]
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            _FONT_READY = True
            return True
    print("[경고] 한글 폰트를 못 찾아서 그래프의 클래스명이 깨질 수 있습니다. "
          "(Mac 은 보통 AppleGothic 이 기본 설치되어 있음)")
    return False


def warn_no_matplotlib(what):
    print(f"[건너뜀] {what} — matplotlib 이 없습니다. "
          f"설치하려면:  pip install matplotlib")


IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def list_images(folder: Path):
    return sorted([p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() in IMG_EXTS])


def resolve_data_dir(given: str) -> Path:
    """원본 데이터 폴더를 찾는다.

    실행 위치(터미널의 현재 폴더)가 어디든 동작하도록, 그럴듯한 후보를 차례로 본다.
    못 찾으면 '어디를 찾아봤는지' 전부 보여주고 멈춘다.
    """
    candidates = [
        Path(given),                 # 실행 위치 기준
        PROJECT_ROOT / given,        # 레포 루트 기준  <- 보통 여기
        SCRIPT_DIR / given,          # ai-model 폴더 기준
    ]
    for c in candidates:
        if c.is_dir() and any(d.is_dir() for d in c.iterdir()):
            return c.resolve()

    msg = ["[오류] 원본 데이터 폴더를 찾지 못했습니다.", "찾아본 곳:"]
    for c in candidates:
        msg.append(f"   - {c.resolve()}  {'(폴더는 있는데 클래스 폴더가 없음)' if c.is_dir() else '(없음)'}")
    msg.append("")
    msg.append("해결 방법: 클래스별 사진이 들어있는 폴더 경로를 --data 로 직접 주세요.")
    msg.append("   예) python train.py --data /Users/dawon/.../recycling-ai-service/data/processed_200")
    sys.exit("\n".join(msg))


# =====================================================================
# 3. 데이터 준비 — 원본 단위로 먼저 나누고, train 에만 확장
# =====================================================================

def split_by_original(raw_dir: str, out_dir: str, val_ratio=VAL_RATIO, seed=SEED):
    """클래스별 원본 사진을 train/val 로 나눠서 복사한다.

    splitfolders 를 쓰지 않는 이유:
      splitfolders 는 '파일 단위'로 섞는다. 변형본이 이미 만들어진 폴더에 쓰면
      같은 원본의 변형이 train 과 val 로 흩어져서 누수가 생긴다.
      그래서 확장 '전'의 원본만 가지고, 여기서 직접 나눈다.
    """
    raw, out = Path(raw_dir), Path(out_dir)
    if not raw.is_dir():
        sys.exit(f"[오류] 원본 데이터 폴더가 없습니다: {raw.resolve()}")

    if out.exists():
        shutil.rmtree(out)   # 이전 분할이 섞이지 않도록 항상 새로 만든다
    for split in ("train", "val"):
        (out / split).mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    classes = sorted([d for d in raw.iterdir() if d.is_dir()])
    if not classes:
        sys.exit(f"[오류] {raw} 안에 클래스 폴더가 없습니다.")

    print(f"[분할] 원본 폴더: {raw}")
    print(f"[분할] {'클래스':<10}{'원본':>6}{'train':>8}{'val':>6}")
    summary = {}
    for cls_dir in classes:
        images = list_images(cls_dir)
        rng.shuffle(images)
        n_val = max(1, int(len(images) * val_ratio))
        val_imgs, train_imgs = images[:n_val], images[n_val:]

        for split, imgs in (("train", train_imgs), ("val", val_imgs)):
            dest = out / split / cls_dir.name
            dest.mkdir(parents=True, exist_ok=True)
            for p in imgs:
                shutil.copy2(p, dest / p.name)

        summary[nfc(cls_dir.name)] = (len(images), len(train_imgs), len(val_imgs))
        print(f"[분할] {nfc(cls_dir.name):<10}{len(images):>6}{len(train_imgs):>8}{len(val_imgs):>6}")

    counts = [v[0] for v in summary.values()]
    if max(counts) - min(counts) > 0.2 * max(counts):
        print(f"[주의] 클래스별 사진 수 차이가 큽니다 {summary}. "
              f"적은 클래스가 불리해지니 수를 맞추는 걸 권장합니다.")
    return summary


def zoom_image(image: Image.Image, scale: float, fill_color=PAD_COLOR) -> Image.Image:
    """scale>1 확대(가운데 크롭), scale<1 축소(회색 여백 채움)"""
    width, height = image.size
    if scale == 1.0:
        return image.copy()
    if scale > 1.0:
        crop_w, crop_h = int(width / scale), int(height / scale)
        left, top = (width - crop_w) // 2, (height - crop_h) // 2
        return image.crop((left, top, left + crop_w, top + crop_h)).resize(
            (width, height), Image.LANCZOS)
    new_w, new_h = int(width * scale), int(height * scale)
    shrunk = image.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (width, height), fill_color)
    canvas.paste(shrunk, ((width - new_w) // 2, (height - new_h) // 2))
    return canvas


def extract_edges(image: Image.Image) -> Image.Image:
    """흑백 -> 대비 강화 -> 윤곽선 -> 다시 RGB 3채널"""
    gray = ImageOps.autocontrast(image.convert("L"))
    return gray.filter(ImageFilter.FIND_EDGES).convert("RGB")


def expand_train_only(dataset_dir: str, scales, include_edges: bool):
    """train 폴더 '안에서만' 변형본을 추가로 만든다. val 은 절대 건드리지 않는다."""
    train_dir = Path(dataset_dir) / "train"
    print(f"[확장] 배율 {scales} / 윤곽선 {include_edges}  (train 폴더에만 적용)")

    made = 0
    for cls_dir in sorted([d for d in train_dir.iterdir() if d.is_dir()]):
        originals = list_images(cls_dir)
        for p in originals:
            try:
                image = Image.open(p).convert("RGB")
            except Exception as e:
                print(f"[확장] 건너뜀(열기 실패) {p.name}: {e}")
                continue
            for scale in scales:
                if scale == 1.0:
                    continue   # 원본은 이미 폴더에 있음
                out = cls_dir / f"{p.stem}_s{int(scale * 100)}.jpg"
                zoom_image(image, scale).save(out, quality=92)
                made += 1
            if include_edges:
                extract_edges(image).save(cls_dir / f"{p.stem}_edge.jpg", quality=92)
                made += 1
        print(f"[확장]   {nfc(cls_dir.name)}: {len(originals)}장 -> {len(list_images(cls_dir))}장")
    print(f"[확장] 총 {made}장 추가 생성")


def build_transforms():
    """학습용 증강 = 회전 + 확대/축소 + 좌우반전 + 색변화 + 흑백 + 노이즈
       검증용은 패딩/리사이즈만 (평가는 항상 '있는 그대로')"""
    train_tf = transforms.Compose([
        transforms.Lambda(pad_to_square),
        transforms.RandomResizedCrop(IMG_SIZE, scale=(0.7, 1.0), ratio=(0.85, 1.18)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15, fill=PAD_COLOR),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.02),
        transforms.RandomGrayscale(p=0.1),
        transforms.ToTensor(),
        transforms.Lambda(add_gaussian_noise),
        transforms.Normalize(MEAN, STD),
    ])
    val_tf = transforms.Compose([
        transforms.Lambda(pad_to_square),
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    return {"train": train_tf, "val": val_tf}


class ImageFolderWithPaths(datasets.ImageFolder):
    """오류 분석 때 '어떤 파일'이 틀렸는지 알아야 해서 경로까지 같이 반환"""
    def __getitem__(self, index):
        img, label = super().__getitem__(index)
        return img, label, self.imgs[index][0]


# =====================================================================
# 4. 모델 — MODEL_NAME 한 줄로 교체
# =====================================================================

def build_model(name: str, num_classes: int, pretrained=True):
    weights = "IMAGENET1K_V1" if pretrained else None

    if name == "mobilenet_v2":
        model = models.mobilenet_v2(weights=weights)
        in_f = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_f, num_classes)
        head_prefix = "classifier"

    elif name == "resnet18":
        model = models.resnet18(weights=weights)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
        head_prefix = "fc"

    elif name == "resnet50":
        model = models.resnet50(weights=weights)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
        head_prefix = "fc"

    elif name == "efficientnet_b0":
        model = models.efficientnet_b0(weights=weights)
        in_f = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_f, num_classes)
        head_prefix = "classifier"

    elif name == "convnext_tiny":
        model = models.convnext_tiny(weights=weights)
        in_f = model.classifier[2].in_features
        model.classifier[2] = nn.Linear(in_f, num_classes)
        head_prefix = "classifier"

    else:
        raise ValueError(
            f"모르는 모델 이름: {name}\n"
            "쓸 수 있는 값: mobilenet_v2, resnet18, resnet50, efficientnet_b0, convnext_tiny"
        )

    for p in model.parameters():      # 전체 파인튜닝
        p.requires_grad = True
    return model, head_prefix


def apply_freezing(model, name, mode, head_prefix):
    """백본 일부를 얼린다. 얼린 레이어는 학습 중에도 값이 바뀌지 않는다.

    반환: (학습되는 파라미터 수, 전체 파라미터 수, 얼린 모듈 목록)
    얼린 모듈 목록은 BatchNorm 때문에 필요하다 (아래 run_epoch 설명 참고).
    """
    if mode == "none":
        for p in model.parameters():
            p.requires_grad = True
        return sum(p.numel() for p in model.parameters()), \
               sum(p.numel() for p in model.parameters()), []

    # 1) 일단 전부 얼린다
    for p in model.parameters():
        p.requires_grad = False

    frozen_modules = []

    # 2) 출력층은 항상 녹인다 (클래스 수가 바뀌었으므로 새로 배워야 함)
    head = getattr(model, head_prefix)
    for p in head.parameters():
        p.requires_grad = True

    # 3) partial 이면 몸통 뒤쪽도 녹인다
    if mode == "partial":
        if hasattr(model, "features"):        # mobilenet / efficientnet / convnext
            blocks = list(model.features.children())
            for blk in blocks[-2:]:
                for p in blk.parameters():
                    p.requires_grad = True
            frozen_modules = blocks[:-2]
        elif hasattr(model, "layer4"):        # resnet 계열
            for p in model.layer4.parameters():
                p.requires_grad = True
            frozen_modules = [model.conv1, model.bn1, model.layer1,
                              model.layer2, model.layer3]
        else:
            raise ValueError(f"{name} 는 partial 동결 방법을 모릅니다. 'head' 로 쓰세요.")
    else:  # "head"
        if hasattr(model, "features"):
            frozen_modules = [model.features]
        elif hasattr(model, "layer4"):
            frozen_modules = [model.conv1, model.bn1, model.layer1,
                              model.layer2, model.layer3, model.layer4]

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    return trainable, total, frozen_modules


def make_optimizer(model, head_prefix):
    """새로 만든 출력층은 빠르게, 사전학습된 몸통은 천천히 학습시킨다.
    (몸통까지 큰 lr 로 흔들면 ImageNet 에서 배운 특징이 망가짐)"""
    head, backbone = [], []
    for n, p in model.named_parameters():
        if not p.requires_grad:      # 얼린 건 옵티마이저에 아예 넣지 않는다
            continue
        (head if n.startswith(head_prefix) else backbone).append(p)

    groups = []
    if backbone:
        groups.append({"params": backbone, "lr": BACKBONE_LR})
    if head:
        groups.append({"params": head, "lr": HEAD_LR})
    return optim.AdamW(groups, weight_decay=WEIGHT_DECAY)


# =====================================================================
# 5. 학습
# =====================================================================

def run_epoch(model, loader, criterion, optimizer, device, train: bool,
              frozen_modules=()):
    model.train() if train else model.eval()

    # 얼린 레이어는 가중치가 안 바뀌지만, model.train() 상태에서는
    # BatchNorm 의 running_mean/var 가 계속 갱신된다.
    # 그러면 "얼렸다"고 해놓고 사실상 몸통이 흔들려서 동결 효과가 반감된다.
    # 그래서 얼린 부분만 eval 모드로 되돌려 통계도 고정한다.
    if train:
        for m in frozen_modules:
            m.eval()
    total_loss, total_correct, n = 0.0, 0, 0
    preds_all, labels_all = [], []

    for inputs, labels, _ in loader:
        inputs, labels = inputs.to(device), labels.to(device)
        if train:
            optimizer.zero_grad()
        with torch.set_grad_enabled(train):
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            _, preds = torch.max(outputs, 1)
            if train:
                loss.backward()
                optimizer.step()

        total_loss += loss.item() * inputs.size(0)
        total_correct += torch.sum(preds == labels.data).item()
        n += inputs.size(0)
        preds_all.extend(preds.cpu().numpy())
        labels_all.extend(labels.cpu().numpy())

    return (total_loss / n,
            total_correct / n,
            f1_score(labels_all, preds_all, average="macro", zero_division=0))


def train_model(model, head_prefix, dataloaders, device, num_epochs=NUM_EPOCHS,
                frozen_modules=()):
    criterion = nn.CrossEntropyLoss(label_smoothing=LABEL_SMOOTHING)
    optimizer = make_optimizer(model, head_prefix)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=num_epochs)

    best_wts = copy.deepcopy(model.state_dict())
    best_f1, best_epoch, best_acc = -1.0, -1, 0.0
    history = []
    since = time.time()

    for epoch in range(1, num_epochs + 1):
        tr_loss, tr_acc, tr_f1 = run_epoch(model, dataloaders["train"], criterion,
                                           optimizer, device, train=True,
                                           frozen_modules=frozen_modules)
        va_loss, va_acc, va_f1 = run_epoch(model, dataloaders["val"], criterion,
                                           optimizer, device, train=False)
        scheduler.step()

        # best 는 정확도가 아니라 macro F1 기준.
        # 클래스가 한쪽으로 쏠렸을 때 정확도는 착시를 주지만 F1 은 안 속는다.
        marker = ""
        if va_f1 > best_f1:
            best_f1, best_acc, best_epoch = va_f1, va_acc, epoch
            best_wts = copy.deepcopy(model.state_dict())
            marker = "  <= best"

        print(f"Epoch {epoch:2d}/{num_epochs} | "
              f"train loss {tr_loss:.4f} acc {tr_acc:.4f} f1 {tr_f1:.4f} | "
              f"val loss {va_loss:.4f} acc {va_acc:.4f} f1 {va_f1:.4f}{marker}")

        history.append({"epoch": epoch,
                        "train_loss": tr_loss, "train_acc": tr_acc, "train_f1": tr_f1,
                        "val_loss": va_loss, "val_acc": va_acc, "val_f1": va_f1})

        # 과적합 조기 경고
        if tr_acc - va_acc > 0.25 and epoch >= 5:
            print(f"      [주의] train 과 val 정확도 차이가 {tr_acc - va_acc:.2f} 입니다. "
                  f"과적합 신호 — 증강을 늘리거나 에폭을 줄여보세요.")

    elapsed = time.time() - since
    print(f"\n학습 완료! {elapsed // 60:.0f}분 {elapsed % 60:.0f}초")
    print(f"가장 좋았던 에폭: {best_epoch}번째 (val macro F1 {best_f1:.4f}, acc {best_acc:.4f})")

    model.load_state_dict(best_wts)
    return model, history, best_epoch, best_f1


def save_history(history, report_dir):
    path = Path(report_dir) / "history.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(history[0].keys()))
        w.writeheader()
        w.writerows(history)
    print(f"[저장] 에폭별 기록 -> {path}")

    plt = get_pyplot()
    if plt is None:
        warn_no_matplotlib("학습 곡선 그리기")
        return
    try:
        epochs = [h["epoch"] for h in history]
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        axes[0].plot(epochs, [h["train_loss"] for h in history], label="train")
        axes[0].plot(epochs, [h["val_loss"] for h in history], label="val")
        axes[0].set_title("Loss"); axes[0].set_xlabel("epoch"); axes[0].legend(); axes[0].grid(alpha=.3)

        axes[1].plot(epochs, [h["train_acc"] for h in history], label="train acc")
        axes[1].plot(epochs, [h["val_acc"] for h in history], label="val acc")
        axes[1].plot(epochs, [h["val_f1"] for h in history], label="val macro F1", linestyle="--")
        axes[1].set_title("Accuracy / F1"); axes[1].set_xlabel("epoch"); axes[1].legend(); axes[1].grid(alpha=.3)

        fig.tight_layout()
        out = Path(report_dir) / "training_curve.png"
        fig.savefig(out, dpi=130); plt.close(fig)
        print(f"[저장] 학습 곡선 -> {out}")
    except Exception as e:
        print(f"[경고] 학습 곡선 그리기 실패(무시하고 계속): {e}")


# =====================================================================
# 6. 평가 + 오류 분석  (멘토님 피드백의 핵심)
# =====================================================================

def tta_logits(model, inputs):
    """predict.py 와 같은 4가지 시점(원본/좌우반전/±10도)의 확률을 평균."""
    views = [
        inputs,
        torch.flip(inputs, dims=[3]),
        TF.rotate(inputs, 10),
        TF.rotate(inputs, -10),
    ]
    probs = [torch.softmax(model(v), dim=1) for v in views]
    return torch.stack(probs).mean(dim=0)


@torch.no_grad()
def collect_predictions(model, loader, device, use_tta=False):
    model.eval()
    all_probs, all_labels, all_paths = [], [], []
    for inputs, labels, paths in loader:
        inputs = inputs.to(device)
        probs = tta_logits(model, inputs) if use_tta else torch.softmax(model(inputs), dim=1)
        all_probs.append(probs.cpu())
        all_labels.extend(labels.numpy())
        all_paths.extend(paths)
    probs = torch.cat(all_probs).numpy()
    return probs, np.array(all_labels), all_paths


def plot_confusion(cm, class_names, report_dir, title, filename):
    plt = get_pyplot()
    if plt is None:
        warn_no_matplotlib("혼동행렬 그림")
        return
    setup_korean_font()

    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(class_names)), class_names, rotation=30, ha="right")
    ax.set_yticks(range(len(class_names)), class_names)
    ax.set_xlabel("모델 예측"); ax.set_ylabel("실제 정답"); ax.set_title(title)

    thresh = cm.max() / 2 if cm.max() else 0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black", fontsize=11)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    out = Path(report_dir) / filename
    fig.savefig(out, dpi=140); plt.close(fig)
    print(f"[저장] 혼동행렬 -> {out}")


def plot_mistake_grid(mistakes, class_names, report_dir, max_per_pair=8):
    """'실제 X인데 Y로 예측' 쌍별로 틀린 사진을 모아서 한 장의 PNG 로 만든다.
    확신이 높았던 오답부터 보여준다 — 모델이 '자신 있게' 틀린 게 가장 정보가 많다."""
    plt = get_pyplot()
    if plt is None:
        warn_no_matplotlib("오분류 이미지 그리드")
        return []
    setup_korean_font()

    by_pair = defaultdict(list)
    for m in mistakes:
        by_pair[(m["true"], m["pred"])].append(m)

    saved = []
    for (t, p), items in sorted(by_pair.items(), key=lambda kv: -len(kv[1])):
        items = sorted(items, key=lambda m: -m["confidence"])[:max_per_pair]
        cols = min(4, len(items))
        rows = (len(items) + cols - 1) // cols
        # 제목이 윗줄 이미지에 겹치지 않도록 줄 높이와 간격을 넉넉히 준다
        fig, axes = plt.subplots(rows, cols,
                                 figsize=(3.1 * cols, 4.0 * rows),
                                 squeeze=False,
                                 gridspec_kw={"hspace": 0.32, "wspace": 0.06})

        for ax in axes.flat:
            ax.axis("off")
        for ax, m in zip(axes.flat, items):
            try:
                img = pad_to_square(Image.open(m["path"]).convert("RGB"))
                ax.imshow(img)
            except Exception:
                ax.text(0.5, 0.5, "이미지 열기 실패", ha="center")
            ax.set_title(f"{m['confidence'] * 100:.0f}% 확신 (정답 {m['true_prob'] * 100:.0f}%)"
                         f"\n{nfc(Path(m['path']).name)[:24]}", fontsize=9)

        fig.suptitle(f"실제 [{t}]  →  모델은 [{p}] 라고 봄   (총 {len(by_pair[(t, p)])}장)",
                     fontsize=14, y=0.98)
        out = Path(report_dir) / f"mistakes_{t}_to_{p}.png"
        fig.savefig(out, dpi=130); plt.close(fig)
        saved.append(out)
        print(f"[저장] 오분류 그리드 -> {out}")
    return saved


def analyze_errors(model, loader, class_names, device, report_dir,
                   use_tta=False, title="검증셋"):
    """혼동행렬 + 클래스별 성적표 + 오분류 목록(CSV) + 오분류 이미지 그리드"""
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    setup_korean_font()

    tag = "TTA 적용" if use_tta else "TTA 없음"
    probs, labels, paths = collect_predictions(model, loader, device, use_tta=use_tta)
    preds = probs.argmax(axis=1)

    acc = (preds == labels).mean()
    f1 = f1_score(labels, preds, average="macro", zero_division=0)
    print(f"\n===== {title} 성적 ({tag}) =====")
    print(f"정확도 {acc:.4f} | macro F1 {f1:.4f}  ({title} {len(labels)}장)")
    print()
    print(classification_report(labels, preds, target_names=class_names,
                                digits=3, zero_division=0))

    cm = confusion_matrix(labels, preds, labels=list(range(len(class_names))))

    # 그림이 없어도 바로 볼 수 있게 글자로도 출력
    w = max(6, max(len(c) for c in class_names) + 1)
    print("----- 혼동행렬 (세로=실제 / 가로=예측) -----")
    print(" " * (w + 2) + "".join(f"{c:>{w}}" for c in class_names))
    for i, c in enumerate(class_names):
        row = "".join(f"{v:>{w}}" for v in cm[i])
        hit = cm[i, i] / max(cm[i].sum(), 1) * 100
        print(f"{c:>{w}}  {row}    ({hit:.0f}% 맞춤)")
    print()

    suffix = "tta" if use_tta else "plain"
    plot_confusion(cm, class_names, report_dir,
                   f"혼동행렬 ({tag}) — 정확도 {acc * 100:.1f}%",
                   f"confusion_matrix_{suffix}.png")

    # ---- 틀린 것 모으기 ----
    mistakes = []
    for i in range(len(labels)):
        if preds[i] == labels[i]:
            continue
        order = probs[i].argsort()[::-1]
        mistakes.append({
            "path": paths[i],
            "true": class_names[labels[i]],
            "pred": class_names[preds[i]],
            "confidence": float(probs[i][preds[i]]),
            "true_prob": float(probs[i][labels[i]]),
            "second": class_names[order[1]],
            "second_prob": float(probs[i][order[1]]),
        })

    csv_path = Path(report_dir) / f"mistakes_{suffix}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["파일", "실제", "예측", "예측확신도", "정답확률", "2순위", "2순위확률"])
        for m in sorted(mistakes, key=lambda m: -m["confidence"]):
            w.writerow([nfc(Path(m["path"]).name), m["true"], m["pred"],
                        f"{m['confidence']:.4f}", f"{m['true_prob']:.4f}",
                        m["second"], f"{m['second_prob']:.4f}"])
    print(f"[저장] 오분류 목록 ({len(mistakes)}장) -> {csv_path}")

    if not mistakes:
        print("틀린 게 하나도 없습니다. 검증셋이 너무 쉽거나 누수를 의심해보세요.")
        return {"acc": acc, "f1": f1, "mistakes": []}

    # ---- 헷갈린 쌍 요약 ----
    pair_counter = Counter((m["true"], m["pred"]) for m in mistakes)
    print(f"\n----- 가장 많이 헷갈린 조합 -----")
    for (t, p), c in pair_counter.most_common(6):
        avg_conf = np.mean([m["confidence"] for m in mistakes
                            if m["true"] == t and m["pred"] == p])
        print(f"  실제 {t:<5} -> 예측 {p:<5} : {c:>3}장 (평균 확신 {avg_conf * 100:.0f}%)")

    # ---- 자신 있게 틀린 것 ----
    print(f"\n----- 자신 있게 틀린 사진 TOP 5 (여기를 먼저 보세요) -----")
    for m in sorted(mistakes, key=lambda m: -m["confidence"])[:5]:
        print(f"  {nfc(Path(m['path']).name)[:40]:<42} "
              f"{m['true']} -> {m['pred']} ({m['confidence'] * 100:.0f}%)  "
              f"정답확률 {m['true_prob'] * 100:.0f}%")

    plot_mistake_grid(mistakes, class_names, report_dir)
    return {"acc": acc, "f1": f1, "mistakes": mistakes}


# =====================================================================
# 7. 메인
# =====================================================================

def build_val_loader(device):
    tfs = build_transforms()
    val_ds = ImageFolderWithPaths(os.path.join(DATASET_DIR, "val"), tfs["val"])
    loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    class_names = [nfc(c) for c in val_ds.classes]
    return loader, class_names


def main():
    global IMG_SIZE   # --img-size 로 덮어쓸 수 있게

    parser = argparse.ArgumentParser()
    parser.add_argument("--analyze-only", metavar="CHECKPOINT", default=None,
                        help="학습 없이 기존 .pth 파일로 오류 분석만 실행")
    parser.add_argument("--model", default=MODEL_NAME, help="사용할 모델 이름")
    parser.add_argument("--epochs", type=int, default=NUM_EPOCHS)
    parser.add_argument("--data", default=RAW_DATA_DIR,
                        help="클래스별 원본 사진이 들어있는 폴더")
    parser.add_argument("--freeze", default=FREEZE_MODE,
                        choices=["none", "partial", "head"],
                        help="백본 동결 정도 (과적합 방지)")
    parser.add_argument("--img-size", type=int, default=IMG_SIZE,
                        help="입력 해상도 (224 / 320 등)")
    args, _ = parser.parse_known_args()   # 코랩에서 돌려도 깨지지 않게
    IMG_SIZE = args.img_size

    set_seed()
    device = pick_device()
    print(f"사용 디바이스: {device}")
    Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)

    # ---------- 분석만 ----------
    if args.analyze_only:
        ckpt = torch.load(args.analyze_only, map_location=device, weights_only=False)
        class_names = [nfc(c) for c in ckpt["classes"]]
        model_name = ckpt.get("model_name", "mobilenet_v2")
        print(f"[분석] 체크포인트: {args.analyze_only} (모델 {model_name})")
        model, _ = build_model(model_name, len(class_names), pretrained=False)
        model.load_state_dict(ckpt["model_state_dict"])
        model = model.to(device)

        loader, folder_classes = build_val_loader(device)
        if folder_classes != class_names:
            print(f"[주의] 체크포인트 클래스 {class_names} 와 "
                  f"폴더 클래스 {folder_classes} 가 다릅니다. 폴더 기준으로 진행합니다.")
        analyze_errors(model, loader, folder_classes, device, REPORT_DIR, use_tta=False)
        if USE_TTA_FOR_FINAL_EVAL:
            analyze_errors(model, loader, folder_classes, device, REPORT_DIR, use_tta=True)
        return

    # ---------- 1) 데이터 준비 ----------
    raw_dir = resolve_data_dir(args.data)
    print(f"원본 데이터 : {raw_dir}")
    print(f"분할 결과   : {Path(DATASET_DIR).resolve()}")
    print(f"분석 리포트 : {Path(REPORT_DIR).resolve()}\n")

    split_by_original(raw_dir, DATASET_DIR)
    if USE_OFFLINE_EXPANSION:
        expand_train_only(DATASET_DIR, SCALES, INCLUDE_EDGES)
    else:
        print("[확장] 오프라인 확장은 꺼져 있습니다 (학습 중 증강만 사용).")

    tfs = build_transforms()
    image_datasets = {
        x: ImageFolderWithPaths(os.path.join(DATASET_DIR, x), tfs[x])
        for x in ("train", "val")
    }
    dataloaders = {
        "train": DataLoader(image_datasets["train"], batch_size=BATCH_SIZE,
                            shuffle=True, num_workers=0),
        "val": DataLoader(image_datasets["val"], batch_size=BATCH_SIZE,
                          shuffle=False, num_workers=0),
    }
    class_names = [nfc(c) for c in image_datasets["train"].classes]
    print(f"\n클래스: {class_names}")
    print(f"학습 {len(image_datasets['train'])}장 / 검증 {len(image_datasets['val'])}장")
    print("(검증 사진은 학습에 한 번도 쓰이지 않은 원본입니다)\n")

    # ---------- 2) 모델 ----------
    model, head_prefix = build_model(args.model, len(class_names))
    trainable, total, frozen_modules = apply_freezing(
        model, args.model, args.freeze, head_prefix)
    model = model.to(device)

    print(f"모델    : {args.model}")
    print(f"입력크기: {IMG_SIZE}px")
    print(f"동결    : {args.freeze}  "
          f"(학습되는 파라미터 {trainable/1e6:.2f}M / 전체 {total/1e6:.2f}M "
          f"= {trainable/total*100:.1f}%)\n")

    # ---------- 3) 학습 ----------
    model, history, best_epoch, best_f1 = train_model(
        model, head_prefix, dataloaders, device, num_epochs=args.epochs,
        frozen_modules=frozen_modules)
    save_history(history, REPORT_DIR)

    # ---------- 4) 저장 ----------
    torch.save({
        "model_state_dict": model.state_dict(),
        "classes": class_names,
        "model_name": args.model,     # predict.py 가 어떤 모델인지 알 수 있게
        "img_size": IMG_SIZE,
        "freeze_mode": args.freeze,
        "best_epoch": best_epoch,
        "best_val_f1": best_f1,
    }, CHECKPOINT_PATH)
    print(f"[저장] 모델 -> {CHECKPOINT_PATH} (best 에폭 {best_epoch})")
    print(f"       서버에 반영하려면:  cp {CHECKPOINT_PATH} {SERVER_MODEL_PATH}")

    # ---------- 5) 오류 분석 ----------
    analyze_errors(model, dataloaders["val"], class_names, device, REPORT_DIR, use_tta=False)
    if USE_TTA_FOR_FINAL_EVAL:
        analyze_errors(model, dataloaders["val"], class_names, device, REPORT_DIR, use_tta=True)

    print(f"\n분석 결과는 {Path(REPORT_DIR).resolve()} 폴더에 있습니다.")
    print("  - confusion_matrix_*.png : 어떤 클래스를 어떤 클래스로 착각하는지")
    print("  - mistakes_A_to_B.png    : 그 착각이 실제로 어떤 사진인지")
    print("  - mistakes_*.csv         : 틀린 사진 전체 목록 (확신도 순)")
    print("  - training_curve.png     : 몇 번째 에폭이 가장 좋았는지")


if __name__ == "__main__":
    main()