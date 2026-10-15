"""카메라·모터·실제 학습을 실행하지 않는 데이터/학습 설정 검사."""
import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
import train_gray_panel as training


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "회색 판 데이터"
        training.initialize(self.root)
        for i, split in enumerate(training.SPLITS):
            Image.new("RGB", (64, 48), (i*40, 100, 90)).save(self.root/"images"/split/"panel.png")
            (self.root/"labels"/split/"panel.txt").write_text("0 0.5 0.5 0.5 0.5\n", encoding="utf-8")

    def label(self, value):
        (self.root/"labels/train/panel.txt").write_text(value, encoding="utf-8")

    def test_valid_and_init_idempotent(self):
        training.initialize(self.root)
        self.assertEqual(training.check_dataset(self.root, True)["splits"]["train"]["boxes"], 1)

    def test_bad_labels(self):
        for value in ("1 0.5 0.5 0.5 0.5", "0 nan 0.5 0.5 0.5", "0 0.1 0.5 0.8 0.2", "0 0.5 0.5 0 0.5", "0 0.2 0.3 0.4 0.5 0.6 0.7"):
            with self.subTest(value=value):
                self.label(value)
                with self.assertRaises(ValueError):
                    training.check_dataset(self.root)

    def test_missing_label(self):
        (self.root/"labels/train/panel.txt").unlink()
        with self.assertRaisesRegex(ValueError, "라벨 없음"):
            training.check_dataset(self.root)

    def test_background_requires_positive(self):
        self.label("")
        with self.assertRaisesRegex(ValueError, "한 개도"):
            training.check_dataset(self.root)

    def test_empty_background_accepted_with_positive(self):
        Image.new("RGB", (64, 48), "white").save(self.root/"images/train/background.png")
        (self.root/"labels/train/background.txt").write_text("", encoding="utf-8")
        self.assertEqual(training.check_dataset(self.root)["splits"]["train"]["backgrounds"], 1)

    def test_duplicate_pixels(self):
        with Image.open(self.root/"images/train/panel.png") as image:
            image.save(self.root/"images/val/panel.png")
        with self.assertRaisesRegex(ValueError, "중복 이미지"):
            training.check_dataset(self.root)

    def test_corrupt_image(self):
        (self.root/"images/train/panel.png").write_bytes(b"invalid")
        with self.assertRaisesRegex(ValueError, "이미지 확인 실패"):
            training.check_dataset(self.root)

    def test_orphan_and_modified_config(self):
        extra = self.root/"labels/train/extra.txt"
        extra.write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "짝이 없는"):
            training.check_dataset(self.root)
        extra.unlink()
        (self.root/"data.yaml").write_text("names: [other]", encoding="utf-8")
        with self.assertRaises(ValueError):
            training.initialize(self.root)

    def test_no_data_no_training(self):
        empty = self.root/"empty"
        training.initialize(empty)
        self.assertEqual(training.main(["train", "--dataset", str(empty)]), 1)

    def test_local_weights_required(self):
        with self.assertRaises(ValueError):
            training.local_model(self.root/"missing.pt")

    def test_training_arguments_no_hardware(self):
        weights = self.root/"base.pt"
        weights.write_bytes(b"mock-only")
        model = MagicMock(task="detect")
        model.trainer.save_dir = self.root/"mock_run"
        factory = MagicMock(return_value=model)
        fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=factory), "torch": fake_torch}):
            result = training.main(["train", "--dataset", str(self.root), "--weights", str(weights), "--epochs", "1", "--name", "unit_test"])
        self.assertEqual(result, 0)
        kwargs = model.train.call_args.kwargs
        self.assertEqual(kwargs["workers"], 0)
        self.assertEqual(kwargs["device"], "cpu")
        self.assertFalse(kwargs["amp"])
        self.assertFalse(kwargs["exist_ok"])
        self.assertEqual(kwargs["epochs"], 1)

    def test_source_no_device_control(self):
        tree = ast.parse(Path(training.__file__).read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or "").split('.')[0])
        self.assertFalse(modules & {"serial", "cv2", "driver_adapter", "manual_motor_test"})

    def test_validate_uses_holdout(self):
        weights = self.root/"best.pt"
        weights.write_bytes(b"mock-only")
        model = MagicMock(task="detect", names={0: "gray_panel"})
        fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=lambda _: model), "torch": fake_torch}):
            result = training.main(["validate", "--dataset", str(self.root), "--weights", str(weights), "--name", "unit_validation"])
        self.assertEqual(result, 0)
        self.assertEqual(model.val.call_args.kwargs["split"], "test")
        model.train.assert_not_called()

    def test_missing_holdout_rejected(self):
        (self.root/"images/test/panel.png").unlink()
        (self.root/"labels/test/panel.txt").unlink()
        training.check_dataset(self.root)
        with self.assertRaisesRegex(ValueError, "test: 사진"):
            training.check_dataset(self.root, True)

    def test_segment_model_rejected(self):
        weights = self.root/"segment.pt"
        weights.write_bytes(b"mock-only")
        model = MagicMock(task="segment")
        fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=lambda _: model), "torch": fake_torch}):
            result = training.main(["train", "--dataset", str(self.root), "--weights", str(weights), "--name", "unit_segment"])
        self.assertEqual(result, 1)
        model.train.assert_not_called()


if __name__ == "__main__":
    unittest.main()
