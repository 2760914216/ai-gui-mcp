"""Linux uinput input backend — kernel-level mouse and keyboard simulation.

Works transparently on Wayland compositors. Does NOT require X11.
"""

import os
import sys
import time
import glob

from evdev import UInput, ecodes as e

from src.backends.base import InputBackend
from src.config import _deep_get

# ── Character-to-keycode mapping for type_text ──────────────────────────

_CHAR_TO_KEY = {
    # Lowercase letters
    "a": e.KEY_A, "b": e.KEY_B, "c": e.KEY_C, "d": e.KEY_D, "e": e.KEY_E,
    "f": e.KEY_F, "g": e.KEY_G, "h": e.KEY_H, "i": e.KEY_I, "j": e.KEY_J,
    "k": e.KEY_K, "l": e.KEY_L, "m": e.KEY_M, "n": e.KEY_N, "o": e.KEY_O,
    "p": e.KEY_P, "q": e.KEY_Q, "r": e.KEY_R, "s": e.KEY_S, "t": e.KEY_T,
    "u": e.KEY_U, "v": e.KEY_V, "w": e.KEY_W, "x": e.KEY_X, "y": e.KEY_Y,
    "z": e.KEY_Z,
    # Digits
    "0": e.KEY_0, "1": e.KEY_1, "2": e.KEY_2, "3": e.KEY_3, "4": e.KEY_4,
    "5": e.KEY_5, "6": e.KEY_6, "7": e.KEY_7, "8": e.KEY_8, "9": e.KEY_9,
    # Punctuation (no shift)
    " ": e.KEY_SPACE, "-": e.KEY_MINUS, "=": e.KEY_EQUAL,
    "[": e.KEY_LEFTBRACE, "]": e.KEY_RIGHTBRACE,
    "\\": e.KEY_BACKSLASH, ";": e.KEY_SEMICOLON,
    "'": e.KEY_APOSTROPHE, ",": e.KEY_COMMA, ".": e.KEY_DOT,
    "/": e.KEY_SLASH, "`": e.KEY_GRAVE,
    # Whitespace
    "\n": e.KEY_ENTER, "\t": e.KEY_TAB,
}

# Characters that require SHIFT on a US keyboard
_CHAR_TO_KEY_SHIFT = {
    "!": e.KEY_1, "@": e.KEY_2, "#": e.KEY_3, "$": e.KEY_4,
    "%": e.KEY_5, "^": e.KEY_6, "&": e.KEY_7, "*": e.KEY_8,
    "(": e.KEY_9, ")": e.KEY_0,
    "_": e.KEY_MINUS, "+": e.KEY_EQUAL,
    "{": e.KEY_LEFTBRACE, "}": e.KEY_RIGHTBRACE,
    "|": e.KEY_BACKSLASH,
    ":": e.KEY_SEMICOLON, '"': e.KEY_APOSTROPHE,
    "<": e.KEY_COMMA, ">": e.KEY_DOT, "?": e.KEY_SLASH,
    "~": e.KEY_GRAVE,
}

# Key name → ecodes mapping for press_combo / key_down / key_up
_KEY_NAME_MAP = {
    # Modifiers
    "ctrl": e.KEY_LEFTCTRL, "leftctrl": e.KEY_LEFTCTRL,
    "rightctrl": e.KEY_RIGHTCTRL,
    "shift": e.KEY_LEFTSHIFT, "leftshift": e.KEY_LEFTSHIFT,
    "rightshift": e.KEY_RIGHTSHIFT,
    "alt": e.KEY_LEFTALT, "leftalt": e.KEY_LEFTALT,
    "rightalt": e.KEY_RIGHTALT,
    "meta": e.KEY_LEFTMETA, "leftmeta": e.KEY_LEFTMETA,
    "rightmeta": e.KEY_RIGHTMETA,
    "super": e.KEY_LEFTMETA,
    # Special keys
    "enter": e.KEY_ENTER, "return": e.KEY_ENTER,
    "tab": e.KEY_TAB, "escape": e.KEY_ESC, "esc": e.KEY_ESC,
    "backspace": e.KEY_BACKSPACE, "delete": e.KEY_DELETE,
    "space": e.KEY_SPACE, "capslock": e.KEY_CAPSLOCK,
    "home": e.KEY_HOME, "end": e.KEY_END,
    "pageup": e.KEY_PAGEUP, "pagedown": e.KEY_PAGEDOWN,
    "up": e.KEY_UP, "down": e.KEY_DOWN,
    "left": e.KEY_LEFT, "right": e.KEY_RIGHT,
    "insert": e.KEY_INSERT, "print": e.KEY_PRINT,
    # Function keys
    "f1": e.KEY_F1, "f2": e.KEY_F2, "f3": e.KEY_F3,
    "f4": e.KEY_F4, "f5": e.KEY_F5, "f6": e.KEY_F6,
    "f7": e.KEY_F7, "f8": e.KEY_F8, "f9": e.KEY_F9,
    "f10": e.KEY_F10, "f11": e.KEY_F11, "f12": e.KEY_F12,
}
# Add single-letter key names
for ch in "abcdefghijklmnopqrstuvwxyz0123456789":
    if ch not in _KEY_NAME_MAP:
        _KEY_NAME_MAP[ch] = getattr(e, f"KEY_{ch.upper()}")


def _resolve_key(key: str) -> int:
    """Resolve a key name string to an evdev key code."""
    key_lower = key.lower()
    if key_lower in _KEY_NAME_MAP:
        return _KEY_NAME_MAP[key_lower]
    # Try ecodes attribute lookup as fallback
    attr = f"KEY_{key.upper()}"
    if hasattr(e, attr):
        return getattr(e, attr)
    raise ValueError(f"Unknown key: {key}")


class UInputBackend(InputBackend):
    """Linux uinput-based input simulation backend.

    Creates two virtual devices: one for mouse (relative movement + buttons)
    and one for keyboard (full key set). Tracks cursor position internally
    since Wayland does not expose global cursor coordinates.
    """

    def __init__(self, config: dict | None = None):
        config = config or {}

        # ── Mouse uinput device ──
        mouse_cap = {
            e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL],
            e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
        }
        mouse_name = _deep_get(config, "input.uinput.device_name", "ai-gui-mcp-virtual") + "-mouse"
        try:
            self._mouse = UInput(
                mouse_cap,
                name=mouse_name,
                version=0x1,
            )
        except PermissionError:
            raise PermissionError(
                "Cannot access /dev/uinput. "
                "Add your user to the 'input' group: "
                "sudo usermod -aG input $USER (then log out and back in)"
            )

        # ── Keyboard uinput device ──
        # Register valid KEY_* codes (0 < code < KEY_MAX, excluding meta-constants)
        key_codes = [
            v for k, v in vars(e).items()
            if k.startswith("KEY_") and 0 < v < e.KEY_MAX
        ]
        keyboard_cap = {e.EV_KEY: key_codes}
        keyboard_name = _deep_get(config, "input.uinput.device_name", "ai-gui-mcp-virtual") + "-keyboard"
        self._kbd = UInput(
            keyboard_cap,
            name=keyboard_name,
            version=0x1,
        )

        # ── Internal cursor tracking ──
        self._x: int = 0
        self._y: int = 0

        # ── Configuration ──
        self._config = config

        print("[ai-gui-mcp] cursor position unknown, tracking assumes (0,0)", file=sys.stderr)

    # ═══════════════════════════════════════════════════════════════════
    # Mouse
    # ═══════════════════════════════════════════════════════════════════

    def move_abs(self, x: int, y: int) -> None:
        dx = x - self._x
        dy = y - self._y
        if dx == 0 and dy == 0:
            return
        self.move_rel(dx, dy)

    def move_rel(self, dx: int, dy: int) -> None:
        self._mouse.write(e.EV_REL, e.REL_X, dx)
        self._mouse.write(e.EV_REL, e.REL_Y, dy)
        self._mouse.syn()
        self._x += dx
        self._y += dy

    def click(self, x: int, y: int, button: str = "left") -> None:
        self.move_abs(x, y)
        self._mouse_click(button)

    def dbl_click(self, x: int, y: int, button: str = "left") -> None:
        self.move_abs(x, y)
        self._mouse_click(button)
        time.sleep(0.05)
        self._mouse_click(button)

    def right_click(self, x: int, y: int) -> None:
        self.move_abs(x, y)
        self._mouse_click("right")

    def mouse_down(self, button: str = "left") -> None:
        btn_code = self._button_code(button)
        self._mouse.write(e.EV_KEY, btn_code, 1)
        self._mouse.syn()

    def mouse_up(self, button: str = "left") -> None:
        btn_code = self._button_code(button)
        self._mouse.write(e.EV_KEY, btn_code, 0)
        self._mouse.syn()

    def scroll(self, dy: int, dx: int = 0) -> None:
        if dy != 0:
            self._mouse.write(e.EV_REL, e.REL_WHEEL, dy)
        if dx != 0:
            self._mouse.write(e.EV_REL, e.REL_HWHEEL, dx)
        self._mouse.syn()

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.move_abs(x1, y1)
        self.mouse_down("left")
        self.move_abs(x2, y2)
        self.mouse_up("left")

    def _mouse_click(self, button: str) -> None:
        btn_code = self._button_code(button)
        self._mouse.write(e.EV_KEY, btn_code, 1)
        self._mouse.syn()
        time.sleep(0.02)
        self._mouse.write(e.EV_KEY, btn_code, 0)
        self._mouse.syn()

    @staticmethod
    def _button_code(button: str) -> int:
        mapping = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE}
        return mapping[button]

    # ═══════════════════════════════════════════════════════════════════
    # Keyboard
    # ═══════════════════════════════════════════════════════════════════

    def type_text(self, text: str) -> None:
        for ch in text:
            if ch in _CHAR_TO_KEY:
                self._send_key(_CHAR_TO_KEY[ch])
            elif ch in _CHAR_TO_KEY_SHIFT:
                self._send_key_with_shift(_CHAR_TO_KEY_SHIFT[ch])
            elif ch.isupper():
                # Uppercase letter: shift + key
                self._send_key_with_shift(_CHAR_TO_KEY[ch.lower()])
            else:
                # Unknown character — skip silently
                pass

    def press_combo(self, keys: list[str]) -> None:
        if not keys:
            return
        codes = [_resolve_key(k) for k in keys]
        # Identify modifiers (held throughout) vs the main key
        modifiers = {e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL, e.KEY_LEFTSHIFT,
                     e.KEY_RIGHTSHIFT, e.KEY_LEFTALT, e.KEY_RIGHTALT,
                     e.KEY_LEFTMETA, e.KEY_RIGHTMETA}
        held = []
        main_key = None
        for code in codes:
            if code in modifiers:
                held.append(code)
            else:
                main_key = code
        # Press modifiers
        for code in held:
            self._kbd.write(e.EV_KEY, code, 1)
            self._kbd.syn()
        # Press and release main key
        if main_key is not None:
            self._kbd.write(e.EV_KEY, main_key, 1)
            self._kbd.syn()
            self._kbd.write(e.EV_KEY, main_key, 0)
            self._kbd.syn()
        # Release in reverse
        for code in reversed(held):
            self._kbd.write(e.EV_KEY, code, 0)
            self._kbd.syn()

    def key_down(self, key: str) -> None:
        code = _resolve_key(key)
        self._kbd.write(e.EV_KEY, code, 1)
        self._kbd.syn()

    def key_up(self, key: str) -> None:
        code = _resolve_key(key)
        self._kbd.write(e.EV_KEY, code, 0)
        self._kbd.syn()

    def _send_key(self, code: int) -> None:
        self._kbd.write(e.EV_KEY, code, 1)
        self._kbd.syn()
        self._kbd.write(e.EV_KEY, code, 0)
        self._kbd.syn()

    def _send_key_with_shift(self, code: int) -> None:
        self._kbd.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
        self._kbd.syn()
        self._send_key(code)
        self._kbd.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
        self._kbd.syn()

    # ═══════════════════════════════════════════════════════════════════
    # Screen
    # ═══════════════════════════════════════════════════════════════════

    def screen_size(self) -> tuple[int, int]:
        """Detect screen resolution from KMS/sysfs, falling back to config."""
        # Try KMS/sysfs DRM detection
        for card_dir in sorted(glob.glob("/sys/class/drm/card*")):
            # Look in each card directory for output subdirs
            for output_dir in sorted(glob.glob(os.path.join(card_dir, "card*-*"))):
                status_path = os.path.join(output_dir, "status")
                modes_path = os.path.join(output_dir, "modes")
                try:
                    with open(status_path, "r") as f:
                        status = f.read().strip()
                except (IOError, FileNotFoundError):
                    continue
                if status != "connected":
                    continue
                # eDP preferred, but accept any connected output
                try:
                    with open(modes_path, "r") as f:
                        first_mode = f.readline().strip()
                except (IOError, FileNotFoundError):
                    continue
                if not first_mode:
                    continue
                # Parse "WIDTHxHEIGHT"
                try:
                    w_str, h_str = first_mode.split("x")
                    return int(w_str), int(h_str)
                except (ValueError, IndexError):
                    continue
        # Fallback to config.yaml
        w = _deep_get(self._config, "screen.width", 1920)
        h = _deep_get(self._config, "screen.height", 1080)
        return int(w), int(h)

    def get_cursor_position(self) -> tuple[int, int]:
        return self._x, self._y

    # ═══════════════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════════════

    def close(self) -> None:
        if hasattr(self, "_mouse"):
            self._mouse.close()
        if hasattr(self, "_kbd"):
            self._kbd.close()
