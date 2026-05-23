## ADDED Requirements

### Requirement: UInputBackend creates independent mouse and keyboard uinput devices
The system SHALL create two separate uinput virtual devices upon initialization: one for mouse (EV_REL + EV_KEY with BTN_LEFT/BTN_RIGHT/BTN_MIDDLE) and one for keyboard (EV_KEY with full key set), each with unique device names.

#### Scenario: Mouse device created
- **WHEN** `UInputBackend()` is initialized with `/dev/uinput` accessible
- **THEN** a uinput device with `EV_REL(REL_X, REL_Y)` and `EV_KEY(BTN_LEFT, BTN_RIGHT, BTN_MIDDLE)` is created

#### Scenario: Keyboard device created
- **WHEN** `UInputBackend()` is initialized
- **THEN** a uinput device with `EV_KEY` containing all key codes is created

#### Scenario: Permission denied
- **WHEN** `/dev/uinput` is not writable
- **THEN** `PermissionError` is raised with a message suggesting `sudo usermod -aG input $USER`

### Requirement: UInputBackend implements relative mouse movement with internal tracking
The system SHALL track cursor position internally using `_x`, `_y` variables, and SHALL implement `move_rel` by writing `EV_REL(REL_X/REL_Y)` events to the mouse uinput device, updating internal state.

#### Scenario: Move right by 100 pixels
- **WHEN** `move_rel(dx=100, dy=0)` is called starting from (0, 0)
- **THEN** `EV_REL(REL_X, 100)` is written, internal state becomes (100, 0)

#### Scenario: Move diagonally
- **WHEN** `move_rel(dx=-50, dy=30)` is called starting from (100, 0)
- **THEN** both REL_X and REL_Y events are written, internal state becomes (50, 30)

### Requirement: UInputBackend converts absolute moves to relative moves
The system SHALL implement `move_abs(x, y)` by computing `dx = x - self._x, dy = y - self._y` and calling `move_rel(dx, dy)`.

#### Scenario: Move from (0,0) to (500,300)
- **WHEN** `move_abs(x=500, y=300)` is called at position (0, 0)
- **THEN** `move_rel(dx=500, dy=300)` is invoked internally

#### Scenario: Move from (500,300) to (200,100)
- **WHEN** `move_abs(x=200, y=100)` is called at position (500, 300)
- **THEN** `move_rel(dx=-300, dy=-200)` is invoked internally

### Requirement: UInputBackend implements click operations
The system SHALL implement `click(x, y, button)` by moving to (x, y) then performing button press and release events with a short delay between them.

#### Scenario: Left click at coordinates
- **WHEN** `click(x=200, y=100, button="left")` is called
- **THEN** cursor moves to (200, 100), `BTN_LEFT` press then release events are written

### Requirement: UInputBackend implements right_click and dbl_click
The system SHALL implement `right_click` using `BTN_RIGHT` and `dbl_click` using two rapid `BTN_LEFT` press-release sequences.

#### Scenario: Right click
- **WHEN** `right_click(x=300, y=300)` is called
- **THEN** cursor moves to (300, 300), `BTN_RIGHT` press and release events are written

#### Scenario: Double click
- **WHEN** `dbl_click(x=300, y=300)` is called
- **THEN** cursor moves to (300, 300), two `BTN_LEFT` press-release sequences are written in rapid succession

### Requirement: UInputBackend implements button down/up
The system SHALL implement `mouse_down(button)` and `mouse_up(button)` as independent press and release events without moving the cursor.

#### Scenario: Mouse down without move
- **WHEN** `mouse_down(button="left")` is called at current position (500, 300)
- **THEN** a `BTN_LEFT` press event is written, cursor position unchanged

### Requirement: UInputBackend implements scroll
The system SHALL implement scroll using `EV_REL(REL_WHEEL)` for vertical and `EV_REL(REL_HWHEEL)` for horizontal scrolling.

#### Scenario: Scroll down
- **WHEN** `scroll(dy=-3)` is called
- **THEN** `EV_REL(REL_WHEEL, -3)` is written

#### Scenario: Scroll with horizontal
- **WHEN** `scroll(dy=2, dx=1)` is called
- **THEN** both `REL_WHEEL` and `REL_HWHEEL` events are written

### Requirement: UInputBackend implements drag
The system SHALL implement `drag(x1, y1, x2, y2)` by: move to (x1, y1), mouse down, move to (x2, y2), mouse up.

#### Scenario: Drag from top-left to bottom-right
- **WHEN** `drag(x1=100, y1=100, x2=400, y2=400)` is called
- **THEN** cursor moves to (100, 100), button down, cursor moves to (400, 400), button up

### Requirement: UInputBackend types text with Shift handling
The system SHALL implement `type_text(text)` by iterating through each character and sending the appropriate key events, using LEFTSHIFT for uppercase and special characters.

#### Scenario: Type lowercase "hello"
- **WHEN** `type_text("hello")` is called
- **THEN** individual KEY_H, KEY_E, KEY_L, KEY_L, KEY_O press-release sequences are written without SHIFT

#### Scenario: Type uppercase "Hello"
- **WHEN** `type_text("Hello")` is called
- **THEN** first character uses LEFTSHIFT+KEY_H, remaining use lowercase press-release sequences

#### Scenario: Handle special characters requiring Shift
- **WHEN** `type_text("!")` is called
- **THEN** LEFTSHIFT+KEY_1 press-release sequence is written

### Requirement: UInputBackend implements key combo
The system SHALL implement `press_combo(keys)` by pressing all modifier keys down in order, pressing and releasing the final key, then releasing all modifier keys in reverse order.

#### Scenario: Ctrl+S combo
- **WHEN** `press_combo(["ctrl", "s"])` is called
- **THEN** KEY_LEFTCTRL down, KEY_S down, KEY_S up, KEY_LEFTCTRL up sequence is written

#### Scenario: Ctrl+Shift+S combo
- **WHEN** `press_combo(["ctrl", "shift", "s"])` is called
- **THEN** LEFTCTRL down, LEFTSHIFT down, KEY_S down, KEY_S up, LEFTSHIFT up, LEFTCTRL up sequence is written

### Requirement: UInputBackend implements individual key down/up
The system SHALL implement `key_down(key)` and `key_up(key)` by writing the corresponding `EV_KEY` press/release event.

#### Scenario: Key down "a"
- **WHEN** `key_down("a")` is called
- **THEN** `EV_KEY(KEY_A, 1)` is written

### Requirement: UInputBackend detects screen resolution via KMS/sysfs
The system SHALL implement `screen_size()` by parsing `/sys/class/drm/` for connected outputs and reading their modes, returning the resolution of the first connected eDP output (falling back to any connected output).

#### Scenario: eDP connected at 2560x1600
- **WHEN** `/sys/class/drm/card1-eDP-2/status` contains "connected" and `/sys/class/drm/card1-eDP-2/modes` starts with "2560x1600"
- **THEN** `screen_size()` returns `(2560, 1600)`

#### Scenario: Resolution not detectable
- **WHEN** no connected DRM outputs are found via KMS/sysfs
- **THEN** `screen_size()` falls back to configured values from `config.yaml` (e.g., `screen.width: 1920, screen.height: 1080`)
