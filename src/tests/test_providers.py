"""Tests for provider abstractions — screenshot, accessibility, vision."""

import pytest

from src.providers.screenshot import ScreenshotProvider, PortalScreenshotProvider, RawImage
from src.providers.a11y import AccessibilityProvider, NullAccessibilityProvider, A11yTree, A11yNode
from src.providers.vision import VisionProvider, DummyVisionProvider
from src.services.perception import PerceptionService


class TestScreenshotProvider:
    def test_raw_image_dataclass(self):
        raw = RawImage(bytes=b"data", mime_type="image/png", width=1920, height=1080)
        assert raw.bytes == b"data"
        assert raw.mime_type == "image/png"
        assert raw.width == 1920
        assert raw.height == 1080

    def test_screenshotprovider_is_abstract(self):
        with pytest.raises(TypeError):
            ScreenshotProvider()


class TestAccessibilityProvider:
    def test_null_provider_not_available(self):
        provider = NullAccessibilityProvider()
        assert provider.is_available() is False

    def test_null_provider_returns_empty_tree(self):
        provider = NullAccessibilityProvider()
        tree = provider.get_tree()
        assert tree.node_count == 0
        assert tree.root is None
        assert tree.source == "none"

    def test_a11y_tree_defaults(self):
        tree = A11yTree()
        assert tree.node_count == 0
        assert tree.source == "none"

    def test_a11y_node_defaults(self):
        node = A11yNode(id="btn1", role="button")
        assert node.id == "btn1"
        assert node.role == "button"
        assert node.name == ""
        assert node.bbox == [0, 0, 0, 0]
        assert node.children == []

    def test_accessibility_provider_is_abstract(self):
        with pytest.raises(TypeError):
            AccessibilityProvider()


class TestVisionProvider:
    def test_dummy_provider_returns_low_quality(self):
        provider = DummyVisionProvider()
        raw = RawImage(bytes=b"data", mime_type="image/png", width=1920, height=1080)
        result = provider.parse(raw)
        assert result.overall_quality == "low"
        assert len(result.warnings) == 1
        assert result.warnings[0].code == "image_unavailable"
        assert result.elements == []

    def test_vision_provider_is_abstract(self):
        with pytest.raises(TypeError):
            VisionProvider()


class TestPerceptionServiceWithProviders:
    def test_accepts_custom_vision_provider(self):
        class FakeVision(VisionProvider):
            def parse(self, image, a11y_hints=None):
                from src.models import AnalysisResult, AnalysisWarning
                return AnalysisResult(
                    snapshot_id="",
                    overall_quality="high",
                    warnings=[],
                    elements=[],
                )

        from unittest.mock import MagicMock

        class FakeScreenshot(ScreenshotProvider):
            def capture(self):
                return RawImage(bytes=b"x", mime_type="image/png", width=10, height=10)

            def screen_size(self):
                return (10, 10)

        input_backend = MagicMock()
        input_backend.get_cursor_position.return_value = (0, 0)

        service = PerceptionService(
            input_backend=input_backend,
            screenshot_provider=FakeScreenshot(),
            vision_provider=FakeVision(),
        )
        result = service.analyze()
        assert result.overall_quality == "high"

    def test_accepts_custom_accessibility_provider(self):
        class FakeA11y(AccessibilityProvider):
            def is_available(self):
                return True

            def get_tree(self, max_depth=5, max_nodes=200):
                return A11yTree(node_count=1, source="at-spi2")

        from unittest.mock import MagicMock

        class FakeScreenshot(ScreenshotProvider):
            def capture(self):
                return RawImage(bytes=b"x", mime_type="image/png", width=10, height=10)

            def screen_size(self):
                return (10, 10)

        input_backend = MagicMock()
        input_backend.get_cursor_position.return_value = (0, 0)

        service = PerceptionService(
            input_backend=input_backend,
            screenshot_provider=FakeScreenshot(),
            accessibility_provider=FakeA11y(),
        )
        result = service.analyze()
        assert result.overall_quality == "low"
