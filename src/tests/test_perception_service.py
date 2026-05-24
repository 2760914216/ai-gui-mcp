"""Tests for PerceptionService — snapshot, image, analyze methods."""

import base64
import time
import pytest
from unittest.mock import MagicMock

from src.stores.observation import ObservationStore
from src.providers.screenshot import RawImage, ScreenshotProvider
from src.providers.vision import DummyVisionProvider
from src.services.perception import PerceptionService


class FakeScreenshotProvider(ScreenshotProvider):
    def __init__(self, size=(1920, 1080)):
        self._size = size

    def capture(self) -> RawImage:
        return RawImage(
            bytes=b"fake_png_data",
            mime_type="image/png",
            width=self._size[0],
            height=self._size[1],
        )

    def screen_size(self) -> tuple[int, int]:
        return self._size


class FailingScreenshotProvider(ScreenshotProvider):
    def capture(self) -> RawImage:
        raise RuntimeError("capture failed")

    def screen_size(self) -> tuple[int, int]:
        return (1920, 1080)


def make_input_backend(cursor=(100, 200)):
    backend = MagicMock()
    backend.get_cursor_position.return_value = cursor
    return backend


class TestSnapshot:
    def test_snapshot_returns_handle(self):
        service = PerceptionService(
            input_backend=make_input_backend(),
            screenshot_provider=FakeScreenshotProvider(),
        )
        result = service.snapshot()
        assert result.snapshot_id.startswith("snap_")
        assert result.has_image is True
        assert result.image_format == "png"
        assert result.screen.width == 1920
        assert result.screen.height == 1080
        assert result.screen.cursor_x == 100
        assert result.screen.cursor_y == 200
        assert result.screen.cursor_source == "tracked"

    def test_snapshot_handle_does_not_contain_base64(self):
        service = PerceptionService(
            input_backend=make_input_backend(),
            screenshot_provider=FakeScreenshotProvider(),
        )
        result = service.snapshot()
        dumped = result.model_dump_json()
        assert "base64" not in dumped
        assert "image_base64" not in dumped

    def test_capture_failure_still_returns_handle(self):
        service = PerceptionService(
            input_backend=make_input_backend(),
            screenshot_provider=FailingScreenshotProvider(),
        )
        result = service.snapshot()
        assert result.has_image is False
        assert "capture failed" in (result.note or "")


class TestImage:
    def test_image_returns_raw_payload(self):
        service = PerceptionService(
            input_backend=make_input_backend(),
            screenshot_provider=FakeScreenshotProvider(),
        )
        snap = service.snapshot()
        payload = service.image(snap.snapshot_id)
        assert payload["snapshot_id"] == snap.snapshot_id
        assert payload["mime_type"] == "image/png"
        decoded = base64.b64decode(payload["image_base64"])
        assert decoded == b"fake_png_data"

    def test_image_unknown_snapshot_raises(self):
        service = PerceptionService(
            input_backend=make_input_backend(),
            screenshot_provider=FakeScreenshotProvider(),
        )
        with pytest.raises(ValueError, match="not available"):
            service.image("snap_nonexistent")


class TestAnalyze:
    def test_analyze_without_snapshot_id_creates_snapshot(self):
        service = PerceptionService(
            input_backend=make_input_backend(),
            screenshot_provider=FakeScreenshotProvider(),
        )
        result = service.analyze()
        assert result.snapshot_id.startswith("snap_")
        assert result.overall_quality == "low"
        assert len(result.warnings) == 1
        assert result.warnings[0].code == "image_unavailable"

    def test_analyze_caches_result(self):
        store = ObservationStore(max_count=10)
        service = PerceptionService(
            input_backend=make_input_backend(),
            screenshot_provider=FakeScreenshotProvider(),
            observation_store=store,
        )
        snap = service.snapshot()
        result1 = service.analyze(snapshot_id=snap.snapshot_id)
        result2 = service.analyze(snapshot_id=snap.snapshot_id)
        assert result1 is result2

    def test_analyze_unknown_snapshot_returns_empty(self):
        service = PerceptionService(
            input_backend=make_input_backend(),
            screenshot_provider=FakeScreenshotProvider(),
        )
        result = service.analyze(snapshot_id="snap_nonexistent")
        assert result.overall_quality == "low"
        assert result.snapshot_id == "snap_nonexistent"
