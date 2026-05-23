## ADDED Requirements

### Requirement: uinput keyboard events produce correct character output
The spike SHALL verify that writing keyboard events to `/dev/uinput` causes typed characters to appear in the focused application on Wayland COSMIC.

#### Scenario: Single key produces correct character
- **WHEN** a Python script creates a UInput device with all key codes and writes `KEY_A` press then release
- **THEN** the character `a` MUST appear at the cursor in the focused text input

#### Scenario: Shift modifier produces uppercase character
- **WHEN** a script writes `KEY_LEFTSHIFT` down, then `KEY_A` down/up, then `KEY_LEFTSHIFT` up
- **THEN** the character `A` (uppercase) MUST appear at the cursor

### Requirement: Keyboard UInput device creation succeeds
The spike SHALL verify that a UInput device with full keyboard capability can be created.

#### Scenario: Full keyboard device creation
- **WHEN** a Python script creates a UInput device with `EV_KEY` containing all `ecodes.keys.keys()`
- **THEN** the device MUST be created without errors
