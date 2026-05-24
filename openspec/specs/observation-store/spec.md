## Requirements

### Requirement: Session-scoped observation storage

The system SHALL maintain an in-memory `ObservationStore` that maps `snapshot_id` to observation records within the current MCP process lifetime.

#### Scenario: Snapshot creation produces unique ID

- **WHEN** `ObservationStore.create(image_bytes, metadata)` is called
- **THEN** it SHALL return a new unique `snapshot_id` in format `snap_{uuid_short}`
- **AND** the stored record SHALL contain the raw image bytes, creation timestamp, and metadata

#### Scenario: Snapshot retrieval by ID

- **WHEN** `ObservationStore.get(snapshot_id)` is called with a valid ID
- **THEN** it SHALL return the corresponding `ObservationRecord`
- **WHEN** called with an unknown or expired ID
- **THEN** it SHALL return `None`

### Requirement: Snapshot lifecycle with TTL and capacity limits

The system SHALL enforce three configurable limits on snapshot retention: maximum count (N), time-to-live (TTL), and total memory budget.

#### Scenario: Count-based eviction

- **WHEN** the store holds N snapshots (default: 16) and a new snapshot is created
- **THEN** the oldest snapshot by creation time SHALL be evicted

#### Scenario: TTL-based eviction

- **WHEN** a snapshot's age exceeds the configured TTL (default: 300 seconds)
- **THEN** it SHALL be evicted on the next access or creation

#### Scenario: Memory budget enforcement

- **WHEN** the total raw image bytes across all stored snapshots exceeds the configured memory budget (default: 256 MB)
- **THEN** the oldest un-analyzed snapshots SHALL be evicted until the budget is satisfied

### Requirement: Analysis cache with snapshot_id key

The system SHALL cache `AnalysisResult` objects keyed by `snapshot_id`. A given snapshot SHALL have at most one cached analysis result in P3A v1.

#### Scenario: Cache hit

- **WHEN** `ObservationStore.get_analysis(snapshot_id)` is called and a cached result exists
- **THEN** the cached `AnalysisResult` SHALL be returned without re-parsing

#### Scenario: Cache miss

- **WHEN** `ObservationStore.get_analysis(snapshot_id)` is called and no cached result exists
- **THEN** `None` SHALL be returned
- **AND** the caller is responsible for producing and storing a new analysis result via `put_analysis(snapshot_id, result)`

#### Scenario: Analysis evicted with snapshot

- **WHEN** a snapshot is evicted (via count, TTL, or memory budget)
- **THEN** its associated cached analysis SHALL also be evicted

### Requirement: Store is process-scoped, not persistent

The system SHALL NOT persist observation records to disk. All data SHALL be lost on process exit.

#### Scenario: Process restart clears store

- **WHEN** the MCP server process restarts
- **THEN** no snapshots from the previous session SHALL be retrievable
