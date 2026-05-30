from __future__ import annotations

import builtins
import sys
import types
from unittest.mock import MagicMock

import pytest
from PIL import Image

from src.providers.gdino.detector import (
    DEFAULT_GDINO_TEXT_PROMPT,
    DetectedBox,
    GroundingDINODetector,
)


@pytest.fixture
def fake_ml_modules(monkeypatch: pytest.MonkeyPatch):
    fake_torch = types.SimpleNamespace(
        float16="float16",
        device=lambda name: f"device:{name}",
        cuda=types.SimpleNamespace(
            is_available=lambda: False,
            empty_cache=MagicMock(),
        ),
    )
    fake_transformers = types.SimpleNamespace(
        AutoModelForZeroShotObjectDetection=MagicMock(),
        AutoProcessor=MagicMock(),
        BitsAndBytesConfig=MagicMock(),
    )

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    return fake_torch, fake_transformers


class TestDetectedBox:
    def test_dataclass_creation(self):
        box = DetectedBox(bbox=[1, 2, 3, 4], label="button", confidence=0.95)
        assert box.bbox == [1, 2, 3, 4]
        assert box.label == "button"
        assert box.confidence == 0.95


class TestGroundingDINODetector:
    def test_init_stores_config(self, fake_ml_modules):
        detector = GroundingDINODetector(model_path="/tmp/gdino", quantization="4bit")

        assert detector._model_path == "/tmp/gdino"
        assert detector._quantization == "4bit"
        assert detector._model is None
        assert detector._processor is None
        assert detector.is_initialized is False

    def test_init_import_guard(self, monkeypatch: pytest.MonkeyPatch):
        original_import = builtins.__import__

        def selective_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "torch":
                raise ImportError("No module named 'torch'")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", selective_import)

        with pytest.raises(ImportError, match="Install: pip install ai-gui-mcp\\[vision\\]"):
            GroundingDINODetector(model_path="/tmp/gdino")

    def test_initialize_loads_model(self, fake_ml_modules):
        _, fake_transformers = fake_ml_modules
        mock_model = MagicMock()
        mock_model.to.return_value = mock_model
        mock_processor = MagicMock()

        fake_transformers.AutoModelForZeroShotObjectDetection.from_pretrained.return_value = mock_model
        fake_transformers.AutoProcessor.from_pretrained.return_value = mock_processor

        detector = GroundingDINODetector(model_path="/tmp/gdino")
        detector.initialize()

        assert detector._model is mock_model
        assert detector._processor is mock_processor
        assert detector.is_initialized is True

    def test_detect_returns_boxes(self, fake_ml_modules):
        detector = GroundingDINODetector(model_path="/tmp/gdino")
        detector._device = "cpu"
        detector._model = MagicMock(return_value={"logits": []})

        model_inputs = MagicMock()
        model_inputs.to.return_value = {"pixel_values": "x", "input_ids": [1, 2, 3]}

        processor = MagicMock()
        processor.return_value = model_inputs
        processor.post_process_grounded_object_detection.return_value = [
            {
                "boxes": [[1.2, 2.9, 50.5, 60.1]],
                "labels": ["button"],
                "scores": [0.87],
            }
        ]
        detector._processor = processor

        image = Image.new("RGB", (100, 80), color="white")
        boxes = detector.detect(image=image, text_prompt=DEFAULT_GDINO_TEXT_PROMPT, box_threshold=0.35)

        assert len(boxes) == 1
        assert isinstance(boxes[0].bbox, list)
        assert all(isinstance(value, int) for value in boxes[0].bbox)
        assert isinstance(boxes[0].label, str)
        assert isinstance(boxes[0].confidence, float)

    def test_detect_clamps_coords(self, fake_ml_modules):
        detector = GroundingDINODetector(model_path="/tmp/gdino")
        detector._device = "cpu"
        detector._model = MagicMock(return_value={"logits": []})

        model_inputs = MagicMock()
        model_inputs.to.return_value = {"pixel_values": "x", "input_ids": [1, 2, 3]}

        processor = MagicMock()
        processor.return_value = model_inputs
        processor.post_process_grounded_object_detection.return_value = [
            {
                "boxes": [[-12.0, -5.0, 500.0, 999.9]],
                "labels": ["panel"],
                "scores": [0.65],
            }
        ]
        detector._processor = processor

        image = Image.new("RGB", (120, 90), color="white")
        boxes = detector.detect(image=image, text_prompt="panel", box_threshold=0.25)

        assert boxes[0].bbox == [0, 0, 120, 90]

    def test_shutdown_releases_memory(self, fake_ml_modules):
        fake_torch, _ = fake_ml_modules
        fake_torch.cuda.is_available = lambda: True

        detector = GroundingDINODetector(model_path="/tmp/gdino")
        detector._model = MagicMock()
        detector._processor = MagicMock()

        detector.shutdown()

        assert detector._model is None
        assert detector._processor is None
        fake_torch.cuda.empty_cache.assert_called_once()

    def test_is_initialized(self, fake_ml_modules):
        detector = GroundingDINODetector(model_path="/tmp/gdino")
        assert detector.is_initialized is False

        detector._model = MagicMock()
        assert detector.is_initialized is True
