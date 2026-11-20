# -*- coding: utf-8 -*-
"""
eval_real_world.py - 우리가 직접 찍은 사진으로 모델을 평가

왜 따로 필요한가
    train.py 의 검증 점수는 AI Hub 사진 기준이다.
    실제 서비스는 사용자가 폰으로 찍은 사진을 받는다.
    둘 사이에 간극이 있으면 "검증 95%인데 현장에서 70%" 같은 일이 벌어진다.
    그래서 같은 잣대로 실사 점수를 따로 재야 한다.

train.py 의 분석 코드를 그대로 가져다 쓴다.
    혼동행렬/오분류 그리드/CSV 가 검증셋 결과와 똑같은 형식으로 나오므로
    두 결과를 나란히 놓고 비교할 수 있다.

폴더 구조 (클래스별로 나눠둘 것. 폴더 이름은 한글/영문 둘 다 됨)
    ai-model/realworld/
        유리병/   또는  glass/
        종이/     또는  paper/
        캔/       또는  can/
        페트병/   또는  pet/

사용법
    cd ai-model
    python eval_real_world.py                                   # realworld/ 를 기본으로 평가
    python eval_real_world.py --test-dir ./내가찍은사진
    python eval_real_world.py --checkpoint model_effnet.pth
    python eval_real_world.py --no-tta                           # TTA 끄고 비교
"""

import argparse
import sys
import unicodedata
from pathlib import Path

import torch
from PIL import Image, ImageFile
from torch.utils.data import DataLoader, Dataset

# 학습 때 쓴 전처리/분석 코드를 그대로 재사용한다.
# (여기서 따로 구현하면 학습과 미묘하게 달라져서 점수가 조용히 틀어진다)
import train as T

# AI Hub 사진 중 일부가 깨져 있어서 열다가 멈추는 경우가 있었음.
# 깨진 뒷부분은 버리고 읽을 수 있는 만큼만 읽는다.
ImageFile.LOAD_TRUNCATED_IMAGES = True

SCRIPT_DIR = Path(__file__).resolve().parent

# 폴더 이름이 영문일 때 우리 클래스명으로 바꿔주는 표
FOLDER_NAME_MAP = {
    "can": "캔", "cans": "캔",
    "glass": "유리병", "glassbottle": "유리병",
    "paper": "종이",
    "pet": "페트병", "plastic": "페트병", "petbottle": "페트병",
}


def canonical(name: str) -> str:
    """폴더 이름 -> 클래스 이름.

    macOS 는 한글 폴더명을 자소 분리(NFD)로 저장해서 '캔' != '캔' 이 되는 일이 있다.
    예전에 이것 때문에 정답률이 0/32 로 나온 적이 있으므로 반드시 NFC 로 맞춘다.
    """
    n = unicodedata.normalize("NFC", name).strip()
    return unicodedata.normalize("NFC", FOLDER_NAME_MAP.get(n.lower(), n))


class RealWorldDataset(Dataset):
    """폴더 이름을 '체크포인트의 클래스 순서'에 맞춰 라벨로 바꿔주는 데이터셋.

    torchvision 의 ImageFolder 를 쓰지 않는 이유:
      ImageFolder 는 폴더 이름을 알파벳순으로 정렬해서 0,1,2,3 을 매긴다.
      그 순서가 학습 때 순서와 다르면 라벨이 통째로 뒤섞여서
      에러 없이 엉뚱한 점수가 나온다. 그래서 직접 매핑한다.
    """

    def __init__(self, test_dir: Path, class_names, transform):
        self.transform = transform
        self.samples = []
        index_of = {c: i for i, c in enumerate(class_names)}

        folders = sorted([d for d in test_dir.iterdir() if d.is_dir()])
        if not folders:
            sys.exit(f"[오류] {test_dir} 안에 클래스 폴더가 없습니다.\n"
                     f"      예) {test_dir}/유리병/, {test_dir}/캔/ ...")

        unknown, empty = [], []
        for folder in folders:
            cls = canonical(folder.name)
            if cls not in index_of:
                unknown.append(folder.name)
                continue
            images = T.list_images(folder)
            if not images:
                empty.append(folder.name)
            for p in images:
                self.samples.append((p, index_of[cls]))

        if unknown:
            print(f"[주의] 모델이 모르는 클래스 폴더는 건너뜁니다: {unknown}")
            print(f"       모델이 아는 클래스: {list(class_names)}")
        if empty:
            print(f"[주의] 사진이 없는 폴더: {empty}")
        if not self.samples:
            sys.exit("[오류] 평가할 사진이 하나도 없습니다.")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        path, label = self.samples[i]
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            sys.exit(f"[오류] 사진을 열 수 없습니다: {path}\n       {e}")
        return self.transform(img), label, str(path)


def main():
    parser = argparse.ArgumentParser(description="직접 찍은 사진으로 모델 평가")
    parser.add_argument("--checkpoint", default=str(SCRIPT_DIR / "best_recycling_model.pth"),
                        help="평가할 모델 파일")
    parser.add_argument("--test-dir", default=str(SCRIPT_DIR / "realworld"),
                        help="클래스별 폴더가 들어있는 사진 폴더")
    parser.add_argument("--no-tta", action="store_true",
                        help="TTA 끄고 평가 (기본은 TTA 적용 — 서비스와 같은 조건)")
    parser.add_argument("--report-dir", default=str(SCRIPT_DIR / "report_realworld"),
                        help="혼동행렬/오분류 그리드/CSV 저장 위치")
    args, _ = parser.parse_known_args()

    ckpt_path = Path(args.checkpoint)
    test_dir = Path(args.test_dir)
    if not ckpt_path.is_file():
        sys.exit(f"[오류] 모델 파일이 없습니다: {ckpt_path.resolve()}\n"
                 f"      먼저 python train.py 로 학습하세요.")
    if not test_dir.is_dir():
        sys.exit(f"[오류] 사진 폴더가 없습니다: {test_dir.resolve()}\n"
                 f"      클래스별 폴더를 만들어 사진을 넣어주세요.\n"
                 f"      예) {test_dir}/유리병/  {test_dir}/종이/  {test_dir}/캔/  {test_dir}/페트병/")

    device = T.pick_device()
    print(f"사용 디바이스: {device}")

    # ---- 체크포인트에서 설정을 읽는다 (여기에 숫자를 박아두면 학습과 어긋남) ----
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    class_names = [T.nfc(c) for c in ckpt["classes"]]
    model_name = ckpt.get("model_name", "mobilenet_v2")
    img_size = ckpt.get("img_size", 224)

    print(f"모델 파일  : {ckpt_path}")
    print(f"  구조     : {model_name}")
    print(f"  입력크기 : {img_size}px")
    print(f"  클래스   : {class_names}")
    if "best_epoch" in ckpt:
        print(f"  학습정보 : best {ckpt['best_epoch']}에폭 / "
              f"val F1 {ckpt.get('best_val_f1', 0):.3f} / "
              f"동결 {ckpt.get('freeze_mode', '?')}")

    # train.py 의 전처리가 이 모델의 해상도를 쓰도록 맞춘다
    T.IMG_SIZE = img_size
    transform = T.build_transforms()["val"]

    model, _ = T.build_model(model_name, len(class_names), pretrained=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model = model.to(device)
    model.eval()

    # ---- 데이터 ----
    dataset = RealWorldDataset(test_dir, class_names, transform)
    loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0)

    counts = {c: 0 for c in class_names}
    for _, label in dataset.samples:
        counts[class_names[label]] += 1
    print(f"\n평가 사진  : {test_dir}")
    print("  " + " / ".join(f"{c} {n}장" for c, n in counts.items()) + f"  (총 {len(dataset)}장)")
    if len(dataset) < 20:
        print("  [주의] 사진이 적어서 점수가 크게 흔들립니다. 클래스당 10장 이상을 권장합니다.")

    # ---- 평가 (train.py 와 완전히 동일한 분석) ----
    use_tta = not args.no_tta
    print(f"\n{'='*60}")
    print(f"실사 평가 {'(TTA 적용 — 실제 서비스와 같은 조건)' if use_tta else '(TTA 없음)'}")
    print("="*60)

    Path(args.report_dir).mkdir(parents=True, exist_ok=True)
    result = T.analyze_errors(model, loader, class_names, device,
                              args.report_dir, use_tta=use_tta, title="실사")

    print(f"\n분석 결과는 {Path(args.report_dir).resolve()} 폴더에 있습니다.")
    print("  검증셋 결과(report/)와 나란히 비교해보세요.")
    print("  두 점수가 비슷하면 AI Hub 사진으로 배운 게 실제 사진에도 통한다는 뜻입니다.")
    print("  실사 점수만 크게 낮으면, 사진 환경 차이(domain gap)가 남아있는 것입니다.")

    return result


if __name__ == "__main__":
    main()
