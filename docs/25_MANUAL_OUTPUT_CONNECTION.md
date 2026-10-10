# Arduino 수동 출력과 같은 화면의 COM 연결

작성일: 2026-09-30. 구현·빌드·PC 모의 검증만 진행했습니다. Arduino 업로드, 실제 COM 개방, 모터 구동은 하지 않았습니다. 작업 중 사용자의 요청 이후에는 창 없는 검증만 수행했습니다.

## 2026-10-09 후속: 모터 전원 OFF 상태의 실제 명령 수락 시험

사용자가 모터 전원이 계속 OFF라고 확인하며 실제 명령 송신까지 요청했습니다. 펌웨어는 앞서 업로드한 `mega_manual_legacy_5khz` 그대로이며, 재업로드·코드 변경은 하지 않았습니다. 아래 무구동 조회 시험과 별개의 후속 시험입니다.

- COM7 실제 Arduino에 채널 1~4의 +1%/-1%를 각각 한 번, 총 8회 전송했습니다. 회전 명령 허용 목록을 M 채널1~4, 비율+1/-1, 최대8회로 제한하고 V 명령은 허용하지 않았습니다.
- 매 시험 POWER_ACK→ARM→M→STATUS/IO→STOP 순서로 수행했습니다. LIMIT=1%, 기존 500ms 명령 시간 제한·1500ms 엔코더 무변화 보호를 변경하지 않았습니다. POWER_ACK는 사용자 확인 절차이며 배터리 ON 실측이 아닙니다.
- 8회 모두 ACK 성공, 선택 채널 내부 출력 +2/-2, 다른 채널0을 확인했습니다. 실제 OCR 읽기는 해당 채널25, 나머지0이었고 타이머 출력 연결 비트·핀 모드 비교도 통과했습니다.
- 양의 명령 때 DIR 하위4비트=15, 음의 명령 때 채널1/2/3/4별 7/13/11/14를 실제 PINC에서 읽었으며 PORTC 기대값과 일치했습니다. 이는 MCU 디지털 읽기이며 드라이버 입력 단자까지의 도통·전압 측정이 아닙니다.
- 각 STOP 후 비무장·4채널출력0·OCR0·DIAG 최초 오류 NONE을 확인했습니다. ENC는 모든 회차에서 [0,-1,-1,0]이었으며 이번에는 손 회전·모터 회전 여부를 실측하지 않았습니다.
- 최종 ESTOP 후 OPERATOR_ESTOP·비무장·출력0을 확인하고 COM포트를 닫았습니다. 이 최종 잠금은 의도한 종료 처리입니다.
- 원본 기록: `data/output/diagnostic_commands_poweroff_20261009.log`. passed=true, 실제 M송신8회, 응답·레지스터·송신시각 포함.

확인 범위: Python→USB/serial→명령 승인→실제 MCU 내부 PWM/DIR 설정→STOP까지입니다. 1%의 짧은 시험이므로 과거 20/40% 장시간 유지, 1.5초 무변화 차단, 실제 전원 인가 후 동작을 통과했다는 뜻은 아닙니다. 커넥터 핀 순서·배선·드라이버 출력·전원·실제 바퀴 위치 대응은 여전히 미검증입니다. 사진의 스티커와 기존 위치 추정이 달라 이번 결과는 물리 위치 확정 없이 코드 채널 번호 기준으로만 기록합니다.

## 2026-10-09 장치 상태: 진단 포함 수동 펌웨어 업로드·무구동 점검 완료 (앞선 시험)

사용자가 모터 전원 OFF·Arduino USB만 연결·조작 앱과 시리얼 모니터 종료를 확인한 뒤 업로드를 승인했습니다. 아래 미업로드 설명은 이전 단계의 이력입니다.

- 대상: COM7 Arduino Mega 2560, VID:PID 2341:0042, USB serial 85036313330351A0E0A0.
- 소스: Git `126f706`, `mega_manual_legacy_5khz`. Flash 13902bytes 쓰기 및 avrdude 읽기 비교 검증 성공, RAM 1876bytes. Fuse E:FD/H:D8/L:FF.
- HEX SHA256: `B06FE718700A621008183893DFEE2BBA7FE9D9AA7F83EEA5202E85C2D716F674`.
- 현재 식별: `CART_2 HKX_20260929 MANUAL_UNMONITORED`. 이전 `ENCODER_PIN_PROBE_V1`을 교체했습니다. 출력 기능이 컴파일된 수동 펌웨어이지만 이번에는 ARM·POWER_ACK·M·V를 전송하지 않았습니다.
- 기존 `--inspect-real --diagnostics` 점검 1회 통과 후, 송신 허용 목록으로 구동 명령을 차단한 별도 세션 2회에서 각 20회, 총 40회 STATUS/ENC/DIAG/IO 반복 점검을 통과했습니다.
- 시작과 재연결: `STARTUP_LOCKED`, armed=0, 내부 출력 네 채널 모두 0. 반복 조회 중 최초 오류 `NONE`, 응답 시간 초과·CRC 오류·재시작 오류가 발생하지 않았습니다.
- 실제 레지스터: ICR1/5=3199, TCCR1A/5A=2, TCCR1B/5B=25, OCR1A/1B/5A/5B/5C=0, DDRB=96, DDRL=48, DDRC=15. 관련 DIR PORTC/PINC 하위 4비트=15로 일치. Timer 설정상 5kHz이나 실제 PWM 파형을 측정한 것은 아닙니다.
- ENC1~4는 두 수집 구간 모두 `[0,-1,-1,0]`으로 유지됐습니다. 초기 -1의 발생 원인은 확인하지 않았으며 회전·고장·A/B 정상의 증거로 사용하지 않습니다. 이번에는 손 회전 시험을 하지 않았습니다.
- STOP 후 출력 0·비무장 유지, ESTOP 후 `OPERATOR_ESTOP`과 DIAG 최초 원인 기록을 확인했습니다. 종료 ESTOP는 의도적으로 보낸 잠금이며 예상하지 못한 오류가 아닙니다. 최종 포트를 닫았습니다.
- 한 세션당 송신: HELLO 1, LIMIT 1(1%), INFO 1, STATUS 22, ENC 20, DIAG 21, IO 21, STOP 1, ESTOP 2. LIMIT 1%는 시험 세션 제한이며 실제 구동이나 향후 허용 출력 승인이 아닙니다.
- 원본 결과: `data/output/diagnostic_idle_20261009.log`. 각 반복 응답과 레지스터, 최종 상태, 송신 종류가 포함됩니다.

남은 한계: A8 전원 피드백이 없어 장치는 배터리 OFF를 직접 감지하지 못합니다. 실제 핀 파형·배선 도통·드라이버 전원/출력·전류·회전·바퀴 위치 대응·물리 비상정지는 이번 점검으로 확인되지 않았습니다. 사진의 스티커 M2/M4와 이전 위치 추정 차이도 미확정입니다. 수동 구동 전 별도 준비 확인이 필요합니다. PIO 중복 Core 경고는 있었으나 빌드·업로드·검증은 성공했습니다.

## 2026-10-09 추가: 최초 오류와 출력 레지스터 진단 (업로드 전 이력)

이 절은 업로드 전 PC 검증 결과입니다. 당시 Arduino에는 `ENCODER_PIN_PROBE_V1` 출력 잠금 진단 펌웨어가 남아 있었습니다. 이후 업로드·실제 응답 결과는 위 최신 장치 상태 절을 참고하십시오.

- `DIAG`: 첫 오류의 원인·MCU 시각·정지 직전 내부 출력 4개·엔코더 카운트 4개를 반환합니다. 뒤따르는 `MOTION_REJECTED`, `STOP`, `ESTOP` 및 `HELLO`로 첫 기록을 덮지 않습니다. 명시적인 `ARM`이 성공하면 새 시험을 위해 초기화하며 MCU 리셋 시에도 사라집니다.
- `IO`: `IO1` 형식으로 MCU 시각, 물리출력 빌드 여부, PWM 분모, ICR1/5, TCCR1A/B·5A/B, OCR1A/B·5A/B/C, DDRB/L/C, PORTC/PINC, 현재 내부 출력 4개를 읽습니다. 포트·타이머 설정과 계산값을 비교하며 전압·전류·파형 실측으로 표시하지 않습니다.
- IO 조회는 해당 시점의 제어 출력/정지를 반영한 뒤 레지스터를 읽습니다. 오류 직전 레지스터 파형을 저장하는 기능은 아닙니다. PWM 입력 핀의 실제 전압과 드라이버 출력은 여전히 확인할 수 없습니다.
- 정지/통신 시간 제한과 출력 상한은 유지합니다. 진단 조회는 ARM 또는 구동 명령을 보내거나 명령 유효시간을 갱신하지 않습니다.
- `MOTION_REJECTED STALL_NO_ENCODER`처럼 거부 응답에 최초 원인을 덧붙입니다. 기존 STATUS 원인 필드는 한 단어를 유지하고 원인 상세는 DIAG에서 읽습니다.
- Python은 최근 송수신 최대128건과 최초 gateway 오류를 보존합니다. GUI 조작과도 공유하는 gateway 기록이며, 터미널 오류 로그에 저장합니다.

새 주행 펌웨어 업로드 후 정지 상태에서만 사용하는 점검 명령입니다. 별도 엔코더 핀 탐색 펌웨어와는 호환되지 않습니다. 실제 점검 전 모터 전원 OFF·USB만 연결·다른 포트 사용 앱 종료를 확인하십시오.

```powershell
py -3.13 scripts\manual_first_drive.py --real --port COM7 --no-power-feedback --inspect-real --diagnostics
```

향후 수동시험에서 기존 터미널 실행 인자에 `--diagnostics`를 붙이면 시작 전 레지스터 검사를 수행합니다. 미지원 펌웨어·잘못된 타이머/방향 설정·출력 잠금 빌드에서는 조작을 시작하지 않습니다. 오류 발생 시 정지 처리를 거쳐 DIAG/IO와 송수신 기록을 `data/output/manual_terminal_*.jsonl`에 저장합니다. 연결 자체가 끊어지면 진단을 읽을 수 없으며 미수신으로 기록합니다. 주행 중 반복 진단 조회를 추가해 기존 명령 주기를 늦추지는 않습니다.

현재 코드만 검증하는 명령은 다음과 같습니다.

```powershell
wsl -d Ubuntu-24.04 -- bash -lc 'cd "/mnt/c/Users/H/Desktop/로봇 자율주행/wafer-cart-line-navigation" && bash scripts/verify_bench_host.sh'
$env:PYTHONPATH='src\wafer_cart_keyboard_drive'
py -3.13 -m unittest discover -s src/wafer_cart_keyboard_drive/test
py -3.13 scripts\manual_first_drive.py --terminal-smoke
pio run -d firmware/mega_cart -e mega_locked -e mega_manual_legacy_5khz
```

PC 시험은 실제 C++ Controller와 AVR 출력 소스를 가상 레지스터에 연결합니다. M3(왼쪽 앞 추정)20%의 OCR1B=501, 1.5초 무변화 원인 보존, STOP/ESTOP 후 기록, 성공한 ARM의 초기화, IO 조회 중에도 통신 시간 제한 유지, 레지스터 변조 검출을 검사합니다. Python 파서는 잘못된 OCR·출력 핀 모드·방향 입력·타이머 설정 및 길이/범위 오류를 검사합니다. Controller만 실행하는 PC fixture는 AVR 레지스터를 `UNAVAILABLE`로 반환합니다.

실측으로 남는 항목: 실제 PWM 파형/전압, 드라이버 전원/출력, 출력 채널과 바퀴 위치, 부하에서 회전 여부입니다. 코드 진단 통과로 이를 정상 확정하지 않습니다.

최종 검증(2026-10-09): Python 101개, C++ 기존100검사·PWM3프로필·600/1500ms 경계·새 진단 회귀, Python/C++13응답, 터미널 모의시험 통과. Mega locked/legacy5kHz 빌드 성공(Flash13634/13902bytes, RAM1876bytes). 새 상세 오류의 STATUS 필드 호환성 검사를 추가해 수정 전 실패·수정 후 통과를 확인했습니다. PlatformIO 6.1.19/6.2.0 중복 경고는 남아 있습니다. 이번 검증에서는 실제COM을 열지 않았습니다.

## 구현된 경로

`기존 Tk 화면 키/버튼 → ManualFirstDrive → 단일 BenchGateway → pyserial → Mega C2/CRC/ACK → Controller 가감속 출력 → Timer1/5 PWM + DIR`

같은 포트에서 STATUS와 네 채널 ENC도 읽습니다. 자동 목적지 주행·ROS/Nav2·카메라 사람 정지는 이 수동 경로에 연결하지 않았습니다. 화면의 소프트웨어 정지는 물리적 전원 차단을 보장하지 않습니다.

- `mega_locked`: 기존 기본 빌드. 출력은 0이며 실차 UI가 이 identity를 거부합니다.
- `mega_manual`: 새 실제 출력용 코드. `MANUAL_ONLY` identity이며 수동 ARM, 출력 상한, 전원 OFF 관찰 후 ON, 현재 출력 0 조건을 확인합니다.
- 정지 명령은 감속, 비상정지·전원 오류·통신 timeout·encoder 미변화 오류는 즉시 출력 0입니다. 방향 반전은 0을 거칩니다. MCU loop 자체가 멈추면 이 소프트웨어 timeout도 실행되지 않으므로 하드웨어 비상정지와 reset 시 PWM pull-down 검증이 필요합니다.
- 임의 bare-V 구형 주행 명령을 받지 않습니다. session·순번·CRC가 맞아야 합니다. 명령 미갱신 500ms 및 encoder 미변화 600ms는 기존 개발값이지 실측 승인된 정지시간이 아닙니다. 실차 encoder 감지는 출력이 0이 아닌 저속에서도 적용하므로 저속·부하 조건에 따라 false fault를 현장 확인해야 합니다.

## 확정 PCB 핀

| 채널 | PWM | DIR | ENC A | ENC B | PWM Timer |
|---|---:|---:|---:|---:|---|
| M1 | 11 | 34 | 3 | 30 | OC1A |
| M2 | 44 | 36 | 18 | 31 | OC5A |
| M3 | 12 | 35 | 19 | 32 | OC1B |
| M4 | 45 | 37 | 20 | 33 | OC5B |

PWM은 16MHz, prescaler 1, TOP 4095로 3906.25Hz입니다. zero duty에서는 OC를 분리하고 LOW로 내려 OCR=0의 좁은 펄스를 피합니다. DIR+PWM sign-magnitude를 사용합니다. M 명령의 +방향은 DIR HIGH이며 바퀴의 실제 전진 방향은 아직 미확인입니다. ENC는 A rising x1, B 기반 원시 부호입니다.

[Cytron 공식 MDD10A 제품 설명](https://www.cytron.io/cytron/p-10amp-5v-30v-dc-motor-driver-2-channels)은 Rev2.0의 최대 30V와 PWM 최대 20kHz를 안내합니다. 코드의 3.90625kHz는 이 PWM 범위 안입니다. 그렇다고 사용자의 배터리 구성·회생전압·배선 안전이 확인된 것은 아닙니다. 29.4V는 사용자 설명이며 새로 측정하지 않았습니다.

## 아직 설정하지 않은 값 — 임의로 채우지 않았습니다

`firmware/mega_cart/include/manual_hardware_config.h`:

- `CART_POWER_ON_LEVEL=-1`: A8 극성 미확정. -1이면 전원 Unknown으로 주행이 거부됩니다. 실제 0~5V 외부 로직 회로인지 확인 후 LOW=ON이면 0, HIGH=ON이면 1로 설정합니다. 24V를 Arduino 입력에 직접 연결하면 안 됩니다. INPUT_PULLUP을 임의로 켜지 않았고 단선 검출은 회로에 따라 달라지므로 별도 시험해야 합니다.
- `CART_PHYSICAL_LIMIT_PERCENT=0`: 실제 출력 상한 미확정. 0이면 LIMIT/ARM이 거부됩니다. 담당자가 결정한 첫 시험 상한(1~30 범위)을 넣어야 하며 과거 30%를 자동으로 승인값으로 사용하지 않습니다.
- `CART_WHEEL_MAPPING_VERIFIED=0`: 단일 M1~M4 시험만 허용합니다. FL/FR/RL/RR에 대응하는 `CART_WHEEL_CHANNELS`(0~3)와 `CART_WHEEL_SIGNS`(+1/-1)을 실물에서 확인한 뒤 이 값을 변경합니다. 기본 배열은 가정이며 현재 실차 매핑이 아닙니다. 중복 채널·잘못된 부호는 V 명령을 거부합니다.
- 4륜 UI도 `measurements.json`의 `firmware_wheel_mapping_verified`가 실제 검증 후 true일 때만 허용합니다. MCU 설정과 일치해야 합니다. 이 플래그만 변경해도 MCU V 검증을 우회하지 못합니다.

## 화면 사용 — 실제 시험 준비를 확인한 이후에만

1. `py -3.13 scripts\manual_first_drive.py`는 항상 모의 모드로 시작합니다. 모의 모드는 WSL/g++를 사용하고 실제 COM을 열지 않습니다.
2. `실차 연결 / 모의 전환`에서 명시적인 COM 번호를 입력합니다. 담당자 준비·출력용 firmware 설정/업로드·전원 및 비상정지 확인을 마쳤을 때만 확인 항목을 선택합니다.
3. `실차 연결`은 포트를 실제로 열며 Mega가 DTR로 reset될 수 있습니다. 자동 ARM·자동 재연결·자동 주행 재개는 하지 않습니다. identity 불일치·상한 미설정·ACK 오류 시 닫습니다.
4. 처음에는 한 모터 모드, 명령 1%로 시작합니다. 실제 firmware 상한보다 큰 변경은 거부됩니다. 1%에서 모터가 움직일지는 토크·부하에 따라 달라지며 성공을 보장하지 않습니다. 시작 시 접촉기 OFF를 관찰시킨 뒤 ON으로 전환해야 합니다. 전원은 반드시 담당자가 조작합니다.
5. `수동 준비` 후 `↑/↓` 또는 화면 M 버튼을 누르는 동안 출력합니다. 4륜 확인 후 W/S, A/D, Q/E도 같은 화면에서 사용할 수 있습니다. 키 해제·창 전환은 STOP, Space 정지, X 비상정지입니다.
6. 실차 모드에서는 실제 원시 엔코더·MCU 출력 상태만 표시합니다. m/s·지도 위치·거리·각도는 미추정이며 대차를 가상 좌표로 움직여 표시하지 않습니다. 지도상의 벽/테이블은 충돌 센서가 아니므로 실차 충돌을 막지 못합니다. 작업자가 주변을 확인해야 합니다.
7. 해제 또는 모의 모드 전환은 ESTOP 후 COM을 닫습니다. 재연결/오류 후에는 수동 준비 및 전원 OFF→ON 조건을 다시 확인합니다. 실차 설정과 출력 상태는 저장해 자동 복원하지 않습니다.

빌드는 `platformio run -d firmware\mega_cart -e mega_manual`입니다. 이것은 업로드 명령이 아닙니다. 실물 준비 확인 전 업로드하지 마세요. 기본 `mega_locked`는 그대로 남았습니다.

## 검증과 한계

- Python 시험: 80건 통과. 포트·담당자 확인 거절, 제한된 read/write timeout, 모의 identity를 실차로 받지 않는 검사 포함입니다.
- Mega locked/manual 두 빌드: 컴파일 통과. `.pio/build/mega_manual/firmware.hex`는 미설정 기본값의 시험 산출물이며 지금 업로드해도 주행 조건을 충족하지 않습니다.
- C++ sanitizer host: 79개 검사 통과, Python/C++ 계약 응답 13개 통과. 실차 분기의 상한 미설정, 원시 단일 모터, wheel 매핑/잘못된 매핑, 전원 Unknown 정지를 포함합니다.
- 요청 이전 실제 Tk 창: 모의 및 PC MANUAL_ONLY fixture의 W 누름/해제, 출력 0·미무장 상태를 확인했습니다. 실제 Arduino·GPIO·COM을 사용한 시험은 아닙니다.
- 요청 이후 `py -3.13 scripts\verify_manual_hardware.py`: 창 없이 실제 C++ 코드의 MANUAL_ONLY gateway로 M1~M4, 여섯 벡터 방향, 포커스 해제 STOP, 자동 재개 금지, timeout, fault latch를 확인합니다. `data/output/manual_hardware_headless.json`에 결과를 남깁니다. fixture 엔코더는 실측으로 표시하지 않습니다.
- `scripts/run_firmware_simulator_checks.ps1` 기본은 창 없는 검사입니다. `-UI`는 창을 열므로 백그라운드 요구가 있을 때 사용하지 않습니다.

실제 핀의 PWM 파형·방향, 배터리·접촉기·A8 입력, encoder 부호, 실제 감속·정지거리, 센서 안전 및 4륜 주행은 모두 미검증입니다. PlatformIO가 두 Core 버전 공존 경고를 냈지만 두 빌드는 성공했습니다. 설치 환경은 임의로 변경하지 않았습니다.

파일은 존재·크기·비어 있지 않음·UTF-8/BOM·대체문자 유무를 확인했고 Python 구문도 검사했습니다. 사용자 요청에 따라 새 VSCode 창을 열지 않았으므로 신규 파일의 VSCode 화면 표시 검사와 최종 시각 검증은 보류했습니다. `design-verified-ui`의 화면 검증 단계보다 사용자의 백그라운드 작업 요청을 우선했습니다.

## 2026-10-07 A8 없는 실제 첫 시험 프로필

사용자가 받침대·물리 비상정지·담당자 준비, 모터 전원 OFF 및 Arduino USB 전원을 확인하고 시험 최대 PWM 비율을 40%로 지정했습니다. PDF `핀변경_보고서_HKX_PCB-A (1).pdf` 4페이지와 PWM/DIR/ENC A/B 및 Timer1/5를 대조해 일치를 확인했습니다. 램프 D14~D17, 전압 감시 A3는 시험 펌웨어에서 미구현입니다. 보고서에는 A8 전원 피드백 배선이 정의되어 있지 않습니다.

기존 기본 잠금은 유지합니다. 새 `mega_manual_no_feedback`만 `CART_OPERATOR_POWER_ACK=1`, protocol/physical 상한 40%를 사용하며 identity는 `CART_2 HKX_20260929 MANUAL_UNMONITORED`입니다. 전원 상태는 Unknown(0)으로 보고하고 가짜 ON 피드백을 만들지 않습니다. POWER_ACK는 실측이 아닌 사용자 선언이며 정지 상태의 수동 준비에서 보내고 한 번 ARM하면 소비합니다. STOP/ESTOP/오류/새 세션은 선언을 취소합니다. 자동 ARM/재연결/주행 재개는 없습니다. timeout 500ms와 encoder 변화 없음 600ms 검사를 유지합니다. 실제 정지 시간·PWM 파형·토크·encoder 부호/count/rev는 미검증입니다.

**물리 전원 차단/복구는 감지할 수 없습니다.** 차단 시 키를 놓고 앱을 종료하고, 전원 복구 후 새로 연결/준비해야 합니다. 전원을 다시 넣기만 하면 안전하게 명령이 취소된다고 가정해서는 안 됩니다. MCU/PC가 멈추면 소프트웨어 정지가 보장되지 않으므로 물리 전원 차단 장치를 사용합니다. 이 프로필은 감독하의 첫 수동시험용이며 자동 운행용이 아닙니다.

업로드 완료 후 실제 조작 실행:

```powershell
cd "C:\Users\H\Desktop\로봇 자율주행\wafer-cart-line-navigation"
py -3.13 scripts\manual_first_drive.py --real --port COM7 --no-power-feedback
```

`CONNECT COM7`를 직접 입력하면 실제 포트를 열고 수동 조작 창으로 들어갑니다. PC 시뮬레이터는 생성하지 않습니다. 연결 초기 명령은 HELLO/LIMIT 1/INFO이며 출력 0/미무장 상태입니다. 시작 출력 1%, 정지 중 숫자/슬라이더로 최대 40%까지 적용합니다. 수동 준비의 전원·주변 확인 후 M1~M4 선택, ↑/↓ 또는 M 버튼을 누르는 동안만 시험합니다. 키 해제·포커스 이탈은 STOP, Space 정지, X 소프트웨어 ESTOP입니다. **실제 바퀴 배정/방향 미확정으로 4륜 주행은 잠금 유지**입니다. 실차 출력/원시 ENC만 표시하며 위치/m/s를 가상으로 적분하지 않습니다. ROS/Nav2 및 카메라 사람 정지는 이 경로에 미연결입니다.

업로드(모터 전원 OFF 및 대상 COM 확인):

```powershell
& "C:\Users\H\.platformio\penv\Scripts\platformio.exe" run -d firmware\mega_cart -e mega_manual_no_feedback -t upload --upload-port COM7
```

현재 장치: Arduino Mega 2560 COM7, VID:PID=2341:0042. 최초 두 업로드는 COM7 PermissionError(13) 접근 거부로 실패했습니다. serial-monitor 종료 시도 뒤에도 점유 후보가 남아 사용자에게 모니터/IDE 닫기를 요청했습니다. IDE 종료 확인 후에는 PlatformIO의 추가 pyserial 초기화 단계에서 대기했습니다. avrdude가 아직 시작되지 않았음을 확인해 이번 업로드 프로세스만 중단했습니다. 프로젝트의 새 프로필에서 `board_upload.disable_flushing=yes`로 추가 초기화를 생략하고 avrdude 자체 wiring reset을 사용했지만, avrdude도 COM7 접근 거부/handshake timeout으로 실패했습니다. 플래시 쓰기/검증 성공 기록은 없고 실제 ARM/M/V는 보내지 않았습니다. USB 재연결을 요청했습니다. 업로드 완료라고 보고하지 않습니다. IDE 소스 및 기존 SolidWorks MCP 작업은 보존했습니다.

최종 결과: 사용자의 새 USB 케이블 연결 후 Mega COM7을 다시 확인했습니다. 재시도 도구 결과 전달이 한 번 끊겨 완료 여부를 추정하지 않고 다시 업로드했습니다. 마지막 avrdude 실행 exit 0/SUCCESS, device signature=0x1e9801, flash 12,458 bytes written/verified, Fuses OK(E:FD/H:D8/L:FF)를 확인했습니다. 이어 `--real --port COM7 --no-power-feedback --inspect-real`을 실제 보드에서 실행하여 identity=MANUAL_UNMONITORED, STATUS=STARTUP_LOCKED, power=Unknown, armed=0, limit=1, 네 출력 모두 0, 원시 ENC 네 값 0을 확인했습니다. 종료 ESTOP 후 COM을 닫았습니다. POWER_ACK/ARM/M/V 및 실제 모터 구동은 하지 않았습니다. 핀의 실제 PWM 파형·물리 방향·실차 제동과 GUI 확인 대화상자 동작은 여전히 미검증입니다. 이전 실패 문단은 과정을 기록한 것이며 최종 업로드는 완료됐습니다.

현재 소스 검증: Python 83개 PASS, 기본/40% C++ 검사 각각 100개 PASS(기본 sanitizer), Mega 세 프로필 컴파일 PASS. 새 PC MANUAL_UNMONITORED 검사에서 M1~M4 40%, 출력 0 초기 상태, Unknown 유지, 포커스 STOP, 준비 취소, 자동 재개 금지, 41% 거절, timeout, ESTOP latch, 미검증 4륜 잠금을 확인했습니다. 처음 고정 대기 검사는 실패하여 조건 기반 대기로 수정 후 PASS했습니다. 기존 모의/수동 gateway 회귀도 PASS했습니다. 가상 ENC를 실측으로 승격하지 않습니다. 창을 띄우지 않는 요청으로 실차 창의 시각 및 새 모달 동작 검증은 보류했습니다. deep-task-analysis/codebase-understanding/design-verified-ui 스킬을 적용했습니다.

## 2026-10-07 출력 명령 비율 조절 개선

기존 숫자/슬라이더 조절을 유지하면서 입력값과 실제 적용값을 분리했습니다. `속도 조절 · 출력 명령 %`에서 숫자를 입력하거나 슬라이더를 이동한 뒤 `정지 중 적용`을 누르십시오. 적용만으로 ARM/주행하지 않습니다. 숫자 입력칸의 Enter도 적용합니다. 정수 1~30 범위를 검증하고 빈 값·문자·NaN·무한대·소수·범위 밖 입력은 거절합니다. 이 범위는 과거 소프트웨어 상한이며 승인된 실제 시험 출력 범위라는 뜻은 아닙니다.

수동 준비·키 유지·주행·감속·오류/비상정지 중에는 입력칸·슬라이더·적용 버튼을 잠급니다. 실차에서는 MCU가 별도로 firmware physical limit를 검사하며 상한 초과는 거절됩니다. 실제 상한보다 작은 UI 범위를 자동 표시하는 기능은 구현하지 않았습니다. MCU 거절 시 기존 fault/정지 정책을 유지하며 UI로 이를 우회하지 않습니다. 실차 m/s는 미교정입니다. 모의 설정은 저장하지만 실차 출력 설정은 자동 복원하지 않고 연결 시 1% 요청으로 시작합니다.

코드베이스 이해와 design-verified-ui 스킬을 적용했습니다. Windows Python 3.13/PYTHONUTF8=1에서 keyboard drive unittest 82개 통과, `--ui-test` 및 `--hardware-ui-test`의 실제 Tk 숫자 적용(7)·슬라이더 적용(9)·NaN 거절·준비 상태 적용 버튼 잠금·1.6초 홀드/해제 STOP 검사가 모두 PASS입니다. 두 GUI 시험은 실제 COM 없이 PC firmware를 사용했습니다. 최초 전체 검사에서 자식 터미널 출력 인코딩 오류 1개가 발생했으나 UTF-8 실행 환경으로 동일 검사를 재실행해 82개가 통과했습니다. GUI 시험의 설정 파일은 output fixture 경로로 분리해 사용자 모의 설정을 덮어쓰지 않습니다.

실행: `py -3.13 scripts\manual_first_drive.py`. 검증 결과는 `data/output/manual_simulator_ui_current.json`, `data/output/manual_hardware_ui_fixture.json`입니다. 실제 Arduino 업로드·PWM 파형·모터 속도·실차 키 해제 정지는 이번 시험 범위에 포함되지 않습니다. A8 극성=-1, physical limit=0의 기본 잠금은 변경하지 않았습니다.
