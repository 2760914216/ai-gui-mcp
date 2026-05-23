## ADDED Requirements

### Requirement: screen_snapshot always returns screenshot

The `screen_snapshot()` action SHALL always return a base64-encoded screenshot, regardless of whether an accessibility tree is available. The screenshot is the primary output; the elements field is best-effort.

#### Scenario: Application without accessibility tree

- **WHEN** `screen_snapshot()` is called and the focused application does not expose an AT-SPI2 tree
- **THEN** the response contains `screenshot` (base64 PNG), `screen` (resolution metadata)
- **AND** `elements` is an empty array `[]`
- **AND** `accessible` is `false`
- **AND** a `note` field explains the fallback situation

#### Scenario: Application with accessibility tree

- **WHEN** `screen_snapshot()` is called and the focused application exposes an AT-SPI2 tree
- **THEN** the response contains `screenshot` (base64 PNG), `screen` (resolution metadata), and `elements` (parsed accessibility tree)
- **AND** `accessible` is `true`
- **AND** each element in `elements` contains at minimum `id`, `role`, and `bbox`

### Requirement: Accessibility tree is best-effort only

The system SHALL treat AT-SPI2 accessibility tree data as optional and best-effort. The absence of a tree SHALL NOT be treated as an error condition.

#### Scenario: AT-SPI2 bus not available

- **WHEN** the AT-SPI2 bus (`org.a11y.Bus`) is not reachable
- **THEN** `screen_snapshot()` still succeeds with `elements: []` and `accessible: false`
- **AND** no error is raised

#### Scenario: AT-SPI2 tree fetch timeout

- **WHEN** AT-SPI2 tree enumeration takes longer than 5 seconds
- **THEN** the fetch is abandoned and `elements` is returned as an empty array
- **AND** `note` indicates "AT-SPI2 tree fetch timed out"

### Requirement: screen_snapshot response includes cursor position

The system SHALL include the tracked cursor position in the `screen_snapshot()` response.

#### Scenario: Cursor position included in snapshot

- **WHEN** `screen_snapshot()` is called
- **THEN** the response includes a `cursor` field with `x` and `y` values from the internal coordinate tracker
