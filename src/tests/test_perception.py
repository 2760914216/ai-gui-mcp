"""Tests for P2 perception models and backends.

Covers ScreenSnapshot model validation, XdgPortalBackend.screen_size(),
and XdgPortalBackend.capture() error paths.
"""

from unittest.mock import patch, MagicMock
import pytest

from src.models import ScreenInfo, CursorInfo, UIElement, ScreenSnapshot


# ═══════════════════════════════════════════════════════════════════════
# 6.2 — ScreenSnapshot model validation
# ═══════════════════════════════════════════════════════════════════════

class TestScreenSnapshotModel:
    def test_valid_screenshot_snapshot(self):
        snap = ScreenSnapshot(
            screen=ScreenInfo(width=2560, height=1600),
            cursor=CursorInfo(x=100, y=200, source="tracked"),
            screenshot="base64data",
            elements=[],
            source="screenshot",
        )
        assert snap.screen.width == 2560
        assert snap.screen.height == 1600
        assert snap.cursor.x == 100
        assert snap.cursor.y == 200
        assert snap.cursor.source == "tracked"
        assert snap.screenshot == "base64data"
        assert snap.elements == []
        assert snap.source == "screenshot"
        assert snap.note is None

    def test_valid_accessibility_snapshot(self):
        elem = UIElement(id="btn1", role="push_button", name="OK", bbox=[10, 20, 110, 50])
        snap = ScreenSnapshot(
            screen=ScreenInfo(width=1920, height=1080),
            cursor=CursorInfo(x=50, y=50, source="tracked"),
            screenshot="img",
            elements=[elem],
            source="accessibility",
            note="AT-SPI2 tree available",
        )
        assert snap.source == "accessibility"
        assert len(snap.elements) == 1
        assert snap.elements[0].id == "btn1"
        assert snap.elements[0].role == "push_button"
        assert snap.note == "AT-SPI2 tree available"

    def test_minimum_viable_uielement(self):
        elem = UIElement(id="minimal")
        assert elem.id == "minimal"
        assert elem.role is None
        assert elem.name is None
        assert elem.bbox is None
        assert elem.states is None
        assert elem.parent is None
        assert elem.confidence is None

    def test_cursor_source_literal(self):
        cursor = CursorInfo(x=0, y=0, source="tracked")
        assert cursor.source == "tracked"
        cursor2 = CursorInfo(x=0, y=0, source="detected")
        assert cursor2.source == "detected"

    def test_invalid_cursor_source(self):
        with pytest.raises(Exception):
            CursorInfo(x=0, y=0, source="invalid")

    def test_invalid_source_literal(self):
        with pytest.raises(Exception):
            ScreenSnapshot(
                screen=ScreenInfo(width=100, height=100),
                cursor=CursorInfo(x=0, y=0, source="tracked"),
                source="invalid",
            )

    def test_model_dump_json(self):
        snap = ScreenSnapshot(
            screen=ScreenInfo(width=800, height=600),
            cursor=CursorInfo(x=10, y=20, source="tracked"),
            screenshot="abc",
            elements=[],
            source="screenshot",
        )
        json_str = snap.model_dump_json()
        assert '"width":800' in json_str
        assert '"height":600' in json_str
        assert '"screenshot":"abc"' in json_str
        assert '"source":"screenshot"' in json_str

    def test_null_screenshot_allowed(self):
        snap = ScreenSnapshot(
            screen=ScreenInfo(width=100, height=100),
            cursor=CursorInfo(x=0, y=0, source="tracked"),
            screenshot=None,
            elements=[],
            source="screenshot",
        )
        assert snap.screenshot is None

    def test_vision_source_with_confidence(self):
        elem = UIElement(id="detected1", role="button", confidence=0.95)
        snap = ScreenSnapshot(
            screen=ScreenInfo(width=1920, height=1080),
            cursor=CursorInfo(x=0, y=0, source="detected"),
            elements=[elem],
            source="vision",
        )
        assert snap.source == "vision"
        assert snap.elements[0].confidence == 0.95


# ═══════════════════════════════════════════════════════════════════════
# 6.3 — XdgPortalBackend.screen_size()
# ═══════════════════════════════════════════════════════════════════════

class FakeCard:
    def __init__(self, path, outputs):
        self.path = path
        self.outputs = outputs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestXdgPortalBackendScreenSize:
    def test_kms_detection_first_connected(self, tmp_path):
        from src.backends.portal import XdgPortalBackend

        card_dir = tmp_path / "card0"
        card_dir.mkdir()
        output_dir = card_dir / "card0-eDP-1"
        output_dir.mkdir()
        (output_dir / "status").write_text("connected")
        (output_dir / "modes").write_text("2560x1600\n")

        with patch("src.backends.portal.glob.glob") as mock_glob:
            mock_glob.side_effect = lambda p: (
                [str(output_dir)] if "card*-*" in p else
                [str(card_dir)] if "card*" in p else []
            )
            backend = XdgPortalBackend(config={})
            w, h = backend.screen_size()
            assert w == 2560
            assert h == 1600

    def test_fallback_to_config(self, tmp_path):
        """When no KMS outputs exist, fall back to config values."""
        from src.backends.portal import XdgPortalBackend

        card_dir = tmp_path / "card0"
        card_dir.mkdir()

        with patch("src.backends.portal.glob.glob") as mock_glob:
            mock_glob.side_effect = lambda p: (
                [str(card_dir)] if "card*" in p else []
            )
            backend = XdgPortalBackend(config={"screen": {"width": 1280, "height": 720}})
            w, h = backend.screen_size()
            assert w == 1280
            assert h == 720

    def test_disconnected_output_skipped(self, tmp_path):
        """Disconnected outputs are skipped, fallback to config."""
        from src.backends.portal import XdgPortalBackend

        card_dir = tmp_path / "card0"
        card_dir.mkdir()
        output_dir = card_dir / "card0-HDMI-1"
        output_dir.mkdir()
        (output_dir / "status").write_text("disconnected")

        with patch("src.backends.portal.glob.glob") as mock_glob:
            mock_glob.side_effect = lambda p: (
                [str(output_dir)] if "card*-*" in p else
                [str(card_dir)] if "card*" in p else []
            )
            backend = XdgPortalBackend(config={"screen": {"width": 1024, "height": 768}})
            w, h = backend.screen_size()
            assert w == 1024
            assert h == 768


# ═══════════════════════════════════════════════════════════════════════
# 6.4 — XdgPortalBackend.capture() error paths
# ═══════════════════════════════════════════════════════════════════════

class TestXdgPortalBackendCaptureErrors:
    def test_import_error_raises_with_hint(self):
        import builtins
        from unittest import mock

        original_import = builtins.__import__

        def selective_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in ("dbus", "dbus.mainloop.glib"):
                raise ImportError(f"No module named '{name}'")
            if name == "gi" and fromlist == ("GLib",):
                raise ImportError(f"No module named 'gi.repository'")
            return original_import(name, globals, locals, fromlist, level)

        with mock.patch.object(builtins, "__import__", selective_import):
            from src.backends.portal import XdgPortalBackend
            with pytest.raises(ImportError, match="dbus-python not available"):
                XdgPortalBackend()

    def test_timeout_raises(self):
        """When capture thread doesn't finish within timeout, raise TimeoutError."""
        from src.backends.portal import XdgPortalBackend

        with patch("src.backends.portal.glob.glob") as mock_glob:
            mock_glob.return_value = []

            backend = XdgPortalBackend(config={
                "screen": {"width": 1920, "height": 1080},
                "perception": {"screenshot": {"timeout_ms": 100}},
            })

            def slow_thread():
                import time
                time.sleep(5)

            with patch("threading.Thread") as mock_thread:
                mock_thread.return_value = MagicMock()
                mock_thread.return_value.is_alive.return_value = True

                with pytest.raises(TimeoutError, match="screenshot timeout"):
                    backend.capture()

    def test_dbus_service_unknown(self):
        from src.backends.portal import XdgPortalBackend
        import dbus

        with patch("src.backends.portal.glob.glob") as mock_glob:
            mock_glob.return_value = []

            backend = XdgPortalBackend(config={
                "screen": {"width": 1920, "height": 1080},
            })

            mock_bus = MagicMock()
            mock_bus.get_object.side_effect = dbus.DBusException(
                "org.freedesktop.DBus.Error.ServiceUnknown: The name ..."
            )
            backend._dbus.SessionBus = MagicMock(return_value=mock_bus)

            with pytest.raises(RuntimeError, match="xdg-desktop-portal not available"):
                backend.capture()
