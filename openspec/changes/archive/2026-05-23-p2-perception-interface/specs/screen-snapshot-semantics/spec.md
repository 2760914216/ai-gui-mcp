## MODIFIED Requirements

### Requirement: screen_snapshot always returns screenshot

The `screen_snapshot()` action SHALL always return a base64-encoded screenshot, regardless of whether an accessibility tree is available. The screenshot is the primary output; the elements field is best-effort.

#### Scenario: Application without accessibility tree

- **WHEN** `screen_snapshot()` is called and the focused application does not expose an accessibility tree
- **THEN** the response SHALL contain `screenshot` (base64 PNG), `screen` (resolution metadata), `source` (set to `"screenshot"`)
- **AND** `elements` SHALL be an empty array `[]`
- **AND** a `note` field MAY explain the situation (optional)

#### Scenario: Application with accessibility tree

- **WHEN** `screen_snapshot()` is called and the focused application exposes an accessibility tree
- **THEN** the response SHALL contain `screenshot` (base64 PNG), `screen` (resolution metadata), and `elements` (parsed accessibility tree)
- **AND** `source` SHALL be `"accessibility"`
- **AND** each element in `elements` contains at minimum `id`, `role`, and `bbox`

### Requirement: screen_snapshot response includes source field

The system SHALL include a `source` field in the `screen_snapshot()` response to indicate how the perception data was obtained.

#### Scenario: Source values

- **WHEN** elements come from an accessibility tree → `source` SHALL be `"accessibility"`
- **WHEN** elements come from a visual recognition model → `source` SHALL be `"vision"`
- **WHEN** no element recognition is available → `source` SHALL be `"screenshot"`

### Requirement: Accessibility tree is best-effort only

The system SHALL treat accessibility tree data as optional and best-effort. The absence of a tree SHALL NOT be treated as an error condition.

#### Scenario: AT-SPI2 bus not available

- **WHEN** the AT-SPI2 bus (`org.a11y.Bus`) is not reachable
- **THEN** `screen_snapshot()` SHALL still succeed with `elements: []` and `source: "screenshot"`
- **AND** no error is raised

#### Scenario: Accessibility tree fetch timeout

- **WHEN** tree enumeration takes longer than 5 seconds
- **THEN** the fetch SHALL be abandoned and `elements` returned as an empty array
- **AND** `note` MAY indicate "AT-SPI2 tree fetch timed out"

### Requirement: screen_snapshot response includes structured cursor position

The system SHALL include the tracked cursor position in the `screen_snapshot()` response as a structured `CursorInfo` object.

#### Scenario: Cursor position included in snapshot

- **WHEN** `screen_snapshot()` is called
- **THEN** the response SHALL include a `cursor` field with `x`, `y`, and `source` properties
- **AND** `source` SHALL be `"tracked"` (internal coordinate tracker) on COSMIC/Wayland where hardware cursor overlay prevents visual detection

## REMOVED Requirements

### Requirement: screen_snapshot response includes accessible boolean

**Reason**: The `accessible` boolean is redundant with the new `source` field. `source="accessibility"` or `source="vision"` conveys whether structured element data is available more precisely than a binary flag.

**Migration**: Callers that checked `accessible: true/false` SHALL now check `source` field. `source="screenshot"` replaces `accessible: false`. `source="accessibility"` or `source="vision"` replaces `accessible: true`.
