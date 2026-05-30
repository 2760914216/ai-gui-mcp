#!/usr/bin/env python3
"""Spike validation script for Architecture C: Qwen3-VL-8B + prompt engineering.

Loads a local Qwen3-VL-8B-Instruct model, runs two-stage structured GUI parsing
on a screenshot, and outputs an AnalysisResult-compatible JSON.

Usage:
    python scripts/spike_arch_c.py \
        --model-path /path/to/Qwen3-VL-8B-Instruct \
        --image docs/spike-screenshots/vscode.png \
        --quantize int8 \
        --max-tokens 2048 \
        --output docs/spike-results/round-1/vscode_analysis.json
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import torch
from PIL import Image
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor, BitsAndBytesConfig


# ──────────────────────────────────────────────────────────────────────────────
# Model loading
# ──────────────────────────────────────────────────────────────────────────────

def load_model(model_path: str, quantize: str = "int8"):
    """Load Qwen3-VL-8B with configurable quantization.

    quantize: "int8" (bitsandbytes), "fp16", "int4" (bitsandbytes 4bit)
    Returns (model, processor).
    """
    quantize = quantize.lower()

    if quantize == "int8":
        try:
            bnb_config = BitsAndBytesConfig(
                load_in_8bit=True,
            )
            model = Qwen3VLForConditionalGeneration.from_pretrained(
                model_path,
                quantization_config=bnb_config,
                device_map="auto",
            )
            print("✓ Model loaded with INT8 quantization")
        except Exception as e:
            print(f"[WARN] INT8 failed ({e}), falling back to FP16 + auto device map")
            model = Qwen3VLForConditionalGeneration.from_pretrained(
                model_path,
                torch_dtype=torch.float16,
                device_map="auto",
            )
            print("✓ Model loaded with FP16 (auto device map, may use CPU offload)")
    elif quantize == "int4":
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            quantization_config=bnb_config,
            device_map="auto",
        )
        print("✓ Model loaded with INT4 quantization")
    elif quantize == "fp16":
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        print("✓ Model loaded with FP16 (auto device map)")
    else:
        raise ValueError(
            f"Unknown quantization mode: {quantize!r}. "
            f"Supported: int8, fp16, int4"
        )

    processor = AutoProcessor.from_pretrained(model_path)
    return model, processor


# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────

COARSE_SYSTEM = """You are a GUI screen analyzer. Your task is to classify the screen type and identify the main layout regions.

Output EXACTLY a JSON object with this structure:
{
  "screen_kind": "<ide|browser|settings|dialog|file_manager|terminal|unknown>",
  "layout_regions": [
    {
      "id": "region-1",
      "type": "<sidebar|toolbar|editor|content|dialog|panel|list|table|form|unknown>",
      "bbox": [x1, y1, x2, y2]
    }
  ]
}

RULES:
- bbox uses pixel coordinates [x1, y1, x2, y2] where (x1,y1) is top-left corner, (x2,y2) is bottom-right corner
- Coordinate origin is the image top-left corner (0, 0)
- Use integer coordinates only
- A region's bbox MUST be fully within the image boundaries
- regions MUST NOT overlap — each pixel belongs to at most one region
- Wrap your JSON in ```json ... ``` code fence
- Do NOT include anything outside the code fence"""

COARSE_USER = "Analyze this screenshot. Identify the screen kind (ide/browser/settings/dialog/file_manager/terminal/unknown) and list all major layout regions with their bounding boxes in pixel coordinates [x1, y1, x2, y2]."

FINE_SYSTEM = """You are a GUI element detector. Given a screenshot, identify ALL visible UI elements.

Output EXACTLY a JSON object:
{
  "elements": [
    {
      "id": "element-1",
      "type": "<button|input|checkbox|radio|tab|menuitem|link|window|dialog|sidebar|toolbar|panel|list|table|form|text|unknown>",
      "bbox": [x1, y1, x2, y2],
      "text": "<visible label text, or null>",
      "confidence": 0.95
    }
  ]
}

CRITICAL RULES:
- List each element only ONCE. After the last element, close with ]} and STOP.
- Do NOT continue generating after the closing ]}.
- bbox uses pixel coordinates [x1, y1, x2, y2] relative to the full screenshot
- Include ALL visible elements: buttons, inputs, checkboxes, tabs, menu items, links, text labels, icons, scrollbars, status bar items
- confidence must be a number between 0.0 and 1.0
- Wrap your JSON in ```json ... ``` code fence"""

FINE_USER = "List ALL visible UI elements in this screenshot. Include buttons, inputs, text labels, icons, tabs, menu items, links, and any other interactive or informational elements. Output their bounding boxes in pixel coordinates [x1, y1, x2, y2] with confidence scores."


# ──────────────────────────────────────────────────────────────────────────────
# JSON parsing
# ──────────────────────────────────────────────────────────────────────────────

def robust_json_parse(text: str) -> Optional[dict]:
    """Extract and parse JSON from model output, with error recovery.

    Handles: markdown code fences, trailing commas, missing closing brackets,
    JSON arrays (wraps in {"elements": [...]}), truncated output.
    Returns None on unrecoverable parse errors.
    """
    if text is None:
        return None

    # Strategy 1: Extract JSON from ```json fence
    match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
    else:
        # Strategy 2: Find JSON object or array by braces/brackets
        # Try object first (preferred format)
        match = re.search(r'\{[^{}]*\{.*?\}[^{}]*\}', text, re.DOTALL)
        if not match:
            match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            json_str = match.group(0)
        else:
            # Try array
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                return None

    # Parse with recovery
    parsed = _try_parse_json(json_str)
    if parsed is not None:
        return parsed

    # If parsing failed, try recovery fixes
    cleaned = re.sub(r',\s*([}\]])', r'\1', json_str)

    open_braces = cleaned.count('{') - cleaned.count('}')
    open_brackets = cleaned.count('[') - cleaned.count(']')
    cleaned += '}' * max(0, open_braces)
    cleaned += ']' * max(0, open_brackets)

    parsed = _try_parse_json(cleaned)
    if parsed is not None:
        return parsed

    # Last resort: try to extract just the first few complete elements
    # from a truncated array
    match = re.search(r'\[(.*?)(?:,\s*\{[^}]*\}){0,3}\]', json_str, re.DOTALL)
    if match:
        return _try_parse_json(match.group(0))

    return None


def _try_parse_json(json_str: str) -> Optional[dict]:
    """Try to parse JSON, auto-wrapping arrays into {"elements": [...]}."""
    if not json_str or not json_str.strip():
        return None
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return None
    # If model output a raw array, wrap it
    if isinstance(parsed, list):
        return {"elements": parsed}
    if isinstance(parsed, dict):
        return parsed
    return None


# ──────────────────────────────────────────────────────────────────────────────
# IoU deduplication
# ──────────────────────────────────────────────────────────────────────────────

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
    elements: list[dict], iou_threshold: float = 0.5
) -> tuple[list[dict], list[dict]]:
    """Remove duplicate elements by IoU + text similarity, keeping higher confidence.

    Returns (deduplicated_elements, duplicate_warnings).
    """
    warnings = []
    # Sort by confidence descending so higher confidence wins
    sorted_elements = sorted(
        elements, key=lambda e: e.get("confidence", 0.0), reverse=True
    )
    keep: list[dict] = []

    for elem in sorted_elements:
        is_dup = False
        e_bbox = elem.get("bbox", [0, 0, 0, 0])
        e_text = elem.get("text", "")
        e_type = elem.get("type", "")
        # Build a semantic key: type + text (if text present)
        e_key = (e_type, e_text) if e_text else None

        for kept in keep:
            # IoU-based dedup
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

            # Text-based dedup: same type+non-empty-text at similar x position
            if (e_key and e_text  # only dedup by text if text is non-empty
                    and e_key == (kept.get("type"), kept.get("text"))):
                k_bbox = kept.get("bbox", [0, 0, 0, 0])
                if (abs(e_bbox[0] - k_bbox[0]) < 10
                        and abs(e_bbox[2] - k_bbox[2]) < 10
                        and e_bbox[1] != k_bbox[1]):
                    warnings.append({
                        "code": "duplicate_element",
                        "severity": "low",
                        "message": (
                            f"Element {elem.get('id', '?')} ({e_type}/{e_text}) "
                            f"is a text duplicate of {kept.get('id', '?')}, removed"
                        ),
                    })
                    is_dup = True
                    break

        if not is_dup:
            keep.append(elem)

    return keep, warnings


# ──────────────────────────────────────────────────────────────────────────────
# Two-stage inference
# ──────────────────────────────────────────────────────────────────────────────

def run_inference(model, processor, image: Image.Image,
                  system_prompt: str, user_text: str,
                  max_tokens: int) -> str:
    """Run a single inference pass, return decoded text output."""
    messages = [
        {
            "role": "system",
            "content": [{"type": "text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": user_text},
            ],
        },
    ]

    text = processor.apply_chat_template(messages, add_generation_prompt=True)
    # processor.apply_chat_template returns str; wrap in list for __call__
    inputs = processor(
        text=[text], images=[image],
        return_tensors="pt", padding=True,
    ).to(model.device)

    with torch.no_grad():
        try:
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
                repetition_penalty=1.1,
            )
        except torch.OutOfMemoryError:
            print("[ERROR] CUDA OOM during inference. Try: --scale 0.5 or --quantize int4",
                  file=sys.stderr)
            raise

    input_len = inputs.input_ids.shape[1]
    output = processor.decode(
        generated_ids[0][input_len:], skip_special_tokens=True
    )
    return output


def coarse_parse(model, processor, image: Image.Image,
                 max_tokens: int = 1024) -> dict:
    """Stage 1: classify screen kind and identify layout regions."""
    output = run_inference(model, processor, image,
                           COARSE_SYSTEM, COARSE_USER, max_tokens)
    result = {"screen_kind": "unknown", "layout_regions": [], "_raw_output": None}
    parsed = robust_json_parse(output)
    if parsed:
        result["screen_kind"] = parsed.get("screen_kind", "unknown")
        result["layout_regions"] = parsed.get("layout_regions", [])
    else:
        result["_raw_output"] = output
    return result


def fine_parse(model, processor, image: Image.Image,
               max_tokens: int = 2048) -> dict:
    """Stage 2: detect detailed UI elements."""
    output = run_inference(model, processor, image,
                           FINE_SYSTEM, FINE_USER, max_tokens)
    result = {"elements": [], "_raw_output": output}
    parsed = robust_json_parse(output)
    if parsed:
        result["elements"] = parsed.get("elements", [])
    # If robust parse failed, try extracting individual elements
    if not result["elements"] and output:
        result["elements"] = _extract_individual_elements(output)
    return result


def _extract_individual_elements(text: str) -> list[dict]:
    """Extract individual JSON element objects from a partial/corrupted output.

    Handles cases where the outer wrapper is missing or malformed but
    individual {type, bbox, text, confidence} objects are present.
    """
    elements = []
    # Find all complete {...} objects within the text
    # Strategy: find each { that looks like an element object
    pattern = re.compile(
        r'\{(?:[^{}]|\{[^{}]*\})*?"type"\s*:\s*"(\w+)"(?:[^{}]|\{[^{}]*\})*?'
        r'"bbox"\s*:\s*\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]'
        r'(?:[^{}]*"text"\s*:\s*"([^"]*)")?'
        r'(?:[^{}]*"confidence"\s*:\s*([\d.]+))?'
        r'[^{}]*\}',
        re.DOTALL,
    )
    for match in pattern.finditer(text):
        elem_type = match.group(1)
        bbox = [int(match.group(2)), int(match.group(3)),
                int(match.group(4)), int(match.group(5))]
        text_val = match.group(6) if match.group(6) else None
        conf = float(match.group(7)) if match.group(7) else 0.9
        elements.append({
            "id": f"element-{len(elements)+1}",
            "type": elem_type,
            "bbox": bbox,
            "text": text_val,
            "confidence": conf,
        })
    return elements


# ──────────────────────────────────────────────────────────────────────────────
# Output mapping
# ──────────────────────────────────────────────────────────────────────────────

def map_to_analysis_result(
    snapshot_id: str,
    coarse: dict,
    fine_elements: list[dict],
    fine_raw: str | None = None,
) -> dict:
    """Map VLM output to an AnalysisResult-compatible dict."""
    # Layout regions
    layout_regions = []
    for region in coarse.get("layout_regions", []):
        bbox = region.get("bbox", [0, 0, 0, 0])
        if len(bbox) != 4:
            bbox = [0, 0, 0, 0]
        layout_regions.append({
            "id": region.get("id", "region-?"),
            "type": region.get("type", "unknown"),
            "bbox": [int(v) for v in bbox],
            "detail": None,
        })

    # Elements
    elements = []
    for i, elem in enumerate(fine_elements):
        if not isinstance(elem, dict):
            continue
        bbox = elem.get("bbox", [0, 0, 0, 0])
        if len(bbox) != 4:
            bbox = [0, 0, 0, 0]
        elements.append({
            "id": elem.get("id", f"element-{i+1}"),
            "type": elem.get("type", "unknown"),
            "bbox": [int(v) for v in bbox],
            "text": elem.get("text"),
            "description": None,
            "confidence": elem.get("confidence"),
            "parent_id": None,
            "children_ids": [],
            "region_ref": None,
        })

    # Deduplication
    elements, dedup_warnings = deduplicate_elements(elements)

    # Heuristic: detect button spam (model repetition artifact)
    button_no_text = sum(
        1 for e in elements
        if e["type"] in ("button",)
        and not e.get("text")
    )
    if button_no_text > 5 and button_no_text > len(elements) * 0.5:
        dedup_warnings.append({
            "code": "hallucinated_element",
            "severity": "medium",
            "message": (
                f"Detected {button_no_text}/{len(elements)} button elements "
                f"with no text — likely model repetition artifact; "
                f"only the first 5 button elements are preserved"
            ),
        })
        # Keep only first 5 button elements with no text
        kept_buttons = 0
        filtered = []
        for e in elements:
            if e["type"] in ("button",) and not e.get("text"):
                if kept_buttons < 5:
                    filtered.append(e)
                    kept_buttons += 1
                continue
            filtered.append(e)
        elements = filtered

    # Warnings
    warnings = list(dedup_warnings)

    if coarse.get("_raw_output"):
        warnings.append({
            "code": "model_parse_error",
            "severity": "high",
            "message": "Failed to parse coarse parsing output as JSON; raw output preserved",
        })

    if not fine_elements and not coarse.get("layout_regions"):
        overall_quality = "low"
    elif len(warnings) > 1:
        overall_quality = "low"
    elif len(warnings) == 1:
        overall_quality = "medium"
    elif len(elements) < 3:
        overall_quality = "medium"
    else:
        overall_quality = "high"

    raw_outputs = {}
    if coarse.get("_raw_output"):
        raw_outputs["coarse_raw"] = str(coarse["_raw_output"])[:2000]
    if fine_raw:
        raw_outputs["fine_raw_first"] = str(fine_raw)[:2000]
        raw_outputs["fine_raw_last"] = str(fine_raw)[-2000:]

    return {
        "snapshot_id": snapshot_id,
        "overall_quality": overall_quality,
        "warnings": warnings,
        "layout_summary": {
            "screen_kind": {
                "kind": coarse.get("screen_kind", "unknown"),
                "detail": None,
            },
            "main_regions": layout_regions,
            "active_dialog": {
                "present": False,
                "region_ref": None,
                "element_ref": None,
            },
            "notes": None,
        },
        "elements": elements,
        "_raw_outputs": raw_outputs,
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Spike: Qwen3-VL-8B GUI grounding validation (Architecture C)"
    )
    parser.add_argument(
        "--model-path", required=True,
        help="Path to Qwen3-VL-8B-Instruct directory"
    )
    parser.add_argument(
        "--image", required=True,
        help="Path to screenshot image (PNG/JPEG)"
    )
    parser.add_argument(
        "--quantize", default="int8", choices=["int8", "fp16", "int4"],
        help="Quantization mode (default: int8)"
    )
    parser.add_argument(
        "--max-tokens", type=int, default=2048,
        help="Max new tokens per generation (default: 2048)"
    )
    parser.add_argument(
        "--scale", type=float, default=1.0,
        help="Image scale factor, <1.0 to downsample (default: 1.0)"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output JSON path (default: <image_stem>_analysis.json)"
    )
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"[ERROR] Image not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    # ── Load model ─────────────────────────────────────────────────────
    print(f"[INFO] Loading model from {args.model_path} (quantize={args.quantize})...")
    t0 = time.time()
    try:
        model, processor = load_model(args.model_path, args.quantize)
    except Exception as e:
        print(f"[FATAL] Failed to load model: {e}", file=sys.stderr)
        sys.exit(1)
    load_time = time.time() - t0
    print(f"[INFO] Model loaded in {load_time:.1f}s")

    # ── Load image ─────────────────────────────────────────────────────
    image = Image.open(image_path).convert("RGB")
    orig_w, orig_h = image.size
    print(f"[INFO] Image: {orig_w}x{orig_h} ({image_path.name})")

    scale_factor = args.scale
    if args.scale < 1.0:
        new_size = (int(orig_w * args.scale), int(orig_h * args.scale))
        image = image.resize(new_size, Image.LANCZOS)
        print(f"[INFO] Scaled to: {new_size[0]}x{new_size[1]}")

    # ── Stage 1: Coarse parsing ────────────────────────────────────────
    print("[INFO] Stage 1: Coarse parsing (screen classification + layout regions)...")
    t1 = time.time()
    coarse = coarse_parse(model, processor, image,
                          max_tokens=min(args.max_tokens, 1024))
    t1_elapsed = time.time() - t1
    screen_kind = coarse.get("screen_kind", "unknown")
    region_count = len(coarse.get("layout_regions", []))
    print(f"[INFO] Stage 1 done in {t1_elapsed:.1f}s — "
          f"screen_kind={screen_kind}, regions={region_count}")

    # ── Stage 2: Fine parsing ─────────────────────────────────────────
    print("[INFO] Stage 2: Fine parsing (element detection)...")
    t2 = time.time()
    fine = fine_parse(model, processor, image, max_tokens=args.max_tokens)
    t2_elapsed = time.time() - t2
    element_count = len(fine.get("elements", []))
    print(f"[INFO] Stage 2 done in {t2_elapsed:.1f}s — "
          f"elements={element_count}")

    # ── Map to AnalysisResult ─────────────────────────────────────────
    snapshot_id = image_path.stem
    try:
        result = map_to_analysis_result(snapshot_id, coarse,
                                        fine.get("elements", []),
                                        fine.get("_raw_output"))
    except Exception as e:
        print(f"[ERROR] Failed to map results: {e}", file=sys.stderr)
        result = {
            "snapshot_id": snapshot_id,
            "overall_quality": "low",
            "warnings": [{"code": "model_parse_error", "severity": "high",
                          "message": f"Post-processing failed: {e}"}],
            "layout_summary": {
                "screen_kind": {"kind": coarse.get("screen_kind", "unknown"), "detail": None},
                "main_regions": [],
                "active_dialog": {"present": False, "region_ref": None, "element_ref": None},
                "notes": None,
            },
            "elements": [],
        }

    total_time = time.time() - t0
    result["_timing"] = {
        "load_s": round(load_time, 1),
        "stage1_s": round(t1_elapsed, 1),
        "stage2_s": round(t2_elapsed, 1),
        "total_s": round(total_time, 1),
    }
    result["_meta"] = {
        "model_path": args.model_path,
        "quantize": args.quantize,
        "image_path": str(image_path),
        "image_size": [orig_w, orig_h],
        "scale_factor": scale_factor,
        "max_tokens": args.max_tokens,
    }

    # ── Save output ───────────────────────────────────────────────────
    output_path = Path(args.output) if args.output else image_path.with_suffix("").with_name(image_path.stem + "_analysis.json")
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[DONE] Results saved to {output_path}")
    print(f"[TIME] Load: {load_time:.1f}s | "
          f"Stage1: {t1_elapsed:.1f}s | Stage2: {t2_elapsed:.1f}s | "
          f"Total: {total_time:.1f}s")

    # Print summary
    warnings_count = len(result.get("warnings", []))
    elements_count = len(result.get("elements", []))
    print(f"[SUMMARY] quality={result['overall_quality']}, "
          f"elements={elements_count}, "
          f"regions={region_count}, "
          f"warnings={warnings_count}")


if __name__ == "__main__":
    main()
