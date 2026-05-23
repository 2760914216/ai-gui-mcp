## ADDED Requirements

### Requirement: Cursor calibration via screenshot analysis

The system SHALL provide a calibration mechanism that detects cursor position from a screenshot and updates the internal coordinate tracker.

#### Scenario: Cursor visible in screenshot

- **WHEN** `ScreenBackend.detect_cursor(screenshot_bytes)` is called and the cursor icon is visible in the screenshot
- **THEN** the system attempts to locate the cursor by template matching or shape detection
- **AND** returns the detected (x, y) pixel coordinates
- **AND** the `InputBackend` internal `_x, _y` is updated to match

#### Scenario: Hardware cursor not visible in screenshot

- **WHEN** the compositor renders the cursor via hardware overlay (not composited into the screenshot)
- **THEN** `detect_cursor()` returns `None` or raises a detectable error
- **AND** the system logs a warning that cursor was not found in the screenshot
- **AND** the calibration is aborted with a descriptive message

### Requirement: Manual calibration as fallback

The system SHALL support a manual calibration mode where the AI specifies expected cursor coordinates, and the system verifies via screenshot analysis.

#### Scenario: AI-initiated manual calibration

- **WHEN** the AI calls the calibration routine with expected coordinates (e.g., "cursor should be at (100, 200)")
- **THEN** the system moves the cursor to (100, 200) via absolute mouse move
- **AND** takes a screenshot
- **AND** attempts to verify cursor position in the screenshot
- **AND** if verification succeeds, updates internal coordinates to (100, 200)
- **AND** returns confirmation with actual detected position

#### Scenario: Manual calibration verification failure

- **WHEN** manual calibration is requested but cursor verification fails (cursor not detected in screenshot)
- **THEN** the system logs a warning
- **AND** updates internal coordinates to the specified position anyway (best-effort)
- **AND** includes a warning in the response that calibration could not be visually verified
