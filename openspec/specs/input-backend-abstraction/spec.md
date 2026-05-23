## ADDED Requirements

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
- **WHEN** `drag(x1: int, y1: int, x2: int, y2: int, button: str = "left")` is called
- **THEN** the method signature accepts start and end coordinates with a default button of "left"

### Requirement: InputBackend defines abstract interface for keyboard operations
The system SHALL provide abstract methods for all keyboard operations including: type text, press key combo, key down, and key up.

#### Scenario: type_text signature
- **WHEN** `type_text(text: str)` is called
- **THEN** the method accepts a single string parameter

#### Scenario: press_combo accepts list of keys
- **WHEN** `press_combo(keys: list[str])` is called with `["ctrl", "s"]`
- **THEN** the method accepts a list of key strings

### Requirement: InputBackend defines screen query interface
The system SHALL provide an abstract method `screen_size()` that returns a tuple of (width, height) in pixels.

#### Scenario: screen_size returns tuple
- **WHEN** `screen_size()` is called
- **THEN** the return type is `tuple[int, int]`

### Requirement: InputBackend defines cursor position query interface
The system SHALL provide an abstract method `get_cursor_position()` that returns a tuple of (x, y) in pixels representing the internally tracked cursor position.

#### Scenario: subclass must implement get_cursor_position
- **WHEN** a subclass does not implement `get_cursor_position()`
- **THEN** instantiation raises `TypeError`

#### Scenario: get_cursor_position returns tuple
- **WHEN** `get_cursor_position()` is called
- **THEN** the return type is `tuple[int, int]`

### Requirement: InputBackend defines lifecycle method
The system SHALL provide an abstract `close()` method for resource cleanup.

#### Scenario: close is abstract
- **WHEN** a subclass does not implement `close()`
- **THEN** instantiation raises `TypeError`
