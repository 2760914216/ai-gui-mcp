## MODIFIED Requirements

### Requirement: screen tool supports snapshot action

The `screen` MCP tool SHALL support a `snapshot` action that captures the screen and returns a base64-encoded PNG image with metadata.

#### Scenario: screen snapshot returns screenshot and metadata

- **WHEN** `screen(action="snapshot")` is called
- **THEN** the system captures the full screen via xdg-desktop-portal
- **AND** returns a JSON object containing:
  - `screen`: `{width: <int>, height: <int>}` — detected resolution
  - `cursor`: `{x: <int>, y: <int>}` — tracked cursor position
  - `screenshot`: `<base64 PNG string>`
  - `elements`: `[]` — empty in spike (AT-SPI2 not integrated)
  - `accessible`: `false` — placeholder for future AT-SPI2 integration

#### Scenario: screen snapshot when capture fails

- **WHEN** `screen(action="snapshot")` is called but screenshot capture fails (portal timeout, not available)
- **THEN** returns an error with a descriptive message explaining the failure reason

## ADDED Requirements

### Requirement: screen tool action enum extended for snapshot

The `screen` tool's `action` parameter SHALL accept `snapshot` as a valid value in addition to the existing `size` and `cursor`.

#### Scenario: snapshot added to action enum

- **WHEN** the MCP server registers the `screen` tool
- **THEN** the `action` enum includes `snapshot` alongside `size` and `cursor`
- **AND** the `snapshot` action requires no additional parameters
