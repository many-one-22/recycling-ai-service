"""
prepare_category.py - tar 압축 해제부터 카테고리별 N장 선정까지 한 번에 처리

동작 순서:
    1. tar 파일 압축 해제
    2. 해제된 폴더 안에서 --category 이름과 정확히 일치하는 폴더를 자동으로 탐색
    3. 그 안의 분할 압축(.zip.part0, .part1...)을 자동으로 찾아서 순서대로 병합 후 압축 해제
       (일반 .zip 파일도 그냥 처리됨)
    4. 하위에 맥주병/소주병처럼 세부 폴더가 있으면 폴더별로 균등 배분,
       세부 폴더 없이 사진이 바로 있으면 전체에서 균등 간격 샘플링
    5. 최종 선정된 사진을 --dest 경로로 복사

사용 예시:
    python3 ai-model/prepare_category.py --tar "data/processed/유리병/download.tar" "data/processed/유리병/download (1).tar" "data/processed/유리병/download (2).tar" "data/processed/유리병/download (3).tar" "data/processed/유리병/download (4).tar" "data/processed/유리병/download (5).tar" "data/processed/유리병/download (6).tar" "data/processed/유리병/download (7).tar" --category 유리병 --dest "data/processed/유리병" --total 2000
    python3 ai-model/prepare_category.py --tar "data/processed/비닐/download.tar" "data/processed/비닐/download (1).tar" "data/processed/비닐/download (2).tar" "data/processed/비닐/download (3).tar" "data/processed/비닐/download (4).tar" "data/processed/비닐/download (5).tar" "data/processed/비닐/download (6).tar" --category 비닐 --dest "data/processed/비닐" --total 2000
"""

import argparse
import re
import shutil
import tarfile
import zipfile
from pathlib import Path


def extract_tars(tar_paths: list, extract_to: Path):
    extract_to.mkdir(parents=True, exist_ok=True)
    print(f"[1/5] tar 파일 {len(tar_paths)}개 압축 해제 중...")
    for tar_path in tar_paths:
        print(f"      해제 중: {tar_path.name}")
        with tarfile.open(tar_path) as tf:
            tf.extractall(extract_to)
    print(f"      전체 완료 → {extract_to}")


def find_category_folders(root: Path, category: str) -> list:
    print(f"[2/5] '{category}' 폴더 탐색 중...")
    matches = [p for p in root.rglob("*") if p.is_dir() and p.name == category]
    if not matches:
        raise FileNotFoundError(
            f"'{category}' 이름의 폴더를 찾지 못했습니다. "
            f"tar 안의 실제 폴더명을 확인해주세요 (예: 종이팩 vs 종이 등 이름 차이 가능)."
        )
    print(f"      {len(matches)}개 발견 (여러 tar에서 나온 것 모두 합쳐서 사용):")
    for m in matches:
        print(f"        - {m}")
    return matches


def merge_and_extract_zip_parts(category_folder: Path):
    print("[3/5] 분할 압축 병합 및 해제 중...")
    part_pattern = re.compile(r"^(.*)\.zip\.part(\d+)$")

    # 분할 파일들을 base 이름 기준으로 그룹핑
    groups = {}
    for f in category_folder.rglob("*.zip.part*"):
        m = part_pattern.match(f.name)
        if not m:
            continue
        base_name = m.group(1)
        key = (f.parent, base_name)
        groups.setdefault(key, []).append(f)

    for (parent, base_name), parts in groups.items():
        parts_sorted = sorted(parts, key=lambda p: int(part_pattern.match(p.name).group(2)))
        merged_zip = parent / f"{base_name}.zip"
        print(f"      병합: {base_name} ({len(parts_sorted)}개 파트)")
        with open(merged_zip, "wb") as out:
            for part in parts_sorted:
                out.write(part.read_bytes())
        try:
            with zipfile.ZipFile(merged_zip) as zf:
                zf.extractall(parent)
            print(f"      압축 해제 완료: {base_name}")
        except zipfile.BadZipFile:
            print(f"      경고: {base_name}.zip 손상됨 (다운로드 재확인 필요), 건너뜀")

    # 병합 없이 바로 있는 일반 .zip 파일도 처리
    for f in category_folder.rglob("*.zip"):
        if f.name.endswith(tuple(f"{k[1]}.zip" for k in groups.keys())):
            continue  # 이미 처리한 병합 zip
        try:
            with zipfile.ZipFile(f) as zf:
                zf.extractall(f.parent)
            print(f"      압축 해제 완료(단일 zip): {f.name}")
        except zipfile.BadZipFile:
            print(f"      경고: {f.name} 손상됨, 건너뜀")

    if not groups:
        print("      분할 압축 없음, 건너뜀")


def sample_evenly(files, n: int):
    if len(files) <= n:
        return files
    step = len(files) / n
    return [files[int(i * step)] for i in range(n)]


def select_images(category_folders: list, total: int):
    print(f"[4/5] 이미지 선정 중 (목표 {total}장, {len(category_folders)}개 폴더 통합)...")

    # 모든 카테고리 폴더에서 "그룹"(세부 폴더 또는 폴더 자체)을 전부 수집
    groups = []  # [(그룹이름, 그룹내jpg파일목록)]
    for category_folder in category_folders:
        subdirs = [
            d for d in category_folder.iterdir()
            if d.is_dir() and (any(d.rglob("*.jpg")) or any(d.rglob("*.jpeg")))
        ]
        if subdirs:
            for d in subdirs:
                files = sorted(list(d.rglob("*.jpg")) + list(d.rglob("*.jpeg")))
                groups.append((d.name, files))
        else:
            files = sorted(list(category_folder.rglob("*.jpg")) + list(category_folder.rglob("*.jpeg")))
            if files:
                groups.append((category_folder.parent.name, files))

    if not groups:
        raise RuntimeError("이미지를 하나도 찾지 못했습니다. 압축 해제가 제대로 됐는지 확인해주세요.")

    total_found = sum(len(files) for _, files in groups)
    print(f"      통합된 그룹 {len(groups)}개, 전체 이미지 {total_found}장 확보")

    per_group = total // len(groups)
    remainder = total % len(groups)

    selected = []
    for i, (name, files) in enumerate(groups):
        quota = per_group + (1 if i < remainder else 0)
        picked = sample_evenly(files, quota)
        selected.extend([(name, f) for f in picked])
        print(f"      {name}: {len(files)}장 중 {len(picked)}장 선택")

    return selected


def copy_to_dest(selected, dest: Path):
    print(f"[5/5] {dest} 로 복사 중...")
    dest.mkdir(parents=True, exist_ok=True)
    for prefix, f in selected:
        name = f"{prefix}_{f.name}"
        # 파일명 중복 방지 (다른 tar에서 같은 이름의 파일이 나올 수 있음)
        dest_path = dest / name
        counter = 1
        while dest_path.exists():
            dest_path = dest / f"{prefix}_{counter}_{f.name}"
            counter += 1
        shutil.copy2(f, dest_path)
    print(f"      완료: 총 {len(selected)}장 저장됨")


def main():
    parser = argparse.ArgumentParser(description="tar 해제부터 카테고리별 이미지 선정까지 일괄 처리")
    parser.add_argument(
        "--tar", type=str, required=True, nargs="+",
        help="다운받은 tar 파일 경로 (여러 개면 공백으로 구분해서 나열)"
    )
    parser.add_argument("--category", type=str, required=True, help="카테고리 폴더명 (예: 유리병, 비닐)")
    parser.add_argument("--dest", type=str, required=True, help="최종 선정 이미지 저장 경로")
    parser.add_argument("--total", type=int, default=2000, help="선정할 이미지 수 (기본 2000)")
    parser.add_argument("--work-dir", type=str, default="./_extract_tmp", help="압축 해제 작업 폴더")
    args = parser.parse_args()

    tar_paths = [Path(t).expanduser() for t in args.tar]
    work_dir = Path(args.work_dir).expanduser()
    dest = Path(args.dest).expanduser()

    extract_tars(tar_paths, work_dir)
    category_folders = find_category_folders(work_dir, args.category)
    for folder in category_folders:
        merge_and_extract_zip_parts(folder)
    selected = select_images(category_folders, args.total)
    copy_to_dest(selected, dest)

    print(f"\n완료! {dest} 에서 결과 확인하세요.")
    print(f"(작업 폴더 {work_dir} 는 확인 후 삭제해도 됩니다: rm -rf {work_dir})")


if __name__ == "__main__":
    main()