"""Tests for UInputBackend mouse operations.

All tests mock evdev.UInput to avoid requiring /dev/uinput access.
"""

from unittest.mock import patch, MagicMock
import pytest

from src.backends.uinput import UInputBackend


@pytest.fixture
def backend():
    with patch("src.backends.uinput.UInput") as mock_uinput_class:
        mock_mouse = MagicMock()
        mock_kbd = MagicMock()
        mock_uinput_class.side_effect = [mock_mouse, mock_kbd]
        instance = UInputBackend()
        instance._mock_mouse = mock_mouse
        instance._mock_kbd = mock_kbd
        yield instance
        instance.close()


class TestMoveRel:
    def test_move_right(self, backend):
        backend.move_rel(100, 0)
        backend._mock_mouse.write.assert_any_call(2, 0, 100)  # EV_REL, REL_X
        backend._mock_mouse.write.assert_any_call(2, 1, 0)    # EV_REL, REL_Y
        assert backend._x == 100
        assert backend._y == 0

    def test_move_diagonal(self, backend):
        backend.move_rel(-50, 30)
        backend._mock_mouse.write.assert_any_call(2, 0, -50)
        backend._mock_mouse.write.assert_any_call(2, 1, 30)
        assert backend._x == -50
        assert backend._y == 30

    def test_move_noop(self, backend):
        backend.move_rel(0, 0)
        assert backend._mock_mouse.syn.called


class TestMoveAbs:
    def test_from_origin(self, backend):
        backend.move_abs(500, 300)
        backend._mock_mouse.write.assert_any_call(2, 0, 500)
        backend._mock_mouse.write.assert_any_call(2, 1, 300)
        assert backend._x == 500
        assert backend._y == 300

    def test_relative_conversion(self, backend):
        backend._x, backend._y = 500, 300
        backend.move_abs(200, 100)
        backend._mock_mouse.write.assert_any_call(2, 0, -300)
        backend._mock_mouse.write.assert_any_call(2, 1, -200)
        assert backend._x == 200
        assert backend._y == 100

    def test_same_position(self, backend):
        backend._x, backend._y = 500, 300
        backend.move_abs(500, 300)
        assert backend._mock_mouse.syn.call_count == 0


class TestClick:
    def test_left_click(self, backend):
        backend.click(200, 100)
        # Verify EV_KEY BTN_LEFT press (1) and release (0)
        backend._mock_mouse.write.assert_any_call(1, 272, 1)
        backend._mock_mouse.write.assert_any_call(1, 272, 0)


class TestDblClick:
    def test_double_click(self, backend):
        backend.dbl_click(300, 200)
        # Key code 272 = BTN_LEFT; should be pressed twice
        press_calls = [c for c in backend._mock_mouse.write.call_args_list
                       if c[0][1] == 272 and c[0][2] == 1]
        assert len(press_calls) >= 2


class TestRightClick:
    def test_right_click(self, backend):
        backend.right_click(400, 300)
        backend._mock_mouse.write.assert_any_call(1, 273, 1)  # BTN_RIGHT
        backend._mock_mouse.write.assert_any_call(1, 273, 0)


class TestMouseDownUp:
    def test_mouse_down(self, backend):
        backend._x, backend._y = 500, 300
        backend.mouse_down("left")
        backend._mock_mouse.write.assert_called_with(1, 272, 1)
        assert backend._x == 500  # Unchanged

    def test_mouse_up(self, backend):
        backend.mouse_up("left")
        backend._mock_mouse.write.assert_called_with(1, 272, 0)

    def test_mouse_down_right(self, backend):
        backend.mouse_down("right")
        backend._mock_mouse.write.assert_called_with(1, 273, 1)


class TestScroll:
    def test_scroll_down(self, backend):
        backend.scroll(dy=-3)
        backend._mock_mouse.write.assert_called_with(2, 8, -3)  # REL_WHEEL

    def test_scroll_with_horizontal(self, backend):
        backend.scroll(dy=2, dx=1)
        calls = backend._mock_mouse.write.call_args_list
        wheel_calls = [(c[0][1], c[0][2]) for c in calls if c[0][0] == 2]
        assert (8, 2) in wheel_calls   # REL_WHEEL
        assert (6, 1) in wheel_calls   # REL_HWHEEL


class TestDrag:
    def test_drag(self, backend):
        backend.drag(100, 100, 400, 400)
        # Verify mouse_down and mouse_up were called
        press_calls = [c for c in backend._mock_mouse.write.call_args_list
                       if c[0][0] == 1 and c[0][1] == 272]
        assert press_calls[0][0][2] == 1  # press
        assert press_calls[-1][0][2] == 0  # release
        assert backend._x == 400
        assert backend._y == 400


class TestGetCursorPosition:
    def test_initial_position(self, backend):
        """get_cursor_position() returns (0, 0) after init."""
        assert backend.get_cursor_position() == (0, 0)

    def test_after_move_abs(self, backend):
        """get_cursor_position() returns tracked position after move."""
        backend.move_abs(500, 300)
        assert backend.get_cursor_position() == (500, 300)

    def test_after_move_rel(self, backend):
        """get_cursor_position() returns updated position after relative move."""
        backend.move_rel(100, -50)
        assert backend.get_cursor_position() == (100, -50)


class TestStartupWarning:
    def test_warning_printed_to_stderr(self):
        """Verify startup warning is printed to stderr on init."""
        from unittest.mock import patch
        import io
        with patch("src.backends.uinput.UInput") as mock_uinput_class:
            mock_mouse = MagicMock()
            mock_kbd = MagicMock()
            mock_uinput_class.side_effect = [mock_mouse, mock_kbd]
            with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                UInputBackend()
                output = mock_stderr.getvalue()
                assert "cursor position unknown, tracking assumes (0,0)" in output


class TestPermissionError:
    def test_no_uinput_access(self):
        with patch("src.backends.uinput.UInput", side_effect=PermissionError):
            with pytest.raises(PermissionError, match="input"):
                UInputBackend()

    def test_close_cleanup(self, backend):
        backend.close()
        backend._mock_mouse.close.assert_called_once()
        backend._mock_kbd.close.assert_called_once()
