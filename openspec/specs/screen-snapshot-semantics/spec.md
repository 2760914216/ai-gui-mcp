## Requirements

### Requirement: Accessibility tree is best-effort only

The system SHALL treat accessibility tree data as optional and best-effort. The absence of a tree SHALL NOT be treated as an error condition. This requirement is unchanged but the implementation moves from direct `ScreenBackend` to `AccessibilityProvider` within `PerceptionService`.

#### Scenario: AT-SPI2 bus not available

- **WHEN** the AT-SPI2 bus (`org.a11y.Bus`) is not reachable
- **THEN** `AccessibilityProvider.is_available()` SHALL return `False`
- **AND** `PerceptionService` SHALL proceed without accessibility hints
- **AND** no error is raised

#### Scenario: Accessibility tree fetch timeout

- **WHEN** tree enumeration takes longer than the configured timeout
- **THEN** the fetch SHALL be abandoned and an empty tree returned
- **AND** `AnalysisResult.warnings` MAY include a `provider_timeout` warning

### Requirement: snapshot action returns observation handle

The `screen(action="snapshot")` action SHALL create an observation handle rather than returning raw image data or structured elements.

#### Scenario: Snapshot returns handle

- **WHEN** `screen(action="snapshot")` is called
- **THEN** the response SHALL be a `SnapshotResult` with `snapshot_id`, `created_at`, `screen`, `has_image`, `image_format`, and `note`
- **AND** the response SHALL NOT include `screenshot`, `elements`, `source`, or `cursor` fields

#### Scenario: Failed capture still returns a valid handle

- **WHEN** `screen(action="snapshot")` is called and portal capture fails
- **THEN** a `SnapshotResult` with `has_image=false` SHALL still be returned
- **AND** the system SHALL NOT raise a tool-level error for capture failures

#### Scenario: Application without accessibility tree

- **WHEN** `screen(action="snapshot")` is called and the focused application does not expose an accessibility tree
- **THEN** the response SHALL contain a valid `SnapshotResult` with screen metadata
- **AND** `has_image` SHALL be `true` when capture succeeds

#### Scenario: Application with accessibility tree

- **WHEN** `screen(action="snapshot")` is called and the focused application exposes an accessibility tree
- **THEN** the response SHALL contain a valid `SnapshotResult` regardless of tree availability
- **AND** accessibility data is accessed separately via `screen(action="analyze")`

### Requirement: analyze action returns structured GUI understanding

The `screen(action="analyze", snapshot_id?)` action SHALL return an `AnalysisResult` with layout summary, elements, quality assessment, and warnings.

#### Scenario: Analyze with explicit snapshot_id

- **WHEN** `screen(action="analyze", snapshot_id="snap_abc")` is called with a valid and cached analysis
- **THEN** the cached `AnalysisResult` SHALL be returned immediately

#### Scenario: Analyze without snapshot_id creates implicit snapshot

- **WHEN** `screen(action="analyze")` is called without a `snapshot_id`
- **THEN** the system SHALL first create a new snapshot internally
- **AND** then parse it to produce the `AnalysisResult`

#### Scenario: Analyze when no image is available

- **WHEN** `screen(action="analyze")` is called and no screenshot can be captured
- **THEN** `AnalysisResult.overall_quality` SHALL be `"low"`
- **AND** a warning with code `image_unavailable` SHALL be included
- **AND** `elements` SHALL be an empty array

### Requirement: image action returns raw payload on demand

The `screen(action="image", snapshot_id)` action SHALL return the raw image payload for a previously created snapshot.

#### Scenario: Image retrieval succeeds

- **WHEN** `screen(action="image", snapshot_id="snap_abc")` is called with a valid ID that has an image
- **THEN** the response SHALL contain `snapshot_id`, `mime_type`, and `image_base64`

#### Scenario: Image retrieval fails for missing snapshot

- **WHEN** `screen(action="image", snapshot_id="snap_abc")` is called with an unknown or expired ID
- **THEN** a tool-level error SHALL be raised indicating the snapshot is not available

### Requirement: screen tool action enum extension

The `screen` tool's `action` parameter SHALL accept `"analyze"` and `"image"` in addition to the existing `"size"`, `"cursor"`, and `"snapshot"`.

#### Scenario: Screen tool schema includes new actions

- **WHEN** the MCP server advertises the `screen` tool
- **THEN** its `action` enum SHALL include: `"size"`, `"cursor"`, `"snapshot"`, `"analyze"`, `"image"`
- **AND** `"analyze"` SHALL have an optional `snapshot_id` parameter
- **AND** `"image"` SHALL have a required `snapshot_id` parameter

### Requirement: Cursor position available in snapshot context

The system SHALL include tracked cursor position in `SnapshotResult.screen` via the `ScreenState` model.

#### Scenario: Cursor in snapshot

- **WHEN** `screen(action="snapshot")` is called
- **THEN** the `SnapshotResult.screen` SHALL include `cursor_x`, `cursor_y`, and `cursor_source="tracked"` (on Wayland/COSMIC)
