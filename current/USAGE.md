# 최신 실행·사용 안내

저장소를 완전히 압축 해제한 뒤 current 폴더에서 실행합니다. 각 모듈 README는 원래 작업 당시 기록을 포함하므로 현재 실행법은 이 문서, 최신 검증은 STATUS.md를 우선 확인하세요.

## 1. 설치

Windows Python 3.13 64bit(Tcl/Tk 포함) 기준입니다.

```powershell
cd .\current
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
# YOLO/학습 사용 시 추가합니다.
.\.venv\Scripts\python.exe -m pip install -r requirements-vision.txt
.\launch.cmd
```

실행 메뉴는 current/.venv → py -3 → python 순서로 선택합니다. 패키지 설치는 자동으로 하지 않습니다. 기존 Python 환경을 쓰는 경우 해당 환경에 같은 의존성이 있어야 합니다. GPU는 대상 PC에 맞는 PyTorch/드라이버 확인이 필요하며, 원래 PC의 CUDA 13.0 성공과 신규 설치 성공은 별개입니다.

## 2. 주행 UI

```powershell
.\launch.cmd drive
# 실차 선택이 차단된 화면 확인:
.\launch.cmd preview
```

1. 먼저 모의 연결로 버튼과 정지 동작을 확인합니다.
2. 실차는 다른 모터 프로그램·시리얼 모니터 종료, 모터 전원 OFF 상태에서 배선·받침대·퓨즈·물리 차단 수단·주변을 확인합니다.
3. 실차 COM 선택 → 현재 Arduino 포트 입력 → 안전 확인 → 연결 순서입니다. COM7은 원래 PC 기록이며 고정값이 아닙니다.
4. INFO 표식 MECANUM_HKX_REVIEW_20261012를 검사합니다. 불일치하면 과거 펌웨어를 임의로 업로드하지 말고 담당자와 확인하세요.
5. 모든 키를 놓고 입력 대기를 확인합니다. 동력 투입은 현장 담당자가 판단합니다.
6. W 전진 / S 후진 / A 좌회전 / D 우회전 / Z 왼쪽 평행 / C 오른쪽 평행입니다. 키나 버튼 하나를 누르는 동안 명령을 보냅니다.
7. Space는 정지, Esc/X/Q/E 또는 빨간 버튼은 즉시 정지 명령을 시도하고 연결을 종료합니다. 소프트웨어 정지는 물리 차단을 대체하지 않습니다.
8. 창·탭 전환, 다중 방향 입력, 통신 오류는 정지/중단을 일으킬 수 있습니다. 키를 모두 놓고 새로 눌러야 합니다.

### 출력과 주행별 시간

- 키보드 수동 → 주행별 시간 · 6방향 탭 → 5~40%를 5% 단위로 선택 → 정지 중 적용입니다. 기본 10%이며 선택만 바꾸면 적용되지 않습니다.
- 하단 +/- 및 [ / ]도 정지 상태에서 사용합니다. 출력 %는 실측 속도·전류 제한이 아닙니다.
- 방향별 명령 시간·출력·모의/실차를 기록합니다. 실제 바퀴의 움직임 시작/종료 시간이나 실제 거리 자동 계측이 아닙니다.
- 1m는 같은 차체 기준점으로 표시한 출발선/도착선을 직접 확인합니다. F8은 대기, W 전진 중 F9는 도착 기록입니다. **F9는 정지 명령이 아닙니다.**
- 연결 종료 후 CSV 저장을 누르세요. 정상 종료 시에도 미저장 주행 기록을 저장하지만 강제 종료는 보장하지 않습니다. 최근 500건을 유지합니다.

### 버튼형 순서 주행

미연결 상태 → 순서 주행 20% → 동작 순서 탭 → 직진/좌회전/우회전/왼쪽 평행/오른쪽 평행 → 동작 추가 → 입력 검사 / 시간 환산 → 모의 확인 후 실행 순서입니다.

| 동작 | 입력 | 환산 기준 |
|---|---|---|
| 직진 | 0.1~5m | 초/m를 직접 설정, 참고 약 8.54371초/m |
| 좌/우회전 | 5~180° | 사용자 관찰값 20%에서 45°=1초, 90°=2초 |
| 좌/우 평행 | 구간별 0.5~60초 | 거리 환산 없음 |

구간 시간 0.5~60초, 전체 최대 20구간·구동 합계 120초, 출력 20% 고정입니다. 정지 대기 시간은 별도입니다. 각 구간 종료 후 정지 응답/ENC 정지 대기를 거치지만 물리 정지의 독립 검증은 아닙니다. Space·창/탭 전환·오류·연결 종료는 남은 순서를 취소하고 자동 재개하지 않습니다.

측정 평균을 자동 적용하지 않습니다. 같은 출력·바닥·하중·배터리 조건의 직접 확인한 기록으로 초/m를 정하세요. 정확한 m/각도 도착이나 장애물 회피를 보장하지 않습니다.

### 저장 위치 — current 기준

| 기능 | 위치 | 주의 |
|---|---|---|
| 주행 CSV | cart-manual-ui/logs/travel_*.csv | 연결 종료 후 저장, 방향·명령 시간 |
| 순서 CSV | cart-manual-ui/logs/sequence_*.csv | 구간·명령·정지 응답 |
| 회전 CSV | cart-manual-ui/logs/rotation_*.csv | 회전 명령 시간 |
| 화면 녹화 | cart-manual-ui/recordings/cart_screen_*.avi | 녹화 시작 → 중지/저장 |
| 센서 CSV | cart-sensor-check/logs/sensor_check_*.csv | 종료 전에 수치 CSV 저장 |

녹화는 앱 창만, 무음 MJPG AVI, 기준 5fps, 최대 30분입니다. 전체 데스크톱/마이크는 캡처하지 않습니다. 최소화·창 종료·캡처 실패 시 종료하며 강제 종료 시 저장이 불완전할 수 있습니다. CAD는 정적 참고 PNG이며 현재 위치나 실시간 3D가 아닙니다.

## 3. 카메라 단독 · YOLO

MODELS.md의 모델 배치 후 `.\launch.cmd camera`를 실행합니다. 다른 카메라 앱 종료 → 번호 확인(기존 StreamCam 0) → 카메라 시작 → YOLO 박스 클릭 순서입니다.

- Full HD 1920×1080/30fps를 요청하고 실제 수신 크기를 별도로 표시합니다. 느리면 종료 후 HD로 낮추세요. F11은 크게 보기, Esc는 복원입니다. 광학 시야각이 늘어나는 기능은 아닙니다.
- X/Y는 픽셀 오차이며 mm 이동량이 아닙니다. 중앙 일치는 주차 완료가 아닙니다.
- 전진/후진 안내는 대차 왼쪽 정측면 바깥을 직립으로 보는 조건을 확인한 경우만 사용합니다. 반전되지 않은 영상에서 표적이 오른쪽이면 전진, 왼쪽이면 후진입니다.
- **현재처럼 아래로 기울인 장착은 기존 방향 안내의 검증 범위 밖입니다.** 현장 검증 전에는 위치 표시로만 사용하세요.
- 세로 오차로 평행이동/회전을 결정하지 않습니다. 상실·중복·잘림·오래된 영상·동일 영상 반복 시 안내를 중지합니다.
- 모터/COM 연결이 없습니다. 색상 클릭은 선명한 빨강/파랑 등만 지원하며 회색 판 학습을 대신하지 못합니다.

## 4. 카메라 + LiDAR 점검

```powershell
.\launch.cmd sensors
# 장치 없는 합성 화면:
.\launch.cmd demo
```

센서 모드는 두 센서 수신을 자동 시작합니다. 카메라/라이다를 쓰는 다른 창은 먼저 닫으세요. Arduino/모터 포트는 열지 않습니다.

1. 왼쪽 YOLO 박스를 클릭해 표적 종류를 선택합니다.
2. 오른쪽 점군에서 점을 클릭하거나 방위·각도폭·중심거리·거리폭 입력 후 구간 적용합니다.
3. 노란 점은 선택 구간입니다. **카메라 박스와 자동 대응하지 않습니다.**
4. 기준 거리 잡기 후 물체를 옮겨 변화·최근 3초 변화폭·그래프를 확인합니다. 구간 밖이면 무효이며 자동 재추적하지 않습니다.
5. 종료 전에 수치 CSV 저장을 누릅니다. 최근 최대 6000행이며 센서 CSV는 종료 시 자동 저장하지 않습니다. 영상은 저장하지 않습니다.

거리 기준은 LiDAR 원점→측정점입니다. 차체-테이블 간격이나 FOUP 정렬 오차가 아닙니다. 0.35초 지난 점/0거리점은 제외하고 3점 미만 또는 구간 내부 거리폭 20cm 초과면 무효입니다. 원시 각도이며 삼각측량 각도 보정·카메라 좌표 보정은 아직 없습니다.

현재 확인한 CP210x VID 10C4 / PID EA60 / serial 0001만 허용하고 COM7은 거부합니다. 다른 어댑터/COM 배치에서는 제한 때문에 시작되지 않을 수 있습니다. 모터 포트인지 먼저 확인한 뒤 별도 변경·검증을 받아야 합니다. COM3 / 128000bps X4 방식 수신 기록은 정확한 하드웨어 모델명 확정과 구분합니다.

### 남은 동일 표적 검사

대차는 움직이지 않고 빨간 상자만 치웠다 놓고, 아래 원통은 유지하세요. 카메라 검출과 LiDAR 선택 구간이 함께 사라지고 돌아오는지 비교합니다. 거리가 그대로면 다른 표면일 수 있습니다. 이후 기준자로 같은 센서 원점에서 거리·이동량을 비교해야 합니다. 과거의 504~506mm 안정성만으로 동일 표적이나 정확도를 확정하지 않습니다.

## 5. 회색 판 학습

```powershell
.\launch.cmd train-init
.\launch.cmd train-check
.\.venv\Scripts\python.exe -B .\gray-panel-training\train_gray_panel.py train --epochs 100 --batch 8 --device auto --name gray_panel_v1
.\.venv\Scripts\python.exe -B .\gray-panel-training\train_gray_panel.py validate --weights .\gray-panel-training\runs\train\gray_panel_v1\weights\best.pt --split test --name gray_panel_test_v1
```

init은 설치 위치에 맞는 data.yaml과 빈 폴더를 만듭니다. 기존 PC 절대경로 data.yaml은 배포하지 않았습니다. 실제 데이터가 없으면 check/train은 중단하며 정상입니다. dataset/images 및 labels의 train/val/test를 촬영 세션별로 분리하고 같은 이름의 .txt에 `0 x중심 y중심 폭 높이`(0~1)를 기록합니다.

상세 라벨 준비는 gray-panel-training/README.md를 확인하세요. 새 결과는 덮어쓰지 않고 모델을 자동 적용하지 않습니다. 카메라 단독 창에서 선택해 확인합니다. 학습 중 실차 주행은 하지 마세요.

## 6. 무구동 검사

아래는 current 폴더 기준입니다. 실제 장치를 열지 않지만 테스트용 Tk 창은 잠깐 생길 수 있습니다.

```powershell
Push-Location .\cart-manual-ui
..\.venv\Scripts\python.exe -B -m unittest -q test_travel_log test_adapter test_timed_drive
Pop-Location
Push-Location .\cart-target-preview
..\.venv\Scripts\python.exe -B -m unittest -q test_preview
Pop-Location
Push-Location .\cart-sensor-check
..\.venv\Scripts\python.exe -B -m unittest -q test_app
Pop-Location
Push-Location .\gray-panel-training
..\.venv\Scripts\python.exe -B -m unittest -q test_training
Pop-Location
Push-Location .\ROBOT-motor-review-928b2a8
..\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_manual_motor_safety.py -q
Pop-Location
```

펌웨어는 보존 소스이며 자동 업로드하지 않습니다. platformio.ini의 COM3는 과거 설정이며 현재 원래 PC에서는 LiDAR 포트였습니다. **포트 확인 없이 upload를 실행하지 마세요.**
