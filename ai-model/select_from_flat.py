"""
select_from_flat.py - 하위 폴더 구분 없이 섞여있는 review_glass 폴더에서
균등 간격으로 N장을 샘플링 (한쪽에 몰리지 않도록 정렬 후 간격 추출)

사용 예시:
    python select_from_flat.py --src ./review_glass --out ./selected_100 --total 100
"""

import argparse
import shutil
from pathlib import Path


def sample_evenly(files, n: int):
    if len(files) <= n:
        return files
    step = len(files) / n
    return [files[int(i * step)] for i in range(n)]


def main():
    parser = argparse.ArgumentParser(description="flat 폴더에서 균등 샘플링")
    parser.add_argument("--src", type=str, required=True, help="review_glass 폴더 경로")
    parser.add_argument("--out", type=str, default="./selected_100", help="결과 저장 폴더")
    parser.add_argument("--total", type=int, default=100)
    args = parser.parse_args()

    src = Path(args.src)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(src.glob("*.jpg"))
    print(f"전체 발견된 이미지: {len(files)}장")

    if len(files) == 0:
        print("경고: jpg 파일을 찾지 못했습니다. --src 경로를 확인하세요.")
        return

    picked = sample_evenly(files, args.total)
    for f in picked:
        shutil.copy2(f, out_dir / f.name)

    print(f"완료: {len(picked)}장을 {out_dir}에 저장했습니다.")
    if len(files) < args.total:
        print(f"주의: 전체 이미지가 {args.total}장보다 적어서, 있는 {len(files)}장을 전부 사용했습니다.")


if __name__ == "__main__":
    main()