"""Tests for UInputBackend keyboard operations.

All tests mock evdev.UInput to avoid requiring /dev/uinput access.
"""

from unittest.mock import patch, MagicMock
import pytest

from src.backends.uinput import UInputBackend, _resolve_key


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


class TestTypeText:
    def test_lowercase_hello(self, backend):
        backend.type_text("hello")
        # Each character: press then release — 5 chars × 2 writes = 10 writes
        # Plus 1 syn per char pair = 5 syns
        ev_key_calls = [
            c for c in backend._mock_kbd.write.call_args_list
            if c[0][0] == 1  # EV_KEY
        ]
        assert len(ev_key_calls) == 10  # 5 press + 5 release

    def test_uppercase_hello(self, backend):
        backend.type_text("Hello")
        # 'H' needs shift: shift_down → H_down → H_up → shift_up
        # Then e, l, l, o normally
        ev_key_calls = [
            c for c in backend._mock_kbd.write.call_args_list
            if c[0][0] == 1
        ]
        assert len(ev_key_calls) > 10  # Extra shift events for 'H'

    def test_special_char(self, backend):
        backend.type_text("!")
        # '!' is shift+1
        ev_key_calls = [
            c for c in backend._mock_kbd.write.call_args_list
            if c[0][0] == 1
        ]
        # shift_down → 1_down → 1_up → shift_up = 4 EV_KEY events
        assert len(ev_key_calls) == 4

    def test_empty_string(self, backend):
        backend.type_text("")
        assert backend._mock_kbd.write.call_count == 0

    def test_unknown_char_skipped(self, backend):
        backend.type_text("héllo")
        # é is unknown, should be skipped — only "hllo" typed (4 chars × 2)
        ev_key_calls = [
            c for c in backend._mock_kbd.write.call_args_list
            if c[0][0] == 1
        ]
        assert len(ev_key_calls) == 8  # 4 chars × 2


class TestPressCombo:
    def test_ctrl_s(self, backend):
        backend.press_combo(["ctrl", "s"])
        calls = [(c[0][1], c[0][2]) for c in backend._mock_kbd.write.call_args_list
                 if c[0][0] == 1]
        # leftctrl down → s down → s up → leftctrl up
        assert calls[0] == (29, 1)    # KEY_LEFTCTRL down
        assert calls[1] == (31, 1)    # KEY_S down
        assert calls[2] == (31, 0)    # KEY_S up
        assert calls[3] == (29, 0)    # KEY_LEFTCTRL up

    def test_ctrl_shift_s(self, backend):
        backend.press_combo(["ctrl", "shift", "s"])
        calls = [(c[0][1], c[0][2]) for c in backend._mock_kbd.write.call_args_list
                 if c[0][0] == 1]
        # leftctrl down → leftshift down → s down → s up → leftshift up → leftctrl up
        assert calls[0] == (29, 1)    # KEY_LEFTCTRL down
        assert calls[1] == (42, 1)    # KEY_LEFTSHIFT down
        assert calls[2] == (31, 1)    # KEY_S down
        assert calls[3] == (31, 0)    # KEY_S up
        assert calls[4] == (42, 0)    # KEY_LEFTSHIFT up
        assert calls[5] == (29, 0)    # KEY_LEFTCTRL up

    def test_empty_combo(self, backend):
        backend.press_combo([])
        assert backend._mock_kbd.write.call_count == 0

    def test_unknown_key_raises(self, backend):
        with pytest.raises(ValueError, match="Unknown key"):
            backend.press_combo(["nonexistent_key"])


class TestKeyDownUp:
    def test_key_down(self, backend):
        backend.key_down("a")
        assert backend._mock_kbd.write.call_args_list[-1][0] == (1, 30, 1)  # KEY_A down
        assert backend._mock_kbd.syn.called

    def test_key_up(self, backend):
        backend.key_up("a")
        assert backend._mock_kbd.write.call_args_list[-1][0] == (1, 30, 0)  # KEY_A up
        assert backend._mock_kbd.syn.called

    def test_modifier_key(self, backend):
        backend.key_down("ctrl")
        assert backend._mock_kbd.write.call_args_list[-1][0] == (1, 29, 1)
        backend.key_up("ctrl")
        assert backend._mock_kbd.write.call_args_list[-1][0] == (1, 29, 0)

    def test_unknown_key_raises(self, backend):
        with pytest.raises(ValueError, match="Unknown key"):
            backend.key_down("nonexistent")


class TestResolveKey:
    def test_known_key(self):
        assert _resolve_key("enter") == 28

    def test_case_insensitive(self):
        assert _resolve_key("CTRL") == 29
        assert _resolve_key("Shift") == 42

    def test_single_letter(self):
        assert _resolve_key("a") == 30
        assert _resolve_key("Z") == 44

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown key"):
            _resolve_key("superduperkey")
