## Requirements

### Requirement: PerceptionService as internal orchestration layer

The system SHALL define a `PerceptionService` class that composes provider-level backends and exposes methods for the `screen` tool actions: `snapshot()`, `analyze()`, and `image()`.

#### Scenario: PerceptionService composes providers

- **WHEN** `PerceptionService` is initialized
- **THEN** it SHALL accept a `ScreenshotProvider`, an optional `AccessibilityProvider`, and an optional `VisionProvider`
- **AND** it SHALL own an `ObservationStore` instance

#### Scenario: snapshot() delegates to ScreenshotProvider

- **WHEN** `PerceptionService.snapshot()` is called
- **THEN** it SHALL call `ScreenshotProvider.capture()` to obtain raw image data
- **AND** it SHALL create a new `ObservationRecord` in the `ObservationStore`
- **AND** it SHALL return a `SnapshotResult` containing `snapshot_id`, `has_image`, and metadata

#### Scenario: analyze() uses VisionProvider

- **WHEN** `PerceptionService.analyze(snapshot_id?)` is called
- **THEN** if `snapshot_id` is provided, it SHALL retrieve the observation from `ObservationStore`
- **THEN** if `snapshot_id` is omitted, it SHALL first call `snapshot()` to create a new observation
- **AND** it SHALL call `VisionProvider.parse(image, a11y_hints)` to produce an `AnalysisResult`
- **AND** it SHALL cache the `AnalysisResult` in `ObservationStore` keyed by `snapshot_id`

#### Scenario: image() retrieves raw payload

- **WHEN** `PerceptionService.image(snapshot_id)` is called with a valid ID
- **THEN** it SHALL return `{snapshot_id, mime_type, image_base64}` from the stored observation
- **WHEN** called with an unknown or expired ID
- **THEN** it SHALL raise an error indicating the snapshot is not available

### Requirement: Screen tool action routing through PerceptionService

The MCP server's `screen` tool handler SHALL route actions through `PerceptionService` rather than calling backends directly.

#### Scenario: Server routes screen actions to service

- **WHEN** `_handle_screen(action="snapshot")` is invoked
- **THEN** it SHALL call `PerceptionService.snapshot()` and return the `SnapshotResult`
- **WHEN** `_handle_screen(action="analyze")` is invoked
- **THEN** it SHALL call `PerceptionService.analyze()` and return the `AnalysisResult`
- **WHEN** `_handle_screen(action="image")` is invoked with `snapshot_id`
- **THEN** it SHALL call `PerceptionService.image()` and return the image payload

#### Scenario: Server does not call backends directly

- **WHEN** processing any `screen` perception action (snapshot/analyze/image)
- **THEN** `server.py` SHALL NOT import or call `ScreenBackend`, `XdgPortalBackend`, or any provider directly
- **AND** all perception orchestration SHALL be delegated to `PerceptionService`

### Requirement: Provider abstraction separate from service layer

The system SHALL define provider-level abstract classes independent of `PerceptionService`, each responsible for one perception source.

#### Scenario: ScreenshotProvider abstraction

- **WHEN** a `ScreenshotProvider` subclass is implemented
- **THEN** it MUST implement `capture() -> RawImage` for producing raw screenshot data
- **AND** it MUST implement `screen_size() -> tuple[int, int]`

#### Scenario: AccessibilityProvider abstraction

- **WHEN** an `AccessibilityProvider` subclass is implemented
- **THEN** it MUST implement `is_available() -> bool` to check AT bus reachability
- **AND** it MUST implement `get_tree(max_depth, max_nodes) -> A11yTree`

#### Scenario: VisionProvider abstraction

- **WHEN** a `VisionProvider` subclass is implemented
- **THEN** it MUST implement `parse(image: RawImage, a11y_hints: A11yTree | None) -> AnalysisResult`
- **AND** parsing SHALL be best-effort: partial results are returned when full parsing fails

#### Scenario: AccessibilityProvider empty implementation is valid

- **WHEN** `AccessibilityProvider.is_available()` returns `False`
- **THEN** `get_tree()` SHALL return an empty tree with `node_count=0`
- **AND** this SHALL NOT be treated as an error by `PerceptionService`
