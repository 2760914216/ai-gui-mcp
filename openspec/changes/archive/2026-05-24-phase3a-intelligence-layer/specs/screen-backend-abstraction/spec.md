## MODIFIED Requirements

### Requirement: ScreenBackend abstract interface

The `ScreenBackend` abstract class SHALL be retained but its role SHALL shift from "perception endpoint" to "screenshot provider". The new `PerceptionService` SHALL be the primary perception entry point consumed by `server.py`.

#### Scenario: ScreenBackend continues as capture abstraction

- **WHEN** a concrete class implements `ScreenBackend`
- **THEN** it MUST implement `capture() -> ScreenSnapshot` for full-screen capture
- **AND** MUST implement `screen_size() -> tuple[int, int]` for resolution
- **AND** MUST implement `close()` for resource cleanup

#### Scenario: ScreenBackend is called by PerceptionService, not by server

- **WHEN** `PerceptionService.snapshot()` is invoked
- **THEN** it SHALL call `ScreenBackend.capture()` internally
- **AND** `server.py` SHALL NOT call `ScreenBackend.capture()` directly
- **AND** `server.py` SHALL NOT import `ScreenBackend` for snapshot handling

#### Scenario: ScreenBackend capture returns ScreenSnapshot (internal model)

- **WHEN** `XdgPortalBackend.capture()` is called
- **THEN** the return value SHALL be a `ScreenSnapshot` pydantic model (internal use)
- **AND** `PerceptionService` SHALL transform it into a `SnapshotResult` for public output

### Requirement: InputBackend retains screen state methods during transition

The existing `InputBackend.screen_size()` and `InputBackend.get_cursor_position()` SHALL remain in place. They SHALL be consumed by `PerceptionService` for cursor position in snapshot context.

#### Scenario: InputBackend provides cursor for snapshots

- **WHEN** `PerceptionService.snapshot()` is called
- **THEN** cursor position SHALL be obtained from `InputBackend.get_cursor_position()` (not from `ScreenBackend`)

#### Scenario: Existing InputBackend methods unchanged

- **WHEN** P3A perception service is implemented
- **THEN** `src/backends/base.py` is NOT modified
- **AND** `src/backends/uinput.py` is NOT modified
- **AND** existing P1 tests continue to pass

### Requirement: ScreenBackend lives in src/backends/

The `ScreenBackend` abstract class SHALL remain in `src/backends/screen.py`. New provider abstractions (`ScreenshotProvider`, `AccessibilityProvider`, `VisionProvider`) SHALL be placed in `src/providers/`.

#### Scenario: Backend and provider locations

- **WHEN** the P3A change is applied
- **THEN** `src/backends/screen.py` still contains `ScreenBackend`
- **AND** `src/providers/screenshot.py` contains `ScreenshotProvider` (or adapter over `XdgPortalBackend`)
- **AND** `src/providers/a11y.py` contains `AccessibilityProvider`
- **AND** `src/providers/vision.py` contains `VisionProvider`

## ADDED Requirements

### Requirement: PerceptionService as new perception entry point

The system SHALL define `PerceptionService` in `src/services/perception.py` as the primary perception orchestration layer consumed by `server.py`.

#### Scenario: PerceptionService initialization

- **WHEN** `PerceptionService` is initialized in `server.py`'s `main()`
- **THEN** it SHALL receive an `InputBackend`, a `ScreenBackend` (wrapped as `ScreenshotProvider`), and optional `AccessibilityProvider` / `VisionProvider`
- **AND** it SHALL create an internal `ObservationStore`

#### Scenario: server.py uses PerceptionService for all screen perception actions

- **WHEN** `_handle_screen()` processes `snapshot`, `analyze`, or `image` actions
- **THEN** it SHALL delegate to `PerceptionService` methods
- **AND** it SHALL NOT directly call `ScreenBackend.capture()` or access `ObservationStore`
