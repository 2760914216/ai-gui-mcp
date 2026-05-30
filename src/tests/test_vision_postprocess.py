import importlib

vision_postprocess = importlib.import_module("src.providers.vision_postprocess")

ProcessedDetection = vision_postprocess.ProcessedDetection
adaptive_min_crop_size = vision_postprocess.adaptive_min_crop_size
clamp_bbox = vision_postprocess.clamp_bbox
deduplicate_by_iou = vision_postprocess.deduplicate_by_iou
filter_by_area = vision_postprocess.filter_by_area
should_skip_crop = vision_postprocess.should_skip_crop


def _det(bbox, label="test", confidence=0.5):
    return ProcessedDetection(bbox=bbox, label=label, confidence=confidence)


class TestFilterByArea:
    def test_large_element_filtered(self):
        elements = [_det([0, 0, 1000, 600])]
        filtered, dropped = filter_by_area(elements, screen_width=1000, screen_height=1000)
        assert filtered == []
        assert dropped == 1

    def test_small_element_kept(self):
        elements = [_det([0, 0, 1000, 100])]
        filtered, dropped = filter_by_area(elements, screen_width=1000, screen_height=1000)
        assert filtered == elements
        assert dropped == 0

    def test_exactly_at_threshold(self):
        elements = [_det([0, 0, 1000, 500])]
        filtered, dropped = filter_by_area(elements, screen_width=1000, screen_height=1000)
        assert filtered == elements
        assert dropped == 0

    def test_empty_list(self):
        filtered, dropped = filter_by_area([], screen_width=1000, screen_height=1000)
        assert filtered == []
        assert dropped == 0

    def test_zero_area_element_dropped(self):
        elements = [_det([0, 0, 0, 0])]
        filtered, dropped = filter_by_area(elements, screen_width=1000, screen_height=1000)
        assert filtered == []
        assert dropped == 1

    def test_negative_bbox_dropped(self):
        elements = [_det([100, 100, 50, 150])]
        filtered, dropped = filter_by_area(elements, screen_width=1000, screen_height=1000)
        assert filtered == []
        assert dropped == 1

    def test_returns_filtered_and_count(self):
        elements = [_det([0, 0, 1000, 100]), _det([0, 0, 1000, 800])]
        filtered, dropped = filter_by_area(elements, screen_width=1000, screen_height=1000)
        assert isinstance(filtered, list)
        assert dropped == 1
        assert filtered == [elements[0]]


class TestDeduplicateByIou:
    def test_high_iou_different_confidence(self):
        a = _det([0, 0, 100, 100], confidence=0.9)
        b = _det([10, 10, 110, 110], confidence=0.7)
        deduped, removed = deduplicate_by_iou([a, b])
        assert deduped == [a]
        assert removed == 1

    def test_high_iou_same_confidence(self):
        a = _det([0, 0, 100, 100], confidence=0.8)
        b = _det([5, 5, 105, 105], confidence=0.8)
        deduped, removed = deduplicate_by_iou([a, b])
        assert deduped == [a]
        assert removed == 1

    def test_low_iou_both_kept(self):
        a = _det([0, 0, 100, 100], confidence=0.8)
        b = _det([82, 0, 182, 100], confidence=0.9)
        deduped, removed = deduplicate_by_iou([a, b])
        assert deduped == [a, b]
        assert removed == 0

    def test_empty_list(self):
        deduped, removed = deduplicate_by_iou([])
        assert deduped == []
        assert removed == 0

    def test_single_element(self):
        a = _det([0, 0, 10, 10])
        deduped, removed = deduplicate_by_iou([a])
        assert deduped == [a]
        assert removed == 0

    def test_exact_overlap(self):
        a = _det([0, 0, 50, 50], confidence=0.6)
        b = _det([0, 0, 50, 50], confidence=0.5)
        deduped, removed = deduplicate_by_iou([a, b])
        assert deduped == [a]
        assert removed == 1

    def test_non_overlapping(self):
        a = _det([0, 0, 10, 10], confidence=0.9)
        b = _det([20, 20, 30, 30], confidence=0.8)
        c = _det([40, 40, 50, 50], confidence=0.7)
        deduped, removed = deduplicate_by_iou([a, b, c])
        assert deduped == [a, b, c]
        assert removed == 0


class TestAdaptiveMinCropSize:
    def test_small_screen_returns_16(self):
        assert adaptive_min_crop_size(800, 600) == 16

    def test_boundary_1024x768_returns_16(self):
        assert adaptive_min_crop_size(1024, 768) == 16

    def test_large_screen_returns_32(self):
        assert adaptive_min_crop_size(2560, 1600) == 32

    def test_wide_small_height(self):
        assert adaptive_min_crop_size(2000, 600) == 32


class TestShouldSkipCrop:
    def test_small_crop_skipped(self):
        assert should_skip_crop([0, 0, 20, 20], min_crop_size=32) is True

    def test_large_crop_not_skipped(self):
        assert should_skip_crop([0, 0, 100, 100], min_crop_size=32) is False

    def test_exact_min_size(self):
        assert should_skip_crop([0, 0, 32, 32], min_crop_size=32) is False

    def test_negative_dimensions(self):
        assert should_skip_crop([10, 10, 5, 20], min_crop_size=32) is True

    def test_zero_dimensions(self):
        assert should_skip_crop([0, 0, 0, 0], min_crop_size=32) is True


class TestClampBbox:
    def test_within_bounds_unchanged(self):
        assert clamp_bbox([10, 20, 100, 200], image_width=1920, image_height=1080) == [10, 20, 100, 200]

    def test_negative_coords_clamped(self):
        assert clamp_bbox([-10, -20, 100, 200], image_width=1920, image_height=1080) == [0, 0, 100, 200]

    def test_overflow_coords_clamped(self):
        assert clamp_bbox([10, 20, 3000, 2000], image_width=1920, image_height=1080) == [10, 20, 1920, 1080]

    def test_both_overflow(self):
        assert clamp_bbox([-5, -6, 3000, 2000], image_width=1920, image_height=1080) == [0, 0, 1920, 1080]
