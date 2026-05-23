## ADDED Requirements

### Requirement: ScreenBackend abstract interface

The system SHALL define a `ScreenBackend` abstract base class with methods for screen capture and perception, independent of `InputBackend`. This is a production-grade interface, not a spike prototype.

#### Scenario: ScreenBackend defines capture methods

- **WHEN** a new platform backend implements `ScreenBackend`
- **THEN** it MUST implement `capture() -> ScreenSnapshot` for full-screen capture returning structured data
- **AND** MUST implement `screen_size() -> tuple[int, int]` for resolution (independent of InputBackend)
- **AND** MUST implement `close()` for resource cleanup

#### Scenario: ScreenBackend operates independently

- **WHEN** `ScreenBackend` methods are called
- **THEN** they SHALL NOT depend on `InputBackend` state
- **AND** `screen_size()` in `ScreenBackend` SHALL be an independent implementation (not forwarded from `InputBackend`)

#### Scenario: ScreenBackend capture returns ScreenSnapshot not raw bytes

- **WHEN** `XdgPortalBackend.capture()` is called
- **THEN** the return value SHALL be a `ScreenSnapshot` pydantic model with `screenshot` containing base64-encoded PNG data
- **AND** the caller SHALL NOT need to base64-encode or parse resolution from raw bytes

### Requirement: ScreenBackend does not duplicate InputBackend responsibilities

The `ScreenBackend` SHALL focus on perception (capture, accessibility, window info). It SHALL NOT implement input simulation (mouse, keyboard) — those remain in `InputBackend`.

#### Scenario: ScreenBackend responsibilities

- **WHEN** designing the `ScreenBackend` interface
- **THEN** it SHALL NOT include methods for mouse movement, clicking, or keyboard input
- **AND** it MAY include methods for window management (list/focus) through compositor protocols (future extension point)

### Requirement: InputBackend retains screen state methods during transition

The existing `InputBackend.screen_size()` and `InputBackend.get_cursor_position()` SHALL remain in place. These methods are NOT removed or deprecated at this stage.

#### Scenario: Existing InputBackend methods unchanged

- **WHEN** P2 perception interface is implemented
- **THEN** `src/backends/base.py` is NOT modified
- **AND** `src/backends/uinput.py` is NOT modified
- **AND** existing P1 tests continue to pass

### Requirement: ScreenBackend lives in src/backends/

The `ScreenBackend` abstract class SHALL be placed in `src/backends/screen.py` as production code, alongside the existing `InputBackend` in `src/backends/base.py`.

#### Scenario: Production location

- **WHEN** the P2 perception interface change is applied
- **THEN** `src/backends/screen.py` exists and contains the `ScreenBackend` abstract class
- **AND** it is importable as `from src.backends.screen import ScreenBackend`
