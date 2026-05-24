## Requirements

### Requirement: SnapshotResult as public snapshot contract

The system SHALL define a `SnapshotResult` pydantic model that replaces `ScreenSnapshot` as the return type for `screen(action="snapshot")`.

#### Scenario: SnapshotResult is a lightweight handle

- **WHEN** `screen(action="snapshot")` is called
- **THEN** the response SHALL be a `SnapshotResult` containing `snapshot_id`, `created_at`, `screen` (ScreenState), `has_image`, `image_format`, and `note`
- **AND** the response SHALL NOT contain a `screenshot` base64 field
- **AND** the response SHALL NOT contain an `elements` field
- **AND** the response SHALL NOT contain a `source` field

#### Scenario: SnapshotResult when capture succeeds

- **WHEN** screenshot capture succeeds
- **THEN** `has_image` SHALL be `true`
- **AND** `image_format` SHALL indicate the image MIME type (e.g., `"png"`)

#### Scenario: SnapshotResult when capture fails

- **WHEN** screenshot capture fails (portal unavailable, timeout, permission error)
- **THEN** `has_image` SHALL be `false`
- **AND** `note` SHALL contain a descriptive error message

### Requirement: ScreenSnapshot output model

The `ScreenSnapshot` pydantic model SHALL be reclassified as an internal model used between `PerceptionService` and providers. It SHALL NOT be the public return type of `screen(action="snapshot")`.

#### Scenario: ScreenSnapshot is internal only

- **WHEN** `ScreenSnapshot` is used
- **THEN** it SHALL only appear in provider-level and `PerceptionService` internal logic
- **AND** it SHALL NOT be serialized as an MCP tool response directly

#### Scenario: ScreenSnapshot retains existing structure

- **WHEN** any `ScreenBackend.capture()` is called (during transition)
- **THEN** the returned `ScreenSnapshot` SHALL still contain: `screen` (width/height), `cursor` (x/y/source), `screenshot` (base64 PNG string or null), `elements` (list of UIElement), `source` (one of "screenshot","accessibility","vision"), and `note`

#### Scenario: source field indicates perception origin (internal use)

- **WHEN** `source` is `"screenshot"` (bare capture, no element recognition)
- **THEN** `elements` MUST be an empty array
- **WHEN** `source` is `"vision"` (elements from visual recognition model)
- **THEN** `elements` MAY contain UIElement entries with a numeric `confidence` value (0.0-1.0)

### Requirement: UIElement model for structured GUI elements

The existing `UIElement` SHALL be retained as an internal/perception model. The new `ParsedElement` (defined in `gui-parser-result`) SHALL be the public-facing element model for `AnalysisResult`.

#### Scenario: UIElement continues to serve internal providers

- **WHEN** a provider (accessibility or vision) discovers elements
- **THEN** it MAY use `UIElement` as an internal representation
- **AND** `PerceptionService` SHALL convert `UIElement` to `ParsedElement` for public output

#### Scenario: ParsedElement replaces UIElement in public API

- **WHEN** `AnalysisResult.elements` is populated
- **THEN** each element SHALL be a `ParsedElement` with fields: `id`, `type` (controlled enum), `bbox`, `text`, `description`, `confidence`, `parent_id`, `children_ids`, `region_ref`

#### Scenario: Minimum viable UIElement

- **WHEN** only element identity is known without position or role
- **THEN** a `UIElement` with only `id` populated (and all others defaulting to None) SHALL be valid

### Requirement: CursorInfo model with source tracking

The `CursorInfo` model SHALL continue to be used internally. The public `ScreenState` model SHALL expose cursor fields directly instead of wrapping a separate `CursorInfo` object.

#### Scenario: CursorInfo remains internal

- **WHEN** cursor position is tracked or detected
- **THEN** `CursorInfo` SHALL be used internally with fields: `x`, `y`, `source` (Literal["tracked","detected"])

#### Scenario: ScreenState exposes cursor in public API

- **WHEN** `screen(action="cursor")` is called
- **THEN** the response SHALL be a `ScreenState` with `cursor_x`, `cursor_y`, and `cursor_source` fields (not a nested `CursorInfo` object)

#### Scenario: Default source on COSMIC/Wayland

- **WHEN** `XdgPortalBackend` returns a `ScreenSnapshot`
- **THEN** `cursor.source` MUST be `"tracked"` because Wayland hardware cursor overlay is not composited into screenshots
