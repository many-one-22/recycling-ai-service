import os
import shutil
import csv
import cv2
import numpy as np
from PIL import Image

def check_image_quality(image_path, min_width=1280, min_height=720, blur_threshold=80.0):
    """
    이미지 해상도 및 선명도(블러) 검사 함수
    """
    results = {
        "pass": True,
        "reasons": [],
        "width": 0,
        "height": 0,
        "blur_score": 0.0
    }
    
    # 1. PIL로 크기(해상도) 및 손상 여부 검사
    try:
        with Image.open(image_path) as img:
            img.verify()
            
        with Image.open(image_path) as img:
            width, height = img.size
            results["width"] = width
            results["height"] = height
            
            if width < min_width or height < min_height:
                results["pass"] = False
                results["reasons"].append(f"크기 미달 ({width}x{height} < 기준 {min_width}x{min_height})")
    except Exception as e:
        return {"pass": False, "reasons": [f"이미지 손상 또는 읽기 실패: {e}"], "width": 0, "height": 0, "blur_score": 0.0}

    # 2. OpenCV로 흐림(선명도) 검사 (한글 경로 지원)
    try:
        img_array = np.fromfile(image_path, np.uint8)
        cv_img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
    except Exception:
        cv_img = None

    if cv_img is None:
        results["pass"] = False
        results["reasons"].append("OpenCV 디코딩 실패")
        return results

    # 라플라시안 분산 계산 (선명도 점수)
    blur_score = cv2.Laplacian(cv_img, cv2.CV_64F).var()
    results["blur_score"] = round(blur_score, 2)
    
    if blur_score < blur_threshold:
        results["pass"] = False
        results["reasons"].append(f"이미지가 흐림 (점수: {results['blur_score']} < 기준 {blur_threshold})")

    return results


def process_dataset(source_dir, output_dir, target_count=2000):
    """
    폴더 내 이미지를 검수하여 합격작만 통과시키고 보고서를 작성하는 함수
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 이미지 확장자 목록
    valid_extensions = ('.jpg', '.JPG', '.jpeg', '.JPEG')
    
    report_data = []
    passed_count = 0

    print("🔍 이미지 품질 검수 및 수집 시작...")

    # 폴더 내 모든 파일 탐색
    for root, _, files in os.walk(source_dir):
        for file in files:
            # 목표 수량 달성 시 종료
            if passed_count >= target_count:
                print(f"\n🎉 목표 수량 {target_count}장을 모두 채웠습니다!")
                break

            file_path = os.path.join(root, file)

            # 품질 검사 실행
            quality = check_image_quality(file_path)

            # 리포트용 데이터 기록
            report_data.append({
                "file_name": file,
                "pass": quality["pass"],
                "width": quality["width"],
                "height": quality["height"],
                "blur_score": quality["blur_score"],
                "reasons": " / ".join(quality["reasons"]) if quality["reasons"] else "합격"
            })

            # 합격시 복사
            if quality["pass"]:
                passed_count += 1
                dest_path = os.path.join(output_dir, file)
                shutil.copy2(file_path, dest_path)
                print(f"[{passed_count}/{target_count}] 합격: {file} (점수: {quality['blur_score']})")

        if passed_count >= target_count:
            break

    # 3. pandas 대신 파이썬 기본 csv 모듈로 결과 리포트 저장
    report_csv_path = "selection_report.csv"
    with open(report_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        if report_data:
            writer = csv.DictWriter(f, fieldnames=report_data[0].keys())
            writer.writeheader()
            writer.writerows(report_data)

    print("\n==========================================")
    print(f"✅ 검수 완료!")
    print(f" - 총 검사한 이미지: {len(report_data)}장")
    print(f" - 최종 합격 이미지: {passed_count}장")
    print(f" - 합격 이미지 저장 경로: {output_dir}")
    print(f" - 검수 보고서 저장 완료: {report_csv_path}")
    print("==========================================")


# === 실행 파트 ===
if __name__ == "__main__":
    # 1. 원본 사진들이 들어있는 폴더 경로 (현재 작업 폴더 기준)
    SOURCE_DIRECTORY = r"C:\Users\dlagk\Downloads\232.재활용품 분류 및 선별 데이터\01-1.정식개방데이터\Training\01.원천데이터\TS_2.직접촬영_05.스티로폼_001.스티로폼_2"
    OUTPUT_DIRECTORY = r"C:\Users\dlagk\Desktop\AICOSS\ST"
    
    # 실행
    process_dataset(SOURCE_DIRECTORY, OUTPUT_DIRECTORY, target_count=2000)