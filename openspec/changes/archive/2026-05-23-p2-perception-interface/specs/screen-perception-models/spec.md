## ADDED Requirements

### Requirement: ScreenSnapshot output model

The system SHALL define a `ScreenSnapshot` pydantic model as the unified return type for all `ScreenBackend.capture()` implementations.

#### Scenario: ScreenSnapshot structure

- **WHEN** any `ScreenBackend.capture()` is called
- **THEN** the returned `ScreenSnapshot` SHALL contain: `screen` (width/height), `cursor` (x/y/source), `screenshot` (base64 PNG string or null), `elements` (list of UIElement), and `source` (one of "screenshot", "accessibility", "vision")

#### Scenario: source field indicates perception origin

- **WHEN** `source` is `"screenshot"` (bare capture, no element recognition)
- **THEN** `elements` MUST be an empty array
- **WHEN** `source` is `"accessibility"` (elements from AT-SPI2/UIA/AX tree)
- **THEN** `elements` MAY contain UIElement entries with `confidence=null` (inherently certain)
- **WHEN** `source` is `"vision"` (elements from visual recognition model)
- **THEN** `elements` MAY contain UIElement entries with a numeric `confidence` value (0.0-1.0)

### Requirement: UIElement model for structured GUI elements

The system SHALL define a `UIElement` pydantic model representing a single GUI element discovered via accessibility tree or visual recognition.

#### Scenario: UIElement fields

- **WHEN** a `UIElement` is created
- **THEN** it SHALL have an `id` field (string, unique within the snapshot)
- **AND** it SHALL have optional fields: `role` (string, e.g. "push_button"), `name` (string, display text), `bbox` (list of 4 ints [x, y, w, h]), `states` (list of strings), `parent` (string, parent element id), `confidence` (float or None)

#### Scenario: Minimum viable UIElement

- **WHEN** only element identity is known without position or role
- **THEN** a `UIElement` with only `id` populated (and all others defaulting to None) SHALL be valid

### Requirement: CursorInfo model with source tracking

The system SHALL define a `CursorInfo` pydantic model representing the cursor position and its detection method.

#### Scenario: CursorInfo structure

- **WHEN** cursor position is reported in a `ScreenSnapshot`
- **THEN** the `CursorInfo` SHALL contain: `x` (int), `y` (int), `source` (Literal["tracked", "detected"])
- **AND** `source="tracked"` indicates internal coordinate tracking (uinput accumulation)
- **AND** `source="detected"` indicates visual detection from screenshot (reserved for P3)

#### Scenario: Default source on COSMIC/Wayland

- **WHEN** `XdgPortalBackend` returns a `ScreenSnapshot`
- **THEN** `cursor.source` MUST be `"tracked"` because Wayland hardware cursor overlay is not composited into screenshots
