## ADDED Requirements

### Requirement: Cumulative coordinate tracking error is measurable
The spike SHALL verify that accumulating uinput relative move operations over multiple round-trips produces a measurable total position error.

#### Scenario: 20-step round-trip produces measurable offset
- **WHEN** a script writes 20 × `REL_X=+100` moves then 20 × `REL_X=-100` moves with small delays
- **THEN** the on-screen cursor position after the round-trip MUST be visually compared to the starting position, and the offset in pixels MUST be estimated

### Requirement: Tracking error classification informs P1 strategy
The spike SHALL classify the cumulative error into one of three tiers to determine whether internal coordinate tracking is viable for Phase 1.

#### Scenario: Error within acceptable range (≤20px)
- **WHEN** the measured round-trip offset is ≤ 20 pixels
- **THEN** the result MUST be marked ✅ and internal coordinate tracking SHALL proceed without calibration

#### Scenario: Error within warning range (21-50px)
- **WHEN** the measured round-trip offset is between 21 and 50 pixels
- **THEN** the result MUST be marked ⚠️ and Phase 1 SHALL incorporate periodic cursor recalibration (e.g., move to known screen corner)

#### Scenario: Error exceeds usable range (>50px)
- **WHEN** the measured round-trip offset is > 50 pixels
- **THEN** the result MUST be marked ❌ and the team SHALL evaluate alternative positioning strategies before Phase 1 implementation
