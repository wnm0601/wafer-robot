# HKX 쉴드·PCB-A 핀 및 실차 연동 검토

검토일: 2026-09-29 KST. 사용 스킬: pdf. 제공 PDF 4쪽의 텍스트와 렌더링을 모두 확인했습니다.
이 문서는 설계·코드 대조 기록입니다. PCB 실물 검증, 실측 완료, 모터 구동 승인으로 사용하지 않습니다.

### 추가 결정: PDF 쉴드 핀을 개발 기준으로 채택 (2026-09-29)

사용자 확인: "핀번호 바뀐거 맞고 실제 사진없어도 괜찮아 저대로 갈거야".
이에 따라 PDF의 변경된 HKX 쉴드·PCB-A 설계를 향후 개발 기준으로 채택합니다. PCB 사진 제출을 소프트웨어 준비의 선행 조건으로 두지 않습니다.

- 모터 배열: PWM=[11,44,12,45], DIR=[34,36,35,37].
- encoder 배열: A=[3,18,19,20], B=[30,31,32,33]. M1~M4는 ENC1~ENC4에 대응하는 설계를 기준으로 합니다.
- 램프 D14~D17, 전압 입력 A3 및 connector 변경은 아래 문서 표를 기준으로 합니다. 램프 색상과 실제 동작 레벨은 미확정입니다.
- 기준 선택과 실물 검증은 구분합니다. 실제 배선·업로드 상태, 바퀴 위치별 대응·count/rev·부호·속도·정지거리는 여전히 미검증입니다.
- 이번 반영은 문서와 비활성 참고 JSON뿐입니다. 원본 firmware, 실측 설정, runtime 제어는 변경하지 않았으며 firmware 업로드와 실제 모터 구동을 승인받은 것으로 취급하지 않습니다.

### 추가 확인: 보드·배터리·접촉기와 PWM 주파수 (2026-09-29)

사용자 답변으로 다음 구성을 기록합니다. 구성 확인은 현물 배선·전압·차단 시험의 완료와 구분합니다.

| 항목 | 사용자 확인 내용 | 남은 확인 |
|---|---|---|
| 제어 보드 | Arduino Mega 2560 | 장착 보드 식별과 실제 업로드본 |
| 모터 드라이버 | MDD10A 2개 | 제품 revision과 장착 상태 |
| 주 배터리 | VOLTON, nominal 24V, 10Ah, 전체 전원부 공급. 최대 충전전압은 29.4V로 알고 계신다고 답변 | 29.4V는 사용자 보고값이며 미실측. 정확한 모델·화학계·BMS·과도 전압·전원 분기 |
| 보조 배터리 | 작은 용량의 nominal 24V, 접촉기 스위치/제어 용도로 사용 예정. 최대 충전전압은 모름 | 용량·완충/저전압 시 코일 단자 전압·제어 결선·주 배터리와의 전기적 관계 |
| 전자접촉기 | 제공 이미지의 LS MC-40a, 코일 DC24V를 설계 정보로 채택 | 실제 주문 옵션·정격 표시·부하별 DC 차단 적합성·접속 방식 |
| 물리 비상정지 | 버튼을 누르면 접촉기에서 차단하며 Arduino는 계속 켜져 있음 | 실제 차단 분기·복구 잠금·상태 feedback·차단 시험. 센서/노트북 유지전원은 별도 미확인 |
| 바퀴 M1~M4 위치 | 아직 미정, 시험 때 확인 예정 | 단일 채널/encoder 시험으로 FL/FR/RL/RR 대응과 부호 등록 |
| PWM 주파수 | 프로젝트에서 약 3.9kHz 사용을 요청 | 실제 PWM 파형 측정, 최대 출력 비율은 별도 미정 |

보조 배터리는 접촉기 제어 전원이라는 사용자 의도로 기록합니다. 두 배터리를 직렬·병렬로 연결한다고 가정하지 않으며, 정확한 코일 결선이나 공통 GND 연결을 임의로 정하지 않습니다.

[Cytron 공식 MDD10A 제품 사양](https://www.cytron.io/cytron/p-10amp-5v-30v-dc-motor-driver-2-channels)을 2026-09-29 확인했습니다. 최대 PWM 입력 주파수는 20kHz이며 Sign-Magnitude PWM/DIR 제어를 지원합니다. 약 3.9kHz는 이 주파수 범위 안입니다. 제조사가 3.9kHz만을 권장한다고 확인한 것은 아닙니다.
기존 Timer1/5 소스의 계산값은 3906.25Hz이며 실측값은 아닙니다. 주파수(Hz), PWM duty(%), firmware 명령 비율(%), 바퀴 속도, 전류는 서로 다른 값입니다. 최대 주파수 20kHz를 최대 출력 또는 시험 허용 비율로 사용하지 않습니다.

공식 Rev2.0 전원 범위는 5~30V이며 역극성 보호가 없습니다. 사용자 장착본의 revision은 미확인입니다. nominal 24V라는 이름만으로 완충·회생·과도 상태 전압이 정격 안이라고 판정하지 않습니다. 공식 채널 정격은 연속 10A / peak 30A(10초)이지만, 이 수치는 실제 모터 stall 전류·배선·fuse·접촉기 정격 선정과 실측을 대체하지 않습니다.

실제 전원 투입/구동 전에 전원부 담당자와 확인할 항목:

1. 접촉기 모델은 아래 MC-40a 공식 자료와 대조했습니다. 실제 주문 옵션·부하 조건·전류를 확인해야 합니다. AC 전류 정격만 보고 DC 모터 회로의 차단 능력을 확정하지 않습니다.
2. 버튼 조작과 보조 배터리 방전/분리 때 접촉기가 어떻게 동작하는지, 어떤 분기가 차단되는지 확인합니다. Arduino 유지전원은 사용자 확인값이며 센서·노트북 유지전원과 현물 차단 시험은 미확인입니다.
3. 비상정지 해제 또는 전원 복구만으로 재출발하지 않도록 설계·검증합니다. 접촉기 보조접점 또는 절연된 전원/안전 상태 감시 등으로 차단 사실을 프로그램이 알 수 있는 방법이 필요합니다. feedback GPIO와 회로는 미정이며 24V를 Mega 입력에 직접 연결하지 않습니다.
4. 코일의 제조사 지정 suppression/보호 부품, 역기전력·회생·과도 전압 처리, 양쪽 배터리 보호·fuse·DC-DC 및 극성을 확인합니다. 모델을 모르는 상태에서 diode/회로 변경을 지시하지 않습니다.
5. 일반 STOP의 ramp 감속과 물리 E-Stop의 전원 차단은 구분합니다. 전원 차단이 즉시 기계적 정지를 보장하지 않으므로 실제 정지거리·잔류 동작·복구 차단을 별도 시험합니다.

사진과 바퀴 위치 미정은 별도 firmware 작업본·mock 준비를 막지 않습니다. 다만 바퀴 위치 미확정 상태에서 전체 차체 방향 주행이나 odom을 완료로 표시하지 않습니다.
다음 소프트웨어 준비는 PDF 핀을 적용한 작업본, startup 정지·수동 시험 허용, E-Stop/fault latch, 엄격한 명령/ACK 분류, 비동기 FAULT/EVENT 처리와 heartbeat/timeout 회귀입니다. 기존 상한 MAX_COMMAND_PCT=30을 자동 확대하지 않으며 실제 시험 명령 비율은 담당자 준비 확인 후 별도로 정합니다. 이번에는 해당 제어 코드를 구현/변경하거나 업로드하지 않았습니다.

### 추가 확인: MC-40a 보조접점·코일 전압·Arduino 유지전원 (2026-09-29)

사용자 제공 이미지: C:/Users/H/AppData/Local/Temp/codex-clipboard-8f399311-18f1-40e4-a760-01a5f8f53ace.png.
이미지는 모델/설계 참고자료이며 실제 장착품의 명판·결선 사진이나 시험 결과로 취급하지 않습니다. 이미지 속 직렬 bridge, 12AWG ferrule, 85% 충전 지시는 제조사 근거와 별도로 검토합니다.

공식 근거: [LS ELECTRIC Metasol 2025 한국어 카탈로그](https://www.ls-electric.com/ko/cat/%5BMetasol_MS%5D_KO_C04001-35-202504.pdf).
PDF 23·24·34·178쪽의 표와 결선도를 텍스트 및 렌더링으로 확인했습니다. 쪽수는 PDF의 1-based 쪽수입니다.
로컬 원본: C:/Users/H/.codex/visualizations/2026/09/21/01a0c3d8-c3fc-7a90-a805-60dec69ed6af/ls-mc40a-reference/ls-metasol-ko-202504.pdf.
SHA256: 61441a58c5087406863aa98bb699505a6328efa21dd00f05c9f648dad24a2a02.

| 항목 | 제조사 자료에서 확인한 내용 | 현재 대차에 대한 판단 |
|---|---|---|
| 표준 보조접점 | MC-40a 표준 2a2b, 즉 NO 2개·NC 2개 (34쪽) | 모델 사양 확보. 실제 주문 옵션·미사용 접점·결선은 미검증 |
| 보조접점 번호 | NO: 13–14, 43–44 / NC: 21–22, 31–32 (178쪽) | Arduino GPIO 번호가 아닙니다. 코일 무여자 정상 상태 기준이며 실제 도통은 미확인 |
| 코일 | DC24V 옵션, 동작전압 85~110% Uc, DC24V/20°C에서 투입·유지 8W (24쪽 40AF 열) | 계산상 20.4~26.4V. 실제 소비전력·단자 전압은 미실측 |
| 주접점 DC 직렬 정격 | 3극 직렬 DC1(L/R=1ms): 24/48V에서 35A. DC3,5(L/R=15ms): 24V 35A, 48V 30A (34쪽) | 29.4V·드라이버 2개·모터 4개의 합산 부하 적합성을 확정하지 않습니다. 모델명의 40을 DC40A로 해석하지 않습니다 |
| 전선 접속 | 23쪽 MC-32a/40a 주단자 표: ferrule 열은 '-', ferrule 없는 stranded AWG12–6 / 2.5–16mm². 34쪽 개요 표는 AWG8–6 / 10–16mm² | 이미지의 12AWG ferrule을 승인된 조합으로 확정할 근거가 부족합니다. 실제 단자·lug·전류 조건과 표 적용 범위를 공급사에 확인해야 합니다 |

NO는 평상시 열림, NC는 평상시 닫힘입니다. A1/A2는 코일 단자이며 보조접점과 구분합니다. 표준 2a2b와 다른 주문 옵션도 있으므로 모델명만으로 실제 모든 단자가 사용 가능하다고 보장하지 않습니다.

중요한 전압 구분:

- 카탈로그의 85%는 코일 정격전압에 대한 동작 범위의 하한이지 배터리 충전량(SOC) 권장치가 아닙니다. 이미지의 '85%까지만 충전'은 제조사 운용 기준으로 확인되지 않았습니다.
- 보조 배터리가 29.4V라고 가정하지 않습니다. 만약 코일에 29.4V가 직접 걸린다면 26.4V 상한을 초과하므로 해당 범위에 맞지 않습니다. 보조 배터리의 완충~저전압 구간 전압 또는 정격에 맞는 제어 전원 설계를 확인해야 합니다.
- 주 배터리 29.4V와 MDD10A Rev2.0 상한 30V의 산술 여유는 0.6V입니다. 실제 장착 revision·회생 제동·BMS·차단 시 과도 전압·허용오차를 확인하기 전에는 적합 판정하지 않습니다.
- 3극 직렬은 접점 3개가 같은 전류를 흐르게 하는 방식이며 전류 허용량을 3배로 늘리는 방법이 아닙니다. 이미지의 2–3/4–5 bridge는 현물 단자 표시와 전원 차단 상태의 회로 확인을 대체하지 않습니다.

Arduino가 유지전원이므로 다음은 향후 firmware/host의 필수 요구이며 아직 구현·실차 검증 완료가 아닙니다.

1. MCU와 별개로 물리 E-Stop이 구동 전원을 차단해야 합니다. 보조접점은 정격에 맞는 보호/절연 입력 회로를 통한 상태 feedback 후보이며 24V를 Mega GPIO에 직접 연결하지 않습니다. feedback GPIO는 미정입니다.
2. 차단/비상정지 감지 시 fault를 latch하고 목표·현재 출력과 대기 주행 명령을 제거합니다. 비상정지 중 새 주행 명령을 거부합니다.
3. 버튼 해제·접촉기 재투입·통신 복구만으로 재출발하지 않습니다. 정상 feedback 확인과 작업자의 별도 재개 조작을 요구합니다.
4. 일반 보조접점을 안전 인증 mirror contact 또는 주접점 용착 검출 장치로 자동 인정하지 않습니다. [LS 공식 안전 접점 안내](https://gics.ls-electric.com/knowledgeBase/user/detail.do?baseId=164)의 SAFETY 옵션과 실제 인증/표시를 구분해야 합니다.

남은 하드웨어 확인: 보조 배터리 모델·최대 충전전압·코일 단자 전압, 장착 접촉기 옵션/feedback 회로, 합산 부하·돌입·stall 전류 및 DC 차단 적합성, 승인된 전선/단자·보호·suppression, 실제 차단 분기와 수동 복구 시험입니다. 사진 없이 문서·mock 준비는 계속할 수 있지만 이 현물 확인들을 완료로 바꾸지는 않습니다.
이번 갱신은 이 검토 문서와 비활성 참고 JSON만 변경했습니다. firmware·실측 설정·원본 vendor는 보존했고 serial·모터·코일 구동·업로드를 실행하지 않았습니다.

## 1. 결론과 보존 원칙

- 보고서에 적힌 쉴드용 PWM·DIR·encoder connector·램프·전압 감시 핀을 확보했습니다.
- 보고서의 firmware, 이 PC의 리팩터링 firmware, WSL vendor firmware는 서로 다른 파일입니다.
- PWM·DIR·Timer1/5는 리팩터링 코드에 이미 반영되어 있습니다. encoder M1/M3의 대응은 보고서와 다릅니다.
- 개발 기준은 위 사용자 결정으로 PDF 쉴드 배열을 채택했습니다. 실제 업로드된 firmware와 PCB revision은 미확인입니다. 원본 소스·실차 설정을 자동 교체하지 않습니다.
- PDF에는 새 encoder count/rev, 차체 치수, 속도, 정지거리 실측값이 없습니다. 실차 measurements.json은 변경하지 않았습니다.
- 실제 serial port는 열지 않았고, 모터·램프 명령, firmware 업로드, 납땜·배선 변경은 하지 않았습니다.
- 원본 PDF·vendor·WSL dirty 작업을 보존했습니다. 새 참고표는 docs/hardware/hkx_pcb_a_reference.json이며 runtime이 로드하지 않습니다.
- 파일에 남긴 근거를 다음 채팅에서 다시 읽을 수 있습니다. 별도의 계정 영구 메모리에 저장됐다는 뜻은 아닙니다.

## 2. 자료의 출처와 신뢰 수준

원본: C:/Users/H/Downloads/핀변경_보고서_HKX_PCB-A.pdf
제목: 핀 변경 보고서 - MEGA_SHIELD_HKX · PCB-A
문서 작성 시각: 2026-09-28 21:43, 표기 버전 10.0.4.
대상: C:/Users/MSY/Desktop/ROBOT의 재활용 분류 로봇 저장소입니다. 현재 H 계정의 대차 저장소와 같다고 가정하지 않습니다.

PDF SHA256: b521fd67c6967c2cdd8fba5449bb1d2d63c720d4656180cf1f029a6d33db1f0e
PDF MD5: 0e2ba70765286dd63817397a30d4dce5

| 구분 | 이번 확인 | 판정 |
|---|---|---|
| PDF 1~4쪽 | 본문·표·주석·극성 경고를 추출 및 시각 확인했습니다 | 문서 독해 완료 |
| PDF의 회로도 MD5 | 문서에 기록된 값만 확보했습니다 | 원본 회로도 hash 대조 미완료 |
| C:/Users/MSY/Desktop/ROBOT | 이 PC에 해당 경로가 없습니다 | 원본 미제공 |
| 대차 폴더·리팩터링 폴더·WSL vendor의 대상 회로도 | 조사 범위에서 HKX/PCB_POWER_A KiCad 파일을 찾지 못했습니다 | 넷리스트 재생성 불가 |
| PCB 실물 | 사진·회로 도통·전압을 새로 확인하지 않았습니다 | 실물 미검증 |
| Arduino flash | firmware identity와 upload 기록을 확인하지 않았습니다 | 업로드 상태 미확정 |

PDF 1쪽의 원본 식별값은 JSON에 그대로 보존했습니다. MD5는 문서와 동일 파일인지 비교하는 용도이며 안전·배선 검증을 대신하지 않습니다.

## 3. 쉴드용 모터 핀표

PDF 3쪽 5절의 motor 번호는 0~3 배열 index입니다. 아래 M1~M4 표기는 명령 번호 1~4에 맞춰 설명하기 위한 것이며 실물 바퀴 위치 확정값이 아닙니다.

| 문서 index / 설명용 번호 | PWM | DIR | encoder A | encoder B | driver 경로 | encoder connector |
|---|---|---|---|---|---|---|
| 0 / M1 | D11 | D34 | D3 | D30 | MD1-2 / MD1-1 | ENC1 |
| 1 / M2 | D44 | D36 | D18 | D31 | MD2-2 / MD2-1 | ENC2 |
| 2 / M3 | D12 | D35 | D19 | D32 | MD1-4 / MD1-3 | ENC3 |
| 3 / M4 | D45 | D37 | D20 | D33 | MD2-4 / MD2-3 | ENC4 |

MD1의 핀 1~5: D34, D11, D35, D12, GND.
MD2의 핀 1~5: D36, D44, D37, D45, GND.

| encoder connector | 핀 1 | 핀 2 | 핀 3 | 핀 4 |
|---|---|---|---|---|
| ENC1 | +5V | GND | D30 (B) | D3 (A) |
| ENC2 | +5V | GND | D31 (B) | D18 (A) |
| ENC3 | +5V | GND | D32 (B) | D19 (A) |
| ENC4 | +5V | GND | D33 (B) | D20 (A) |

A/B 의미는 PDF의 motor 표와 connector 표를 대조한 결과입니다. encoder connector에 12V/24V를 직접 연결하지 않습니다.
실제 encoder 정격·케이블 색·connector pin-1 방향은 별도로 확인해야 합니다.

PDF의 '모터·encoder 핀 변경 없음'은 예전 HKX 회로도와 새 HKX 회로도의 비교입니다.
firmware의 옛 GPIO 배열이 쉴드와 호환된다는 뜻이 아닙니다.

PDF 4쪽의 'D2가 D20으로 바뀐다'는 encoder 사용 핀 집합의 차이를 요약한 표현입니다.
3쪽 표의 배열 index별 변경은 0: D2->D3, 1: D3->D18, 2: D18->D19, 3: D19->D20입니다.
옛 배열에서 D2 한 개만 D20으로 치환하면 문서의 쉴드 배열과 달라집니다.

## 4. firmware 세 버전의 대조

| 항목 | PDF가 기록한 firmware | H PC 리팩터링 코드 | WSL vendor 코드 |
|---|---|---|---|
| PWM | 5,6,7,8 | 11,44,12,45 | 5,6,7,8 |
| DIR | 22,23,24,25 | 34,36,35,37 | 22,23,24,25 |
| ENC_A | 2,3,18,19 | 19,18,3,20 | 2,3,18,19 |
| ENC_B 사용 | 쉴드 배선은 있으나 firmware 미사용이라고 기록 | 32,31,30,33을 A 상승 때 읽습니다 | A-only |
| timer | 쉴드용 Timer1/5 변경 전이라고 기록 | Timer1/5 구현 | Timer3/4 |
| lamp | 14,15,16,17 있음·미커밋이라고 기록 | LAMP_PIN/램프 제어 없음 | 조사 대상 파일에 없음 |
| A3 전압 읽기 | 없음 | 없음 | 조사 대상 파일에 없음 |
| MD5 | 2e0a3927040113d7f1d7d977509282bf | 1ab3a5308f70a823da7f1201a15d24e7 | 86a1819b66261ef9b9563d46df493574 |

리팩터링 원본:
C:/Users/H/Desktop/단일카메라_YOLO접근_리팩터링/urt/mecanum_motor/src/main.cpp
SHA256: a25c470cc5e3795f31d0777617217d0dae9dbff38e8e0aee7a63125f6cf1137e

WSL 원본:
/home/mnw/ros2_ws/vendor/ROBOT/urt/mecanum_motor/src/main.cpp
ROS workspace branch: codex/phase-6-base-gateway-mock, HEAD: 00b86c48496cd2013117e4a0d9abbd373afbf9df.
vendor는 untracked 폴더이므로 이 Git HEAD가 vendor 파일 버전을 증명하지는 않습니다.

### 우선 해결: M1과 M3의 encoder pairing

쉴드 설계표는 M1에 ENC1(D3,D30), M3에 ENC3(D19,D32)를 대응시킵니다.
리팩터링 코드는 M1에 ENC3(D19,D32), M3에 ENC1(D3,D30)를 대응시킵니다.
M2·M4는 문서와 같습니다. A와 B를 묶어서 비교해야 하며 A만 교체하면 안 됩니다.

이 차이가 의도된 케이블 재배치인지, 이전 측정 순서인지, 현재 오배선인지 아직 판정하지 않았습니다.
향후 개발 기준은 사용자 결정에 따라 PDF의 M1=ENC1, M3=ENC3입니다. 실제 구동 전에는 도통과 바퀴별 encoder 변화가 선택한 기준에 맞는지 확인해야 합니다.
PDF보다 코드가 틀렸다고 단정하거나, 코드의 '실측' 주석을 이번 실물 검증으로 취급하지 않습니다.

리팩터링 코드의 다른 후보값:
- POS_TO_MOTOR = [1,0,3,2] (FL,FR,RL,RR -> M2,M1,M4,M3)
- INVERT = [true,false,true,false]
- ENC_INVERT = [true,false,true,false]
- STRAFE_SIGN = -1 (주석에서 재확인 필요로 표시)
- ENC_PPR = [942.8,931.8,906.6,874.0] count/rev, A 상승 x1 기준 과거 후보

encoder 순서를 변경하면 PPR·부호·motor pairing도 함께 재검토합니다. 숫자만 임의로 섞지 않습니다.

## 5. PWM·통신·정지 동작의 코드 근거

리팩터링 코드에서 확인했습니다. 실제 보드에서 측정한 값은 아닙니다.

| 항목 | 코드 값/동작 | 주의 |
|---|---|---|
| serial | 115200 baud, 개행 종료 | 실제 flash와 port 미확인 |
| PWM | Timer1: D11 OC1A / D12 OC1B, Timer5: D44 OC5C / D45 OC5B | pinMode 배열과 OCR register 대응을 함께 맞춰야 합니다 |
| 주파수 | TOP=4095, prescaler=1, 16MHz 가정 계산 3906.25Hz | 오실로스코프 측정 전입니다 |
| 명령 상한 | MAX_COMMAND_PCT=30 | V/M/G의 입력과 mixing 출력에 제한이 있습니다 |
| duty 스케일 | MAX_DUTY=200, 명령 30% -> nominal duty 60/255 | 30% 명령은 전기적 PWM 30%나 모터 속도 30%와 같지 않습니다 |
| 일반 STOP | target만 0으로 하고 ramp 적용 | 실제 감속·제동거리 미측정 |
| ramp | step=2, tick=15ms | 최고 후보 duty60에서 0까지 30tick=450ms 계산. scheduling·제동·미끄럼 포함 실측값은 아닙니다 |
| deadman | 새 motion 명령 없이 500ms 초과 시 target=0 | 다음 ramp 시간이 추가됩니다. 임의의 ENC poll만으로 구동 heartbeat를 대체하면 안 됩니다 |
| stall | target/current duty30 이상 조건에서 pulse 600ms 부재 시 즉시 출력0·fault | 대응 encoder가 잘못되면 다른 모터로 판단할 수 있습니다 |
| ESTOP | 즉시 출력0, stall latch를 해제합니다 | 이후 V가 다시 허용됩니다. 물리 E-Stop feedback과 호스트 latch가 필요합니다 |
| SYNC | 기본 OFF, 더 빠른 축을 감속하는 보정 | 전류 제한·토크 보증·정확한 속도 폐루프와 같지 않습니다 |

PDF 4쪽의 50% 단일 모터 시험 예시는 실행하지 않았으며 승인된 시험값으로 채택하지 않습니다.
현재 리팩터링 파일의 30% 제한을 기록하지만, uploaded firmware에도 같은 제한이 있다고 보증하지 않습니다.
WSL vendor의 MAX_DUTY=200만 보고 30% 제한이 있다고 추정해서는 안 됩니다.

## 6. 램프·전압 입력 및 connector 변경

### HKX CN1과 PCB-A J11

| 기능 | Mega | CN1 pin | PCB-A J11 pin | 이후 경로 |
|---|---|---|---|---|
| lamp1 | D14 | 1 | 1 | U1 input1 -> output1 -> J9-1 |
| lamp2 | D15 | 2 | 2 | U1 input2 -> output2 -> J9-2 |
| lamp3 | D16 | 3 | 3 | U1 input3 -> output3 -> J9-3 |
| lamp4 | D17 | 4 | 4 | U1 input4 -> output4 -> J9-4 |
| 전압 감시 | A3 | 5 | 5 | VSENSE_A |
| GND | CN1에는 없음 | 6,7은 NC | 6,7은 GND | 별도 공통 기준 경로 확인 필요 |
| 예비 | 없음 | 8은 NC | 8은 NC | 사용하지 않습니다 |

CN1/J11을 8핀 일대일 케이블로 잇는다고 CN1에 GND가 생기지는 않습니다.
두 보드가 다른 전원 연결로 공통 GND를 공유하는지 원본 회로도와 전원 차단 상태의 도통으로 확인해야 합니다.
connector를 정면에서 보는지, 뒤에서 보는지, pin-1 표시와 케이블 꼬임은 전원 투입 전 현물에서 확인합니다. 사진은 보조 자료이며 소프트웨어 준비를 중단시키는 조건이 아닙니다.

[Arduino 공식 Mega 자료](https://store.arduino.cc/products/arduino-mega-2560-rev3)에 따라 D14~17은 Serial2/3, D18/19는 Serial1, D20은 SDA와 겸용입니다.
현재 배치에서 Serial2/3는 lamp와, Serial1·I2C SDA는 encoder와 충돌할 수 있습니다.
GPIO로 사용할 때 해당 UART/Wire 기능을 동시에 시작하지 않는 기준을 두어야 합니다.
핀 배열의 중복이 없다는 검사만으로 주변장치 충돌까지 해결되지는 않습니다.

문서 표기 주의: PDF 3쪽의 Mega J7 목록에는 /*52가 있고 1쪽에서는 *를 PWM 표시라고 설명합니다.
공식 Mega의 PWM 범위는 D2~13 및 D44~46이며 D52는 SPI SCK입니다. 따라서 /*52라는 net 이름을 PWM 지원 근거로 사용하지 않습니다.
원본 회로도의 net 이름·별표 의미를 재확인해야 합니다. JSON에서는 해당 header를 D52로 정규화했으며 PWM capability를 부여하지 않았습니다.

### PCB-A J9

| pin | 이전 6핀 | 현재 5핀 |
|---|---|---|
| 1 | RELAY_COM | LAMP1_OUT |
| 2 | LAMP1_OUT | LAMP2_OUT |
| 3 | LAMP2_OUT | LAMP3_OUT |
| 4 | LAMP3_OUT | LAMP4_OUT |
| 5 | LAMP4_OUT | GND |
| 6 | GND | 삭제 |

이전 6핀 harness를 같은 순서로 재사용하지 않습니다. J9의 RELAY_COM은 제거됐습니다.
램프 번호와 실제 색·부저의 대응은 PDF에 없습니다. 'lamp1=빨강' 같은 값을 만들어 넣지 않습니다.
PDF는 MCU HIGH를 relay ON으로 기록하지만 실제 릴레이 모듈 active-low/high와 결선은 미확인입니다.

### 삭제·변경 항목

- HKX ST1~3와 HK1이 삭제됐고 CN1이 추가됐습니다.
- ST1의 D22/23/38, ST2의 D24/25/39, ST3의 D26/27/40은 해당 connector와의 연결이 없어졌습니다. Mega header 자체가 없어진 것은 아닙니다.
- PCB-A C3(VSENSE_A-GND 필터 capacitor)가 삭제됐습니다.
- U1 pin9 COM은 미연결입니다.
- F1 보드 fuse와 J2 switch connector는 비교 이전 파일에도 이미 없다고 기록됐습니다. 외부 fuse·switch·E-Stop의 존재를 증명하는 정보는 아닙니다.

## 7. 전기적 재확인 항목

### P0: 전원 투입 전

1. PCB revision·Gerber 제작판과 실제 조립 부품이 문서의 회로도와 같은지 확인합니다.
2. XT60: PDF는 PCB-A J1 pad1(네모)=+24V, pad2(원)=GND이고 실크 방향이 통상 XT60 모서리 설명과 반대라고 경고합니다.
   문서의 '180도' 표현만 보고 회전·납땜하지 않습니다. 전원을 분리하고 각인 극성·pad·실제 net의 연결을 확인해야 합니다.
3. F1/J2가 빠진 만큼 배터리 근처의 외부 fuse, 주전원 switch, 물리 E-Stop 차단/feedback, BMS, 전선·connector 정격과 보호 회로도를 요청합니다.
   소프트웨어 ESTOP과 보호용 fuse는 서로를 대체하지 않습니다.
4. Mega·sensor용 logic 전원 변환 경로를 확인합니다. 24V bus를 5V encoder/logic pin에 직접 연결하지 않습니다.
5. CN1/J11 공통 GND, J9의 변경된 pin-5 GND, pin-1 방향과 harness revision을 확인합니다.

### P1: 릴레이 interface와 A3

[TI ULN2003A 공식 datasheet](https://www.ti.com/lit/ds/symlink/uln2003a.pdf)의 output은 전류를 끌어내리는 open-collector입니다.
MCU HIGH는 output을 +5V로 구동한다는 의미가 아닙니다. 외부 relay module input의 pull-up·active level·전류·전원·절연 구조가 필요합니다.
COM pin9는 내부 flyback diode 공통점입니다. 직접 inductive coil을 구동하는지, 이미 보호된 relay module의 logic input을 구동하는지 구분해야 하므로 COM 미연결만으로 정상/불량을 단정하지 않습니다.
어느 공급선에 COM을 잇거나 board를 개조하라는 지시도 하지 않았습니다.

A3의 보고서식은 V_pack = adc * 5.0 / 1023 * 118 / 18입니다.
이는 nominal reference=5V, divider ratio=118/18이라는 설계 후보이며 실제 저항값·tolerance·AREF·pack 전압을 측정한 식이 아닙니다.
기본 Mega ADC 범위는 공식 자료상 0~5V이지만 실제 전원과 analogReference 설정을 확인해야 합니다.
nominal full-scale pack 전압은 식으로 32.78V입니다. 허용 입력 전압이나 안전 한계로 사용하지 않습니다.
pack 최대 충전전압·surge·역극성·A3 보호·C3 제거 후 ripple·필터·settling·읽기 주기·보정은 별도 확인합니다.
A3는 pack A 한 곳만 측정하는 설계입니다. pack B 상태·전체 배터리 잔량을 알 수 있다고 가정하지 않습니다.

## 8. ROS2·UI에 남은 연결

검토한 새 대차 transport는 READY/OK V/OK STOP/OK ESTOP를 한 줄씩 대기합니다.
단일 포트를 공유해 ENC, SPD, lamp, voltage, fault/event를 섞으면 송수신 상태 머신과 응답 분류가 필요합니다.
리팩터링 firmware가 보내는 FAULT STALL_NO_ENCODER와 EVENT DEADMAN_TIMEOUT은 기존 ROS parser의 지원 목록에 없습니다.
lamp/voltage의 실제 명령 형식도 PDF에 없습니다. 기존 READY만으로 firmware 버전·핀·제한을 식별할 수 없습니다.

기존 ROS mock gateway는 serial을 열지 않고 nonzero Twist를 거절합니다. 4-wheel parser와 계산 함수가 있어도 실차 /odom·TF가 완성됐다는 뜻은 아닙니다.
필요한 순서:
1. 선택한 PDF PCB profile에 맞는 firmware 준비, wheel pairing 검증 및 설정 불일치 시 enable 거부.
2. 단일 serial owner: READY/ACK/ENC/status/fault, timeout·재연결·reset 처리.
3. calibrated 4-wheel /odom·odom->base_link TF 및 counts timestamp/receive age.
4. command arbitration·physical E-Stop feedback·camera/LiDAR stale 정지·명시적 재개.
5. 검증된 m/s·rad/s -> percent 변환, host와 firmware 모두의 상한.
6. ROS 상태 -> UI 실제 source/freshness·error, lamp/voltage 연동.
7. robot arm Wi-Fi count/load-complete -> mission -> HOME/DESTINATION 왕복.

lamp와 전압은 보조 표시이며 안전 회로 완료·실차 주행의 선행 gate를 대신하지 않습니다.
이번에는 UI·driver·ROS 제어 코드와 firmware를 구현/수정하지 않았습니다.

## 9. 실측 정보의 현재 상태

PDF에 새 count/rev나 기구·주행 실측은 없습니다. 과거 PPR·CAD 수치는 후보 자료로 유지합니다.

| 항목 | 필요한 근거/측정 |
|---|---|
| firmware 실제 장착본 | 소스 파일, platformio.ini/보드 설정, Git commit 또는 hash, upload 날짜와 담당자 |
| motor/encoder pairing | 전원 격리 후 connector 도통, 각 바퀴 수동 회전의 ENC 변화, motor channel 표 |
| encoder count | motor disabled 상태에서 정·역 5~10회전 반복, 실제 회전수·counting x1/x2/x4·편차 |
| footprint/기구 | 최종 케이스 포함 외곽, wheel 지름·중심 간격·base_link 전방 |
| sensor TF | 카메라/LiDAR x,y,z와 roll,pitch,yaw, camera optical 기준·범퍼 offset |
| 주행 calibration | 준비 확인 후 저속 실제 거리/속도, yaw angle, 슬립·적재 조건 |
| 정지 | 승인된 현장에서 STOP·communication timeout·물리 E-Stop의 거리/지연과 재시작 차단 |
| 전압 | 전원부 담당자가 pack 및 A3 실제 전압·분압·기준전압·noise·보호를 확인 |
| 현장 | 두 선 간격·곡률·회전 공간, HOME/DESTINATION 표식·정차 오차, map_id |

측정 절차 기본 양식: docs/12_MEASUREMENT_CHECKLIST.md.
수동 encoder 시험이라도 전기적 enable 차단·손 끼임·역기전력 조건을 먼저 확인합니다.
PDF에 제시된 motor command 예시를 자동 실행하지 않습니다.

## 10. 다음에 주시면 좋은 자료와 우선순위

소프트웨어 준비는 사진 없이 선택한 PDF 기준으로 진행할 수 있습니다. 아래 자료 중 실물·전원 관련 확인은 실제 전원 투입 및 구동 전 단계에 필요하며, 모두를 일반 코드·mock 작업의 선행 조건으로 두지 않습니다.

추가 자료 및 실제 구동 전 확인:
- 실제 제작한 HKX/PCB-A revision과 connector pin-1 방향. 앞뒤 사진은 제공 가능할 때 참고하며 필수 제출 자료로 요구하지 않습니다.
- HKX·PCB_POWER_A의 .kicad_sch와 .kicad_pcb, 프로젝트/필요 library 또는 독립 export netlist.
- PDF가 언급한 핀변경_보고서_HKX_PCB-A.json과 전원 PCB_설계기준_24V2팩.md.
- Arduino에 실제 사용한 main.cpp, platformio.ini 또는 IDE 보드/라이브러리 설정, 마지막 upload 기록.
- MDD10A revision, relay module·배터리/BMS·DC-DC·접촉기 주문 옵션과 전원 fuse/E-Stop 전체 회로. Mega 2560·MDD10A 2개·VOLTON nominal 24V 10Ah, 보고된 완충 29.4V·보조 24V 접촉기 제어 용도·LS MC-40a DC24V 및 Arduino 유지전원은 위에 기록했습니다. 현물 검증과는 구분합니다.

P1: 사용자 선택으로 확정한 PDF pin profile을 기준으로 별도 firmware 작업본과 motor-disabled mock 회귀를 준비합니다. 원본과 과거 실측 후보는 보존하며 pairing·부호·PPR을 임의로 옮기지 않습니다.
P2: 담당자가 준비된 상태에서 전원·encoder 센서 확인, 승인된 바퀴 시험, 속도·정지 실측을 진행합니다.
P3: 실제 센서 SLAM/위치추정과 UI를 연결하고 line/Nav2의 제어권을 단일화합니다.

원본 회로도 없이는 KiCad netlist 표를 독립 재현할 수 없습니다.
추가자료 없이도 firmware identity·profile mismatch·async fault parser 설계와 mock 시험은 가능하지만 이번 검토에서 구현하지 않았습니다.

## 11. 이번 파일·검증 기록

- PDF 4쪽 전체 독해 및 PNG 시각 확인, PDF/local firmware hash 확인, 배열 추출·대조를 수행했습니다.
- WSL ROS branch/HEAD 및 dirty 상태를 읽었고 원본을 수정하지 않았습니다.
- 계산한 3906.25Hz·60/255·450ms·32.78V는 코드/설계식의 결과이며 물리 측정값이 아닙니다.
- 참고 JSON에는 hardware_verified=false, runtime_enabled=false를 넣었습니다. 이는 데이터 분류일 뿐 실제 motor 출력 차단 장치가 아닙니다.
- 실제 실측 설정·기존 참고값 및 firmware는 그대로 유지합니다.
- Markdown UTF-8 BOM·JSON UTF-8·실제 파일 존재/비어 있지 않음·한글 U+FFFD 없음·JSON parse를 확인했습니다.
- 참고 JSON의 PWM/DIR/ENC_A/ENC_B 배열과 로컬 source/hash, PDF SHA256, CN1/J9 배열 및 reference-only flag를 assertion으로 확인했습니다.
- 기존 measurements.json과 reference_measurements.json의 SHA256이 검토 시작 시점과 동일한 것을 확인했습니다. git diff --check도 통과했습니다.
- 이번 검토에서 기존 ROS gateway 순수 테스트 10개가 통과했습니다. 별도 문자열 입력 검사로 FAULT/EVENT가 현재 parser에서 ProtocolError로 거절되는 것을 재확인했습니다. serial I/O는 하지 않았습니다.
- VSCode에 실제 두 파일을 여는 code --reuse-window 명령은 exit 0이었으며 Codex 오른쪽 파일 탭 요청은 queued였습니다.
  제공 도구에서 VSCode 창 내용을 볼 수 없어 실제 편집기 표시·한글 렌더링은 미검증입니다. 빈 미저장 탭을 확인했다고 주장하지 않습니다.
- 파일 링크가 열리지 않으면 VSCode 터미널에서 다음 명령을 사용하실 수 있습니다:
  code --reuse-window "C:\Users\H\Desktop\로봇 자율주행\wafer-cart-line-navigation\docs\18_HKX_PCB_A_REVIEW.md"
- 이 검토의 변경은 README 문서 목록 및 두 참고 파일뿐입니다. Git push·PR 변경과 실제 제어 코드 변경은 하지 않았습니다.
- 추가 사용자 결정은 문서와 참고 JSON에 기록했습니다. 사진 없이 소프트웨어 준비가 가능하도록 구분했으며 실제 실물 검증·업로드·모터 구동 완료로 표시하지 않았습니다. 위 테스트 결과는 최초 검토 당시 기록이며 이 결정 반영에서 새로 실행한 결과가 아닙니다.
- 추가 전원 구성은 사용자 답변, 드라이버 한계는 공식 제품 사양, 3906.25Hz는 기존 소스 계산으로 구분해 기록했습니다. 이번 전원 정보 반영의 검증 범위는 파일/JSON·수치/출처·보존 확인이며 firmware build·실차 시험의 성공을 뜻하지 않습니다.
