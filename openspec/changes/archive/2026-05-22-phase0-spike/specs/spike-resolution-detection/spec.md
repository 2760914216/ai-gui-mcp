## ADDED Requirements

### Requirement: Screen resolution is obtainable without interactive user action
The spike SHALL verify that screen dimensions (width × height in pixels) can be retrieved programmatically on Wayland COSMIC without requiring user-in-the-loop dialog authorization.

#### Scenario: At least one detection method succeeds
- **WHEN** the spike tests wlr-randr, COSMIC DBus, KMS sysfs, and manual config methods in priority order
- **THEN** at least one method MUST return valid integer width and height values without interactive prompts

#### Scenario: Returned resolution matches visual expectation
- **WHEN** a resolution value is obtained
- **THEN** the width and height MUST be within the expected range for the connected display (e.g., 1366-3840 × 768-2160)

### Requirement: Failed methods log reason for failure
The spike SHALL document why each detection method failed, to inform future maintainability.

#### Scenario: Each method reports success or failure reason
- **WHEN** the spike completes resolution detection
- **THEN** the results document MUST include one line per method attempted, stating the method name, whether it succeeded, and the error or output for failed methods
