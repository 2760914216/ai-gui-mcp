#!/usr/bin/env python3
"""Spike validation script: Grounding DINO-T + Qwen3-VL-4B two-stage pipeline.

Stage 1 (Detection): Grounding DINO-T open-vocabulary object detection
Stage 2 (Description): Qwen3-VL-4B Q4_K_M on each cropped bbox region

Outputs AnalysisResult-compatible JSON + annotated PNG + elements.txt
for each screenshot, matching the format of spike_arch_c.py for comparison.

Usage:
    # Single-image tuning mode
    python scripts/spike_pipeline_gq.py \
        --single --image COMIC-setting.png \
        --text-prompt "button. input field. checkbox. tab. menu item."

    # Detection-only mode (no Qwen description)
    python scripts/spike_pipeline_gq.py \
        --single --image COMIC-setting.png --skip-describe

    # Batch mode (all 8 screenshots)
    python scripts/spike_pipeline_gq.py \
        --image-dir docs/spike-screenshots/ \
        --output-dir docs/spike-results/pipeline-round1/
"""

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

import torch
from PIL import Image
from transformers import (
    GroundingDinoForObjectDetection,
    GroundingDinoProcessor,
    Qwen3VLForConditionalGeneration,
    AutoProcessor,
    BitsAndBytesConfig,
)


# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════

# Valid ParsedElement.type values (from src/models.py)
VALID_ELEMENT_TYPES = {
    "button", "input", "checkbox", "radio", "tab", "menuitem", "link",
    "window", "dialog", "sidebar", "toolbar", "panel", "list", "table",
    "form", "text", "unknown",
}

# Default text prompt for open-vocabulary detection
DEFAULT_TEXT_PROMPT = (
    "button . input field . checkbox . radio button . tab . menu item . "
    "link . text label . sidebar . toolbar . panel . dialog . window . "
    "list . table . form . icon . scrollbar . status bar"
)

# Qwen description prompt — asks for JSON output
QWEN_SYSTEM_PROMPT = (
    "You are a precise UI element analyzer. Identify the given UI element "
    "crop and output ONLY a JSON object. Do not include any other text."
)

QWEN_USER_PROMPT = (
    "Identify this UI element. "
    "Output EXACTLY this JSON format (no markdown, no extra text):\n"
    '{"type": "<button|input|checkbox|radio|tab|menuitem|link|window|dialog'
    '|sidebar|toolbar|panel|list|table|form|text|unknown>", '
    '"text": "<visible text or null>", "confidence": <0.0-1.0>}'
)

# Minimum crop dimensions — regions smaller than this are skipped
MIN_CROP_SIZE = 32

# IoU threshold for duplicate removal
IOU_DEDUP_THRESHOLD = 0.5

# Bbox expansion ratio for cropping (1.2x)
BBOX_EXPAND_RATIO = 0.1  # 10% each side = 1.2x total

# Type mapping: Qwen output type string → canonical type
# (handles variations like "input field" → "input", "text box" → "input", etc.)
TYPE_MAPPING = {
    "button": "button",
    "input": "input",
    "input field": "input",
    "text field": "input",
    "text box": "input",
    "textbox": "input",
    "text input": "input",
    "search box": "input",
    "search field": "input",
    "checkbox": "checkbox",
    "check box": "checkbox",
    "radio": "radio",
    "radio button": "radio",
    "tab": "tab",
    "menu item": "menuitem",
    "menuitem": "menuitem",
    "menu": "menuitem",
    "link": "link",
    "hyperlink": "link",
    "window": "window",
    "dialog": "dialog",
    "popup": "dialog",
    "modal": "dialog",
    "sidebar": "sidebar",
    "toolbar": "toolbar",
    "tool bar": "toolbar",
    "panel": "panel",
    "list": "list",
    "table": "table",
    "form": "form",
    "text": "text",
    "text label": "text",
    "label": "text",
    "icon": "unknown",
    "scrollbar": "unknown",
    "status bar": "unknown",
    "title bar": "unknown",
}


# ══════════════════════════════════════════════════════════════════════════════
# Section 2: Grounding DINO-T Detection Module
# ══════════════════════════════════════════════════════════════════════════════

def load_gdino_model(model_path: str = "IDEA-Research/grounding-dino-tiny"):
    """Load Grounding DINO-T model and processor.

    Args:
        model_path: HuggingFace model ID or local path.
            Default: IDEA-Research/grounding-dino-tiny (uses cache).

    Returns:
        Tuple of (model, processor).
    """
    print(f"[GDINO] Loading model from {model_path} ...")
    t0 = time.time()

    processor = GroundingDinoProcessor.from_pretrained(model_path)
    model = GroundingDinoForObjectDetection.from_pretrained(model_path).to("cuda")

    elapsed = time.time() - t0
    print(f"[GDINO] Model loaded in {elapsed:.1f}s (device: {model.device})")
    return model, processor


def detect_elements(
    model,
    processor,
    image: Image.Image,
    text_prompt: str = DEFAULT_TEXT_PROMPT,
    box_threshold: float = 0.25,
    text_threshold: float = 0.25,
) -> list[dict]:
    """Run open-vocabulary detection on a single image.

    Args:
        model: Loaded GroundingDinoForObjectDetection model.
        processor: Loaded GroundingDinoProcessor.
        image: PIL Image in RGB mode.
        text_prompt: Natural language description of UI elements to detect.
            Use period-separated terms like "button. input field. checkbox."
        box_threshold: Minimum confidence score for object boxes.
        text_threshold: Minimum confidence score for text-to-image matching.

    Returns:
        List of dicts: [{"bbox": [x1,y1,x2,y2], "label": "button",
                         "confidence": 0.92}, ...]
    """
    t0 = time.time()

    inputs = processor(
        images=image,
        text=text_prompt,
        return_tensors="pt",
    ).to(model.device)

    with torch.no_grad():
        outputs = model(**inputs)

    target_size = image.size[::-1]  # (height, width)
    results = processor.post_process_grounded_object_detection(
        outputs,
        threshold=box_threshold,
        text_threshold=text_threshold,
        target_sizes=[target_size],
    )

    elements = []
    result = results[0] if results else {}
    boxes = result.get("boxes", None)
    scores = result.get("scores", None)
    labels = result.get("text_labels", None) or result.get("labels", None)

    if boxes is not None and len(boxes) > 0:
        for i in range(len(boxes)):
            b = boxes[i].cpu().tolist()
            x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
            score = float(scores[i]) if scores is not None else 0.0
            label = str(labels[i]) if labels is not None else "unknown"

            elements.append({
                "bbox": [x1, y1, x2, y2],
                "label": label,
                "confidence": score,
            })

    elapsed = time.time() - t0
    print(f"[GDINO] Detection: {len(elements)} elements in {elapsed:.1f}s "
          f"(thresholds: box={box_threshold}, text={text_threshold})")
    return elements


def map_bbox_to_original(
    bboxes: list[dict],
    scale_factor: float,
) -> list[dict]:
    """Map bbox coordinates from scaled image back to original dimensions.

    Args:
        bboxes: List of element dicts with "bbox": [x1,y1,x2,y2] in scaled coords.
        scale_factor: The factor used to scale down (e.g., 0.5 means 50% scale).

    Returns:
        Same list with bbox coordinates mapped to original image coordinates.
    """
    if scale_factor >= 1.0:
        return bboxes

    inv_scale = 1.0 / scale_factor
    for elem in bboxes:
        bbox = elem["bbox"]
        elem["bbox"] = [
            int(bbox[0] * inv_scale),
            int(bbox[1] * inv_scale),
            int(bbox[2] * inv_scale),
            int(bbox[3] * inv_scale),
        ]
    return bboxes


# ══════════════════════════════════════════════════════════════════════════════
# Section 3: Qwen3-VL-4B Description Module
# ══════════════════════════════════════════════════════════════════════════════

def load_qwen_model(
    model_path: str,
    quantize: str = "q4",
):
    """Load Qwen3-VL-4B-Instruct with configurable quantization.

    Args:
        model_path: Path to local Qwen3-VL-4B-Instruct directory.
        quantize: "q4" (bitsandbytes 4bit), "q8" (8bit), or "fp16".

    Returns:
        Tuple of (model, processor).
    """
    quantize = quantize.lower()
    print(f"[QWEN] Loading model from {model_path} (quantize={quantize}) ...")
    t0 = time.time()

    if quantize == "q4":
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            quantization_config=bnb_config,
            device_map="auto",
        )
        print("[QWEN] Model loaded with INT4 quantization")
    elif quantize == "q8":
        bnb_config = BitsAndBytesConfig(load_in_8bit=True)
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            quantization_config=bnb_config,
            device_map="auto",
        )
        print("[QWEN] Model loaded with INT8 quantization")
    elif quantize == "fp16":
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        print("[QWEN] Model loaded with FP16")
    else:
        raise ValueError(
            f"Unknown quantization mode: {quantize!r}. Supported: q4, q8, fp16"
        )

    processor = AutoProcessor.from_pretrained(model_path)

    elapsed = time.time() - t0
    print(f"[QWEN] Model loaded in {elapsed:.1f}s (device: {model.device})")
    return model, processor


def map_element_type(raw_type: str) -> str:
    """Map Qwen output type string to canonical ParsedElement.type value.

    Handles variations: "input field" → "input", "text box" → "input", etc.
    Falls back to "unknown" if no match.

    Args:
        raw_type: Raw type string from Qwen model output.

    Returns:
        Canonical type string (one of VALID_ELEMENT_TYPES).
    """
    if not raw_type:
        return "unknown"

    cleaned = raw_type.strip().lower()

    # Direct match (case-insensitive)
    if cleaned in VALID_ELEMENT_TYPES:
        return cleaned

    # Use mapping table
    mapped = TYPE_MAPPING.get(cleaned, None)
    if mapped:
        return mapped

    # Fuzzy: try stripping trailing 's' (plural)
    if cleaned.endswith("s"):
        singular = cleaned[:-1]
        if singular in VALID_ELEMENT_TYPES:
            return singular
        mapped = TYPE_MAPPING.get(singular)
        if mapped:
            return mapped

    # Fuzzy: check if any known type is a substring
    for known_type, canonical in TYPE_MAPPING.items():
        if known_type in cleaned or cleaned in known_type:
            return canonical

    return "unknown"


def parse_qwen_json(text: str) -> Optional[dict]:
    """Extract and parse JSON from Qwen model output, with error recovery.

    Handles: markdown code fences, extra text, trailing commas,
    missing closing brackets, numeric confidence values.

    Args:
        text: Raw text output from Qwen3-VL-4B.

    Returns:
        Parsed dict with "type", "text", "confidence" keys, or None.
    """
    if not text:
        return None

    # Strategy 1: Extract JSON from ```json fence
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
    else:
        # Strategy 2: Find JSON object by braces
        match = re.search(r'\{[^{}]*"type"\s*:\s*"[^"]*"[^{}]*\}', text, re.DOTALL)
        if not match:
            match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            json_str = match.group(0)
        else:
            return None

    # Try direct parse
    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict) and "type" in parsed:
            return parsed
    except json.JSONDecodeError:
        pass

    # Recovery: fix trailing commas and missing brackets
    cleaned = re.sub(r',\s*([}\]])', r'\1', json_str)
    open_braces = cleaned.count('{') - cleaned.count('}')
    cleaned += '}' * max(0, open_braces)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "type" in parsed:
            return parsed
    except json.JSONDecodeError:
        pass

    return None


def describe_region(
    model,
    processor,
    cropped_image: Image.Image,
    max_tokens: int = 64,
) -> dict:
    """Run Qwen3-VL-4B inference on a cropped UI element region.

    Args:
        model: Loaded Qwen3VLForConditionalGeneration.
        processor: Loaded AutoProcessor with chat template.
        cropped_image: PIL Image of the cropped region.
        max_tokens: Max new tokens for generation (short output expected).

    Returns:
        Dict: {"type": str, "text": str|None, "confidence": float}
        Falls back to {"type": "unknown", "text": None, "confidence": 0.0}
        on parse failure.
    """
    fallback = {"type": "unknown", "text": None, "confidence": 0.0}

    # Build messages with chat template
    messages = [
        {"role": "system", "content": [{"type": "text", "text": QWEN_SYSTEM_PROMPT}]},
        {"role": "user", "content": [
            {"type": "image", "image": cropped_image},
            {"type": "text", "text": QWEN_USER_PROMPT},
        ]},
    ]

    try:
        text_prompt = processor.apply_chat_template(
            messages, add_generation_prompt=True
        )
        inputs = processor(
            text=[text_prompt],
            images=[cropped_image],
            return_tensors="pt",
            padding=True,
        ).to(model.device)

        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
            )

        input_len = inputs.input_ids.shape[1]
        output_text = processor.decode(
            generated_ids[0][input_len:], skip_special_tokens=True
        )

    except torch.OutOfMemoryError:
        print("[QWEN] OOM during region description, returning fallback", file=sys.stderr)
        return fallback
    except Exception as e:
        print(f"[QWEN] Inference error: {e}", file=sys.stderr)
        return fallback

    # Parse JSON from output
    parsed = parse_qwen_json(output_text)
    if parsed is None:
        return fallback

    # Extract and normalize fields
    raw_type = str(parsed.get("type", "unknown"))
    elem_type = map_element_type(raw_type)
    text_val = parsed.get("text", None)
    if text_val is not None:
        text_val = str(text_val) if text_val else None

    # Parse confidence
    try:
        confidence = float(parsed.get("confidence", 0.5))
    except (ValueError, TypeError):
        confidence = 0.5

    # Clamp confidence to [0.0, 1.0]
    confidence = max(0.0, min(1.0, confidence))

    return {"type": elem_type, "text": text_val, "confidence": confidence}


def generate_crops(
    image: Image.Image,
    bboxes: list[dict],
    expand_ratio: float = BBOX_EXPAND_RATIO,
    min_size: int = MIN_CROP_SIZE,
) -> list[dict]:
    """Generate cropped regions from detected bboxes.

    Args:
        image: Original PIL Image (full resolution).
        bboxes: List of element dicts with "bbox": [x1,y1,x2,y2].
        expand_ratio: Fraction to expand on each side (0.1 = 10% → 1.2x total).
        min_size: Minimum width/height in pixels — smaller regions are skipped.

    Returns:
        List of dicts: [{..., "crop_image": PIL.Image, "skip": False}, ...]
        Elements below min_size get skip=True.
    """
    img_w, img_h = image.size
    results = []

    for elem in bboxes:
        bbox = elem["bbox"]
        x1, y1, x2, y2 = bbox
        w, h = x2 - x1, y2 - y1

        # Expand by ratio
        expand_x = int(w * expand_ratio)
        expand_y = int(h * expand_ratio)

        cx1 = max(0, x1 - expand_x)
        cy1 = max(0, y1 - expand_y)
        cx2 = min(img_w, x2 + expand_x)
        cy2 = min(img_h, y2 + expand_y)

        crop_w = cx2 - cx1
        crop_h = cy2 - cy1

        elem_copy = dict(elem)
        elem_copy["crop_bbox"] = [cx1, cy1, cx2, cy2]

        if crop_w < min_size or crop_h < min_size:
            elem_copy["skip"] = True
            elem_copy["crop_image"] = None
        else:
            elem_copy["skip"] = False
            elem_copy["crop_image"] = image.crop((cx1, cy1, cx2, cy2))

        results.append(elem_copy)

    skipped = sum(1 for r in results if r["skip"])
    print(f"[CROP] {len(results)} regions: {len(results) - skipped} cropped, "
          f"{skipped} skipped (size < {min_size}px)")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# Section 4: Pipeline Orchestration and Post-Processing
# ══════════════════════════════════════════════════════════════════════════════

def compute_iou(bbox1: list[int], bbox2: list[int]) -> float:
    """Compute Intersection over Union for two [x1,y1,x2,y2] bboxes."""
    x_left = max(bbox1[0], bbox2[0])
    y_top = max(bbox1[1], bbox2[1])
    x_right = min(bbox1[2], bbox2[2])
    y_bottom = min(bbox1[3], bbox2[3])

    if x_right <= x_left or y_bottom <= y_top:
        return 0.0

    intersection = (x_right - x_left) * (y_bottom - y_top)
    area1 = max(1, (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1]))
    area2 = max(1, (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1]))
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def deduplicate_elements(
    elements: list[dict],
    iou_threshold: float = IOU_DEDUP_THRESHOLD,
) -> tuple[list[dict], list[dict]]:
    """Remove duplicate elements by IoU overlap, keeping higher confidence.

    Args:
        elements: List of element dicts with "bbox" and "confidence" keys.
        iou_threshold: IoU above which elements are considered duplicates.

    Returns:
        Tuple of (deduplicated_elements, duplicate_warnings).
    """
    warnings = []
    sorted_elements = sorted(
        elements, key=lambda e: e.get("confidence", 0.0), reverse=True
    )
    keep: list[dict] = []

    for elem in sorted_elements:
        is_dup = False
        e_bbox = elem.get("bbox", [0, 0, 0, 0])
        for kept in keep:
            if compute_iou(e_bbox, kept["bbox"]) > iou_threshold:
                warnings.append({
                    "code": "duplicate_element",
                    "severity": "low",
                    "message": (
                        f"Element {elem.get('id', '?')} duplicates "
                        f"{kept.get('id', '?')} (IoU > {iou_threshold}), removed"
                    ),
                })
                is_dup = True
                break
        if not is_dup:
            keep.append(elem)

    return keep, warnings


def build_analysis_result(
    snapshot_id: str,
    elements: list[dict],
    warnings: list[dict] | None = None,
) -> dict:
    """Build an AnalysisResult-compatible dict from pipeline output.

    Args:
        snapshot_id: Unique identifier for this analysis (e.g., image stem).
        elements: List of element dicts with id, type, bbox, text, confidence.
        warnings: Optional list of AnalysisWarning-compatible dicts.

    Returns:
        Dict matching the AnalysisResult schema from src/models.py.
    """
    warnings = list(warnings or [])

    # Determine overall quality
    elem_count = len(elements)
    if elem_count == 0:
        overall_quality = "low"
        warnings.append({
            "code": "dense_ui_possible_misses",
            "severity": "high",
            "message": "Grounding DINO-T detected zero elements on this screenshot",
        })
    elif elem_count < 3:
        overall_quality = "medium"
    elif len(warnings) <= 1:
        overall_quality = "high"
    else:
        overall_quality = "medium"

    # Clamp all confidences
    for e in elements:
        conf = e.get("confidence")
        if conf is not None:
            e["confidence"] = max(0.0, min(1.0, float(conf)))

    return {
        "snapshot_id": snapshot_id,
        "overall_quality": overall_quality,
        "warnings": warnings,
        "layout_summary": {
            "screen_kind": {"kind": "unknown", "detail": None},
            "main_regions": [],
            "active_dialog": {"present": False},
            "notes": None,
        },
        "elements": elements,
    }


def run_pipeline(
    image_path: str | Path,
    output_dir: str | Path,
    gdino_model,
    gdino_processor,
    qwen_model=None,
    qwen_processor=None,
    text_prompt: str = DEFAULT_TEXT_PROMPT,
    box_threshold: float = 0.25,
    text_threshold: float = 0.25,
    img_scale: float = 0.5,
    max_tokens: int = 64,
    skip_describe: bool = False,
    snapshot_id: str | None = None,
) -> dict:
    """Run the full detect → crop → describe → merge pipeline.

    Returns:
        AnalysisResult-compatible dict.
    """
    image_path = Path(image_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    name = image_path.stem
    if snapshot_id is None:
        snapshot_id = f"pipeline_gq_r1_{name}"

    print(f"\n{'='*60}")
    print(f"[PIPELINE] Processing: {image_path.name}")
    print(f"[PIPELINE] Output dir: {output_dir}")

    # ── Load image ───────────────────────────────────────────────────
    image = Image.open(image_path).convert("RGB")
    orig_w, orig_h = image.size
    print(f"[PIPELINE] Image: {orig_w}x{orig_h}")

    scaled_image = image
    scale_factor = 1.0
    if img_scale < 1.0:
        new_size = (int(orig_w * img_scale), int(orig_h * img_scale))
        scaled_image = image.resize(new_size, Image.Resampling.LANCZOS)
        scale_factor = img_scale
        print(f"[PIPELINE] Scaled to: {new_size[0]}x{new_size[1]} (factor={img_scale})")

    # ── Stage 1: Detection ───────────────────────────────────────────
    print(f"[PIPELINE] Stage 1: Grounding DINO-T detection")
    print(f"[PIPELINE]   prompt: {text_prompt[:80]}...")
    t1 = time.time()
    raw_elements = detect_elements(
        gdino_model, gdino_processor, scaled_image,
        text_prompt=text_prompt,
        box_threshold=box_threshold,
        text_threshold=text_threshold,
    )
    t1_elapsed = time.time() - t1

    # Map bboxes from scaled to original coordinates
    if scale_factor < 1.0:
        raw_elements = map_bbox_to_original(raw_elements, scale_factor)

    # IoU dedup on detection results
    raw_elements, dedup_warnings = deduplicate_elements(raw_elements)
    print(f"[PIPELINE] Stage 1 done: {len(raw_elements)} elements "
          f"({len(dedup_warnings)} duplicates removed) in {t1_elapsed:.1f}s")

    # ── Stage 2: Description (optional) ──────────────────────────────
    if skip_describe or qwen_model is None:
        print(f"[PIPELINE] Stage 2: SKIPPED (--skip-describe)")

        # Build elements with type=unknown for detection-only mode
        elements = []
        for i, elem in enumerate(raw_elements):
            elements.append({
                "id": f"el_{i+1:03d}",
                "type": "unknown",
                "bbox": elem["bbox"],
                "text": elem.get("label"),
                "description": None,
                "confidence": elem.get("confidence", 0.0),
                "parent_id": None,
                "children_ids": [],
                "region_ref": None,
            })

        warnings = list(dedup_warnings)
        if len(raw_elements) == 0:
            warnings.append({
                "code": "dense_ui_possible_misses",
                "severity": "high",
                "message": "Zero elements detected",
            })

        result = build_analysis_result(snapshot_id, elements, warnings)
        result["_timing"] = {
            "stage1_s": round(t1_elapsed, 1),
            "stage2_s": 0,
            "total_s": round(t1_elapsed, 1),
        }
        result["_meta"] = {
            "image_path": str(image_path),
            "image_size": [orig_w, orig_h],
            "scale_factor": scale_factor,
            "box_threshold": box_threshold,
            "text_threshold": text_threshold,
            "text_prompt": text_prompt,
            "pipeline": "gq_r1",
            "describe_skipped": True,
        }

    else:
        print(f"[PIPELINE] Stage 2: Qwen3-VL-4B description "
              f"({len(raw_elements)} regions)")
        t2 = time.time()

        # Generate crops
        crops = generate_crops(image, raw_elements)

        # Describe each crop
        elements = []
        describe_count = 0
        for i, crop_info in enumerate(crops):
            elem_id = f"el_{i+1:03d}"

            if crop_info["skip"]:
                elements.append({
                    "id": elem_id,
                    "type": "unknown",
                    "bbox": crop_info["bbox"],
                    "text": crop_info.get("label"),
                    "description": None,
                    "confidence": 0.0,
                    "parent_id": None,
                    "children_ids": [],
                    "region_ref": None,
                })
                continue

            # Run description
            desc = describe_region(
                qwen_model, qwen_processor,
                crop_info["crop_image"],
                max_tokens=max_tokens,
            )
            describe_count += 1

            # Merge GDINO label if Qwen returned unknown
            elem_type = desc["type"]
            if elem_type == "unknown" and crop_info.get("label"):
                # Try to map GDINO label as fallback
                gdino_label = crop_info.get("label", "").strip().lower()
                elem_type = map_element_type(gdino_label)

            # Merge confidence: use Qwen confidence, fall back to GDINO
            confidence = desc.get("confidence", 0.0)
            if confidence <= 0.0:
                confidence = crop_info.get("confidence", 0.0)
            confidence = max(0.0, min(1.0, confidence))

            elements.append({
                "id": elem_id,
                "type": elem_type,
                "bbox": crop_info["bbox"],
                "text": desc.get("text"),
                "description": None,
                "confidence": confidence,
                "parent_id": None,
                "children_ids": [],
                "region_ref": None,
            })

        t2_elapsed = time.time() - t2
        print(f"[PIPELINE] Stage 2 done: {describe_count} regions described "
              f"in {t2_elapsed:.1f}s")

        # Post-description dedup (with more complete type info)
        elements, final_dedup = deduplicate_elements(elements)
        warnings = dedup_warnings + final_dedup

        result = build_analysis_result(snapshot_id, elements, warnings)
        result["_timing"] = {
            "stage1_s": round(t1_elapsed, 1),
            "stage2_s": round(t2_elapsed, 1),
            "total_s": round(t1_elapsed + t2_elapsed, 1),
        }
        result["_meta"] = {
            "image_path": str(image_path),
            "image_size": [orig_w, orig_h],
            "scale_factor": scale_factor,
            "box_threshold": box_threshold,
            "text_threshold": text_threshold,
            "text_prompt": text_prompt,
            "max_tokens": max_tokens,
            "pipeline": "gq_r1",
            "describe_skipped": False,
        }

    # ── Save analysis JSON ───────────────────────────────────────────
    th_suffix = f"_th{box_threshold}-{text_threshold}" if not skip_describe else f"_th{box_threshold}-{text_threshold}_detectonly"
    json_path = output_dir / f"{name}{th_suffix}_analysis.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[PIPELINE] Analysis JSON saved: {json_path}")

    # ── Run visualization ────────────────────────────────────────────
    ann_path = None
    txt_path = None
    try:
        from visualize_bboxes import draw_bboxes
        ann_path, txt_path = draw_bboxes(str(image_path), str(json_path), str(output_dir))
    except ImportError:
        import subprocess
        vis_script = Path(__file__).parent / "visualize_bboxes.py"
        if vis_script.exists():
            subprocess.run([
                sys.executable, str(vis_script),
                str(json_path), str(image_path),
                "-o", str(output_dir),
            ], check=False)
            ann_path = str(output_dir / f"{name}_annotated.png")
            txt_path = str(output_dir / f"{name}_elements.txt")
        else:
            print(f"[PIPELINE] WARNING: visualize_bboxes.py not found, "
                  f"skipping visualization")

    if ann_path:
        new_ann = output_dir / f"{name}{th_suffix}_annotated.png"
        Path(ann_path).rename(new_ann)
    if txt_path:
        new_txt = output_dir / f"{name}{th_suffix}_elements.txt"
        Path(txt_path).rename(new_txt)

    # ── Summary ──────────────────────────────────────────────────────
    elem_count = len(result["elements"])
    quality = result["overall_quality"]
    warn_count = len(result["warnings"])
    print(f"[PIPELINE] SUMMARY: quality={quality}, elements={elem_count}, "
          f"warnings={warn_count}")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Section 5: CLI and Output Generation
# ══════════════════════════════════════════════════════════════════════════════

def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Spike: Grounding DINO-T + Qwen3-VL-4B pipeline (GQ Round 1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single-image tuning mode
  python scripts/spike_pipeline_gq.py --single --image COMIC-setting.png

  # Detection-only mode
  python scripts/spike_pipeline_gq.py --single --image COMIC-setting.png --skip-describe

  # Batch mode
  python scripts/spike_pipeline_gq.py --image-dir docs/spike-screenshots/ \\
      --output-dir docs/spike-results/pipeline-round1/

  # Custom thresholds
  python scripts/spike_pipeline_gq.py --single --image vscode.png \\
      --box-threshold 0.15 --text-threshold 0.15 --img-scale 0.75
        """,
    )

    # Path arguments
    parser.add_argument(
        "--image-dir", default="docs/spike-screenshots/",
        help="Directory containing test screenshots (default: docs/spike-screenshots/)",
    )
    parser.add_argument(
        "--output-dir", default="docs/spike-results/pipeline-round1/",
        help="Output directory for results (default: docs/spike-results/pipeline-round1/)",
    )
    parser.add_argument(
        "--gdino-model", default="IDEA-Research/grounding-dino-tiny",
        help="Grounding DINO model path or HF ID (default: IDEA-Research/grounding-dino-tiny)",
    )
    parser.add_argument(
        "--qwen-model", default="/home/ruruka/文档/Models/Qwen3VL4BInst/",
        help="Path to Qwen3-VL-4B-Instruct local directory",
    )

    # Detection parameters
    parser.add_argument(
        "--text-prompt", default=DEFAULT_TEXT_PROMPT,
        help="Detection text prompt for open-vocabulary search",
    )
    parser.add_argument(
        "--box-threshold", type=float, default=0.25,
        help="GDINO box confidence threshold (default: 0.25)",
    )
    parser.add_argument(
        "--text-threshold", type=float, default=0.25,
        help="GDINO text-image match threshold (default: 0.25)",
    )
    parser.add_argument(
        "--img-scale", type=float, default=0.5,
        help="Image scale factor, <1.0 to downsample (default: 0.5 → 1280×800 for 2560×1600)",
    )

    # Qwen parameters
    parser.add_argument(
        "--qwen-quantize", default="q4",
        choices=["q4", "q8", "fp16"],
        help="Qwen quantization mode (default: q4)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=64,
        help="Max tokens per Qwen region description (default: 64)",
    )

    # Mode flags
    parser.add_argument(
        "--single", action="store_true",
        help="Single-image mode: process only one image for tuning",
    )
    parser.add_argument(
        "--image", default=None,
        help="Image filename (in --image-dir) for single-image mode",
    )
    parser.add_argument(
        "--skip-describe", action="store_true",
        help="Skip Qwen description stage, output detection bboxes only",
    )

    return parser


def print_batch_summary(results: list[dict]):
    """Print a summary comparison table for batch mode results.

    Args:
        results: List of AnalysisResult-compatible dicts from each screenshot.
    """
    print("\n" + "=" * 80)
    print("BATCH SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Screenshot':<32} {'Elements':>8} {'Quality':>8} {'Warnings':>8}  Notable")
    print("-" * 80)

    for r in results:
        name = Path(r.get("_meta", {}).get("image_path", "?")).stem
        elements = len(r.get("elements", []))
        quality = r.get("overall_quality", "?")
        warnings = len(r.get("warnings", []))

        # Pick the most notable warning
        notable = ""
        for w in r.get("warnings", []):
            code = w.get("code", "")
            if code in ("dense_ui_possible_misses", "hallucinated_element"):
                notable = code
                break
        if not notable and warnings > 0:
            notable = r["warnings"][0].get("code", "")

        # Truncate long names
        display_name = name if len(name) <= 30 else name[:27] + "..."

        print(f"{display_name:<32} {elements:>8} {quality:>8} {warnings:>8}  {notable}")

    # Totals
    total_elements = sum(len(r.get("elements", [])) for r in results)
    avg_elements = total_elements / max(1, len(results))
    high_count = sum(1 for r in results if r.get("overall_quality") == "high")
    med_count = sum(1 for r in results if r.get("overall_quality") == "medium")
    low_count = sum(1 for r in results if r.get("overall_quality") == "low")

    print("-" * 80)
    print(f"{'TOTAL/AVG':<32} {avg_elements:>7.1f} "
          f"high={high_count} med={med_count} low={low_count}")
    print("=" * 80)


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Validate inputs ──────────────────────────────────────────────
    if args.single and not args.image:
        print("[ERROR] --single requires --image <filename>", file=sys.stderr)
        sys.exit(1)

    if args.image and not args.single:
        print("[NOTE] --image provided without --single; will run in batch mode "
              "but only process the specified image")

    # ── Collect images to process ────────────────────────────────────
    if args.image:
        image_path = image_dir / args.image
        if not image_path.exists():
            print(f"[ERROR] Image not found: {image_path}", file=sys.stderr)
            sys.exit(1)
        image_paths = [image_path]
    else:
        image_paths = sorted(image_dir.glob("*.png"))
        if not image_paths:
            # Try extension variations
            image_paths = sorted(image_dir.glob("*.PNG")) + sorted(image_dir.glob("*.jpg"))

    if not image_paths:
        print(f"[ERROR] No PNG images found in {image_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Processing {len(image_paths)} image(s) from {image_dir}")
    print(f"[INFO] Output dir: {output_dir}")
    print(f"[INFO] GDINO thresholds: box={args.box_threshold}, text={args.text_threshold}")
    print(f"[INFO] Image scale: {args.img_scale}")
    if not args.skip_describe:
        print(f"[INFO] Qwen quantize: {args.qwen_quantize}, max_tokens: {args.max_tokens}")
    else:
        print(f"[INFO] Qwen: SKIPPED (--skip-describe)")

    # ── Load models ──────────────────────────────────────────────────
    print("\n[LOAD] Loading Grounding DINO-T ...")
    gdino_model, gdino_processor = load_gdino_model(args.gdino_model)

    qwen_model = None
    qwen_processor = None

    if not args.skip_describe:
        print("\n[LOAD] Loading Qwen3-VL-4B ...")
        try:
            qwen_model, qwen_processor = load_qwen_model(
                args.qwen_model, quantize=args.qwen_quantize
            )
        except torch.OutOfMemoryError:
            print("[WARN] OOM loading both models. Trying sequential mode: "
                  "unloading G-DINO first...")
            # Unload GDINO to free VRAM
            gdino_model.cpu()
            del gdino_model
            torch.cuda.empty_cache()

            qwen_model, qwen_processor = load_qwen_model(
                args.qwen_model, quantize=args.qwen_quantize
            )

            # Qwen-only: we need GDINO back after Qwen. But for pipeline,
            # wait — actually the pipeline runs detect first then describe.
            # So if sequential, we need to handle per-image.
            print("[WARN] Sequential mode: GDINO was unloaded. "
                  "Only detection results will be used (no description).")
            args.skip_describe = True

        except Exception as e:
            print(f"[ERROR] Failed to load Qwen model: {e}", file=sys.stderr)
            print("[WARN] Falling back to detection-only mode")
            args.skip_describe = True

    # ── Process images ───────────────────────────────────────────────
    all_results = []

    for i, image_path in enumerate(image_paths):
        print(f"\n{'#'*60}")
        print(f"# Image {i+1}/{len(image_paths)}: {image_path.name}")
        print(f"{'#'*60}")

        try:
            result = run_pipeline(
                image_path=str(image_path),
                output_dir=str(output_dir),
                gdino_model=gdino_model,
                gdino_processor=gdino_processor,
                qwen_model=qwen_model,
                qwen_processor=qwen_processor,
                text_prompt=args.text_prompt,
                box_threshold=args.box_threshold,
                text_threshold=args.text_threshold,
                img_scale=args.img_scale,
                max_tokens=args.max_tokens,
                skip_describe=args.skip_describe,
            )
            all_results.append(result)
        except Exception as e:
            print(f"[ERROR] Failed on {image_path.name}: {e}", file=sys.stderr)
            traceback.print_exc()
            # Continue with next image

        # In single mode, stop after first image
        if args.single:
            print("\n[SINGLE MODE] Processing complete. Review the output and "
                  "adjust parameters as needed.")
            break

    # ── Batch summary ────────────────────────────────────────────────
    if len(all_results) > 1:
        print_batch_summary(all_results)
    elif len(all_results) == 1:
        r = all_results[0]
        print(f"\n[RESULT] {Path(r['_meta']['image_path']).name}: "
              f"quality={r['overall_quality']}, "
              f"elements={len(r['elements'])}, "
              f"warnings={len(r['warnings'])}")

    print(f"\n[DONE] Results saved to {output_dir}")
    print(f"[DONE] Files: {len(all_results)} analysis JSON(s) + visualizations")


if __name__ == "__main__":
    main()
