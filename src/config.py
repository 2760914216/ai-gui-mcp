"""YAML configuration loader.

Loads config.yaml and exposes structured access to server, input, screen, and
behavior settings. Uses _deep_get() for safe dotted-path access with defaults.
"""

from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field


def _deep_get(d: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Safely traverse a nested dict using dotted path notation.

    Example:
        _deep_get(config, "input.uinput.device_name", "default-name")
    """
    keys = key_path.split(".")
    for key in keys:
        if isinstance(d, dict) and key in d:
            d = d[key]
        else:
            return default
    return d


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load YAML configuration from a file path.

    Returns the parsed config dict, or an empty dict if the file is missing.
    """
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── Vision provider configuration ───────────────────────────────────


DEFAULT_GDINO_TEXT_PROMPT = (
    "button. input field. text label. checkbox. radio button. tab. "
    "menu item. link. window. dialog. sidebar. toolbar. panel. list. "
    "table. form field."
)


class VisionConfig(BaseModel):
    """Configuration for the vision provider backend.

    Defaults to ``backend="dummy"`` so non-GPU users are unaffected.
    """

    backend: Literal["dummy", "pipeline_gq"] = "dummy"

    # ── Pipeline GQ parameters ──────────────────────────────────────
    gdino_model_path: str = ""
    """Local path to Grounding DINO-T model directory (required for pipeline_gq)."""

    qwen_model_path: str = ""
    """Local path to Qwen3-VL-4B model directory (required for pipeline_gq)."""

    gdino_quantization: Optional[Literal["int8", "int4"]] = None
    """Quantization for GDINO (None = FP16)."""

    qwen_quantization: Literal["q4", "none"] = "q4"
    """Quantization for Qwen3-VL-4B."""

    effort: Literal["low", "high"] = "low"

    idle_shutdown_sec: int = Field(default=600, ge=0)
    """Idle seconds before unloading models from GPU (0 = never)."""

    text_prompt: str = DEFAULT_GDINO_TEXT_PROMPT
    """Open-vocabulary text prompt passed to Grounding DINO for detection."""

    box_threshold_low: float = Field(default=0.17, ge=0.0, le=1.0)
    """GDINO box threshold for effort='low' (high precision)."""

    box_threshold_high: float = Field(default=0.13, ge=0.0, le=1.0)
    """GDINO box threshold for effort='high' (high coverage)."""

    area_filter_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    """Bboxes covering > this fraction of screen area are dropped."""

    iou_dedup_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    """IoU threshold above which duplicate bboxes are merged."""

    min_crop_size_full: int = Field(default=32, ge=1)
    """Minimum crop side length for screens > 1024×768."""

    min_crop_size_zoom: int = Field(default=16, ge=1)
    """Minimum crop side length for screens ≤ 1024×768."""

    img_scale: float = Field(default=0.5, gt=0.0, le=1.0)
    """Input image scaling factor before inference."""

    max_tokens_per_region: int = Field(default=64, ge=1)
    """Max new tokens for Qwen per crop region."""


def load_vision_config(config: dict[str, Any]) -> VisionConfig:
    """Parse VisionConfig from the raw config dict.

    Reads ``perception.providers.vision`` and merges pipeline_gq sub-keys
    with VisionConfig defaults.  If the vision section is absent the
    result defaults to ``backend="dummy"``.
    """
    raw = _deep_get(config, "perception.providers.vision", {})
    if not raw:
        return VisionConfig()

    # Merge pipeline_gq sub-dict (if present) into the top-level config
    merged = dict(raw)
    pq = merged.pop("pipeline_gq", None)
    if pq and isinstance(pq, dict):
        # Map snake_case keys from pipeline_gq into VisionConfig fields
        field_map = {
            "gdino_model_path": "gdino_model_path",
            "qwen_model_path": "qwen_model_path",
            "gdino_quantization": "gdino_quantization",
            "qwen_quantization": "qwen_quantization",
            "effort": "effort",
            "idle_shutdown_sec": "idle_shutdown_sec",
            "text_prompt": "text_prompt",
            "box_threshold_low": "box_threshold_low",
            "box_threshold_high": "box_threshold_high",
            "area_filter_ratio": "area_filter_ratio",
            "iou_dedup_threshold": "iou_dedup_threshold",
            "min_crop_size_full": "min_crop_size_full",
            "min_crop_size_zoom": "min_crop_size_zoom",
            "img_scale": "img_scale",
            "max_tokens_per_region": "max_tokens_per_region",
        }
        for yaml_key, model_field in field_map.items():
            if yaml_key in pq:
                merged[model_field] = pq[yaml_key]
    return VisionConfig(**{k: v for k, v in merged.items()
                           if k in VisionConfig.model_fields})
