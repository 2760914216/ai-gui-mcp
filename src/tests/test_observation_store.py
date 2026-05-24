import time

from src.models import AnalysisResult
from src.stores.observation import ObservationRecord, ObservationStore


class TestCreate:

    def test_create_returns_unique_snapshot_id_with_prefix(self):
        store = ObservationStore()
        id1 = store.create(image_bytes=b"\x89PNG")
        id2 = store.create(image_bytes=b"\x89PNG")

        assert id1.startswith("snap_")
        assert id2.startswith("snap_")
        assert id1 != id2


class TestGet:

    def test_get_valid_snapshot_id_returns_record(self):
        store = ObservationStore()
        img = b"\x89PNG_test_data"
        sid = store.create(
            image_bytes=img,
            mime_type="image/png",
            screen_width=1920,
            screen_height=1080,
            cursor_x=100,
            cursor_y=200,
        )

        record = store.get(sid)

        assert record is not None
        assert isinstance(record, ObservationRecord)
        assert record.snapshot_id == sid
        assert record.image_bytes == img
        assert record.mime_type == "image/png"
        assert record.screen_width == 1920
        assert record.screen_height == 1080
        assert record.cursor_x == 100
        assert record.cursor_y == 200

    def test_get_unknown_snapshot_id_returns_none(self):
        store = ObservationStore()
        assert store.get("snap_nonexistent") is None


class TestAnalysisCache:

    def test_put_and_get_analysis_cache_hit(self):
        store = ObservationStore()
        sid = store.create(image_bytes=b"\x89PNG")
        analysis = AnalysisResult(snapshot_id=sid, overall_quality="high")

        store.put_analysis(sid, analysis)
        result = store.get_analysis(sid)

        assert result is not None
        assert result.snapshot_id == sid
        assert result.overall_quality == "high"

    def test_get_analysis_cache_miss_returns_none(self):
        store = ObservationStore()
        assert store.get_analysis("snap_unknown") is None


class TestEvictionByCount:

    def test_evicts_oldest_when_exceeding_max_count(self):
        store = ObservationStore(max_count=16)
        ids = []
        for i in range(17):
            sid = store.create(image_bytes=b"\x89PNG")
            ids.append(sid)

        # First snapshot should be evicted
        assert store.get(ids[0]) is None
        # Last snapshot should remain
        assert store.get(ids[-1]) is not None


class TestEvictionByTTL:

    def test_evicts_expired_snapshots(self):
        store = ObservationStore(ttl_sec=0)
        sid = store.create(image_bytes=b"\x89PNG")

        # After creation with ttl=0, any get() triggers eviction
        # Sleep briefly to ensure time has passed
        time.sleep(0.01)
        result = store.get(sid)

        assert result is None


class TestEvictionByMemory:

    def test_evicts_oldest_when_exceeding_memory_budget(self):
        # 1KB budget
        store = ObservationStore(memory_budget_mb=0.001, max_count=100)
        # Each image >512 bytes, so 2+ will exceed 1KB
        big_image = b"\x89" * 600

        id1 = store.create(image_bytes=big_image)
        id2 = store.create(image_bytes=big_image)

        # First should be evicted to stay under budget
        assert store.get(id1) is None
        # Second should remain
        assert store.get(id2) is not None


class TestAnalysisCoEviction:

    def test_analysis_removed_when_snapshot_evicted_by_count(self):
        store = ObservationStore(max_count=2)
        sid1 = store.create(image_bytes=b"\x89PNG")
        analysis = AnalysisResult(snapshot_id=sid1, overall_quality="medium")
        store.put_analysis(sid1, analysis)

        # Create 2 more to evict sid1
        store.create(image_bytes=b"\x89PNG")
        store.create(image_bytes=b"\x89PNG")

        assert store.get(sid1) is None
        assert store.get_analysis(sid1) is None
