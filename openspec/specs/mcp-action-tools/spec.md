## ADDED Requirements

### Requirement: MCP Server registers four tool definitions
The system SHALL register exactly four MCP tools: `mouse`, `keyboard`, `screen`, and `batch`, each with a typed `action` parameter that discriminates the operation.

#### Scenario: tool/list returns all four tools
- **WHEN** MCP client requests `tool/list`
- **THEN** the response contains `mouse`, `keyboard`, `screen`, and `batch` tool definitions

### Requirement: mouse tool routes actions to InputBackend
The `mouse` tool SHALL accept an `action` parameter (`move`, `move_rel`, `click`, `dbl_click`, `right_click`, `down`, `up`, `scroll`, `drag`) and route to the corresponding `InputBackend` method. For `click`, `dbl_click`, and `right_click`, the `x` and `y` parameters are optional (defaulting to current cursor position). For `drag`, `x1`, `y1`, `x2`, `y2` parameters specify start and end coordinates.

#### Scenario: mouse move action
- **WHEN** `mouse(action="move", x=500, y=300)` is called
- **THEN** `backend.move_abs(500, 300)` is invoked

#### Scenario: mouse click action with default button
- **WHEN** `mouse(action="click", x=200, y=100)` is called without button parameter
- **THEN** `backend.click(200, 100, button="left")` is invoked

#### Scenario: mouse click at current position
- **WHEN** `mouse(action="click")` is called without x,y parameters and the cursor is at (150, 200)
- **THEN** `backend.click(150, 200, button="left")` is invoked using the current cursor position

#### Scenario: mouse drag action
- **WHEN** `mouse(action="drag", x1=100, y1=100, x2=400, y2=400)` is called
- **THEN** `backend.drag(100, 100, 400, 400)` is invoked

#### Scenario: mouse scroll action
- **WHEN** `mouse(action="scroll", dy=-2)` is called
- **THEN** `backend.scroll(dy=-2, dx=0)` is invoked

#### Scenario: mouse right_click at current position
- **WHEN** `mouse(action="right_click")` is called without x,y parameters and the cursor is at (300, 400)
- **THEN** `backend.right_click(300, 400)` is invoked using the current cursor position

### Requirement: keyboard tool routes actions to InputBackend
The `keyboard` tool SHALL accept an `action` parameter (`type`, `press`, `down`, `up`) and route to the corresponding `InputBackend` method.

#### Scenario: keyboard type action
- **WHEN** `keyboard(action="type", text="hello")` is called
- **THEN** `backend.type_text("hello")` is invoked

#### Scenario: keyboard press action
- **WHEN** `keyboard(action="press", keys=["ctrl", "s"])` is called
- **THEN** `backend.press_combo(["ctrl", "s"])` is invoked

#### Scenario: keyboard down action
- **WHEN** `keyboard(action="down", key="shift")` is called
- **THEN** `backend.key_down("shift")` is invoked

### Requirement: screen tool returns screen size and cursor position
The `screen` tool SHALL accept `action="size"` and `action="cursor"`. `action="size"` returns `{"width": int, "height": int}` from `InputBackend.screen_size()`. `action="cursor"` returns `{"x": int, "y": int}` from `InputBackend.get_cursor_position()`.

#### Scenario: screen size action
- **WHEN** `screen(action="size")` is called on a 2560x1600 display
- **THEN** the response is `{"width": 2560, "height": 1600}`

#### Scenario: screen cursor action
- **WHEN** `screen(action="cursor")` is called and the tracked position is (500, 300)
- **THEN** the response is `{"x": 500, "y": 300}`

### Requirement: Coordinate clamping rejects out-of-bounds values
The MCP Server handler SHALL reject mouse actions with coordinates outside the screen boundaries (0 ≤ x < width, 0 ≤ y < height) by returning an error response, without calling the backend.

#### Scenario: X coordinate negative
- **WHEN** `mouse(action="move", x=-10, y=100)` is called
- **THEN** an error response is returned, `backend.move_abs` is NOT called

#### Scenario: Y coordinate exceeds height
- **WHEN** `mouse(action="click", x=100, y=2000)` is called on a 1600px screen
- **THEN** an error response is returned, `backend.click` is NOT called

### Requirement: Server validates input via pydantic models
The MCP Server SHALL use pydantic models (`MouseAction`, `KeyboardAction`, `ScreenAction`, `BatchAction`) to validate tool inputs before routing to the backend, returning validation errors for invalid `action` values.

#### Scenario: Invalid mouse action value
- **WHEN** `mouse(action="invalid_action", x=0, y=0)` is called
- **THEN** a pydantic validation error is returned

#### Scenario: Missing required parameter
- **WHEN** `keyboard(action="type")` is called without `text` parameter
- **THEN** a validation error is returned because `text` is required

### Requirement: Server configuration is loaded from YAML
The MCP Server SHALL load its configuration from `config.yaml` including: server name, transport mode, input backend selection, uinput device names, and screen resolution fallback values. At startup, the server SHALL log the detected resolution to stderr and emit a warning if the detected resolution differs from the configured fallback.

#### Scenario: config.yaml specifies uinput backend
- **WHEN** `config.yaml` contains `input.backend: "uinput"`
- **THEN** the server instantiates `UInputBackend`

#### Scenario: config.yaml specifies screen fallback dimensions
- **WHEN** KMS/sysfs resolution detection fails and `config.yaml` contains `screen.width: 1920` and `screen.height: 1080`
- **THEN** `screen_size()` returns `(1920, 1080)`

#### Scenario: Startup logs detected resolution
- **WHEN** the server starts and resolution detection succeeds at 2560x1600
- **THEN** a message like `[ai-gui-mcp] detected resolution: 2560x1600` is written to stderr

#### Scenario: Startup warns on resolution mismatch
- **WHEN** the server starts with detected resolution 2560x1600 but `config.yaml` specifies `screen.width: 1920, screen.height: 1080`
- **THEN** a warning message like `[ai-gui-mcp] WARNING: detected resolution 2560x1600 differs from config 1920x1080` is written to stderr
