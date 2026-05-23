"""Cross-platform input backend abstract interface.

Defines the contract that all input backends must fulfill.
P1 implements UInputBackend; future phases add XTest, Windows, macOS backends.
"""

from abc import ABC, abstractmethod


class InputBackend(ABC):
    """Abstract base class for input simulation backends.

    All methods are abstract — subclasses must implement every one.
    The MCP server calls these methods via the tool handlers; it never
    depends on a concrete backend type.
    """

    # ── Mouse ──────────────────────────────────────────────

    @abstractmethod
    def move_abs(self, x: int, y: int) -> None:
        """Move cursor to absolute screen coordinates (x, y)."""
        ...

    @abstractmethod
    def move_rel(self, dx: int, dy: int) -> None:
        """Move cursor relative to current position by (dx, dy) pixels."""
        ...

    @abstractmethod
    def click(self, x: int, y: int, button: str = "left") -> None:
        """Move to (x, y) and perform a single click."""

    @abstractmethod
    def dbl_click(self, x: int, y: int, button: str = "left") -> None:
        """Move to (x, y) and perform a double-click."""

    @abstractmethod
    def right_click(self, x: int, y: int) -> None:
        """Move to (x, y) and perform a right-click."""

    @abstractmethod
    def mouse_down(self, button: str = "left") -> None:
        """Press a mouse button down at current position."""

    @abstractmethod
    def mouse_up(self, button: str = "left") -> None:
        """Release a mouse button at current position."""

    @abstractmethod
    def scroll(self, dy: int, dx: int = 0) -> None:
        """Scroll vertically (dy) and horizontally (dx).

        Positive dy = scroll up, negative dy = scroll down.
        Positive dx = scroll right, negative dx = scroll left.
        """

    @abstractmethod
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Drag from (x1, y1) to (x2, y2)."""

    # ── Keyboard ───────────────────────────────────────────

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type a string of text, handling shift for uppercase/symbols."""

    @abstractmethod
    def press_combo(self, keys: list[str]) -> None:
        """Press a key combination, e.g. press_combo(["ctrl", "s"])."""

    @abstractmethod
    def key_down(self, key: str) -> None:
        """Press and hold a key."""

    @abstractmethod
    def key_up(self, key: str) -> None:
        """Release a held key."""

    # ── Screen ─────────────────────────────────────────────

    @abstractmethod
    def screen_size(self) -> tuple[int, int]:
        """Return screen resolution as (width, height) in pixels."""

    @abstractmethod
    def get_cursor_position(self) -> tuple[int, int]:
        """Return tracked cursor position as (x, y) in pixels."""

    # ── Lifecycle ──────────────────────────────────────────

    @abstractmethod
    def close(self) -> None:
        """Release all resources (uinput devices, etc.)."""
