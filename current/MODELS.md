# 기존 YOLO 모델 복원

공개 저장소에 현장 모델 가중치와 사진은 넣지 않았습니다. 원래 PC에서 복사하거나 담당자에게 별도로 받으세요. 신뢰할 수 있는 출처의 .pt만 사용하세요.

| 용도 | 저장소 안 목적지 | 원래 파일 크기 |
|---|---|---|
| 6종 물체 인식 | current/six_class_detection_training/runs/segment/train/weights/best.pt | 6,023,445 bytes |
| 회색 판 detect 학습 시작점 | current/object_detection_training/yolo11n.pt | 5,613,764 bytes |

6종 모델은 red_box, blue_cylinder, black_sphere, green_star, blue_box, brown_box를 학습한 segment 모델입니다. 사각형 라벨의 회색 판 학습에는 대신 detect 모델인 yolo11n.pt를 사용합니다.

카메라 단독 창은 모델 선택 버튼으로 다른 로컬 파일을 선택할 수 있습니다. 통합 센서 창은 위 best.pt 기본 경로를 사용합니다. 파일이 없으면 오류를 표시하고 자동 다운로드하지 않습니다.

## 원래 PC에서만 사용하는 복사 예시

다른 PC에서는 원본/저장소 경로를 실제 위치로 바꾸세요.

```powershell
$work = 'C:\Users\H\Desktop\로봇 자율주행'
$repo = Join-Path $work 'wafer-robot'
New-Item -ItemType Directory -Force -Path "$repo/current/six_class_detection_training/runs/segment/train/weights", "$repo/current/object_detection_training"
Copy-Item -LiteralPath "$work/six_class_detection_training/runs/segment/train/weights/best.pt" -Destination "$repo/current/six_class_detection_training/runs/segment/train/weights/best.pt"
Copy-Item -LiteralPath "$work/object_detection_training/yolo11n.pt" -Destination "$repo/current/object_detection_training/yolo11n.pt"
```

이번 배포 중 모델은 복사/업로드하지 않았습니다. .gitignore가 .pt와 학습 결과를 제외합니다. 모델·Ultralytics의 배포 및 재학습 라이선스 조건은 별도로 확인하세요.
