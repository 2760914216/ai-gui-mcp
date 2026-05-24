"""ObservationStore — bounded in-memory cache for screen snapshots and analyses.

Manages snapshot lifecycle with three eviction strategies:
- Count-based: keeps at most max_count records
- TTL-based: expires records older than ttl_sec
- Memory-based: keeps total image bytes under memory_budget_mb
"""

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from src.models import AnalysisResult


@dataclass
class ObservationRecord:

    snapshot_id: str
    image_bytes: bytes
    mime_type: str = "image/png"
    created_at: float = field(default_factory=time.time)
    screen_width: int = 0
    screen_height: int = 0
    cursor_x: int = 0
    cursor_y: int = 0
    analysis: AnalysisResult | None = None


class ObservationStore:
    """Bounded in-memory store for screen observations.

    Eviction order: expired first, then oldest-first by count/memory.
    """

    def __init__(
        self,
        max_count: int = 16,
        ttl_sec: float = 300.0,
        memory_budget_mb: float = 256.0,
    ):
        self._records: OrderedDict[str, ObservationRecord] = OrderedDict()
        self._analyses: dict[str, AnalysisResult] = {}
        self.max_count: int = max_count
        self.ttl_sec: float = ttl_sec
        self.memory_budget_bytes: int = int(memory_budget_mb * 1024 * 1024)

    def create(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        screen_width: int = 0,
        screen_height: int = 0,
        cursor_x: int = 0,
        cursor_y: int = 0,
    ) -> str:
        snapshot_id = f"snap_{uuid.uuid4().hex[:8]}"
        record = ObservationRecord(
            snapshot_id=snapshot_id,
            image_bytes=image_bytes,
            mime_type=mime_type,
            screen_width=screen_width,
            screen_height=screen_height,
            cursor_x=cursor_x,
            cursor_y=cursor_y,
        )
        self._records[snapshot_id] = record
        self._evict_if_needed()
        return snapshot_id

    def get(self, snapshot_id: str) -> ObservationRecord | None:
        self._evict_expired()
        return self._records.get(snapshot_id)

    def put_analysis(self, snapshot_id: str, analysis: AnalysisResult) -> None:
        self._analyses[snapshot_id] = analysis

    def get_analysis(self, snapshot_id: str) -> AnalysisResult | None:
        return self._analyses.get(snapshot_id)

    def _evict_if_needed(self) -> None:
        self._evict_expired()
        self._evict_by_count()
        self._evict_by_memory()

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [
            sid
            for sid, rec in self._records.items()
            if now - rec.created_at > self.ttl_sec
        ]
        for sid in expired:
            self._remove_snapshot(sid)

    def _evict_by_count(self) -> None:
        while len(self._records) > self.max_count:
            oldest = next(iter(self._records))
            self._remove_snapshot(oldest)

    def _evict_by_memory(self) -> None:
        total = sum(len(rec.image_bytes) for rec in self._records.values())
        while total > self.memory_budget_bytes and len(self._records) > 0:
            oldest = next(iter(self._records))
            self._remove_snapshot(oldest)
            total = sum(len(rec.image_bytes) for rec in self._records.values())

    def _remove_snapshot(self, snapshot_id: str) -> None:
        self._records.pop(snapshot_id, None)
        self._analyses.pop(snapshot_id, None)
