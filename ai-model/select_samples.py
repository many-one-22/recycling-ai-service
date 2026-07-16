"""
select_samples.py - 유리병 하위 폴더(맥주병, 소주병 등)에서
종류별로 균등하게, 같은 개체 연속촬영본은 피해서 총 N장을 샘플링

사용 예시:
    python select_samples.py --root ./유리병 --out ./selected_100 --total 100
"""

import argparse
import os
import shutil
from pathlib import Path


def list_subtype_folders(root: Path):
    """유리병 폴더 바로 아래의 하위 폴더(맥주병, 소주병...) 목록"""
    return [p for p in root.iterdir() if p.is_dir()]


def collect_jpgs(folder: Path):
    """폴더 내 모든 jpg를 정렬해서 반환 (정렬 기준: 파일명)
    같은 개체 연속촬영본은 보통 파일명이 순서대로 붙어있으므로,
    정렬 후 일정 간격으로 뽑으면 여러 개체에 걸쳐 고르게 분산됨
    """
    files = sorted(folder.rglob("*.jpg"))
    return files


def sample_evenly(files, n: int):
    """정렬된 리스트에서 n개를 균등 간격으로 샘플링 (연속촬영본 몰림 방지)"""
    if len(files) <= n:
        return files
    step = len(files) / n
    return [files[int(i * step)] for i in range(n)]


def main():
    parser = argparse.ArgumentParser(description="유리병 이미지 균등 샘플링")
    parser.add_argument("--root", type=str, required=True, help="유리병 폴더 경로")
    parser.add_argument("--out", type=str, default="./selected_100", help="결과 저장 폴더")
    parser.add_argument("--total", type=int, default=100, help="최종 뽑을 총 장수")
    args = parser.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    subtypes = list_subtype_folders(root)
    if not subtypes:
        print(f"경고: {root} 아래에 하위 폴더가 없습니다. root 경로를 확인하세요.")
        return

    per_subtype = args.total // len(subtypes)
    remainder = args.total % len(subtypes)

    print(f"발견된 종류: {[s.name for s in subtypes]}")
    print(f"종류당 기본 {per_subtype}장씩, 나머지 {remainder}장은 앞쪽 종류에 1장씩 추가")

    selected_count = 0
    for i, subtype in enumerate(subtypes):
        quota = per_subtype + (1 if i < remainder else 0)
        files = collect_jpgs(subtype)
        if not files:
            print(f"  {subtype.name}: jpg 없음, 건너뜀")
            continue

        picked = sample_evenly(files, quota)
        for f in picked:
            # 파일명 충돌 방지를 위해 종류명 접두어 붙임
            dest = out_dir / f"{subtype.name}_{f.name}"
            shutil.copy2(f, dest)
            selected_count += 1

        print(f"  {subtype.name}: 전체 {len(files)}장 중 {len(picked)}장 선택")

    print(f"\n완료: 총 {selected_count}장을 {out_dir}에 저장했습니다.")


if __name__ == "__main__":
    main()