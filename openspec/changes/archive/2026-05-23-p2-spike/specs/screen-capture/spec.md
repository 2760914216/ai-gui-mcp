## ADDED Requirements

### Requirement: Screen capture via xdg-desktop-portal

The system SHALL capture the full screen as a PNG image using the xdg-desktop-portal Screenshot API with `interactive=false`. The captured image SHALL be returned as a base64-encoded string with resolution metadata.

#### Scenario: Successful non-interactive screenshot

- **WHEN** `ScreenBackend.capture()` is called while xdg-desktop-portal and its backend (e.g., xdg-desktop-portal-cosmic) are running
- **THEN** the system sends a D-Bus `Screenshot` call with `interactive=false` to `org.freedesktop.portal.Desktop`
- **AND** subscribes to the async `Response` signal on `org.freedesktop.portal.Request`
- **AND** upon receiving `response=0` (success), reads the screenshot file from the returned `uri`
- **AND** returns the PNG bytes and screen resolution (width, height)

#### Scenario: Screenshot timeout

- **WHEN** xdg-desktop-portal does not respond within 10 seconds
- **THEN** the system raises a timeout error with a descriptive message indicating portal unavailability

#### Scenario: Portal not available

- **WHEN** `org.freedesktop.portal.Desktop` is not activatable on the session D-Bus
- **THEN** the system raises an error with the message "xdg-desktop-portal not available on this system"

### Requirement: Screenshot converted to MCP-friendly format

The system SHALL convert captured screenshots to base64-encoded PNG for transmission over MCP stdio, and SHALL include screen resolution metadata in the response.

#### Scenario: Screenshot returned as base64 with metadata

- **WHEN** a screenshot is successfully captured at 2560×1600
- **THEN** the response includes a `screenshot` field containing a base64-encoded PNG string
- **AND** includes `screen.width` and `screen.height` fields matching the captured resolution
- **AND** includes a `cursor` field with the tracked cursor position (x, y)

#### Scenario: Large payload measurement

- **WHEN** a screenshot is captured and base64-encoded
- **THEN** the system logs the base64 string length and encoding time
- **AND** this data is recorded in spike results for MCP transport assessment
