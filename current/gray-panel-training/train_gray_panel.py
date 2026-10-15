"""회색 판 YOLO 학습 도구. 카메라·COM·모터 연결은 하지 않습니다."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parent
BASE_MODEL = ROOT.parent / "object_detection_training/yolo11n.pt"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
SPLITS = ("train", "val", "test")


def yaml_text(root):
    return (f"path: {json.dumps(root.resolve().as_posix(), ensure_ascii=False)}\n"
            "train: images/train\nval: images/val\ntest: images/test\n"
            "names:\n  0: gray_panel\n")


def initialize(root):
    root = root.resolve()
    config = root / "data.yaml"
    if config.exists() and config.read_text(encoding="utf-8-sig") != yaml_text(root):
        raise ValueError("기존 data.yaml이 다른 설정입니다. 덮어쓰지 않습니다. 새 폴더를 사용해 주세요.")
    for kind in ("images", "labels"):
        for split in SPLITS:
            (root / kind / split).mkdir(parents=True, exist_ok=True)
    if not config.exists():
        config.write_text(yaml_text(root), encoding="utf-8")
    return config


def label_count(path):
    """빈 라벨만 명시적인 배경 사진으로 허용합니다."""
    count = 0
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5 or parts[0] != "0":
            raise ValueError(f"{path.name}:{number}: '0 x중심 y중심 폭 높이' 5개 값이 필요합니다.")
        x, y, w, h = map(float, parts[1:])
        if not all(math.isfinite(v) for v in (x, y, w, h)):
            raise ValueError(f"{path.name}:{number}: NaN/Inf는 사용할 수 없습니다.")
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
            raise ValueError(f"{path.name}:{number}: 정규화 좌표 범위가 잘못되었습니다.")
        if x-w/2 < -1e-6 or x+w/2 > 1+1e-6 or y-h/2 < -1e-6 or y+h/2 > 1+1e-6:
            raise ValueError(f"{path.name}:{number}: 박스가 이미지 밖으로 나갑니다.")
        count += 1
    return count


def check_dataset(root, require_test=False):
    root = root.resolve()
    config = root / "data.yaml"
    if not config.is_file() or config.read_text(encoding="utf-8-sig") != yaml_text(root):
        raise ValueError("init으로 만든 data.yaml이 필요합니다. 임의 클래스/경로 변경은 허용하지 않습니다.")
    report = {"splits": {}, "warnings": []}
    seen = {}
    for split in SPLITS:
        image_dir, label_dir = root / "images" / split, root / "labels" / split
        images = sorted(p for p in image_dir.rglob("*") if p.suffix.lower() in EXTENSIONS)
        if (split != "test" or require_test) and not images:
            raise ValueError(f"{split}: 사진이 없습니다. 학습용/검증용 사진을 준비해 주세요.")
        boxes = backgrounds = 0
        expected = set()
        for path in images:
            label = label_dir / path.relative_to(image_dir).with_suffix(".txt")
            if label in expected:
                raise ValueError(f"같은 라벨을 공유하는 이미지 이름: {path.name}")
            expected.add(label)
            if not label.is_file():
                raise ValueError(f"라벨 없음: {label}. 배경 사진도 빈 .txt 파일이 필요합니다.")
            try:
                with Image.open(path) as image:
                    image.load()
                    if image.getexif().get(274, 1) != 1:
                        raise ValueError("EXIF 회전을 실제 픽셀에 적용한 뒤 다시 라벨링해 주세요.")
                    rgb = image.convert("RGB")
                    digest = hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()
            except Exception as exc:
                raise ValueError(f"이미지 확인 실패: {path}: {exc}") from exc
            if digest in seen:
                raise ValueError(f"중복 이미지: {path} / {seen[digest]}. 다른 파일명도 동일 픽셀이면 중복입니다.")
            seen[digest] = path
            count = label_count(label)
            boxes += count
            backgrounds += count == 0
        extra = set(label_dir.rglob("*.txt")) - expected
        if extra:
            raise ValueError(f"짝이 없는 라벨: {next(iter(extra))}")
        if images and not boxes:
            raise ValueError(f"{split}: gray_panel 라벨이 한 개도 없습니다.")
        report["splits"][split] = {"images": len(images), "boxes": boxes, "backgrounds": backgrounds}
        if images and len(images) < 30:
            report["warnings"].append(f"{split}: {len(images)}장뿐입니다. 실행 점검은 가능하지만 성능 판정에는 부족할 수 있습니다.")
    report["warnings"].append("연속 프레임/같은 촬영 장면의 분할 누수는 자동 검출하지 못합니다. 촬영 세션별로 나누세요.")
    return report


def local_model(path):
    path = path.resolve()
    if path.suffix.lower() != ".pt" or not path.is_file():
        raise ValueError(f"로컬 .pt 파일이 없습니다: {path}. 모델을 자동 다운로드하지 않습니다.")
    return path


def run_model(args):
    report = check_dataset(args.dataset, require_test=args.command == "validate" and args.split == "test")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    weights = local_model(args.weights)
    if args.epochs < 1 or args.batch < 1 or args.imgsz < 32 or args.imgsz % 32:
        raise ValueError("epochs/batch는 양수, imgsz는 32의 배수여야 합니다.")
    if not args.name or Path(args.name).name != args.name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in args.name):
        raise ValueError("실행 이름은 영문·숫자·밑줄·하이픈만 사용할 수 있습니다.")
    project = ROOT / "runs" / ("train" if args.command == "train" else "validation")
    if (project / args.name).exists():
        raise ValueError("동일한 결과 폴더가 있습니다. --name을 바꿔 주세요. 덮어쓰지 않습니다.")
    import torch
    from ultralytics import YOLO
    device = (0 if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    model = YOLO(str(weights))
    if model.task != "detect":
        raise ValueError("이번 라벨은 사각형 detect용입니다. 기존 segment 모델 대신 yolo11n.pt를 사용해 주세요.")
    options = dict(data=str(args.dataset.resolve()/"data.yaml"), imgsz=args.imgsz,
                   batch=args.batch, device=device, workers=0, project=str(project),
                   name=args.name, exist_ok=False, plots=False)
    print(f"장치: {device} / gray_panel 전용 / 모터 연결 없음")
    if args.command == "train":
        model.train(**options, epochs=args.epochs, patience=20, seed=42,
                    amp=False, cache=False, hsv_h=0.0, hsv_s=0.0, hsv_v=0.25,
                    degrees=10, flipud=0.0, fliplr=0.5, mosaic=0.5, close_mosaic=10)
        print(f"학습 결과: {model.trainer.save_dir / 'weights' / 'best.pt'}")
        print("자동 적용하지 않습니다. 화면 전용 미리보기에서 모델을 직접 선택해 주세요.")
    else:
        if model.names != {0: "gray_panel"}:
            raise ValueError("gray_panel로 학습된 모델만 검증할 수 있습니다. 학습 결과 best.pt를 지정해 주세요.")
        metrics = model.val(**options, split=args.split)
        print(f"검증 지표: {metrics.results_dict}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="회색 판 사각형 검출 학습 · 모터/카메라 연결 없음")
    parser.add_argument("command", choices=("init", "check", "train", "validate"))
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset")
    parser.add_argument("--weights", type=Path, default=BASE_MODEL)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="auto", help="auto / cpu / 0")
    parser.add_argument("--name", default="gray_panel_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    parser.add_argument("--split", choices=("val", "test"), default="test")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            print(f"데이터 폴더 준비: {initialize(args.dataset)}")
        elif args.command == "check":
            print(json.dumps(check_dataset(args.dataset), ensure_ascii=False, indent=2))
        else:
            run_model(args)
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        print(f"중단: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
