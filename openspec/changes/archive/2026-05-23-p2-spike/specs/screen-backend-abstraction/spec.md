## ADDED Requirements

### Requirement: ScreenBackend abstract interface

The system SHALL define a `ScreenBackend` abstract base class with methods for screen capture and perception, independent of `InputBackend`.

#### Scenario: ScreenBackend defines capture methods

- **WHEN** a new platform backend implements `ScreenBackend`
- **THEN** it MUST implement `capture() -> bytes` for raw PNG screenshot
- **AND** MUST implement `capture_base64() -> str` for base64-encoded screenshot
- **AND** MUST implement `screen_size() -> tuple[int, int]` for resolution
- **AND** MUST implement `close()` for resource cleanup

#### Scenario: ScreenBackend operates independently

- **WHEN** `ScreenBackend` methods are called
- **THEN** they SHALL NOT depend on `InputBackend` state
- **AND** `screen_size()` in `ScreenBackend` SHALL be an independent implementation (not forwarded from `InputBackend`)

### Requirement: ScreenBackend does not duplicate InputBackend responsibilities

The `ScreenBackend` SHALL focus on perception (capture, accessibility, window info). It SHALL NOT implement input simulation (mouse, keyboard) — those remain in `InputBackend`.

#### Scenario: ScreenBackend responsibilities

- **WHEN** designing the `ScreenBackend` interface
- **THEN** it SHALL NOT include methods for mouse movement, clicking, or keyboard input
- **AND** it MAY include methods for window management (list/focus) through compositor protocols

### Requirement: InputBackend retains screen state methods during transition

The existing `InputBackend.screen_size()` and `InputBackend.get_cursor_position()` SHALL remain in place during the spike phase. These methods are NOT removed or deprecated at this stage.

#### Scenario: Existing InputBackend methods unchanged

- **WHEN** the spike is implemented
- **THEN** `src/backends/base.py` is NOT modified
- **AND** `src/backends/uinput.py` is NOT modified
- **AND** existing P1 tests continue to pass

### Requirement: Spike prototype ScreenBackend implementation

The spike SHALL include a prototype `ScreenBackend` implementation using xdg-desktop-portal for screenshots.

#### Scenario: PortalScreenBackend exists as prototype

- **WHEN** the spike scripts are run
- **THEN** a `PortalScreenBackend` class exists in `spike/` directory (not in `src/backends/`)
- **AND** it implements `capture()` and `capture_base64()` via xdg-desktop-portal D-Bus API
- **AND** it implements `screen_size()` via KMS/sysfs (same method as P1)

#### Scenario: Spike code is separated from production code

- **WHEN** the spike is complete and results are documented
- **THEN** the prototype code lives in `spike/` directory only
- **AND** `src/` directory contains only the abstract `ScreenBackend` interface (if spike concludes it should be added)
- **AND** the decision to add `ScreenBackend` to `src/backends/` is deferred to P2 implementation
