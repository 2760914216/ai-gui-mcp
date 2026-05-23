"""Cross-platform screen perception backend abstract interface.

Defines the contract that all perception backends must fulfill.
Independent of InputBackend — perception and input are separate concerns.
"""

from abc import ABC, abstractmethod

from src.models import ScreenSnapshot


class ScreenBackend(ABC):
    """Abstract base class for screen perception backends.

    All methods are abstract — subclasses must implement every one.
    This is a production-grade interface for screen capture and perception,
    independent of InputBackend.
    """

    @abstractmethod
    def capture(self) -> ScreenSnapshot:
        """Capture full-screen snapshot returning structured data.

        Returns a ScreenSnapshot containing screen metadata, cursor info,
        optional base64-encoded screenshot, and optional structured elements.
        """

    @abstractmethod
    def screen_size(self) -> tuple[int, int]:
        """Return screen resolution as (width, height) in pixels.

        Implemented independently from InputBackend.screen_size().
        """

    @abstractmethod
    def close(self) -> None:
        """Release all resources (D-Bus connections, etc.)."""
