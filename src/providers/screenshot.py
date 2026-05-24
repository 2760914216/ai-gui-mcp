import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RawImage:
    """Container for raw screenshot data."""
    bytes: bytes
    mime_type: str
    width: int
    height: int


class ScreenshotProvider(ABC):
    @abstractmethod
    def capture(self) -> RawImage:
        ...

    @abstractmethod
    def screen_size(self) -> tuple[int, int]:
        ...


class PortalScreenshotProvider(ScreenshotProvider):
    def __init__(self, portal_backend):
        self._backend = portal_backend

    def capture(self) -> RawImage:
        snapshot = self._backend.capture()
        b64_str = snapshot.screenshot or ""
        image_bytes = base64.b64decode(b64_str) if b64_str else b""
        return RawImage(
            bytes=image_bytes,
            mime_type="image/png",
            width=snapshot.screen.width,
            height=snapshot.screen.height,
        )

    def screen_size(self) -> tuple[int, int]:
        return self._backend.screen_size()
