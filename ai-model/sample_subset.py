"""
sample_subset.py - 이미 모아둔 카테고리별 대량 데이터(예: 2000장)에서
지정한 개수(예: 200장)만 균등 간격으로 뽑아 별도 폴더로 복사

원본은 그대로 두고 복사만 하므로, 나중에 규모를 다시 늘리고 싶을 때
원본 2000장 폴더가 그대로 남아있어 재사용 가능함.

사용 예시:
    python sample_subset.py --src data/processed --dest data/processed_200 --n 200
"""

import argparse
import shutil
from pathlib import Path


def sample_evenly(files, n):
    if len(files) <= n:
        return files
    step = len(files) / n
    return [files[int(i * step)] for i in range(n)]


def main():
    parser = argparse.ArgumentParser(description="카테고리별 폴더에서 N장씩 균등 샘플링")
    parser.add_argument("--src", type=str, required=True, help="원본 폴더 (카테고리별 하위 폴더 포함)")
    parser.add_argument("--dest", type=str, required=True, help="결과 저장 폴더")
    parser.add_argument("--n", type=int, required=True, help="카테고리당 뽑을 이미지 수")
    args = parser.parse_args()

    src = Path(args.src)
    dest = Path(args.dest)

    categories = [d for d in src.iterdir() if d.is_dir()]
    print(f"발견된 카테고리: {[c.name for c in categories]}")

    for category in categories:
        files = sorted(list(category.glob("*.jpg")) + list(category.glob("*.jpeg")))
        picked = sample_evenly(files, args.n)

        out_dir = dest / category.name
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in picked:
            shutil.copy2(f, out_dir / f.name)

        print(f"  {category.name}: {len(files)}장 중 {len(picked)}장 → {out_dir}")

    print(f"\n완료. {dest} 를 학습 스크립트의 input_folder로 사용하세요.")


if __name__ == "__main__":
    main()