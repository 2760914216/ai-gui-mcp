## Why

Phase 1 implementation (action-layer MCP server) depends on assumptions about the Linux Wayland (COSMIC) environment — that `/dev/uinput` is accessible, that keyboard/ mouse events are correctly received by applications, that screen resolution can be detected, and that coordinate tracking is accurate enough for relative positioning. These assumptions must be proven, not assumed. Running 6 spike tests on the actual target hardware eliminates the risk of building on a broken foundation.

## What Changes

- Six technical verification scripts (Python/bash) that test each subsystem independently
- A structured conclusion document recording pass/fail results for each test
- Discovery of any environment-specific issues (permissions, compositor behavior) before they become development blockers
- Go/no-go decision for each Phase 1 technical dependency based on measured results

## Capabilities

### New Capabilities
- `spike-uinput-mouse`: Verify that uinput relative mouse events are received by COSMIC applications and produce actual cursor movement.
- `spike-uinput-keyboard`: Verify that uinput keyboard events (single keys and combos like Shift+A) are received by COSMIC applications and produce correct text output.
- `spike-resolution-detection`: Verify that screen resolution can be obtained non-interactively on Wayland COSMIC, identifying the most robust method among wlr-randr, DBus, KMS, or manual config fallback.
- `spike-coordinate-tracking`: Verify that internal coordinate tracking via uinput relative move accumulation stays within acceptable error bounds (no compositor acceleration skew beyond usable range).
- `spike-atspi2-coverage`: Scan 5-10 real applications on the target system to measure AT-SPI2 accessibility tree availability, informing how much Phase 2 perception work must fall back to visual-only approaches.
- `spike-screenshot-feasibility`: Confirm a non-interactive screenshot method works on COSMIC (xdg-desktop-portal or PipeWire), avoiding surprises when Phase 2 needs this capability.

### Modified Capabilities
None — this is the first work on the project.

## Impact

- **No production code affected** — this is a standalone spike producing conclusion documentation
- **Phase 1 technical decisions** will be confirmed or revised based on results
- **Dependencies**: `evdev`, `dasbus` (pip-installable, exploration-only)
- **System access**: `/dev/uinput` group permissions required for tests 0.1-0.4
- **Platform**: Single-machine (current Linux Wayland COSMIC desktop), no cross-platform scope
