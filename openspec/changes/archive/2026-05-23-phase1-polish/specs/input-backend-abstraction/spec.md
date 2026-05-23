## ADDED Requirements

### Requirement: InputBackend defines cursor position query interface
The system SHALL provide an abstract method `get_cursor_position()` that returns the tracked cursor position as a tuple of `(x: int, y: int)` in pixels.

#### Scenario: get_cursor_position is abstract
- **WHEN** a subclass does not implement `get_cursor_position()`
- **THEN** instantiation raises `TypeError`

#### Scenario: get_cursor_position returns tuple
- **WHEN** `get_cursor_position()` is called
- **THEN** the return type is `tuple[int, int]`

## MODIFIED Requirements

### Requirement: InputBackend defines abstract interface for mouse operations
The system SHALL provide an abstract base class `InputBackend` with abstract methods for all mouse operations including: move absolute, move relative, click, double-click, right-click, mouse button down, mouse button up, scroll, and drag (using start and end coordinates).

#### Scenario: All mouse methods are abstract
- **WHEN** a subclass of `InputBackend` is created without implementing all mouse methods
- **THEN** Python raises `TypeError` at instantiation time

#### Scenario: move_abs signature
- **WHEN** `move_abs(x: int, y: int)` is called
- **THEN** the method signature accepts two integer coordinates

#### Scenario: click signature with default button
- **WHEN** `click(x: int, y: int, button: str = "left")` is called
- **THEN** the button parameter defaults to "left"

#### Scenario: drag signature with start and end coordinates
- **WHEN** `drag(x1: int, y1: int, x2: int, y2: int)` is called
- **THEN** the method accepts start coordinate (x1, y1) and end coordinate (x2, y2)
