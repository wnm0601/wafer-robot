# 가져온 파일 기록

- 목적: 다른 Windows 데스크탑에서 현재 수동 대차 조작·진단 코드를 검사하기 위한 별도 저장소.
- 원본 저장소: https://github.com/wnm0601/wafer-cart-line-navigation
- 원본 branch: `codex/pcb-firmware-bench-mock`.
- 기준 commit: `87208daff82ccc94b60eeaae2fba0792a2ba6448`.
- 복사 기준: 2026-10-10 생성한 `wafer-cart-manual-20261010.zip`의 전달본106개 파일.
- ZIP SHA256: `5CA5165E58A7B66110AE41E6653C995955186DD86A7BF43A7D3AA68A1BA6736B`.
- 기존 경로를 유지한 소스: `src/wafer_cart_keyboard_drive`, `src/wafer_cart_core`, `firmware/mega_cart`, `firmware/encoder_pin_probe`, 선별한 scripts/config/docs/mapping config.
- 원본에서 untracked였던 `docs/18_HKX_PCB_A_REVIEW.md`, `docs/hardware/hkx_pcb_a_reference.json`도 관련 참고자료로 포함했습니다.
- `reference_photos/wiring-1.jpg`~`wiring-6.jpg`는 사용자가 제공한 배선 사진이며 원본 이미지 내용은 변경하지 않았습니다.
- PDF는 사용자 제공 핀변경_보고서_HKX_PCB-A.pdf, 대차_사용전_점검표.pdf를 파일명만 영문화하여 복사했습니다.
- evidence는 과거 로그의 사본이며 새 데스크탑 시험 결과가 아닙니다.
- 전달본 추가 파일: README_FIRST.md, START.cmd, START.ps1, requirements-manual.txt, FILE_MANIFEST.json.
- 이 저장소 추가 파일: GitHub 첫 화면 README, 본 출처 기록, .gitignore/.gitattributes, data/output/.gitkeep.
- 현재 제어 코드·핀·출력 제한·보호 로직은 복사 과정에서 변경하지 않았습니다. .gitattributes는 최초 전달본 파일의 바이트/해시 보존을 위해 줄바꿈 자동 변환을 끕니다.
- 기존 ROS2 저장소·대차 저장소·Git 이력은 변경하지 않았으며 .git·비밀키·로컬 가상환경·도구 캐시는 복사하지 않았습니다.

## 2026-10-15 최신 실행본 추가

- 대상: current/. 기존 루트 진단본을 덮어쓰지 않고 별도 실행 메뉴를 추가했습니다.
- 보존 모터 원본: https://github.com/maeng052097-blip/ROBOT 의 claude/gracious-cannon-lh630u, 기준 928b2a807e65263fab3f504023284e4cdec0f3a2.
- 실제 복사본은 그 커밋 이후 로컬 codex/motor-review-safety의 검토 변경이 포함된 작업 파일입니다. upstream 커밋 자체와 동일한 코드라고 표현하지 않습니다.
- common/manual_motor_test.py, common/color.py, common/mecanum.py, 선별 tests, urt/mecanum_motor 소스/설정, 검토 문서를 필요한 상대 경로 그대로 복사했습니다.
- 새 UI/카메라/학습/센서 코드는 원래 작업 루트의 cart-manual-ui, cart-target-preview, gray-panel-training, cart-sensor-check에서 가져왔습니다.
- 주행 UI의 assets/cart-final.png만 기술 미리보기로 복사했습니다. CAD 원본·현장 사진·가중치·학습 데이터·원시 CSV·녹화·백업·.git·.pio는 추가하지 않았습니다.
- 런타임 Python 및 모터 소스는 변경하지 않았습니다. 배포용 .cmd 진입점만 current/launch.cmd로 연결했습니다. 카메라 테스트는 최신 UI 해시/모델 미포함 배포 조건에 맞게 갱신했습니다.
- 복사 파일별 원본/배포 SHA256은 current/SOURCE_MANIFEST.json에 기록합니다. 기존 루트 FILE_MANIFEST.json은 과거 전달본 기록을 그대로 유지합니다.
- 보존 모터 원본 폴더의 기존 스테이징 상태와 다른 저장소들의 미커밋 변경은 건드리지 않았습니다. 새 배포 파일만 이 저장소에서 커밋합니다.
