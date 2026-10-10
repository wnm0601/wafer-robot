# 펌웨어 기반 지도 주행 모의환경

작성일: 2026-09-30. 기존 수동 시험 창을 지도와 대차 위치가 표시되는 환경으로 업데이트했습니다.

## 실행과 조작

저장소에서 `py -3.13 scripts\manual_first_drive.py`를 실행하세요. Windows Python 3.13, Tkinter, WSL Ubuntu-24.04의 기존 g++를 사용합니다. 첫 실행 또는 제어 소스 변경 시 PC용 C++ 실행 파일을 자동 빌드합니다. Arduino 업로드는 실행하지 않습니다.

- 기존 부스의 뒤쪽 가림벽과 테이블을 표시합니다. 지도에서 `출발지 설정` 또는 `목적지 설정`을 누른 뒤 빈 위치를 클릭하세요. 대차 외곽이 벽·테이블·지도 경계와 겹치는 지점은 거부합니다.
- 출발지 변경은 대차의 위치와 주행 궤적을 해당 출발지로 초기화합니다. 목적지 변경은 빨간 목적지 표식을 옮깁니다.
- 4륜 모드: `수동 준비` 후 `W/S` 전후, `A/D` 좌우 횡이동, `Q/E` 회전. 한 모터 모드: M1~M4 선택 후 `↑/↓`. 화면의 방향 버튼도 누르는 동안 동작합니다.
- 키·버튼을 놓거나 창을 벗어나면 STOP 명령으로 감속합니다. 다시 움직이려면 수동 준비가 필요합니다. Space는 정지, X는 소프트웨어 비상정지 모의이며 X 이후에는 앱을 다시 시작해야 합니다. Esc는 정지와 지점 선택 취소입니다.
- 속도는 1~30% 슬라이더·숫자 입력 후 `적용`으로 변경합니다. 주행·준비·감속 중에는 변경하지 못합니다. 표시 m/s는 가상 모델의 환산값입니다.
- 지점과 적용 속도는 `data/manual_simulation_ui.json`에 저장합니다. 재시작 후 지점·속도는 복원하지만 주행은 자동 재개하지 않습니다.
- 대차 위치·각도·이동거리·주행 궤적·네 바퀴 출력과 가상 encoder count를 표시합니다. 충돌이 예상되면 이동을 막고 STOP을 보냅니다. 반대 방향으로 수동 준비해 빠져나오거나 정지 후 위치 초기화를 사용하세요.

## 실제 코드가 움직임으로 이어지는 경로

`Tk 키/버튼 → ManualFirstDrive → BenchGateway(C2/CRC/ACK) → PC의 cart::Controller → STATUS의 가감속 바퀴 출력 → SimulationPlant → 지도 좌표/가상 encoder → Controller counts()`

`firmware/mega_cart/src/cart_controller.cpp`와 `include/cart_controller.h`는 Mega 빌드와 PC 모의 빌드가 **같은 소스 파일**을 사용합니다. PC 전용 `test/simulator_wire.cpp`가 실제 시간으로 tick·통신을 중계합니다. 세션·순번·CRC, 수동 ARM, 제한값, 가감속, 500ms 명령 유효기간, encoder 미변화 감지, STOP·ESTOP은 C++ Controller가 처리합니다. 화면 키 값을 위치에 직접 더하지 않습니다.

PC 설정은 `simulation=true, mapping_verified=true`이며 가상 바퀴 순서는 FL/FR/RL/RR입니다. 실제 Mega의 `main.cpp`는 기존 출력 잠금을 유지합니다. 가상 매핑 승인은 실차 매핑 승인으로 사용하지 않습니다. 기존 bare-V 키보드 정책의 오른쪽/CW 양수 convention을 새 C2 경계에서 왼쪽/CCW 양수로 변환했습니다.

바퀴 출력을 실차 속도로 환산하는 교정값이 아직 없으므로 `config/manual_simulation.json`의 최고 바퀴 속도·바퀴 반지름·회전 계수·count/rev는 명시적인 가상 설정값입니다. 질량·모터 토크·배터리 전압·바닥 마찰·미끄러짐·실제 제동거리는 이 모델에서 확인할 수 없습니다.

지도는 `booth_mock.json`의 가상 배치를 사용합니다. 테이블 길이 1.8m는 사용자 제공값이고 나머지 위치·크기는 현장 실측이 아닙니다. 대차 외곽은 `reference_measurements.json`의 CAD 참고 footprint를 사용합니다. 실제 SLAM 지도나 Nav2 자동 목적지 주행은 이번 수동 모의환경에 포함되지 않습니다.

## 반복 검증

- `py -3.13 scripts\manual_first_drive.py --smoke`: 기존 Python 프로토콜 fixture 확인. C++ 지도 시험과 구분합니다.
- `py -3.13 scripts\manual_first_drive.py --sim-smoke`: 실제 C++ 제어 소스와 가상 플랜트의 전후·횡이동·회전, 네 단일 모터, 가상 encoder 응답, 수동 재준비, 테이블 충돌 정지, 명령 timeout·ESTOP 확인.
- `py -3.13 scripts\manual_first_drive.py --ui-test`: 실제 Tk 창에서 키 이벤트를 1.6초 유지한 후 해제하여 지도 이동과 최종 출력 0을 검사합니다. 사용자 저장 설정을 변경하지 않습니다.
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_firmware_simulator_checks.ps1 -UI`: 위 검사를 모아 실행합니다.

보고서는 `data/output/manual_simulator_current.json`과 `manual_simulator_ui_current.json`에 저장합니다. 소스 SHA-256을 기록하고, 캐시된 PC 실행 파일의 SHA-256도 빌드 manifest로 확인합니다. 불일치 시 다시 빌드합니다. `--port`는 실제 COM 포트를 열기 전에 거부합니다.

화면 검증: 지도와 상태줄 표시, 출발지·목적지 지도 클릭, 숫자 속도 적용을 실제 Windows 창에서 확인했습니다. 모델·통신·Tk 홀드 시험 결과는 이번 실행의 보고서에 기록합니다.

이번 실행 결과: 키보드·플랜트 관련 Python 시험 70건 통과, 실제 C++ 기반 주행/encoder/충돌/timeout/ESTOP 시험 통과, Tk 키 1.6초 유지 후 해제 시험 통과했습니다. 최종 Tk 시험에서 가상 이동 약 0.162m, 해제 후 네 출력 0, 미무장 상태를 확인했습니다. 실행 창에서 설정한 지점·20% 속도는 로컬 사용자 설정 파일에 저장됩니다.

앱 재시작 후 두 지점과 20% 속도 복원, 출발지 정지 시작을 실제 창에서 확인했습니다. 1120×720 및 최소 940×720 창에서 지도·버튼·하단 상태줄 표시를 확인했습니다. Windows 화면 캡처는 150% 배율에서 각각 1682×1128, 1412×1128 픽셀이었습니다.
