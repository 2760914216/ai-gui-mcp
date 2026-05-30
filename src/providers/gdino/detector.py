from __future__ import annotations

from collections.abc import Iterable
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, cast

from PIL import Image


@dataclass
class DetectedBox:
    bbox: list[int]
    label: str
    confidence: float


DEFAULT_GDINO_TEXT_PROMPT = (
    "button. input field. text label. checkbox. radio button. tab. menu item. "
    "link. window. dialog. sidebar. toolbar. panel. list. table. form field."
)


class GroundingDINODetector:
    def __init__(self, model_path: str, quantization: str | None = None):
        try:
            import torch
            from transformers import (
                GroundingDinoForObjectDetection,
                GroundingDinoProcessor,
                BitsAndBytesConfig,
            )
        except ImportError as exc:
            raise ImportError(
                "PipelineGQ requires PyTorch. Install: pip install ai-gui-mcp[vision]"
            ) from exc

        self._torch: Any = torch
        self._auto_model_cls: Any = GroundingDinoForObjectDetection
        self._auto_processor_cls: Any = GroundingDinoProcessor
        self._bnb_config_cls: Any = BitsAndBytesConfig

        self._model_path: str = model_path
        self._quantization: str | None = quantization
        self._model: Any | None = None
        self._processor: Any | None = None
        self._device: Any | None = None

    def initialize(self) -> None:
        torch = self._torch

        use_cuda = torch.cuda.is_available()
        self._device = torch.device("cuda" if use_cuda else "cpu")

        self._processor = self._auto_processor_cls.from_pretrained(self._model_path)
        self._model = self._auto_model_cls.from_pretrained(self._model_path)

        if use_cuda:
            self._model = self._model.to(self._device)

    def detect(
        self,
        image: Image.Image,
        text_prompt: str,
        box_threshold: float,
    ) -> list[DetectedBox]:
        if self._model is None or self._processor is None:
            raise RuntimeError("GroundingDINODetector not initialized")

        model_inputs = self._processor(images=image, text=text_prompt, return_tensors="pt")
        if hasattr(model_inputs, "to"):
            model_inputs = model_inputs.to(self._device)

        no_grad = self._torch.no_grad if hasattr(self._torch, "no_grad") else nullcontext
        with no_grad():
            outputs = self._model(**model_inputs)

        if isinstance(model_inputs, dict):
            input_ids = model_inputs.get("input_ids")
        else:
            input_ids = getattr(model_inputs, "input_ids", None)
        processed = self._processor.post_process_grounded_object_detection(
            outputs,
            threshold=box_threshold,
            text_threshold=box_threshold,
            target_sizes=[(image.height, image.width)],
        )

        result = processed[0] if processed else {"boxes": [], "labels": [], "scores": []}
        boxes = self._as_list(result.get("boxes", []))
        labels_raw = result.get("text_labels", None) or result.get("labels", [])
        labels = self._as_list(labels_raw)
        scores = self._as_list(result.get("scores", []))

        width, height = image.width, image.height
        detected: list[DetectedBox] = []
        for box, label, score in zip(boxes, labels, scores):
            x1 = int(max(0, min(width, float(box[0]))))
            y1 = int(max(0, min(height, float(box[1]))))
            x2 = int(max(0, min(width, float(box[2]))))
            y2 = int(max(0, min(height, float(box[3]))))

            detected.append(
                DetectedBox(
                    bbox=[x1, y1, x2, y2],
                    label=str(label),
                    confidence=float(score),
                )
            )

        return detected

    def shutdown(self) -> None:
        self._model = None
        self._processor = None
        self._device = None

        if self._torch.cuda.is_available():
            self._torch.cuda.empty_cache()

    @property
    def is_initialized(self) -> bool:
        return self._model is not None

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            return cast(list[Any], tolist())
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
            return [item for item in value]
        return [value]
