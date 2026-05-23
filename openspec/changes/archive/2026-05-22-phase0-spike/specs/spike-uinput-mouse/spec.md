## ADDED Requirements

### Requirement: uinput mouse events produce visible cursor movement
The spike SHALL verify that writing relative mouse events to `/dev/uinput` causes actual cursor movement visible on the Wayland COSMIC desktop.

#### Scenario: Mouse moves on relative X/Y write
- **WHEN** a Python script creates a UInput device with `EV_REL` capabilities and writes `REL_X=100, REL_Y=100`
- **THEN** the on-screen cursor MUST visibly move from its current position by approximately 100 pixels in both axes

#### Scenario: Mouse click reaches focused application
- **WHEN** a UInput device with `EV_KEY: BTN_LEFT` capability writes a button press then release event
- **THEN** the focused application MUST receive a left-click event at the current cursor position

### Requirement: uinput device creation succeeds with proper permissions
The spike SHALL verify that `/dev/uinput` is accessible for writing by the current user (in `input` group).

#### Scenario: Device node is writable
- **WHEN** the user runs `ls -la /dev/uinput`
- **THEN** the output MUST show group `input` with write permission (`rw`) for group members

#### Scenario: UInput device creation does not raise PermissionError
- **WHEN** a Python script calls `UInput(...)` with valid capability definitions
- **THEN** the UInput object MUST be created successfully without a `PermissionError` exception
