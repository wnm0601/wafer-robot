# 회색 판 YOLO 학습 준비

## 현재 범위

`gray_panel` 한 종류를 사각형 박스로 검출하는 학습 코드입니다. 기존 6종 모델에 7번째 종류를 합치는 작업이 아니라 별도의 회색 판 전용 모델을 만듭니다. 기존 모터 코드·미리보기 기본 모델·학습 원본은 수정하지 않습니다. 카메라 촬영, COM 연결, 모터 구동, 모델 자동 적용은 하지 않습니다.

회색 판 사진과 정답 라벨은 아직 없습니다. 코드 준비가 학습 완료나 인식 성공을 뜻하지 않습니다. 회색이라는 색깔만으로 구별하는 방식이 아니므로 실제 판의 모양·테두리·배경·조명을 다양하게 학습해야 합니다.

## 실행 순서

PowerShell에서 아래 위치로 이동합니다. 기존 Python 환경의 ultralytics, torch, Pillow를 사용하며 이번 작업에서 패키지를 설치하거나 업데이트하지 않습니다.

```powershell
cd 'C:\Users\H\Desktop\로봇 자율주행\gray-panel-training'
$py = 'C:\Users\H\AppData\Local\Programs\Python\Python313\python.exe'
& $py -B train_gray_panel.py init
```

### 1. 실제 판 사진과 박스 라벨 준비

초기 실험 목표로 서로 다른 장면의 사진 200~400장 정도를 권장합니다. 이것은 성능을 보장하는 최소 장수가 아닙니다. 가까이/멀리, 좌우 위치, 비스듬한 각도, 밝고 어두운 환경, 실제 측면 카메라 높이에서 촬영합니다. 회색 벽·테이블·금속판처럼 혼동할 배경도 포함하세요.

사진 속 **목표 회색 판 전체**를 둘러싼 사각형을 표시해 YOLO detection 라벨로 내보냅니다. 같은 사진에 판이 여러 개면 전부 표시합니다. 판이 없다는 것을 확인한 배경 사진만 빈 `.txt` 라벨로 둡니다. 라벨이 없으면 자동으로 배경 처리하지 않고 중단합니다. 현재 도구에는 촬영/마우스 라벨링 창이 포함되어 있지 않습니다.

```text
dataset/
  data.yaml
  images/train/scene01.jpg
  labels/train/scene01.txt
  images/val/scene02.jpg
  labels/val/scene02.txt
  images/test/scene03.jpg
  labels/test/scene03.txt
```

라벨 한 줄: `0 x중심 y중심 폭 높이`. 좌표는 사진 폭/높이로 나눈 0~1 값입니다. 예시 `0 0.5 0.5 0.4 0.6`은 중앙에 있는 폭 40%, 높이 60% 박스이며 실제 사진을 보고 작성해야 합니다. 예시 값을 모든 사진에 복사하지 마세요.

촬영 세션별로 대략 train 70% / val 20% / test 10%로 분리하세요. 같은 동영상의 인접 프레임이 여러 분할로 섞이면 성능이 부풀려집니다. 파일명만 다른 동일 픽셀은 코드가 차단하지만 비슷한 장면까지 자동 판별하지는 않습니다. test는 학습/튜닝에 사용하지 않고 마지막 확인용으로 보관합니다.

### 2. 데이터 검사

```powershell
& $py -B train_gray_panel.py check
```

빈 데이터, 손상 사진, 누락/짝 없는 라벨, 잘못된 클래스/좌표, 화면 밖 박스, EXIF 회전, 중복 사진을 검사합니다. 박스가 실제 판을 정확히 둘러싸는지는 사람이 확인해야 합니다.

### 3. 학습

```powershell
& $py -B train_gray_panel.py train --epochs 100 --batch 8 --device auto --name gray_panel_v1
```

기존 로컬 `object_detection_training/yolo11n.pt` 검출 모델을 시작점으로 사용합니다. 기존 6종 `best.pt`는 segmentation 모델이므로 이 사각형 라벨 학습에는 사용하지 않습니다. GPU가 없으면 CPU로 실행하며 시간이 오래 걸릴 수 있습니다. GPU 메모리 부족 시 `--batch 2`, GPU 실행 문제가 있으면 `--device cpu`로 재실행하세요. 결과 이름은 매번 다르게 지정합니다. 기존 결과는 덮어쓰지 않습니다. AMP 부가 모델 확인을 피하도록 `amp=False`, Windows 호환성을 위해 `workers=0`을 사용합니다.

결과 위치: `runs/train/gray_panel_v1/weights/best.pt`. 학습이 실제 성공한 뒤에만 만들어집니다.

### 4. 학습에 쓰지 않은 사진으로 평가

```powershell
& $py -B train_gray_panel.py validate --weights '.\runs\train\gray_panel_v1\weights\best.pt' --split test --name gray_panel_test_v1
```

test 사진/라벨이 없으면 중단합니다. 임시로 val 평가만 하려면 `--split val`을 지정하되 독립 테스트로 보고하지 마세요. Precision/Recall/mAP뿐 아니라 실제 설치 위치에서 판이 없을 때 오인식, 가림, 여러 판, 조명 변화도 점검해야 합니다.

### 5. 기존 중앙 오차 화면에서 확인

`cart-target-preview/start-preview.cmd` 실행 → 카메라 종료 → **기존 YOLO 모델 선택** → 위 학습 결과 `best.pt` 선택 → YOLO 모드에서 카메라 시작 → 검출 박스 클릭.

모터 연결은 없습니다. 박스 중심 오차는 픽셀 값이며 거리(mm), 판의 실제 중심, 대차 각도 또는 주차 완료를 보장하지 않습니다. 가림·비스듬한 각도에서는 박스 중심도 달라집니다. 기존 6종 모델로 돌아가려면 창을 다시 실행하거나 원래 best.pt를 선택하세요.

## 코드 검증

```powershell
& $py -B -m unittest -v test_training
```

자동 검사는 임시 합성 이미지와 가짜 학습 객체로 데이터 검사/호출 설정을 확인합니다. 실제 회색 판 학습 성능을 검증하지 않습니다.

2026-10-14: 자동 검사 15개 통과. 제한된 실행 환경의 임시 폴더 접근 거부 후 일반 환경에서 재실행했습니다. 실제 판 데이터는 아직 없으며 학습/인식률은 미검증입니다. 기존 펌웨어·수동 모터 코드·메인 UI·driver_adapter의 SHA256이 이전 기록과 동일함을 확인했습니다.

일반 환경에서 Ultralytics 8.4.90 / torch 2.11.0+cu130 및 CUDA 사용 가능 상태를 확인했습니다. 로컬 yolo11n.pt를 실제로 로드하고 합성 단색 이미지 1장에 CPU 추론을 실행했습니다(task=detect, 결과 1개, 검출 박스 0개). 이는 라이브러리/모델 호환성 검사이며 회색 판 학습이나 GPU 학습 성공 증거는 아닙니다.

## 공식 형식 참고

- [YOLO detection 데이터 형식](https://docs.ultralytics.com/datasets/detect/)
- [Ultralytics 학습 설정 및 Windows 실행](https://docs.ultralytics.com/modes/train/)
