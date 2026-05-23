## ADDED Requirements

### Requirement: screen tool supports cursor position query
The `screen` tool SHALL accept `action="cursor"` and return `{"x": int, "y": int}` from `InputBackend.get_cursor_position()`, representing the internally tracked cursor position.

#### Scenario: cursor position query
- **WHEN** `screen(action="cursor")` is called and internal tracking is at (500, 300)
- **THEN** the response is `{"x": 500, "y": 300}`

#### Scenario: cursor position after move
- **WHEN** `mouse(action="move", x=800, y=600)` is called followed by `screen(action="cursor")`
- **THEN** the response is `{"x": 800, "y": 600}`

## MODIFIED Requirements

### Requirement: mouse tool routes actions to InputBackend
The `mouse` tool SHALL accept an `action` parameter (`move`, `move_rel`, `click`, `dbl_click`, `right_click`, `down`, `up`, `scroll`, `drag`) and route to the corresponding `InputBackend` method, passing coordinate and button parameters. For `click`, `dbl_click`, and `right_click` actions, the `x` and `y` parameters SHALL be optional — when absent, the action is performed at the current cursor position without moving.

#### Scenario: mouse move action
- **WHEN** `mouse(action="move", x=500, y=300)` is called
- **THEN** `backend.move_abs(500, 300)` is invoked

#### Scenario: mouse click action with coordinates
- **WHEN** `mouse(action="click", x=200, y=100)` is called without button parameter
- **THEN** `backend.click(200, 100, button="left")` is invoked

#### Scenario: mouse click action without coordinates
- **WHEN** `mouse(action="click")` is called without x and y parameters
- **THEN** `backend.mouse_down("left")` then `backend.mouse_up("left")` are invoked at current position

#### Scenario: mouse double-click without coordinates
- **WHEN** `mouse(action="dbl_click")` is called without x and y parameters
- **THEN** two press-release sequences are performed at current position without moving

#### Scenario: mouse right-click without coordinates
- **WHEN** `mouse(action="right_click")` is called without x and y parameters
- **THEN** right button press-release is performed at current position without moving

#### Scenario: mouse scroll action
- **WHEN** `mouse(action="scroll", dy=-2)` is called
- **THEN** `backend.scroll(dy=-2, dx=0)` is invoked

#### Scenario: mouse drag action with (x1,y1,x2,y2) parameters
- **WHEN** `mouse(action="drag", x1=100, y1=100, x2=400, y2=400)` is called
- **THEN** `backend.drag(100, 100, 400, 400)` is invoked

### Requirement: screen tool returns screen size
The `screen` tool SHALL accept `action="size"` and return `{"width": int, "height": int}` from `InputBackend.screen_size()`.

#### Scenario: screen size action
- **WHEN** `screen(action="size")` is called on a 2560x1600 display
- **THEN** the response is `{"width": 2560, "height": 1600}`

### Requirement: Server configuration is loaded from YAML
The MCP Server SHALL load its configuration from `config.yaml` including: server name, transport mode, input backend selection, uinput device names, and screen resolution fallback values. On startup, the server SHALL log the detected screen resolution to stderr and, if the configured resolution differs, SHALL log a warning indicating both values and which is in use.

#### Scenario: config.yaml specifies uinput backend
- **WHEN** `config.yaml` contains `input.backend: "uinput"`
- **THEN** the server instantiates `UInputBackend`

#### Scenario: config.yaml specifies screen fallback dimensions
- **WHEN** KMS/sysfs resolution detection fails and `config.yaml` contains `screen.width: 1920` and `screen.height: 1080`
- **THEN** `screen_size()` returns `(1920, 1080)`

#### Scenario: detected resolution differs from config
- **WHEN** KMS detects 2560x1600 but config.yaml specifies 1920x1080
- **THEN** server logs to stderr: `[ai-gui-mcp] screen: 2560x1600 (detected from KMS), config: 1920x1080 — using detected`
