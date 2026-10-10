# 작업 규칙

## 우선 원칙

- 모든 설명과 문서는 한국어 존댓말로 작성합니다.
- 실측하지 않은 거리·속도·각도·encoder count를 확정값으로 넣지 않습니다.
- 실제 motor 구동, firmware upload, E-Stop 배선 변경 전에는 담당자와 하드웨어
  준비 상태를 다시 확인합니다.
- 재시작 시 차량은 항상 정지 상태여야 하며 자동 운행을 재개하지 않습니다.
- 하나의 base gateway만 motor와 encoder가 연결된 serial port를 소유합니다.
- 모터를 설명할 때 번호와 차체 위치를 함께 표시합니다. 실제 출력 위치가
  검증되지 않았다면 `M2(오른쪽 뒤 추정)`처럼 추정임을 명시합니다.
- 엔코더 손 회전으로 확인한 위치를 모터 출력 위치의 확정값으로 취급하지 않습니다.
- `ros2-slam-nav2-robot`과 vendor 원본을 직접 덮어쓰지 않습니다.

## 파일 규칙

- Markdown은 UTF-8 with BOM, Python은 UTF-8로 저장합니다.
- `build/`, `install/`, `log/`는 수정하거나 commit하지 않습니다.
- 기존 코드를 가져올 때 `imports/README.md`에 source repository, branch, commit,
  원본 경로, 수정 이유를 기록합니다.

## 검증

- 순수 로직은 motor-disabled 단위 테스트를 먼저 작성합니다.
- ROS2 변경은 `colcon build --symlink-install`과 관련 `colcon test`로 확인합니다.
- 센서와 실제 차체 시험은 실행 날짜, 장치, 설정, 성공/실패 범위를 따로 기록합니다.
- 과거 성공 기록을 현재 실행 성공으로 표현하지 않습니다.

