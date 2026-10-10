# 다른 데스크탑용 대차 수동 검사 전달본

작성일: 2026-10-10 (한국 시간). 이 ZIP은 현재 수동 조작 코드의 독립 실행 전달본입니다. 기존 프로젝트를 변경하지 않고 필요한 파일을 복사했습니다. 압축 해제·메뉴 실행만으로 Arduino 업로드나 모터 구동을 하지 않습니다.

## 1. 작업 목표

다른 Windows 데스크탑에서 현재 수동 터미널/GUI, 무구동 진단, PC 모의시험, Arduino 펌웨어를 검사합니다. 카메라·ROS2·Nav2 전체 환경 이관본은 아닙니다. 현재 수동 모터 경로에는 ROS·카메라·LiDAR가 필요하지 않습니다.

## 2. 현재 환경과 가장 빠른 시작

1. ZIP을 완전히 풀어 `C:\wafer-cart-manual` 같은 쓰기 가능한 폴더에 둡니다. ZIP 내부에서 직접 실행하지 마세요.
2. Windows용 Python 3.13 64bit를 설치합니다. Python Launcher와 Tcl/Tk 옵션도 포함합니다. Python 설치 파일·패키지 캐시는 미포함이며 최초 설치에는 인터넷이 필요합니다.
3. `START.cmd`를 열고 **1번**으로 이 폴더 전용 `.venv`와 pyserial을 설치합니다. 다른 프로젝트 환경을 변경하지 않습니다.
4. 다시 `START.cmd` → **3번**으로 장치 없는 모의·단위시험을 진행합니다.
5. 모터 배터리를 분리하고 Arduino USB만 연결한 뒤 **2번**으로 새 COM 번호를 확인합니다. 다른 데스크탑에서도 COM7이라고 가정하지 마세요.
6. 조작 앱·시리얼 모니터를 모두 닫고 **4번**으로 정지 상태를 검사합니다. 모터 회전 명령은 보내지 않습니다.
7. 실제 수동 시험 준비를 확인한 후에만 **5번(터미널)** 또는 **6번(GUI)**을 선택합니다. 이 단계는 실제 출력이 가능합니다.

`START.cmd`는 해당 프로세스에만 PowerShell 실행 정책 Bypass를 적용합니다. 시스템 실행 정책이나 관리자 권한 설정은 변경하지 않습니다. 회사/학교 정책으로 차단되면 아래 Python 명령을 사용하세요.

Python/pyserial만 있으면 실제 수동 터미널·GUI·정지 진단·기본 모의시험이 가능합니다. **C++ 펌웨어 기반 가상 지도 GUI와 terminal-smoke/sim-smoke에는 WSL Ubuntu-24.04 및 g++가 추가로 필요**합니다. PlatformIO는 펌웨어 재빌드·업로드할 때만 필요합니다.

## 3. 현재까지 확인된 사항과 미확정 사항

2026-10-09 원래 PC에서 수행한 과거 실차 기록입니다. 새 데스크탑에서 통과했다는 뜻이 아닙니다.

- Mega 2560에 `mega_manual_legacy_5khz` 업로드 및 플래시 비교 검증 완료. 식별 `CART_2 HKX_20260929 MANUAL_UNMONITORED`.
- 모터 OFF에서 반복 정지 진단40회와 채널별 ±1% 명령 총8회 수락·레지스터 반영·STOP 출력0 확인.
- 전원 ON 모터 회전 성공, 실제 배선 도통·PWM 파형·드라이버 출력 전압은 미확정입니다.
- 과거의 `MOTION_REJECTED`와 `STALL_NO_ENCODER` 문제는 짧은 전원 OFF 시험만으로 해결됐다고 보증하지 않습니다.
- 전원 피드백 A8 없음. 프로그램은 실제 배터리 ON/OFF나 물리 비상정지를 직접 알지 못합니다.
- **4륜 실차 주행은 바퀴 매핑 미검증으로 잠겨 있습니다.** 현재 확실하게 제공하는 실차 조작은 한 채널씩 수동 시험입니다. 잠금을 임의로 해제하지 마세요.
- GUI·터미널의 M1=왼쪽 뒤 추정, M2=오른쪽 뒤 추정, M3=왼쪽 앞 추정, M4=오른쪽 앞 추정 표시는 검증값이 아닙니다. 사진 스티커의 M2/M4 위치와 다를 수 있으므로 번호·실제 위치를 따로 확인해야 합니다.
- 펌웨어 코드의 40% 상한은 시험 안전 승인이나 바퀴 속도40%를 뜻하지 않습니다. 이번 전달본의 터미널 시작값은1%입니다.

## 4. 파일 구성과 권장 읽기 순서

| 경로 | 내용 |
|---|---|
| README_FIRST.md / START.cmd / START.ps1 | 이 안내와 실행 메뉴 |
| scripts/manual_first_drive.py | 현재 수동 터미널·GUI·진단 진입점 |
| src/wafer_cart_keyboard_drive/ | 현재 통신·키보드·GUI·시뮬레이터·단위시험 |
| src/wafer_cart_core/ | 모의 터미널 시험에 필요한 공통 로직 |
| config/manual_simulation.json | 가상 운동 모델, 실측값 아님 |
| src/wafer_cart_mapping/config/ | GUI에 필요한 부스·CAD 참고·미확정 실측 설정 |
| firmware/mega_cart/ | 현재 Arduino C++ 소스, PlatformIO 설정, PC용 C++ 시험 |
| firmware/encoder_pin_probe/ | 별도 출력 잠금 엔코더 핀 탐색 소스, 현재 주행 프로토콜과 비호환 |
| firmware/prebuilt/ | 10월9일 업로드본 HEX 사본. 자동 업로드 없음 |
| docs/25_MANUAL_OUTPUT_CONNECTION.md | 최신 시험 결과와 제약, 과거 이력 포함 |
| docs/18_HKX_PCB_A_REVIEW.md / docs/hardware/ | 핀·PCB 검토, 과거 미확정 표기 포함 |
| docs/HKX_PCB_A_original.pdf / preuse_checklist_original.pdf | 사용자 제공 핀 보고서·사용 전 점검표 원본 |
| reference_photos/ | 사용자 제공 배선 사진6장 원본 사본 |
| evidence/ | 원래 PC의 진단 성공 및 과거 실패 로그 |
| FILE_MANIFEST.json | 파일별 크기·SHA256 목록 |

소스 기준 Git: `87208daff82ccc94b60eeaae2fba0792a2ba6448`, branch `codex/pcb-firmware-bench-mock`. `.git` 자체는 포함하지 않습니다. docs/18과 docs/hardware는 원래 작업 폴더의 untracked 참고자료 사본입니다. 카메라 관련 미커밋 변경은 포함하지 않았습니다. 사용자 경로·장치 식별값이 참고자료와 로그에 남아 있으므로 이 ZIP은 팀 내부 전달용이며 공개 업로드 전 검토하세요.

## 5. 현재 문제와 수동 실행 명령

아래 명령은 ZIP을 푼 최상위 폴더의 PowerShell에서 실행합니다. 예시 COM7은 반드시 새 PC의 실제 번호로 바꾸세요.

```powershell
# 최초 설치
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-manual.txt

# 장치 없는 모의시험
.\.venv\Scripts\python.exe scripts\manual_first_drive.py --smoke

# 포트 목록 (포트 열지 않음)
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v

# 배터리 분리·USB만·다른 조작 앱 종료 후 정지 점검
.\.venv\Scripts\python.exe scripts\manual_first_drive.py --real --port COM7 --no-power-feedback --inspect-real --diagnostics

# 실제 출력 가능한 수동 터미널: 준비 확인 후에만 실행
.\.venv\Scripts\python.exe scripts\manual_first_drive.py --real --port COM7 --no-power-feedback --terminal --percent 1 --diagnostics

# 실제 출력 가능한 수동 GUI: 준비 확인 후에만 실행
.\.venv\Scripts\python.exe scripts\manual_first_drive.py --real --port COM7 --no-power-feedback
```

실제 수동 모드는 `CONNECT COM7`처럼 현재 포트를 직접 입력해야 연결됩니다. 터미널에서 1~4로 코드 채널 선택, ↑/↓를 누르는 동안 명령, 놓으면 정지, Space 정지, X/Esc 잠금 종료, +/-는 정지 후 출력 설정 변경입니다. GUI에도 출력 숫자/슬라이더가 있습니다. 키를 놓고 정지한 상태에서 설정하세요. 회전 방향과 바퀴 위치는 아직 추정입니다.

1%는 명령 경로 검사용 시작값이며 실제 모터 회전이나 안전을 보장하는 값이 아닙니다. 엔코더 무변화1.5초와 명령 갱신 중단0.5초의 기존 보호는 유지합니다. `STALL_NO_ENCODER`는 회전이 안 됐거나 피드백이 없다는 결과이지 전원·배선·모터 중 원인을 확정하는 진단명이 아닙니다.

포트 접근 거부: 다른 조작 앱·Arduino 시리얼 모니터/플로터를 닫으세요. 예전 무프레임 V 명령 코드와 현재 C2/CRC 펌웨어는 호환되지 않습니다. `scripts/bench_console.py`와 `terminal_mock.py`는 모의시험용이지 실제 모터 조작기가 아닙니다.

## 6. 다음 담당자의 작업과 추천 스킬

먼저 메뉴3 모의시험, 메뉴4 정지진단, 핀별 배선 대조를 수행합니다. 필요한 경우 codebase-understanding, error-log-diagnosis 스킬을 참고할 수 있지만 새 PC 설치 여부는 확인하지 않았습니다.

현재 보드를 그대로 옮긴다면 PC 변경만을 이유로 Arduino에 재업로드할 필요는 없습니다. 식별이 다르거나 소스 변경을 시험해야 할 때만 아래 절차를 사용하세요.

```powershell
# 설치/빌드만: 장치 업로드 없음
.\.venv\Scripts\python.exe -m pip install platformio==6.1.19
.\.venv\Scripts\python.exe -m platformio run -d firmware\mega_cart -e mega_manual_legacy_5khz

# 아래는 실제 업로드입니다. 배터리 분리·USB만·다른 포트 앱 종료 후 별도 승인한 경우에만 실행
.\.venv\Scripts\python.exe -m platformio run -d firmware\mega_cart -e mega_manual_legacy_5khz -t upload --upload-port COM7
```

이 프로젝트는 Arduino IDE에 단일 .ino로 넣는 구성 대신 PlatformIO의 `platformio.ini`와 include/src를 함께 사용합니다. 기본환경 `mega_locked`는 출력 잠금이므로 현재 수동 펌웨어와 다릅니다. HEX 기준 SHA256은 `B06FE718700A621008183893DFEE2BBA7FE9D9AA7F83EEA5202E85C2D716F674`입니다. 툴체인/버전 차이로 재빌드 HEX가 달라질 수 있습니다.

## 7. 수정 금지와 승인 필요 작업

- 실제 시험 전 준비 확인 없이 모터 전원을 켜거나 구동하지 마세요. 자동 ARM·자동 재출발·보호 해제는 추가하지 마세요.
- 노란색 배터리 커넥터의 극성, 외부 퓨즈·차단, 쉴드→드라이버 PWM/DIR/GND 연결을 확인해야 합니다. LED 점등은 배선 정상 증거가 아닙니다.
- 단일 프로그램만 COM 포트를 사용합니다. 카메라·사람 감지 정지는 이 수동 경로에 연결되지 않았습니다.
- PCB 원본·vendor·참고 측정값을 근거 없이 변경하지 마세요. 실제 출력 채널은 엔코더 손 회전만으로 확정할 수 없습니다.

## 8. 결과물 기록 형식

새 시험은 PC/날짜/COM/펌웨어/모터 전원 상태/명령/응답을 구분해 기록하세요. 수동 터미널은 `data/output/manual_terminal_*.jsonl`을 생성합니다. evidence 폴더는 10월9일 과거 기록이므로 새 결과로 덮어쓰지 마세요. 문서는 UTF-8 with BOM, Python은 UTF-8을 유지합니다.

## 9. 검증 기준과 남은 위험

전달본 작성 시 검증(2026-10-10): 원본이 아닌 이 복사 폴더에서 Python 모의시험 MANUAL_MOCK_PASS, 단위시험101개 통과, START.ps1 -CheckOnly의 필수 경로 검사 통과, 포함 HEX의 SHA256 일치를 확인했습니다. 실제 COM 접근·구동·업로드는 하지 않았습니다. 새 PC 설치, 실차 GUI 렌더링, WSL 기반 가상 GUI는 이번 포장 과정에서 실행하지 않았습니다. Python에서 실행 파일 실제 경로 탐색 경고가 출력됐으나 모의시험과101개 시험은 정상 종료했습니다.

메뉴3 통과, 메뉴4에서 식별 일치·비무장·출력0·IO register_check_passed=true가 기준입니다. 이것만으로 물리 배선/드라이버/회전 정상은 보증되지 않습니다. 부스 지도는 가상이며 실차 위치를 표시하지 않습니다. 새 데스크탑의 USB·드라이버·키 포커스·Tk 화면·실제 COM은 현장 확인이 필요합니다.

## 10. 다음 담당자에게 복사할 프롬프트

> 이 폴더는 대차 수동시험 전달본입니다. README_FIRST.md와 docs/25_MANUAL_OUTPUT_CONNECTION.md를 먼저 읽고 코드/모의시험을 검사해 주세요. 현재 펌웨어는 CART_2/HKX_20260929/MANUAL_UNMONITORED이며 네 바퀴 물리 매핑은 미검증입니다. 과거 로그를 현재 검증으로 취급하지 마세요. 전원 상태 확인과 별도 요청 없이 COM을 열거나 업로드·모터 구동하지 말고, 최초 오류와 출력 레지스터 기록을 보존해 주세요.
