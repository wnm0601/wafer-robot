# 웨이퍼 대차 — 주행 UI · 카메라 · LiDAR

**2026-10-15 최신 실행본은 [current/](current/)입니다.** 기존 모터 펌웨어·Python 제어 코드는 바이트 그대로 보존하고, 새 UI·센서 점검·학습 준비 코드를 함께 정리했습니다.

> 시간 주행은 정확한 거리/각도를 보장하지 않습니다. 센서 점검은 모터와 연결되지 않았고 자동 주차·장애물 정지 기능이 아닙니다. 설치/메뉴 실행은 Arduino 업로드를 하지 않습니다.

## 빠른 시작

Windows Python 3.13 64bit(Tcl/Tk 포함)가 필요합니다. 저장소를 clone하거나 ZIP을 완전히 압축 해제한 뒤 루트의 PowerShell에서:

```powershell
cd .\current
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\launch.cmd preview
```

카메라/YOLO/학습을 사용하려면 `requirements-vision.txt`도 설치하고 [모델 배치 안내](current/MODELS.md)를 따라 기존 신뢰할 수 있는 모델을 복사하세요. **공개 저장소에는 학습 가중치가 포함되지 않습니다.** 모의 화면과 주행 UI는 모델 없이 사용할 수 있습니다.

## 바로 실행 — current 폴더에서

| 명령 | 기능 | 실장치 동작 |
|---|---|---|
| `.\launch.cmd` | 번호 선택 메뉴 | 선택 전 없음 |
| `.\launch.cmd drive` | 최신 주행 메인 UI | 처음에는 미연결; 실차 연결 후 조작 시 출력 가능 |
| `.\launch.cmd preview` | 주행 모의 전용 | 실제 COM 연결 차단 |
| `.\launch.cmd camera` | YOLO·중앙 픽셀 오차 | 시작 버튼으로 카메라 수신, 모터 없음 |
| `.\launch.cmd sensors` | 카메라+LiDAR 점검 | 센서 수신 자동 시작, 모터 없음 |
| `.\launch.cmd demo` | 센서 모의 화면 | 장치 없음 |
| `.\launch.cmd train-init` / `train-check` | 학습 폴더 준비 / 검사 | 실제 학습·장치 연결 없음 |

## 상세 문서

- [UI·센서·기록·학습 사용법](current/USAGE.md)
- [모델 파일 위치와 복원](current/MODELS.md)
- [현재 상태와 검증·미검증 사항](current/STATUS.md)
- [작업 인수인계](current/HANDOFF.md)
- [소스 출처](imports/README.md) · [보존 파일 SHA256](current/SOURCE_MANIFEST.json)

## 기능과 제한

- W/S 전후, A/D 회전, Z/C 좌우 평행: 누르는 동안 명령 전송, Space 정지입니다.
- 수동 출력 5~40%, 5% 단위, 기본 10%. 정지 중에만 변경하며 실측 속도가 아닙니다.
- 순서 주행은 20% 고정입니다. 직진 m·회전 도·평행이동 초를 버튼으로 추가합니다.
- 직진 약 8.54371초/m, 회전 45°/초는 참고 환산값입니다. 바닥·하중·배터리에 따라 직접 재측정해야 합니다.
- 6방향 명령 시간·CSV·앱 창 녹화·정적 CAD 미리보기를 제공합니다.
- 카메라는 기존 6종 YOLO 모델과 Full HD 영상을 사용합니다. 회색 판 학습은 데이터 미준비입니다.
- LiDAR는 COM3 / X4 방식 128000bps 수신 확인 기록이 있습니다. 정확한 모델명·센서 좌표 보정은 미확정입니다.
- 2026-10-14 마지막 30초 109표본: 카메라/검출/선택 구간 모두 유효, 거리 504~506mm. **상자와 아래 원통 중 어느 표면인지, 실제 정확도·이동량 추종은 미검증입니다.**
- 보존 펌웨어는 ENC A상만 사용하고 B상은 사용하지 않습니다. 전원 감시도 비활성 상태입니다. 정밀 거리/각도 폐루프 제어나 안전 인증 장치가 아닙니다.

## 과거 진단본과 혼용 금지

루트 START.cmd, firmware/, src/, scripts/는 **2026-10-10 과거 진단본**입니다. 현재 실행은 current/launch.cmd를 사용하세요. 과거 CART_2/ARM과 최신 plain-text M/P/V 프로토콜은 호환되지 않습니다.

[과거 README](docs/LEGACY_MANUAL_20261010.md) 및 README_FIRST.md는 당시 기록입니다. FILE_MANIFEST.json도 최초 전달본 기준입니다. 과거 자료를 삭제하거나 Git 이력을 변경하지 않았습니다.

이번 추가분에는 현장 사진·녹화·원시 CSV·학습 데이터·가중치·CAD 원본·빌드 결과·가상환경을 넣지 않았습니다. 기술용 CAD 정적 PNG만 포함했습니다. 기존 커밋에 이미 있는 자료는 이번 배포 제외 정책과 별개입니다.
