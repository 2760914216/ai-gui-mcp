## ADDED Requirements

### Requirement: Non-interactive screenshot method works on COSMIC
The spike SHALL verify that a screenshot can be captured on Wayland COSMIC programmatically without user-in-the-loop dialog authorization.

#### Scenario: Screenshot captured without interactive dialog
- **WHEN** a command calls `xdg-desktop-portal` Screenshot method with `interactive: false`
- **THEN** the command MUST either return image data or fail with an informative error — it MUST NOT pop up a dialog requiring user confirmation

#### Scenario: Alternative method identified if portal fails
- **WHEN** xdg-desktop-portal returns an error or requires interactive consent
- **THEN** the results document MUST note the portal behavior and identify whether a PipeWire-based alternative is feasible for investigation in Phase 2

### Requirement: Feasibility finding recorded for Phase 2
The spike SHALL produce a documented finding confirming or rejecting the feasibility of non-interactive screenshot capture for later implementation.

#### Scenario: Screenshot feasibility is documented
- **WHEN** the screenshot test completes (whether success or failure)
- **THEN** the SPIKE-RESULTS.md document MUST contain a clear statement: "Screenshot on COSMIC: [feasible via method X / not feasible — [reason]]", and this SHALL be the input for Phase 2 screenshot planning
