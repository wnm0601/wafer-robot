엔코더 핀 탐색 진단 프로그램 (2026-10-09)

최신 장치 상태 (아래의 진단 펌웨어 잔존 기록은 당시 이력입니다)
2026-10-09 사용자 승인과 모터 OFF·USB만 연결 확인 후 진단 포함 수동 펌웨어로 교체했습니다.
Arduino COM7 현재 식별은 CART_2 HKX_20260929 MANUAL_UNMONITORED입니다.
Git126f706 mega_manual_legacy_5khz Flash13902bytes 업로드 및 flash 비교 검증 완료.
기존 inspect-real 진단1회 및 재연결2회/반복40회 정지·ENC·DIAG·IO 점검 통과.
앞선 조회시험에서는 ARM/POWER_ACK/M/V 전송없음. 출력0 유지, 종료 시 ESTOP 잠금 후 COM포트를 닫았습니다.
이후 사용자 승인으로 모터전원OFF 상태에서 채널1~4 각+1/-1% 총8회 실제 명령을 전송했습니다.
POWER_ACK/ARM/M 수락, 내부출력+2/-2, 해당OCR25·나머지0, DIR핀 읽기 정/역 기대값 일치.
각 STOP 후 비무장·출력0 확인, 마지막ESTOP 잠금 후 COM종료. V·전원인가 시험은 하지 않았습니다.
배선/드라이버 전기출력/실제회전 검증과 구분하며 기록은 data/output/diagnostic_commands_poweroff_20261009.log입니다.
현재는 이 폴더의 ENCODER_PIN_PROBE_V1이 장치에 남아 있지 않습니다.
현재 수동 펌웨어는 출력기능이 포함되므로 이전 핀탐색 전용 출력잠금과 구분하십시오.
이번에는 실제 모터 구동을 하지 않았습니다. 자세한 최신 결과는 docs/25_MANUAL_OUTPUT_CONNECTION.md.

목적
오른쪽 앞바퀴를 손으로 돌릴 때 실제 반응하는 입력 핀을 찾아,
예정 핀 D20/D33과 다르게 연결됐을 가능성을 조사합니다.
모터 출력 채널과 바퀴 위치를 자동 확정하거나 핀 설정을 자동 변경하지 않습니다.

출력 잠금
주행 펌웨어와 분리된 PlatformIO 프로젝트입니다.
PWM D11/D44/D12/D45와 DIR D34/D36/D35/D37은 LOW로 고정합니다.
Timer1/5 출력을 분리하고 타이머를 정지합니다. M/V/ARM 등 구동 명령은 없습니다.
Serial 입력은 모두 버립니다. 기존 주행 프로그램과 통신 호환되지 않습니다.
리셋/부트로더/업로드 중에는 이 소프트웨어 잠금이 동작하지 않습니다.
따라서 반드시 모터 전원을 물리적으로 OFF한 상태에서 업로드·검사하십시오.
24V를 Arduino 입력에 연결해서는 안 됩니다. 이 프로그램은 전압을 측정하지 않습니다.

준비된 코드만 빌드하는 명령 (업로드 아님)
cd "C:\Users\H\Desktop\로봇 자율주행\wafer-cart-line-navigation\firmware\encoder_pin_probe"
pio run -e mega_encoder_probe

실제 검사 순서 (업로드는 담당자 준비 확인 후 별도 실행)
1. 모터 전원을 OFF하고 Arduino는 USB로만 켭니다.
2. 주행 앱과 시리얼 모니터를 모두 닫습니다. 포트 소유자는 하나만 둡니다.
3. 담당자 준비 확인 후 이 진단 펌웨어를 업로드합니다. 기존 펌웨어가 교체됩니다.
4. 115200 baud 시리얼 모니터에서 ENCODER_PIN_PROBE_V1 배너를 확인합니다.
5. 아무 바퀴도 돌리지 않고 약 5초 관찰합니다. 잡음성 변화의 기준을 확인합니다.
6. 오른쪽 앞바퀴 본체와 중앙 허브만 천천히 약 5초 돌리고, 5초 멈춥니다.
7. 반대 방향으로 돌린 뒤 멈춥니다. 같은 바퀴로 최소 두 번 재현합니다.
8. 움직일 때만 반복적으로 증가하는 pin의 poll_rise/poll_fall/irq_rise를 비교합니다.
9. 종료 후 주행용 펌웨어를 복구하기 전 핀 결과를 검토합니다.
   현재 주행 소스의 M2 PWM 타이머 오류는 별도 수정·검증이 필요합니다.

표시 형식
P ms pin level poll_rise poll_fall irq_rise mode
카운트는 부팅 이후 누적값입니다. 최초 HIGH 레벨은 펄스로 세지 않습니다.
irq_rise는 D2/D3/D18/D19/D20/D21만 지원하며 다른 핀은 '-'입니다.
poll 카운트는 입력 변화가 관찰된 횟수이며 실제 엔코더 총 펄스/회전당 count가 아닙니다.
출력 중 샘플링 지연과 빠른 펄스 때문에 poll은 누락될 수 있습니다.
max_scan_gap_us는 부팅 이후 최대 스캔 간격이며, 지연을 판단하는 참고값입니다.
알려진 엔코더 핀만 기존처럼 INPUT_PULLUP, 나머지는 INPUT으로 읽습니다.
연결되지 않은 INPUT에는 잡음이 생길 수 있어 변화만으로 엔코더 핀을 확정하지 않습니다.
D13은 보드 LED, D20/D21은 I2C, D50~D53은 SPI와 공유하므로 주변장치 활동도 구분해야 합니다.
Serial·모터·램프 출력 핀, 아날로그 핀은 탐색 대상에서 제외합니다.
탐색 범위 밖으로 연결됐거나 신호가 없으면 이 검사만으로 핀을 찾을 수 없습니다.
무응답이어도 핀 불일치/전원/접촉/엔코더 고장을 코드만으로 구분할 수 없습니다.

현재 범위
PC/컴파일 검증과 아래 실제 업로드·수신 검사까지 수행했습니다.
실제 PWM LOW 전압과 모터 구동은 미검증입니다.

2026-10-09 검증 결과
Mega 2560 컴파일 성공: Flash 5672 bytes, RAM 706 bytes.
PC C++ 검사 통과: 후보 핀 중복/출력 핀 제외, 초기값 처리, 고정 입력,
양쪽 edge 변화, unsigned count wrap. AddressSanitizer/UndefinedBehaviorSanitizer 사용.
PC 검사는 실제 핀 신호나 PWM 전압 검증을 대신하지 않습니다.
빌드 도구에 PlatformIO 6.1.19/6.2.0 중복 경고가 있었지만 컴파일은 성공했습니다.
이 빌드 검증 단계에서는 Arduino 업로드와 모터 전원 투입을 하지 않았습니다.

2026-10-09 실제 진단 업로드·수신 결과
사용자가 모터 전원 OFF 준비 항목을 선택한 뒤 COM7 Mega 2560에 업로드했습니다.
장치 VID:PID 2341:0042, serial 85036313330351A0E0A0, signature 0x1e9801.
avrdude에서 5672 bytes 작성·검증 성공, 종료 코드 0, fuses FD/D8/FF.
실제 ENCODER_PIN_PROBE_V1 부팅 식별 문구를 수신했습니다.
첫 PC 수신은 보고서 중간부터 시작해 전체 핀 검사가 실패하고 포트를 닫았습니다.
부팅 식별 이전의 조각 수신을 무시한 재시도에서는 완전한 프레임을 받았습니다.
정지 기준 약 5초 + 오른쪽 앞 손 회전 안내 후 40초, 총 완전한 보고서 44개.
40개 후보 핀 모두 polling 상승/하강 증가량 0.
D3 IRQ 상승 증가량 6, 나머지 IRQ 지원 핀 D2/D18/D19/D20/D21은 0.
D20/D33은 기준·마지막 모두 HIGH. 전압을 측정한 결과가 아니라 디지털 읽기 결과입니다.
D3의 소수 IRQ는 핀 연결 확정 근거가 아닙니다. 짧은 펄스·잡음·다른 바퀴 움직임 등은 미확정입니다.
정지 기준 polling 변화는 없었으며 D3 기준 IRQ도 0이었습니다.
PC에서 시리얼 명령은 보내지 않았고 마지막에 COM7을 닫았습니다.
현재 Arduino에는 진단 펌웨어가 남아 있습니다. 주행용 펌웨어를 자동 복구하지 않았습니다.
권장 다음 검사: 기존에 반응한 왼쪽 뒷바퀴만 같은 진단으로 돌려 D3/D30을 비교한 뒤
오른쪽 앞 재검사와 실제 엔코더 커넥터·전원·A/B 연결을 확인하십시오.

2026-10-09 왼쪽 뒷바퀴 비교 검사
모터 전원 OFF 유지 안내 후 기존 진단 펌웨어를 그대로 사용했습니다. 추가 업로드 없음.
COM7 장치 식별과 ENCODER_PIN_PROBE_V1 배너를 다시 확인했습니다.
정지 기준 약 5초 동안 polling 및 IRQ 변화 없음.
왼쪽 뒷바퀴 손 회전 안내 후 40초, 완전한 보고서 총 44개.
D3: polling 상승 428 / 하강 427 증가, IRQ 상승 531 증가.
D30: polling 상승 427 / 하강 427 증가.
D2: polling 상승/하강 각각 7, IRQ 상승 11 증가.
D4: polling 상승/하강 각각 7 증가.
D2/D4는 INPUT 모드이므로 연결되지 않은 입력의 잡음이나 유도 신호일 수 있습니다.
그 밖의 후보 핀은 polling/IRQ 변화 없었습니다. D20/D33도 변화 없었습니다.
polling과 IRQ 차이는 보고서 출력 중 스캔 누락 등으로 생길 수 있습니다.
카운트를 회전당 count나 실제 이동 거리로 환산하지 않았습니다.
PC 시리얼 명령 전송 없음, 종료 시 COM7 닫힘 확인.
판단: 같은 진단 코드로 왼쪽 뒤 ENC1의 D3/D30 반복 신호를 읽는 것은 확인했습니다.
오른쪽 앞에서는 반복 A/B 신호를 찾지 못했으므로 핀 불일치만으로 단정하지 않습니다.
오른쪽 앞 신호 경로의 전원·커넥터·A/B 배선·엔코더와 Arduino 해당 입력을 추가 확인해야 합니다.
입력 전압/연속성/오실로스코프 검증 및 모터 출력 검증은 하지 않았습니다.
현재 장치는 계속 진단 펌웨어이며 주행 펌웨어 복구와 M2 타이머 오류 수정은 미실행입니다.

2026-10-09 이후 주행 코드의 M2(오른쪽 뒤 추정) PWM 오류 수정
주행 소스에서 D44를 잘못 제어하던 OCR5A/COM5A1 대신 OCR5C/COM5C1을 사용하도록 수정했습니다.
시작 시 OCR5C 초기값도 0으로 설정했습니다. 기존 핀 번호와 엔코더 처리 방식은 변경하지 않았습니다.
실제 main.cpp를 가상 레지스터 환경에서 실행하는 회귀시험을 추가했습니다.
수정 전 시험: M2(오른쪽 뒤 추정)의 OCR5C 설정 검사에서 예상대로 실패.
수정 후 시험: 채널별 PWM, 정지 출력 분리, 반전, 다른 채널 독립성, 시작값 검사 통과.
기존 C++ 제어 검사 100개, Python/C++ 응답 계약 13개, Python 단위시험 83개 통과.
mega_locked / mega_manual / mega_manual_no_feedback 컴파일 모두 성공.
기존 scripts/verify_bench_host.sh에 PWM 회귀시험을 포함했습니다.
주의: PC 시험은 실제 D44 파형을 측정한 것이 아닙니다. 수정 펌웨어를 업로드하지 않았습니다.
Arduino에는 여전히 진단 펌웨어가 남아 있습니다. 실제 구동 전 별도 준비 확인·복구가 필요합니다.
모터/엔코더를 같은 번호로 연결했다는 조건의 위치표:
M1(왼쪽 뒤 추정), M2(오른쪽 뒤 추정), M3(왼쪽 앞 추정), M4(오른쪽 앞 추정).
이 표는 실제 모터 출력 시험으로 확정하지 않았으며 주행용 4륜 매핑도 활성화하지 않았습니다.

2026-10-09 수정한 수동 주행 펌웨어 복구 업로드
담당자가 모터 전원 OFF·Arduino USB만 연결 상태를 확인한 뒤 수행했습니다.
source commit 7f3dd47, profile mega_manual_no_feedback, COM7.
Mega 2560 VID:PID 2341:0042, serial 85036313330351A0E0A0, signature 0x1e9801.
flash 12510 bytes 작성·검증 성공, avrdude 종료 성공, fuses FD/D8/FF.
업로드 빌드의 Flash 12510 / RAM 1650 bytes. PlatformIO 중복 버전 경고는 남아 있습니다.
실제 INFO 응답 CART_2 HKX_20260929 MANUAL_UNMONITORED 확인.
STATUS 5회 모두 STARTUP_LOCKED, power Unknown(0), armed 0, LIMIT 1,
M1(왼쪽 뒤 추정)·M2(오른쪽 뒤 추정)·M3(왼쪽 앞 추정)·M4(오른쪽 앞 추정)의 펌웨어 출력값 모두 0.
ENC 응답 5회 모두 [0,0,-1,0]. 정지 수신에서 변하지 않았습니다.
이 응답은 손 회전 또는 실제 모터 구동 검사가 아닙니다. ENC4 문제는 미해결입니다.
POWER_ACK/ARM/M/V는 보내지 않았습니다. 종료 처리에서 ESTOP 후 COM7을 닫았습니다.
전원 피드백은 감시하지 않으며 power Unknown을 실제 OFF 판정으로 표현하지 않습니다.
PWM 전압·파형·모터 회전·전기적 정지는 측정하지 않았습니다.
첫 실제 출력 전에 받침대·바퀴 주변·독립 전원 차단·담당자 준비를 다시 확인해야 합니다.

2026-10-09 키 홀드 수동 시험 방식 추가 (PC 프로그램 변경만)
실차 실행 명령은 이전과 같습니다. 기존 앱은 모터 전원 OFF 후 닫고 재실행해야 합니다.
cd "C:\Users\H\Desktop\로봇 자율주행\wafer-cart-line-navigation"
py -3.13 scripts\manual_first_drive.py --real --port COM7 --no-power-feedback
처음 CONNECT COM7 확인을 하면 단일 모터 키 홀드 세션을 설정합니다.
이 확인 자체는 POWER_ACK/ARM/M/V를 보내지 않으며 모터를 움직이지 않습니다.
화면에서 모터를 선택하고 출력 명령을 설정한 뒤 새로 누른 ↑/↓로 동작합니다.
매번 수동 준비 버튼을 누르거나 전원 확인 팝업에 답할 필요는 없습니다.
시작 출력 1%, 기존 상한 40%. 명령값은 실제 속도나 안전 승인값이 아닙니다.
키를 놓으면 STOP. Space는 STOP, X는 오류 잠금이 유지되는 소프트웨어 ESTOP입니다.
정지·모터 선택·포커스 이탈 후에는 이미 누르고 있던 키의 자동반복을 차단합니다.
키를 완전히 놓고 새로 눌러야 다시 동작하며 감속 중 키 입력을 나중에 자동 실행하지 않습니다.
각 새로운 키 홀드에서 상태 확인 및 펌웨어의 일회 POWER_ACK/ARM 절차를 수행합니다.
오류가 나면 최초 명령·오류·gateway 원인을 보존하고 확인 세션을 무효화합니다.
다른 버튼을 눌러도 최초 오류가 지워지지 않습니다. 모터 전원 OFF 후 앱을 다시 연결해야 합니다.
기존 수동 준비 버튼 직후 오류의 실제 최초 원인은 기록 소실로 아직 확정하지 못했습니다.
이번 변경은 반복 확인창 경로를 제거하고 최초 오류를 보존하며 안전 잠금을 유지한 것입니다.
전원/물리 비상정지 피드백은 여전히 없으므로 전원 차단·복구 전에 키를 놓고 앱을 닫아야 합니다.
현재 펌웨어 그대로 사용할 수 있으며 이 변경을 위한 Arduino 재업로드는 하지 않았습니다.
4륜 위치·방향 매핑은 여전히 잠금, ENC4 무응답은 미해결입니다.
실제 GUI 화면·물리 키 홀드·모터 회전 검증은 이번 작업에서 하지 않았습니다.
UI 핸들러는 창 없이 호출해 Space 자동반복 차단·모터 선택 정지·최초 오류 보존을 검증했습니다.
PC C++ 펌웨어 통합시험은 --keyboard-hold로 실행하며 실제 COM을 열지 않습니다.
이번 변경 후 Python 단위시험 98개 통과, 수정 Python 파일 구문 검사 통과.
PC C++ 키 홀드 통합시험 6항목, 기존 MANUAL_ONLY 6항목 및 MANUAL_UNMONITORED 7항목 통과.
주입한 통신 실패로 잠금·최초 오류 보존·재시작 차단을 확인했습니다. 실제 기기 오류가 아닙니다.

2026-10-09 전버전 가감속 비교 및 별도 시험 빌드 (업로드 안 함)
사용자가 실제 구동했던 코드로 확인한 Documents/카카오톡 받은 파일/main.cpp 전체를 읽었습니다.
핀 PWM {11,44,12,45}, DIR {34,36,35,37}, ENC A {3,18,19,20}는 현재와 같습니다.
전버전은 A상만 명령 부호로 카운트하며 현재는 A/B로 실제 커넥터 부호를 셉니다.
전버전: RAMP_STEP=8 / 15ms, MAX_DUTY=200, OCR=mag*4095/255.
현재 기본: RAMP_STEP=2 / 15ms, DUTY_SCALE=200, OCR=mag*4095/200.
40% 명령은 내부 목표 80입니다. 전버전 실제 PWM 듀티는 약31.4%, 현재는40%입니다.
UI 마지막 출력 64는 내부 크기이지64%가 아니며, 실제 전압·전류 측정도 아닙니다.
전버전에는 encoder 무변화 정지가 없지만 현재는600ms 무변화로 잠깁니다.
이 차이는 원인 후보이지 실제 전원/배선/모터 고장의 확정 진단이 아닙니다.
별도 mega_manual_legacy_ramp는 전버전 ramp8 및 /255 환산만 적용합니다.
기본 mega_manual_no_feedback는 변경하지 않으며 명령CRC·ARM·40%상한·500ms lease·600ms stall은 유지합니다.
한 모터씩 기존 화면 ↑/↓로 시험하며 미확정4륜 매핑은 여전히 잠깁니다.
새 빌드의 MCU INFO는 기존 MANUAL_UNMONITORED와 같아 이 응답만으로 빌드 구분은 불가능합니다.
업로드 전 모터 전원 OFF·Arduino USB만·담당자 확인·앱/시리얼 모니터 종료가 필요합니다.
준비 확인 후 사용할 업로드 명령 (이번 작업에서는 실행하지 않았습니다):
pio run -d firmware\mega_cart -e mega_manual_legacy_ramp -t upload --upload-port COM7
업로드가 성공한 뒤 기존 앱 명령:
py -3.13 scripts\manual_first_drive.py --real --port COM7 --no-power-feedback
롤백은 mega_manual_no_feedback 프로필을 모터 전원 OFF에서 다시 업로드합니다.
이번 빌드 Flash12508/RAM1650 bytes 성공, PlatformIO 중복 버전 경고는 남아 있습니다.
C++ 기존100검사 및 Python/C++13응답 통과, 기존/전버전 PWM AVR어댑터 검사 모두 통과.
신규 ramp 시험:40%목표에 모의150ms 도달, STOP 후0, 엔코더 무변화로 여전히 잠김 확인.
실제 전압·PWM파형·회전은 미검증입니다. 급한 요청이어도 바로 회전한다고 보장하지 않습니다.

2026-10-09 전버전 ramp 시험 빌드 실제 업로드 완료
사용자가 모터 전원 OFF·Arduino USB만 연결을 확인하고 업로드를 승인했습니다.
첫 시도는 COM7 접근 거부로 실패했으며 기존 manual_first_drive.py 프로세스 실행을 확인했습니다.
사용자가 조작 앱을 닫은 뒤 재시도: mega_manual_legacy_ramp / source0a79370 / COM7.
avrdude signature0x1e9801, Flash12508 bytes 작성 및 읽기 검증 성공, fusesFD/D8/FF, 종료0.
--inspect-real 실행 종료0: INFO CART_2 HKX_20260929 MANUAL_UNMONITORED.
STATUS STARTUP_LOCKED / powerUnknown / armed0 / LIMIT1 / 네 출력0 확인.
ENC [0,0,-1,0] 한 번 수신. 실제 회전 또는 손회전 검증은 아닙니다.
motion_commands_sent=false; ARM/M/V를 보내지 않았고 정지 검사 후 포트를 닫았습니다.
현재 Arduino에는 legacy_ramp 시험 빌드가 있습니다. 실제 전압·전류·회전은 여전히 미검증입니다.

2026-10-09 담당자 승인 단일 출력 시험 (실제 명령 전송)
사용자가 받침대·차단 담당자 준비를 확인하고 M3(왼쪽 앞 추정)20%·0.5초를 승인했습니다.
COM7 INFO 일치, 초기STATUS STARTUP_LOCKED/powerUnknown/armed0/LIMIT20/네 출력0 확인.
초기ENC [0,0,-1,0]. POWER_ACK/ARM 후 M 3 20 정상 응답을 받았습니다.
별도타이머의 raw ESTOP 전송 시간은 시작 후0.5094초였습니다(PC 타이밍은 정밀0.5초 보장이 아닙니다).
이후 상태 수집은 stale, duplicate or mismatched ACK로 중단되었습니다.
raw ESTOP 응답과 framed ACK 경합 가능성이 있으나 정확한 원인은 미확정입니다.
종료 경로에서도 ESTOP을 전송하고 포트를 닫았습니다. 담당자에게 모터 전원 OFF를 요청했습니다.
구동 없이 --inspect-real 재연결: STARTUP_LOCKED/armed0/네 출력0 확인, ENC [0,0,-1,0].
재연결은 MCU를 리셋하므로 이ENC를 시험 중 카운트 변화의 증거로 사용하지 않습니다.
실제 회전 여부는 담당자 관찰 확인이 필요하며 물리정지·전압·전류를 측정하지 않았습니다.

2026-10-09 이전 웹캠·LiDAR 버전 5kHz PWM 현재핀 적용 (모의시험만)
별도 mega_manual_legacy_5khz: Timer1/5, TOP3199, prescaler1, 분모255, ramp8/15ms.
PWM {11,44,12,45}, DIR {34,36,35,37} 유지. D44는 OC5C, D46은 출력하지 않습니다.
이전 Timer3/4와 동일한 주파수/환산을 현재 PCB용 Timer1/5로 설정했습니다.
기본 TOP4095(3906.25Hz) 및 기존 프로필은 유지합니다.
새 모의시험은 수정 전 TOP 불일치를 실제 실패로 검출했습니다.
수정 후 3프로필 AVR어댑터시험 통과: 기본3.9kHz/기존legacy3.9kHz/새legacy5kHz.
검사항목: TOP·mode14·prescaler1·계산주파수·각OCR·방향·정지·채널 독립·시작값.
기존 제어100검사, ramp/STOP/stall 회귀, Python/C++13응답 시험도 통과했습니다.
이 검증은 실제 핀의 파형 측정이 아니며 주파수가 회전 실패 원인이라고 확정하지 않습니다.
ARM·CRC·lease500ms·stall600ms·미확정4륜 잠금은 그대로입니다.
새5kHz 빌드는 이번 작업에서 Arduino에 업로드하지 않았고 COM도 열지 않았습니다.
현재 실제Arduino는 이전에 업로드한 mega_manual_legacy_ramp(3.9kHz) 그대로입니다.
mega_locked/mega_manual_legacy_ramp/mega_manual_legacy_5khz 세 빌드 컴파일 모두 성공.
새5kHz Flash12508/RAM1650 bytes. PlatformIO 중복버전 경고는 남아 있습니다.

2026-10-09 현재PCB 5kHz 시험 빌드 업로드 완료
사용자가 모터 전원 OFF 업로드를 선택했습니다. COM7 Mega VID:PID2341:0042/serial85036313330351A0E0A0 확인.
조작 앱/serial-monitor 관련 프로세스는 사전 검사에 표시되지 않았습니다.
source76244f6, profile mega_manual_legacy_5khz, signature0x1e9801.
Flash12508 bytes 작성 및 읽기 검증 성공, fusesFD/D8/FF, 업로드 종료0.
--inspect-real 종료0: INFO CART_2 HKX_20260929 MANUAL_UNMONITORED.
STATUS STARTUP_LOCKED/powerUnknown/armed0/LIMIT1/네 출력0, ENC [0,0,-1,0].
ARM/M/V를 보내지 않았습니다. 종료 시 ESTOP 후 포트를 닫았습니다.
현재 실제Arduino는 mega_manual_legacy_5khz입니다. INFO문자열만으로 주파수를 구분하지는 못합니다.
업로드 검증은 실제 PWM파형·전압·모터 회전 검증이 아닙니다. 실제 구동은 수행하지 않았습니다.

2026-10-09 시험용 encoder 무변화 감시1500ms 적용 및 업로드
사용자 요청으로 mega_manual_legacy_5khz에만 CART_STALL_MS=1500 적용했습니다.
기본 및 다른프로필은600ms 유지. 키 해제STOP/통신lease500ms/ESTOP/40%상한은 변경하지 않았습니다.
출력 상승 구간도 감시시간에 포함되며 엔코더 변화가 있으면 시간 기준이 갱신됩니다.
1500ms는 실측 안전 기준이 아닌 임시 시험값이며 정지감지 지연 위험이 커집니다.
PC600/1500ms 경계시험·기존100검사·PWM3프로필·Python/C++13응답 모두 통과.
사용자가 모터 전원OFF·ArduinoUSB만·조작 앱 종료를 다시 확인했습니다.
COM7 Mega signature0x1e9801, Flash12508 bytes 작성 및 읽기검증 성공, fusesFD/D8/FF, 업로드 종료0.
PlatformIO 중복버전 경고는 남아 있습니다. 실제 모터 구동은 하지 않았습니다.
업로드 후 --inspect-real 종료0: STARTUP_LOCKED/powerUnknown/armed0/LIMIT1/네 출력0.
ENC [0,0,-1,0], motion_commands_sent=false 확인. 종료 후 포트는 닫았습니다.

2026-10-09 실제Arduino 상한/정지수신 간격 점검 (구동 없음)
사용자가 모터OFF·앱종료·ArduinoUSB만 확인했습니다. COM7 재연결 후 최초상한1 확인.
정지 상태에서40%상한 설정을 정상수락하고 STATUS의limit40을 확인했습니다.
이는 이전 오류 당시 상한값을 복원한 것이 아닙니다. 재연결은 MCU를 리셋할 수 있습니다.
키입력 없는 ManualHardware.tick(STATUS+ENC)30회, 각회 후25ms대기 측정.
수신처리시간 min65.72/mean70.57/max82.19ms; 시작간격 min91.91/mean96.43/max107.91ms.
네 출력0·armed0·STARTUP_LOCKED 유지, ENC [0,0,-1,0]. ARM/M/V는 보내지 않았습니다.
GUI렌더링·실제M전송을 포함하지 않은 측정이므로 실제주행 명령간격 증거로 확장하지 않습니다.
40%지원 및 정지통신은 확인됐지만 실제MOTION_REJECTED 원인은 아직 확정되지 않았습니다.
키입력부터ARM/M/STATUS/ENC/비동기event까지 같은세션의 계측이 다음 진단에 필요합니다.

2026-10-09 GUI 없는 Python 터미널 수동 모드 추가
py -3.13 scripts\manual_first_drive.py --real --port COM7 --no-power-feedback --terminal --percent 20
최초 CONNECT COM7 입력 후 키를 모두 놓습니다. 현재 터미널 창의 포커스를 유지합니다.
↑/↓: 선택한 한 모터 홀드. 1~4: 모터 선택. +/-: 정지 후5%씩(1~40%).
Space:정지, X/Esc:비상정지·종료, Ctrl+C:종료 경로ESTOP. 포커스 이탈 시STOP.
M1(왼쪽 뒤 추정), M2(오른쪽 뒤 추정), M3(왼쪽 앞 추정), M4(오른쪽 앞 추정).
모터 선택 후 이미 누르던 방향키는 놓고 새로 눌러야 합니다. 시작 출력 기본1%입니다.
Tk/지도/카메라 렌더링 없이 기존Python drive/gateway/Arduino프로토콜을 그대로 사용합니다.
ARM·stall1500ms(업로드된5kHz빌드)·500mslease·4륜잠금은 유지하며 Arduino 재업로드는 필요하지 않습니다.
터미널 루프400ms 이상 지연 시 중단합니다. 실제 물리정지 보장은 없으므로 담당자 차단 준비가 필요합니다.
실행별 data/output/manual_terminal_날짜_시간.jsonl에 키·출력설정·status·encoder·cycle/error 기록.
기록은 내부 출력/응답이며 실제 전압·속도·물리회전 측정이 아닙니다.
--terminal-smoke: 실제C++ PC모의제어로 시작정지/키홀드/Space재시작차단/선택/포커스/ESTOP 통과.
기존 test_manual*.py41개 회귀 및 Python구문검사 통과. GUI원인 확정 또는 실제 터미널 키입력 검증은 아닙니다.
이번 작업에서 실제COM을 열지 않았고 업로드·모터 구동도 하지 않았습니다.

2026-10-09 전체 무구동 진단 (현재 확인 결과)
사용자가 모터 전원OFF·ArduinoUSB만·조작 앱 종료를 확인했습니다.
COM7 Mega signature0x1e9801, avrdude -n -D flash:v 읽기 비교 종료0.
현재 mega_manual_legacy_5khz HEX의12508bytes가 실제flash와 일치했습니다. 쓰기/삭제/업로드 없음.
HEX SHA256 8C1458E2A45439D8EE3A39BEE74277CCD046CFD42541973D323432967BFACB1F.
컴파일된ELF에서 출력값 읽기·TOP3199/분모255 환산·OCR1A/5C/1B/5B 쓰기를 확인했습니다.
Timer1/5 mode14·prescaler1 설정 및 apply_outputs 호출이 있습니다. 출력 잠금 빌드가 아닙니다.
설치된Mega core핀표 및 기존PCB검토표 대조: PWM11/44/12/45, DIR34/36/35/37 일치.
D44는OC5C입니다. 실제 배선 일치·GPIO파형·드라이버 전압을 측정했다는 뜻은 아닙니다.
새 PC시험: 제어100검사, PWM3프로필, ramp/STOP, stall600/1500ms 경계, Python/C++13계약 통과.
Python unittest98개 통과 및 --terminal-smoke 통과. GUI/실차 주행 시험은 아닙니다.
실제 INFO CART_2 HKX_20260929 MANUAL_UNMONITORED; STATUS/ENC25회 확인.
MCU1817~4172ms 구간 STARTUP_LOCKED·armed0·limit1·네 출력0 유지, ENC [0,0,-1,0] 변동없음.
ARM/M/V 명령은 전송하지 않았습니다. 종료 시 안전ESTOP 후COM포트를 닫았습니다.
정지 중 안정성만 검증했으며 바퀴 회전 시 encoder 반응은 이번에 시험하지 않았습니다.
코드 문제: receive의 선행tick에서stall/lease 정지 후 M이 도착하면 MOTION_REJECTED로 원인이 덮일 수 있습니다.
호스트 오류 처리ESTOP도 MCU상태를 OPERATOR_ESTOP로 바꿉니다. 최초 원인 보존 보완이 필요합니다.
최근 terminal로그는 M3(왼쪽 앞 추정)20% 명령과 내부출력40/255 및 encoder무변화를 보여줍니다.
약1.5초 후 거부는stall 후 원인 덮임과 부합하지만, 당시 최초event기록이 없어 확정하지 않습니다.
남은 사항: 실제PWM/DIR·드라이버입력전원·공통GND·커넥터연속성, A8차단피드백, ENC4반응, 출력모터 위치.
M1(왼쪽 뒤 추정), M2(오른쪽 뒤 추정), M3(왼쪽 앞 추정), M4(오른쪽 앞 추정): 출력 위치는 미검증입니다.
진단 요청 범위에서 코드 수정/안전잠금 해제/실제 구동은 하지 않았습니다. 전체 무결함 판정은 불가합니다.

2026-10-09 MOTION_REJECTED 원인 덮임 PC재현
실제 COM/Arduino에 접근하지 않고 현재C++제어소스를 PC에서 실행했습니다.
진단 artifact data/output/bench_build/diagnose_rejected.cpp (ignored, 제어코드 수정 없음).
현재프로필과 같은 ramp8/15ms, limit40, stall1500ms 설정. 가상 M3명령20%, encoder무변화.
150ms마다 명령을 갱신해lease500ms 만료를 배제했습니다.
1515ms STALL_NO_ENCODER 확인 → 다음M명령 ERR M MOTION_REJECTED → ESTOP 후 OPERATOR_ESTOP.
세 단계assert 통과. 오류원인 덮임을 현재코드로 재현했으며 실제모터 구동은 없습니다.
실제저장로그 manual_terminal_20261009_141846.jsonl: M3(왼쪽 앞 추정)20% 수락11회.
수락기록 구간1.4888603초, ENC [0,0,-1,0] 그대로, 최대 moving cycle205.6934ms.
초기ARM 또는20%상한 위반보다는 stall후 원인덮임이 가장 유력합니다.
기존로그에는 최초비동기event가 없어 당시 실제최초원인을 확정할 수는 없습니다.
이 진단은 엔코더무변화에 의한 거부경로를 설명하며 모터가 움직이지 않은 전기적/기계적 원인은 미확정입니다.
업로드/안전잠금해제/제어소스수정은 하지 않았습니다.

2026-10-09 A/B 분리 확인 준비: 전용 진단 재업로드
사용자가 모터 전원OFF·USB만·앱종료 및 진단 업로드를 승인했습니다.
COM7 VID:PID2341:0042/serial85036313330351A0E0A0, Mega signature0x1e9801.
mega_encoder_probe 빌드 성공 Flash5672/RAM706. 작성 및 읽기 검증5672bytes 성공, fusesFD/D8/FF.
PlatformIO 중복Core 경고는 남아 있습니다. 업로드 종료0.
수신 확인 과정의PC 인자따옴표오류 및 제목행파싱오류는 수정해 재시도했습니다. 진단소스 변경 없음.
최종읽기7초: ENCODER_PIN_PROBE_V1 OUTPUT_LOCKED NO_DRIVE_COMMANDS 배너, FRAME6개 확인.
5000/6000ms 입력level: A(D3,D18,D19,D20)=[1,0,1,1], B(D30,D31,D32,D33)=[0,1,0,1].
두 프레임의poll rise/fall 모두0. D19 irq누적1은 두 프레임에서 고정이며 회전증거가 아닙니다.
정지level 수신만 확인했으며 A/B 회전응답 정상판정은 아직 아닙니다. 손회전시험 대기.
시리얼에 명령을 쓰지 않았고 읽기 후COM포트를 닫았습니다. 모터전원OFF 유지가 필요합니다.

2026-10-09 왼쪽 앞바퀴 A/B 손 회전 수집
사용자 왼쪽 앞 준비 선택 후 회전 안내, 출력잠금 진단펌웨어에서25초 읽기 수행.
초기 대화형입력 대기는 stdin EOF로 종료되어 읽기전용 시간제수집으로 재실행했습니다.
실제식별 확인, 완전FRAME23개(MCU1000~23000ms) 수신. 구동명령 전송없음, 포트종료.
MCU1000~18000ms: 알려진A/B poll변화0, D19 irq1은 시작부터 고정.
MCU19000~23000ms: D19(A) poll rise690/fall691, irq775(기준1 대비774 증가).
D32(B) poll rise690/fall689. 다른38개 후보핀 변화없음.
판정: 왼쪽 앞 손 회전 중 ENC3 D19/D32 두 입력 모두 반응함.
M3(왼쪽 앞 추정)의 모터출력 위치/구동성공을 증명하지는 않음.
poll은irq보다 누락될 수 있어 회전당count로 사용금지. A/B 위상·방향정확도 및 정지후안정성은 별도시험 필요.
현재 Arduino는 진단펌웨어 상태 유지. 나머지바퀴 및 주행펌웨어복구는 미완료.

2026-10-09 오른쪽 앞바퀴 A/B 손 회전 수집
사용자 오른쪽 앞 준비 선택 후 회전안내, 모터OFF 상태의 진단펌웨어에서30초 읽기 수행.
식별확인, 완전FRAME28개(MCU1000~28000ms). 전체40개 후보핀 rise/fall/irq 변화없음.
예정 ENC4 D20(A)/D33(B)는 모두HIGH 고정, 변화횟수0.
포트를 닫았고 명령은 전송하지 않았습니다. Arduino는 출력잠금 진단펌웨어 유지.
실제 수집구간에 허브/본체가 함께 회전했는지 사용자 확인 요청 중입니다.
본체회전과 수집시점이 확인되기 전 고장/배선문제로 확정하지 않습니다.
동일조건에서 앞선 왼쪽 앞은 D19/D32 반응이 있었으나, 오른쪽 앞의 무응답 원인은 미확정입니다.
사용자 답변: 안내를 늦게 봐서 첫수집 중 돌리지 못함. 첫수집은 손회전 무반응 근거에서 제외합니다.
재시험: COM7에서진단식별/완전FRAME3개를 먼저확인한 후 손회전 시작을 안내했습니다.
60초 읽기에서 FRAME58개(MCU1000~58000ms), 전체후보핀 변화없음, D20/D33 HIGH고정.
두번째수집 때 실제로 허브/본체를 돌렸는지 아직 사용자확인 전이며 고장으로 확정하지 않습니다.
읽기완료 후 포트종료, 명령전송없음. 출력잠금 진단펌웨어 유지.

2026-10-09 왼쪽 뒷바퀴 A/B 수집
사용자 요청으로 오른쪽 앞은 미확정으로 남기고 뒷바퀴검사로 진행했습니다.
출력잠금 진단식별과 FRAME3개 확인 후 왼쪽 뒤 본체/허브 회전안내.
60초 수집에서 완전FRAME58개(MCU1000~58000ms), 전체40개 후보핀 변화없음.
예정 ENC1 D3(A)=HIGH, D30(B)=LOW 고정. 회전수집 중 실제본체회전 여부는 사용자확인 전.
무변화관측만 기록하며 엔코더고장/핀오류로 확정하지 않습니다.
COM7읽기종료, 명령전송없음. 현재 진단펌웨어 유지. 오른쪽 뒤는 이번 순서에서 아직 검사하지 않았습니다.

2026-10-09 오른쪽 뒷바퀴 A/B 손 회전 수집
사용자 오른쪽 뒤 검사요청, 모터OFF 출력잠금 상태에서60초 읽기, FRAME58개 수신.
진단식별/수집준비 확인 후 오른쪽 뒤 허브/본체 회전을 안내했습니다. MCU3000ms부터 입력변화 감지.
MCU1000~58000ms: D18(A) poll rise1636/fall1635, irq2128 증가.
D31(B) poll rise1635/fall1636 증가. 두 입력의 반복변화 확인.
마지막5개FRAME은 모든누적값이 같아 추가변화없음.
D4 rise2/fall3, D5와D28 각rise1/fall1의 소수변화도 관측됨.
이 핀들은 INPUT_FLOAT_POSSIBLE이며 해당소수변화를 엔코더연결로 판단하지 않습니다.
오른쪽 뒤 검사에서 ENC2 D18/D31 반응확인. 출력채널 M2(오른쪽 뒤 추정)의 실제구동을 증명하지는 않음.
누적값은 회전당count가 아니며 poll누락 존재. A/B정확한위상/방향은 별도검증 필요.
구동명령전송없음, COM7종료, 진단펌웨어 유지. 왼쪽앞/오른쪽뒤 반응확인, 나머지두바퀴 미확정.

2026-10-09 코드 진단 확장 완료 (미업로드)
주행펌웨어 DIAG: 최초오류·MCU시각·차단직전출력/ENC 보존, STOP/ESTOP 후에도 유지, 성공ARM/리셋에서 초기화.
IO: Timer1/5와OCR·DDRB/L/C·PORTC/PINC·내부출력 읽기. 실제전압/파형 측정이 아님.
터미널 --diagnostics: 시작전정지진단, 오류후최초원인/레지스터/최근128송수신 기록. 주행중반복조회 없음.
새주행펌웨어가 필요한 선택옵션이며 현재 ENCODER_PIN_PROBE_V1과 호환되지 않음.
PC101테스트, C++100검사/PWM3프로필/600·1500ms경계/새진단회귀, 계약13응답, 터미널 모의시험 통과.
Mega locked/legacy5kHz 컴파일 성공 Flash13634/13902bytes, RAM1876bytes. PIO중복Core경고 유지.
새 상세오류가STATUS필드를 깨뜨리는 회귀를 검출·수정하고 통과확인. 기존사용자/카메라수정 보존.
현재 작업에서는 COM접근·업로드·모터출력을 하지 않았습니다. Arduino는 출력잠금 엔코더진단 상태 유지.
자세한 실행/한계는 docs/25_MANUAL_OUTPUT_CONNECTION.md의2026-10-09절을 참고하십시오.
