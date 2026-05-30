"""Vision provider abstraction — parses screenshots into structured AnalysisResult."""

from abc import ABC, abstractmethod
from io import BytesIO
from time import time
from typing import Literal, cast

from PIL import Image

from src.config import VisionConfig
from src.models import AnalysisResult, AnalysisWarning, ParsedElement
from src.providers.screenshot import RawImage
from src.providers.a11y import A11yTree
from src.providers.gdino.detector import DEFAULT_GDINO_TEXT_PROMPT, GroundingDINODetector
from src.providers.gdino.label_mapper import GdinoLabelMapper
from src.providers.qwen_vl.descriptor import QwenVLDescriptor
from src.providers.vision_postprocess import (
    adaptive_min_crop_size,
    clamp_bbox,
    deduplicate_by_iou,
    filter_by_area,
    should_skip_crop,
)


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


class PipelineGQVisionProvider(VisionProvider):
    """Two-stage GUI parsing pipeline: Grounding DINO-T detection → Qwen3-VL-4B description.

    The pipeline operates in two stages:
      1. GDINO performs open-vocabulary detection → raw bounding boxes + labels
      2. For each retained bbox, GDINO label is mapped to a coarse category
         (interactive / structural / unknown), constraining Qwen's type selection.
         Qwen examines the cropped region and returns a fine-grained element type.

    Models are lazy-loaded on first ``parse()`` and can be unloaded after a
    configurable idle period via ``shutdown()``.
    """

    _ELEMENT_TYPE_SET: set[str] = {
        "button", "input", "checkbox", "radio", "tab", "menuitem", "link",
        "window", "dialog", "sidebar", "toolbar", "panel", "list", "table",
        "form", "text", "unknown",
    }

    def __init__(self, config: VisionConfig):
        try:
            __import__("torch")
            __import__("transformers")
        except ImportError as exc:
            raise ImportError(
                "PipelineGQVisionProvider requires ML dependencies. "
                "Install: pip install ai-gui-mcp[vision]"
            ) from exc

        self._config: VisionConfig = config
        self._gdino: GroundingDINODetector | None = None
        self._qwen: QwenVLDescriptor | None = None
        self._mapper: GdinoLabelMapper = GdinoLabelMapper()

    def initialize(self) -> None:
        if self._gdino is not None:
            return

        gdino = GroundingDINODetector(
            model_path=self._config.gdino_model_path,
            quantization=self._config.gdino_quantization,
        )
        gdino.initialize()

        qwen = QwenVLDescriptor(
            model_path=self._config.qwen_model_path,
            quantization=self._config.qwen_quantization if self._config.qwen_quantization != "none" else "q4",
            max_tokens_per_region=self._config.max_tokens_per_region,
        )
        if self._config.qwen_quantization != "none":
            qwen.initialize()
        else:
            qwen._quantization = "none"
            qwen.initialize()

        self._gdino = gdino
        self._qwen = qwen

    def shutdown(self) -> None:
        if self._gdino is not None:
            self._gdino.shutdown()
            self._gdino = None
        if self._qwen is not None:
            self._qwen.shutdown()
            self._qwen = None

    def parse(
        self,
        image: RawImage,
        a11y_hints: A11yTree | None = None,
    ) -> AnalysisResult:
        if self._gdino is None:
            self.initialize()

        snapshot_id = f"analyze_{int(time() * 1000)}"
        warnings: list[AnalysisWarning] = []

        full_image = Image.open(BytesIO(image.bytes)).convert("RGB")
        orig_w, orig_h = full_image.width, full_image.height

        img_scale = self._config.img_scale
        if img_scale < 1.0:
            scaled_w = max(1, int(orig_w * img_scale))
            scaled_h = max(1, int(orig_h * img_scale))
            scaled_image = full_image.resize((scaled_w, scaled_h), getattr(Image, "LANCZOS", Image.Resampling.LANCZOS))
        else:
            scaled_w, scaled_h = orig_w, orig_h
            scaled_image = full_image

        box_threshold = (
            self._config.box_threshold_high
            if self._config.effort == "high"
            else self._config.box_threshold_low
        )

        assert self._gdino is not None
        raw_detections = self._gdino.detect(
            image=scaled_image,
            text_prompt=self._config.text_prompt or DEFAULT_GDINO_TEXT_PROMPT,
            box_threshold=box_threshold,
        )

        if img_scale < 1.0:
            inv_scale = 1.0 / img_scale
            for det in raw_detections:
                det.bbox = [
                    int(det.bbox[0] * inv_scale),
                    int(det.bbox[1] * inv_scale),
                    int(det.bbox[2] * inv_scale),
                    int(det.bbox[3] * inv_scale),
                ]

        filtered, _ = filter_by_area(raw_detections, orig_w, orig_h, self._config.area_filter_ratio)
        deduped, dup_count = deduplicate_by_iou(filtered, self._config.iou_dedup_threshold)
        for _ in range(dup_count):
            warnings.append(AnalysisWarning(
                code="duplicate_element",
                severity="low",
                message="overlapping detection removed during IoU deduplication",
            ))

        min_crop = adaptive_min_crop_size(orig_w, orig_h)
        candidates = []
        for det in deduped:
            clamped = clamp_bbox(det.bbox, orig_w, orig_h)
            if not should_skip_crop(clamped, min_crop):
                candidates.append((det, clamped))

        elements: list[ParsedElement] = []
        for idx, (detection, bbox) in enumerate(candidates):
            x1, y1, x2, y2 = bbox
            bw = x2 - x1
            bh = y2 - y1
            pad_w = max(1, int(bw * 0.1))
            pad_h = max(1, int(bh * 0.1))
            crop_box = (
                max(0, x1 - pad_w),
                max(0, y1 - pad_h),
                min(orig_w, x2 + pad_w),
                min(orig_h, y2 + pad_h),
            )
            crop = full_image.crop(crop_box)

            coarse = self._mapper.map(detection.label)

            assert self._qwen is not None
            try:
                description = self._qwen.describe(crop, coarse)
            except Exception:
                continue

            resolved_type: str = description.type if description.type in self._ELEMENT_TYPE_SET else "unknown"
            element_type = cast(
                Literal[
                    "button", "input", "checkbox", "radio", "tab", "menuitem", "link",
                    "window", "dialog", "sidebar", "toolbar", "panel", "list", "table",
                    "form", "text", "unknown",
                ],
                resolved_type,
            )

            elements.append(ParsedElement(
                id=f"elem_{idx}",
                type=element_type,
                bbox=clamp_bbox(detection.bbox, orig_w, orig_h),
                text=description.text,
                confidence=detection.confidence,
            ))

        element_count = len(elements)
        if element_count > 10:
            overall_quality: Literal["high", "medium", "low"] = "high"
        elif element_count > 0:
            overall_quality = "medium"
        else:
            overall_quality = "low"

        return AnalysisResult(
            snapshot_id=snapshot_id,
            overall_quality=overall_quality,
            warnings=warnings,
            elements=elements,
        )

    @property
    def is_initialized(self) -> bool:
        return self._gdino is not None and self._qwen is not None
