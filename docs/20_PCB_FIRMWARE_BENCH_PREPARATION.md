# 새 PCB 기준 firmware·Python 첫 구동시험 준비

작성일: 2026-09-29 KST. branch: `codex/pcb-firmware-bench-mock`.

## 1. 쉽게 보는 결론

Arduino Mega 2560용 프로그램과 Python 시험 콘솔을 작성하고, 실제 Mega 대상 컴파일과 가상 시험을 진행했습니다.
이번 프로그램은 **실제 출력이 차단된 개발용**입니다. 연결 즉시 모터가 돌거나 실차 운용이 승인된 상태가 아닙니다.
Arduino 업로드, serial 포트 열기, 모터 구동, 실제 카메라 재시험은 하지 않았습니다.

사용자가 이번에 확인한 내용은 다음과 같습니다.

- 전원 구성: 미확인입니다.
- Arduino 프로그램: 팀에서 새로 작성해 넣을 예정입니다. 현재 flash 버전은 미확인입니다.
- 드라이버 revision 및 보조 배터리 전압: 미확인입니다.
- 바퀴 받침과 담당자: 준비됐다는 사용자 말씀을 기록했습니다. 현물 시험 완료를 뜻하지 않습니다.

`config/bench_hardware_pending.json`에 미확정 항목을 null/false로 보존합니다.
파일 체크값을 true로 바꾸거나 CLI 인자를 붙여도 실제 출력 잠금은 해제되지 않습니다.

## 2. 이번에 작성한 프로그램

| 파일 | 역할 |
|---|---|
| firmware/mega_cart/include/cart_controller.h | 새 PCB 핀·제어 계약·상태 정의입니다 |
| firmware/mega_cart/src/cart_controller.cpp | Arduino와 호스트 시험이 공유하는 C++ 제어 로직입니다 |
| firmware/mega_cart/src/main.cpp | Mega encoder x1 읽기·Timer1/5 설정·serial 수신 처리입니다. PWM 출력은 LOW로 유지합니다 |
| firmware/mega_cart/platformio.ini | Mega 2560 출력 차단 빌드만 제공합니다 |
| bench_protocol.py | 요청 번호·세션·CRC 체크섬이 있는 명령 형식입니다 |
| bench_gateway.py | 단일 byte stream 소유와 상시 응답/오류 감시를 담당합니다 |
| bench_mock.py | 전원·응답·엔코더를 가정하는 메모리 시험 장치입니다. 실제 firmware 대체품은 아닙니다 |
| scripts/bench_console.py | ROS 없이 단일 모터 요청·정지·엔코더 응답을 시험합니다 |
| scripts/verify_bench_host.sh | C++ sanitizer 검사와 Python↔C++ 계약 검사를 진행합니다 |
| scripts/run_bench_checks.ps1 | 기본 Python 회귀와 선택적 firmware/host 컴파일을 묶습니다 |

Python 모듈은 `src/wafer_cart_keyboard_drive/wafer_cart_keyboard_drive`에 있습니다.
단위 테스트는 해당 패키지 `test/`에 있습니다.

## 3. 핀과 미확정 정보

핀 배열은 M1/M2/M3/M4 순서입니다. 바퀴 FL/FR/RL/RR 순서로 추정하지 않습니다.

| 기능 | M1 | M2 | M3 | M4 |
|---|---:|---:|---:|---:|
| PWM | 11 | 44 | 12 | 45 |
| DIR | 34 | 36 | 35 | 37 |
| Encoder A | 3 | 18 | 19 | 20 |
| Encoder B | 30 | 31 | 32 | 33 |

Encoder는 A rising x1와 B level로 raw count 방향을 읽습니다. 실제 바퀴 전진 부호·count/rev는 넣지 않았습니다.
Timer1/5 계획은 16MHz/(4095+1)=3906.25Hz이며, 현재 OC 출력을 연결하지 않아 실제 PWM 파형은 나오지 않습니다.
A3 전압 분압값과 A8 전원 상태 입력은 실제 회로/극성을 모르는 상태라 설정·측정하지 않습니다.

기존 리팩터링 소스의 30% 명령 상한, duty scale 200/255, 15ms당 step 2, 500ms command lease를 역사적 소프트웨어 후보로만 참고했습니다.
실제 안전 출력·제동거리·전류·속도·정지시간을 보증하는 값이 아닙니다. 30% 명령은 PWM duty 30%와 동일하지 않습니다.
600ms 무펄스 검사는 가상시험용 진단이며, 실제 motor stall/current 보호를 검증한 것이 아닙니다.

## 4. 정지와 재개

- 시작·새 연결·리셋 상태는 정지 및 재개 잠금입니다.
- firmware ARM은 simulation 코어에서만 허용합니다. 실제 Mega 빌드는 HARDWARE_LOCKED를 반환합니다.
- 가상 전원 OFF 관측 → ON → 상한 설정 → 작업자 ARM 뒤에만 가상 명령을 허용합니다.
- M 명령은 모터 한 개의 target만 지정합니다. 다른 모터가 아직 감속 중이면 거부합니다.
- 일반 STOP은 target 0으로 감속하고 재개를 잠급니다. 감속 완료 전에 ARM을 시도하면 fault로 처리합니다.
- 부호 반전은 모델 출력이 0을 거친 뒤 반대 방향으로 증가합니다.
- ESTOP·전원 소실·잘못된 명령·lease 만료·무펄스 fault는 모델 출력을 즉시 0으로 하고 잠급니다.
- fault 뒤에는 OFF 재관측, ON, 명시적 ARM이 필요합니다. 버튼 해제/시간 경과로 자동 재출발하지 않습니다.
- STATUS/ENC 같은 조회는 주행 lease를 연장하지 않습니다.
- MCU/호스트 프로그램이 멈춰도 안전하다는 현물 검증은 아닙니다. 물리 차단·watchdog·reset 중 신호 상태는 실제 구성 확인이 필요합니다.

일반 STOP의 ramp와 fault 출력0은 **소프트웨어 모델 동작**입니다. 실제 대차의 감속/비상정지 방식을 승인한 것이 아닙니다.
현재 `main.cpp`는 출력 LOW만 유지하며, 실제 DIR/PWM 출력 적용과 전원 상태 입력을 완성하려면 확인된 하드웨어 profile과 별도 승인 후 후속 작업이 필요합니다.

## 5. 통신 형식과 기존 프로그램과의 경계

새 개발용 C2 프로토콜은 기존 원본 `V/STOP/ESTOP` 또는 2-count ROS vendor 규약을 덮어쓰지 않습니다.
기존 원본 firmware와 gateway는 유지하며, 새 gateway는 기존 bare ACK를 받아 주행 허용하지 않습니다.
실제 PCB 프로그램으로 채택할 때 firmware와 host를 **같은 버전**으로 함께 선택해야 합니다.

```text
C2 <16자리 session> <uint32 요청 번호> <operation> [정수 인자] *<CRC16>
R2 <session> <요청 번호> OK|ERR <operation> [자료] *<CRC16>
E2 <session> <fault/event> *<CRC16>
```

CRC는 CCITT-FALSE(init FFFF/poly 1021)입니다. 전송 손상 검사용이며 보안 인증은 아닙니다.
HELLO, INFO, LIMIT, ARM, M, V, STOP, ESTOP, STATUS, ENC를 구현합니다.
M/V 인자는 percent이며 m/s·rad/s가 아닙니다. V는 바퀴 mapping 검증 전 차단합니다.
C++ 테스트에서 사용하는 X-roller 조합은 simulation 정의이며 실차 wiring/sign으로 승격하지 않습니다.
ENC는 MCU millis와 M1~M4 signed raw counts를 반환합니다. ROS timestamp/odom으로 바로 사용하지 않습니다.
호스트는 수신 monotonic 시간도 붙이며, time wrap/encoder scale/TF를 포함한 실제 odom 변환은 남아 있습니다.

단일 reader가 ACK 뒤의 비동기 fault도 계속 읽습니다. 이전 session·요청 번호·다른 operation·변조 checksum·timeout은 재시도 없이 잠깁니다.
byte stream adapter는 제한된 읽기/쓰기 timeout과 부분 프레임·부분 write를 검사합니다. COM port를 생성하거나 열지 않습니다.
실제 serial factory는 항상 잠겨 있으며, 설정 파일로 안전 승인을 대신하지 않습니다.
종료 시 가상 ESTOP을 보내고 reader/stream을 정리합니다. 통신이 끊긴 상황의 물리 정지는 보증하지 않습니다.

## 6. 실행 방법 — 전부 모터 비활성

Windows PowerShell에서 저장소 폴더를 열고 실행합니다.

```powershell
py -3.13 scripts\bench_console.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_bench_checks.ps1
```

콘솔 예: `power on` → `arm` → `m 1 10` → `wait 0.35` → `enc` → `quit`.
power on/off는 가짜 피드백입니다. m 명령은 가짜 장치에 0.15초 동안만 요청합니다.
STOP 뒤에는 감속 종료를 확인한 후 작업자가 다시 arm해야 합니다. 실제 COM 옵션은 요청해도 연결 전에 거부합니다.
기존 누르고 있는 동안 입력하는 keyboard_drive dry-run과 camera/line beta는 그대로 유지했습니다. 새 C2와 실차 연결은 하지 않았습니다.

기존 PlatformIO와 WSL g++가 설치되어 있다면 한 번에 컴파일까지 검사합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_bench_checks.ps1 -Firmware -Native
```

이 명령에는 upload target이 없습니다. 컴파일 성공이 장착된 Arduino의 프로그램과 같다는 뜻은 아닙니다.
generated `.hex/.elf`는 `firmware/mega_cart/.pio/build/mega_locked`에 있으며 Git에 넣지 않습니다.

## 7. 검증 결과와 한계

최종 소스로 `run_bench_checks.ps1 -Firmware -Native`를 실제 실행해 exit 0 및 BENCH_CHECKS_PASS를 확인했습니다.
이전 문서의 실제 카메라/Nav2 성공 기록을 이번 검증으로 재사용하지 않습니다.

| 검증 | 이번 결과 | 범위 |
|---|---|---|
| Windows Python core/keyboard/perception | 55/51/17개 통과, 합계 123개 | 새 bench 검사는 keyboard 51개 중 33개입니다 |
| Mega 2560 compile | 성공, RAM 1429B, Flash 11154B | 실제 AVR 대상 컴파일만 수행했습니다. 보드 실행/업로드 아님 |
| C++ host controller | 64개 assertion 통과 | address/undefined sanitizer 사용, GPIO 없음 |
| Python→C++ 계약 | 13개 응답 일치 | 같은 C++ 코어의 session/CRC·정지/재개 응답을 검사했습니다 |
| 실제 출력 활성화 매크로 | 의도한 컴파일 실패 확인 | CART_PHYSICAL_OUTPUT=1을 주면 source의 #error가 차단했습니다 |
| ROS2 colcon build | 3개 패키지 성공 | 별도 wafer_cart_ws, core/keyboard/mapping |
| ROS2 colcon test | 55/51/23개 통과 | Windows core/keyboard와 중복이며 실제 Nav2 goal 재시험은 아닙니다 |
| 가상 터미널/라인 pipeline | 통과 | 실제 센서·모터·로봇팔 입력을 사용하지 않았습니다 |

가상 콘솔 기록은 `data/output/bench_console_current.json`, C++ 계약 기록은 `data/output/bench_contract.json`입니다.
자동 생성 자료는 Git 제외입니다. 실측값·원본 firmware SHA256이 변경되지 않은 것도 확인했습니다.

발견한 문제와 처리:

1. PlatformIO cache lock 접근 권한 때문에 제한 환경의 첫 컴파일이 실패했습니다. 기존 도구를 사용한 컴파일 권한으로 재검사했으며 업로드하지 않았습니다.
2. C++ signed/unsigned 비교 경고를 수정했습니다. AVR 16-bit int의 V mix 곱셈은 int32_t로 계산해 중간 overflow를 피했습니다.
3. Arduino framework의 unused parameter 경고가 전체 Werror와 충돌했습니다. vendor를 고치지 않고 build_src_flags로 우리 소스에만 엄격한 검사를 적용했습니다.
4. 첫 colcon test는 source 경로 누락으로 0개 패키지만 실행했습니다. 기존 결과를 성공으로 사용하지 않고 --base-paths를 명시해 3개 패키지 테스트를 새로 실행했습니다.
5. PowerShell Host 예약 변수와 검사 옵션이 충돌했습니다. 옵션을 Native로 변경하고 최종 일괄 명령을 다시 통과시켰습니다.

기존 ROS2 workspace의 tracked/untracked 작업과 현재 README·docs/18·docs/hardware의 기존 변경은 자동 stage하지 않습니다.

이번 작업은 첫 구동시험용 소프트웨어 준비입니다. 실제 camera 사람 50cm 검증, 4초 자동재개와 새 serial의 정식 연결,
ROS Twist↔percent 실측 변환, 실제 encoder odom/TF·LiDAR SLAM·Nav2·UI·로봇팔 수량 연결은 이번에 완료한 것으로 보고하지 않습니다.
기존 ROS2/Nav2 mock 구성은 보존합니다.

## 8. 실제 구동 전에 남은 것

배선 담당자에게 전달할 빈칸형 요약은 [전원·배선 확인표](21_POWER_WIRING_CONFIRMATION_CHECKLIST.md)를 사용해 주세요. 작성 완료만으로 출력 잠금이 해제되지는 않습니다.

1. PCB-A 임시 구성인지 PCB-C·접촉기·비상정지까지 장착했는지 확인해야 합니다.
2. MDD10A revision, 주/보조 전압, 코일 공급, 극성·퓨즈·GND·부하·reset 시 신호를 담당자가 확인해야 합니다.
3. 피드백 pin·active level, 수동 재개 회로, motor/encoder 위치와 부호를 확인해야 합니다.
4. 승인된 출력 상한을 정하고, 해당 정보로 실제 HAL/전원 감시 profile을 구현·검증해야 합니다.
5. 업로드와 최초 구동 전에 담당자·받침·비상정지 준비를 다시 확인해야 합니다.

제조사 기준 확인: [Mega pinout](https://docs.arduino.cc/resources/pinouts/A000067-full-pinout.pdf),
[PlatformIO Mega 설정](https://docs.platformio.org/en/latest/boards/atmelavr/megaatmega2560.html),
[MDD10A 사양](https://www.cytron.io/cytron/p-10amp-5v-30v-dc-motor-driver-2-channels).

새 Markdown은 UTF-8 BOM, Python은 UTF-8입니다. 원본 vendor·기존 사용자 수정·실측 설정을 보존합니다.
파일 존재·크기·빈 파일·한글 깨짐·인코딩 검사를 완료했고, VSCode에 실제 디스크 문서/Python 파일을 여는 명령이 성공했습니다.
native UI 제어 제한으로 VSCode 화면 픽셀은 직접 검증할 수 없습니다.
파일 링크가 안 열리면 다음 명령을 사용하실 수 있습니다.

```powershell
code --reuse-window "C:\Users\H\Desktop\로봇 자율주행\wafer-cart-line-navigation\docs\20_PCB_FIRMWARE_BENCH_PREPARATION.md"
```
