## ADDED Requirements

### Requirement: Cursor calibration via screenshot analysis

The system SHALL provide a calibration mechanism that attempts to detect cursor position from a screenshot and update the internal coordinate tracker. On Wayland compositors that render cursor via hardware overlay, visual detection is unavailable.

#### Scenario: Cursor visible in screenshot

- **WHEN** `detect_cursor(screenshot_bytes)` is called and the cursor icon is visible in the screenshot
- **THEN** the system attempts to locate the cursor by template matching or shape detection
- **AND** returns the detected (x, y) pixel coordinates
- **AND** the `InputBackend` internal `_x, _y` is updated to match

#### Scenario: Hardware cursor not visible in screenshot (COSMIC/Wayland)

- **WHEN** the compositor renders the cursor via hardware overlay (not composited into the screenshot)
- **THEN** `detect_cursor()` SHALL raise a detectable error or return `None`
- **AND** the system SHALL log a warning that cursor was not found in the screenshot
- **AND** `cursor.source` in `ScreenSnapshot` SHALL remain `"tracked"` (not `"detected"`)
- **AND** this SHALL NOT be treated as a system error — it is the expected behavior on Wayland with hardware cursor

### Requirement: Manual calibration as fallback

The system SHALL support a manual calibration mode where the AI specifies expected cursor coordinates, and the system updates the internal coordinate tracker accordingly.

#### Scenario: AI-initiated manual calibration

- **WHEN** the AI calls the calibration routine with expected coordinates (e.g., "cursor should be at (100, 200)")
- **THEN** the system moves the cursor to (100, 200) via absolute mouse move
- **AND** takes a screenshot
- **AND** updates internal coordinates to (100, 200)
- **AND** returns confirmation with the updated position
- **AND** if visual verification is not possible (hardware overlay), calibration SHALL proceed on trust (best-effort)

#### Scenario: Manual calibration verification failure

- **WHEN** manual calibration is requested but cursor verification is unavailable (hardware overlay)
- **THEN** the system SHALL update internal coordinates to the specified position
- **AND** SHALL include a warning in the response that calibration could not be visually verified
- **AND** this SHALL NOT block the calibration from completing

### Requirement: Cursor calibration acknowledges platform limitations

The system SHALL NOT assume cursor visibility in screenshots. Each `ScreenBackend` implementation SHALL report its cursor detection capability.

#### Scenario: Platform capability reporting

- **WHEN** a `ScreenBackend` implementation is instantiated
- **THEN** it SHALL accurately report whether the platform supports visual cursor detection
- **AND** `XdgPortalBackend` (Wayland/COSMIC) SHALL report cursor detection as unavailable due to hardware overlay
- **AND** this capability information SHALL be reflected in `ScreenSnapshot.cursor.source`
