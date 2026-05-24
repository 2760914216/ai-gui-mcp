"""PerceptionService — internal orchestration layer for screen perception.

Composes ScreenshotProvider, AccessibilityProvider, and VisionProvider
and exposes snapshot(), analyze(), and image() methods consumed by
server.py for the screen tool actions.
"""

from datetime import datetime, timezone

from src.models import ScreenState, SnapshotResult, AnalysisResult, AnalysisWarning
from src.stores.observation import ObservationStore
from src.providers.screenshot import ScreenshotProvider, RawImage
from src.providers.a11y import AccessibilityProvider, NullAccessibilityProvider
from src.providers.vision import VisionProvider, DummyVisionProvider


class PerceptionService:
    """Orchestration layer for screen perception.

    Assembles screenshot, accessibility, and vision providers and
    exposes the three public perception methods: snapshot, analyze, image.
    """

    def __init__(
        self,
        input_backend,
        screenshot_provider: ScreenshotProvider,
        observation_store: ObservationStore | None = None,
        accessibility_provider: AccessibilityProvider | None = None,
        vision_provider: VisionProvider | None = None,
    ):
        self._input = input_backend
        self._screenshot = screenshot_provider
        self._store = observation_store or ObservationStore()
        self._a11y = accessibility_provider or NullAccessibilityProvider()
        self._vision = vision_provider or DummyVisionProvider()

    def snapshot(self) -> SnapshotResult:
        """Create a new observation handle.

        Captures screenshot, stores raw image in ObservationStore,
        returns a lightweight SnapshotResult (no base64 payload).
        On capture failure, still returns a SnapshotResult with has_image=False.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor_x, cursor_y = self._input.get_cursor_position()

        try:
            raw = self._screenshot.capture()
        except Exception as exc:
            screen = ScreenState(
                cursor_x=cursor_x,
                cursor_y=cursor_y,
                cursor_source="tracked",
            )
            return SnapshotResult(
                snapshot_id="snap_error",
                created_at=now_iso,
                screen=screen,
                has_image=False,
                image_format=None,
                note=f"capture failed: {exc}",
            )

        snapshot_id = self._store.create(
            image_bytes=raw.bytes,
            mime_type=raw.mime_type,
            screen_width=raw.width,
            screen_height=raw.height,
            cursor_x=cursor_x,
            cursor_y=cursor_y,
        )

        screen = ScreenState(
            width=raw.width,
            height=raw.height,
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            cursor_source="tracked",
        )

        return SnapshotResult(
            snapshot_id=snapshot_id,
            created_at=now_iso,
            screen=screen,
            has_image=True,
            image_format="png",
            note=None,
        )

    def image(self, snapshot_id: str) -> dict:
        """Retrieve raw image payload for a snapshot.

        Returns dict with snapshot_id, mime_type, image_base64.
        Raises ValueError if snapshot is unknown or expired.
        """
        record = self._store.get(snapshot_id)
        if record is None:
            raise ValueError(
                f"snapshot '{snapshot_id}' not available — it may have expired "
                f"or never existed"
            )

        import base64
        b64 = base64.b64encode(record.image_bytes).decode("ascii")
        return {
            "snapshot_id": snapshot_id,
            "mime_type": record.mime_type,
            "image_base64": b64,
        }

    def analyze(self, snapshot_id: str | None = None) -> AnalysisResult:
        """Produce structured GUI understanding.

        If no snapshot_id is provided, creates a new snapshot internally first.
        Uses cached analysis if available, otherwise delegates to VisionProvider.
        """
        if snapshot_id is None:
            snap_result = self.snapshot()
            snapshot_id = snap_result.snapshot_id
            if not snap_result.has_image:
                return self._empty_analysis(
                    snapshot_id,
                    warnings=[AnalysisWarning(
                        code="image_unavailable",
                        severity="high",
                        message=snap_result.note or "screenshot capture failed",
                    )],
                )

        cached = self._store.get_analysis(snapshot_id)
        if cached is not None:
            return cached

        record = self._store.get(snapshot_id)
        if record is None or not record.image_bytes:
            return self._empty_analysis(
                snapshot_id,
                warnings=[AnalysisWarning(
                    code="image_unavailable",
                    severity="high",
                    message=f"snapshot '{snapshot_id}' has no image data",
                )],
            )

        raw = RawImage(
            bytes=record.image_bytes,
            mime_type=record.mime_type,
            width=record.screen_width,
            height=record.screen_height,
        )

        a11y_tree = self._a11y.get_tree() if self._a11y.is_available() else None
        result = self._vision.parse(raw, a11y_tree)

        if result.snapshot_id != snapshot_id:
            result = AnalysisResult(
                snapshot_id=snapshot_id,
                overall_quality=result.overall_quality,
                warnings=result.warnings,
                layout_summary=result.layout_summary,
                elements=result.elements,
            )

        self._store.put_analysis(snapshot_id, result)
        return result

    @staticmethod
    def _empty_analysis(
        snapshot_id: str,
        warnings: list[AnalysisWarning] | None = None,
    ) -> AnalysisResult:
        return AnalysisResult(
            snapshot_id=snapshot_id,
            overall_quality="low",
            warnings=warnings or [],
        )
