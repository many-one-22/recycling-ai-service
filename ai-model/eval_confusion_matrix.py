# -*- coding: utf-8 -*-
"""
eval_confusion_matrix.py - (더 이상 쓰지 않음)

이 스크립트는 train.py / eval_real_world.py 로 통합되었습니다.

왜 없앴나
    예전 버전에는 조용히 틀린 점수를 내는 문제가 세 가지 있었습니다.
      1) pad_to_square(정사각형 패딩)가 빠져 있어서 비율이 찌그러진 채로 평가했다
      2) 입력 크기가 224 로 박혀 있어서, 320 으로 학습한 모델을 224 로 평가했다
      3) 모델이 mobilenet_v2 로 박혀 있어서 다른 모델은 불러올 수 없었다
    셋 다 에러가 나지 않고 '낮은 점수'만 나오기 때문에
    모델이 나쁜 줄로 오해하기 딱 좋았습니다.

무엇을 대신 쓰나
    검증셋(AI Hub 사진) 분석:
        cd ai-model
        python train.py --analyze-only best_recycling_model.pth
        -> ai-model/report/ 에 혼동행렬 + 오분류 목록 + 오분류 사진 저장

    우리가 직접 찍은 사진 분석:
        cd ai-model
        python eval_real_world.py
        -> ai-model/report_realworld/ 에 같은 형식으로 저장

    아무 폴더나 평가하고 싶을 때 (클래스별 하위 폴더 구조면 됨):
        python eval_real_world.py --test-dir ./원하는폴더

    둘 다 체크포인트에 저장된 입력 크기/모델 구조를 읽어서 쓰므로
    학습과 평가가 어긋날 일이 없습니다.
"""

import sys

MESSAGE = __doc__


if __name__ == "__main__":
    print(MESSAGE)
    sys.exit(
        "이 스크립트는 더 이상 동작하지 않습니다. 위 안내의 명령을 사용하세요."
    )
