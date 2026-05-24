"""Vision provider abstraction — parses screenshots into structured AnalysisResult."""

from abc import ABC, abstractmethod

from src.models import AnalysisResult, AnalysisWarning, ParsedElement
from src.providers.screenshot import RawImage
from src.providers.a11y import A11yTree


class VisionProvider(ABC):
    """Abstract vision parser that converts raw screenshots into structured
    GUI understanding results.

    Implementations may use local models (OmniParser, UI-TARS) or cloud VLMs.
    Parsing is best-effort: partial results are returned when full parsing fails.
    """

    @abstractmethod
    def parse(
        self,
        image: RawImage,
        a11y_hints: A11yTree | None = None,
    ) -> AnalysisResult:
        """Parse a screenshot into structured AnalysisResult."""
        ...


class DummyVisionProvider(VisionProvider):
    """Stub vision provider — returns empty results before real model integration.

    Used until P3A Spike selects and integrates a real vision model.
    Returns overall_quality="low" with image_unavailable warning.
    """

    def parse(
        self,
        image: RawImage,
        a11y_hints: A11yTree | None = None,
    ) -> AnalysisResult:
        return AnalysisResult(
            snapshot_id="",
            overall_quality="low",
            warnings=[
                AnalysisWarning(
                    code="image_unavailable",
                    severity="medium",
                    message="vision provider not configured (dummy stub); wait for P3A Spike to integrate real model",
                ),
            ],
            elements=[],
        )
