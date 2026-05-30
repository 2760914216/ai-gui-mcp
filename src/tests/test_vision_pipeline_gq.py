from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import pytest
from PIL import Image

from src.config import VisionConfig
from src.providers.gdino.detector import DetectedBox
from src.providers.qwen_vl.descriptor import ElementDescription
from src.providers.screenshot import RawImage
from src.providers.vision import PipelineGQVisionProvider


def _make_raw_image(width: int = 1920, height: int = 1080) -> RawImage:
    img = Image.new("RGB", (width, height), color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return RawImage(bytes=buf.getvalue(), mime_type="image/png", width=width, height=height)


def _bypass_import_guard(monkeypatch):
    import builtins
    _orig_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name in ("torch", "transformers"):
            return MagicMock()
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)


class TestPipelineGQVisionProvider:
    def test_parse_returns_analysis_result(self, monkeypatch):
        _bypass_import_guard(monkeypatch)
        config = VisionConfig(
            backend="pipeline_gq",
            gdino_model_path="/fake/gdino",
            qwen_model_path="/fake/qwen",
            effort="low",
        )
        provider = PipelineGQVisionProvider(config)

        mock_gdino = MagicMock()
        mock_qwen = MagicMock()
        provider._gdino = mock_gdino
        provider._qwen = mock_qwen

        mock_gdino.detect.return_value = [
            DetectedBox(bbox=[100, 200, 300, 400], label="button", confidence=0.85),
            DetectedBox(bbox=[500, 100, 700, 250], label="text input", confidence=0.72),
        ]
        mock_qwen.describe.side_effect = [
            ElementDescription(type="button", text="Click Me", confidence=0.98),
            ElementDescription(type="input", text="Enter text", confidence=0.96),
        ]

        raw = _make_raw_image()
        result = provider.parse(raw)

        assert result.snapshot_id.startswith("analyze_")
        assert result.overall_quality == "medium"
        assert len(result.elements) == 2
        assert result.elements[0].type == "button"
        assert result.elements[0].text == "Click Me"
        assert result.elements[0].confidence == pytest.approx(0.85)
        assert result.elements[1].type == "input"

    def test_effort_low_uses_high_threshold(self, monkeypatch):
        _bypass_import_guard(monkeypatch)
        config = VisionConfig(backend="pipeline_gq", gdino_model_path="/x", qwen_model_path="/y", effort="low")
        provider = PipelineGQVisionProvider(config)

        mock_gdino = MagicMock()
        mock_qwen = MagicMock()
        provider._gdino = mock_gdino
        provider._qwen = mock_qwen
        mock_gdino.detect.return_value = [
            DetectedBox(bbox=[10, 10, 50, 50], label="button", confidence=0.9),
        ]
        mock_qwen.describe.return_value = ElementDescription(type="button", text="OK", confidence=0.98)

        provider.parse(_make_raw_image())
        call_args = mock_gdino.detect.call_args
        assert call_args.kwargs["box_threshold"] == pytest.approx(0.17)

    def test_effort_high_uses_low_threshold(self, monkeypatch):
        _bypass_import_guard(monkeypatch)
        config = VisionConfig(backend="pipeline_gq", gdino_model_path="/x", qwen_model_path="/y", effort="high")
        provider = PipelineGQVisionProvider(config)

        mock_gdino = MagicMock()
        mock_qwen = MagicMock()
        provider._gdino = mock_gdino
        provider._qwen = mock_qwen
        mock_gdino.detect.return_value = [
            DetectedBox(bbox=[10, 10, 50, 50], label="button", confidence=0.9),
        ]
        mock_qwen.describe.return_value = ElementDescription(type="button", text="OK", confidence=0.98)

        provider.parse(_make_raw_image())
        call_args = mock_gdino.detect.call_args
        assert call_args.kwargs["box_threshold"] == pytest.approx(0.13)

    def test_zero_detections_returns_empty_elements(self, monkeypatch):
        _bypass_import_guard(monkeypatch)
        config = VisionConfig(backend="pipeline_gq", gdino_model_path="/x", qwen_model_path="/y")
        provider = PipelineGQVisionProvider(config)

        mock_gdino = MagicMock()
        mock_qwen = MagicMock()
        provider._gdino = mock_gdino
        provider._qwen = mock_qwen
        mock_gdino.detect.return_value = []

        result = provider.parse(_make_raw_image())

        assert result.elements == []
        assert result.overall_quality == "low"
        mock_qwen.describe.assert_not_called()

    def test_parse_implicit_initialize_on_first_call(self, monkeypatch):
        _bypass_import_guard(monkeypatch)
        config = VisionConfig(backend="pipeline_gq", gdino_model_path="/x", qwen_model_path="/y")
        provider = PipelineGQVisionProvider(config)
        assert not provider.is_initialized

        monkeypatch.setattr(
            "src.providers.gdino.detector.GroundingDINODetector.initialize", lambda self: None
        )
        monkeypatch.setattr(
            "src.providers.qwen_vl.descriptor.QwenVLDescriptor.initialize", lambda self: None
        )

        mock_detect = MagicMock(return_value=[])
        monkeypatch.setattr(
            "src.providers.gdino.detector.GroundingDINODetector.detect", mock_detect
        )

        provider.parse(_make_raw_image())
        assert provider.is_initialized

    def test_qwen_parse_error_is_skipped(self, monkeypatch):
        _bypass_import_guard(monkeypatch)
        config = VisionConfig(backend="pipeline_gq", gdino_model_path="/x", qwen_model_path="/y")
        provider = PipelineGQVisionProvider(config)

        mock_gdino = MagicMock()
        mock_qwen = MagicMock()
        provider._gdino = mock_gdino
        provider._qwen = mock_qwen

        mock_gdino.detect.return_value = [
            DetectedBox(bbox=[100, 100, 300, 300], label="button", confidence=0.9),
            DetectedBox(bbox=[400, 100, 600, 300], label="text", confidence=0.8),
        ]
        mock_qwen.describe.side_effect = [
            ValueError("parse error"),
            ElementDescription(type="input", text="hello", confidence=0.95),
        ]

        result = provider.parse(_make_raw_image())

        assert len(result.elements) == 1
        assert result.elements[0].type == "input"

    def test_overall_quality_high(self, monkeypatch):
        _bypass_import_guard(monkeypatch)
        config = VisionConfig(backend="pipeline_gq", gdino_model_path="/x", qwen_model_path="/y")
        provider = PipelineGQVisionProvider(config)

        mock_gdino = MagicMock()
        mock_qwen = MagicMock()
        provider._gdino = mock_gdino
        provider._qwen = mock_qwen

        mock_gdino.detect.return_value = [
            DetectedBox(bbox=[i * 50, i * 50, i * 50 + 40, i * 50 + 40], label=f"elem_{i}", confidence=0.9)
            for i in range(15)
        ]
        mock_qwen.describe.return_value = ElementDescription(type="button", text="x", confidence=0.98)

        result = provider.parse(_make_raw_image(2560, 1600))
        assert result.overall_quality == "high"
        assert len(result.elements) == 15

    def test_overall_quality_medium(self, monkeypatch):
        _bypass_import_guard(monkeypatch)
        config = VisionConfig(backend="pipeline_gq", gdino_model_path="/x", qwen_model_path="/y")
        provider = PipelineGQVisionProvider(config)

        mock_gdino = MagicMock()
        mock_qwen = MagicMock()
        provider._gdino = mock_gdino
        provider._qwen = mock_qwen

        mock_gdino.detect.return_value = [
            DetectedBox(bbox=[0, 0, 50, 50], label=f"elem_{i}", confidence=0.9)
            for i in range(3)
        ]
        mock_qwen.describe.return_value = ElementDescription(type="button", text="x", confidence=0.98)

        result = provider.parse(_make_raw_image())
        assert result.overall_quality == "medium"

    def test_import_guard_raises_on_missing_deps(self, monkeypatch):
        import builtins
        _orig_import = builtins.__import__

        def _fail_torch(name, *args, **kwargs):
            if name in ("torch", "transformers"):
                raise ImportError("no torch")
            return _orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fail_torch)
        config = VisionConfig(backend="pipeline_gq", gdino_model_path="/x", qwen_model_path="/y")
        with pytest.raises(ImportError, match="pip install ai-gui-mcp\\[vision\\]"):
            PipelineGQVisionProvider(config)

    def test_shutdown_releases_models(self, monkeypatch):
        _bypass_import_guard(monkeypatch)
        config = VisionConfig(backend="pipeline_gq", gdino_model_path="/x", qwen_model_path="/y")
        provider = PipelineGQVisionProvider(config)

        mock_gdino = MagicMock()
        mock_qwen = MagicMock()
        provider._gdino = mock_gdino
        provider._qwen = mock_qwen

        provider.shutdown()
        assert provider._gdino is None
        assert provider._qwen is None
        assert not provider.is_initialized
        mock_gdino.shutdown.assert_called_once()
        mock_qwen.shutdown.assert_called_once()
