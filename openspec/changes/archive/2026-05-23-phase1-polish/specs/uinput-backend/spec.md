## ADDED Requirements

### Requirement: UInputBackend exposes tracked cursor position
The system SHALL provide a `get_cursor_position()` method that returns the internally tracked cursor position as `(x: int, y: int)`.

#### Scenario: Query cursor position after initialization
- **WHEN** `get_cursor_position()` is called immediately after `UInputBackend` initialization
- **THEN** returns `(0, 0)` (initial tracking position)

#### Scenario: Query cursor position after move
- **WHEN** `move_abs(500, 300)` is called followed by `get_cursor_position()`
- **THEN** returns `(500, 300)`

### Requirement: UInputBackend warns on startup when cursor position is unknown
The system SHALL log a warning to stderr during initialization indicating that the cursor position is unknown and tracking assumes (0, 0).

#### Scenario: Normal startup
- **WHEN** `UInputBackend()` is initialized successfully
- **THEN** a message `[ai-gui-mcp] cursor position unknown, tracking assumes (0,0)` is printed to stderr

## MODIFIED Requirements

### Requirement: UInputBackend implements drag
The system SHALL implement `drag(x1, y1, x2, y2)` by: move to (x1, y1), mouse down, move to (x2, y2), mouse up.

#### Scenario: Drag from top-left to bottom-right
- **WHEN** `drag(x1=100, y1=100, x2=400, y2=400)` is called
- **THEN** cursor moves to (100, 100), button down, cursor moves to (400, 400), button up
