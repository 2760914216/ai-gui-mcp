from dataclasses import dataclass
from typing import Protocol, TypeVar


@dataclass
class ProcessedDetection:
    bbox: list[int]
    label: str
    confidence: float


class _HasBBox(Protocol):
    bbox: list[int]


class _HasBBoxAndConfidence(Protocol):
    bbox: list[int]
    confidence: float


T = TypeVar("T", bound=_HasBBox)
U = TypeVar("U", bound=_HasBBoxAndConfidence)


def _bbox_area(bbox: list[int]) -> int:
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    if w <= 0 or h <= 0:
        return 0
    return w * h


def _iou(a: list[int], b: list[int]) -> float:
    area_a = _bbox_area(a)
    area_b = _bbox_area(b)
    if area_a <= 0 or area_b <= 0:
        return 0.0

    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    intersection_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    intersection_h = max(0, min(ay2, by2) - max(ay1, by1))
    intersection_area = intersection_w * intersection_h
    union_area = area_a + area_b - intersection_area
    if union_area <= 0:
        return 0.0
    return intersection_area / union_area


def filter_by_area(
    elements: list[T],
    screen_width: int,
    screen_height: int,
    ratio: float = 0.5,
) -> tuple[list[T], int]:
    screen_area = screen_width * screen_height
    if screen_area <= 0:
        return [], len(elements)

    filtered: list[T] = []
    dropped = 0
    for element in elements:
        area = _bbox_area(element.bbox)
        if area <= 0:
            dropped += 1
            continue
        if (area / screen_area) > ratio:
            dropped += 1
            continue
        filtered.append(element)
    return filtered, dropped


def deduplicate_by_iou(elements: list[U], threshold: float = 0.5) -> tuple[list[U], int]:
    if len(elements) <= 1:
        return list(elements), 0

    removed: set[int] = set()
    for i, left in enumerate(elements):
        if i in removed:
            continue
        for j in range(i + 1, len(elements)):
            if j in removed:
                continue
            right = elements[j]
            if _iou(left.bbox, right.bbox) <= threshold:
                continue

            if left.confidence >= right.confidence:
                removed.add(j)
            else:
                removed.add(i)
                break

    deduplicated = [element for idx, element in enumerate(elements) if idx not in removed]
    return deduplicated, len(removed)


def adaptive_min_crop_size(image_width: int, image_height: int) -> int:
    if image_width <= 1024 and image_height <= 768:
        return 16
    return 32


def should_skip_crop(bbox: list[int], min_crop_size: int) -> bool:
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    if w <= 0 or h <= 0:
        return True
    return min(w, h) < min_crop_size


def clamp_bbox(bbox: list[int], image_width: int, image_height: int) -> list[int]:
    x1, y1, x2, y2 = bbox
    return [
        max(0, min(x1, image_width)),
        max(0, min(y1, image_height)),
        max(0, min(x2, image_width)),
        max(0, min(y2, image_height)),
    ]
