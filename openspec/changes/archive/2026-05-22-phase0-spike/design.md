## Context

The AI GUI MCP project aims to give AI assistants GUI perception and manipulation capabilities via MCP tools on Linux Wayland (COSMIC). Phase 1 will implement uinput-based mouse/keyboard simulation via an MCP server. Before writing production code, Phase 0 validates that each subsystem actually works on the target hardware.

**Current state**: No code exists. Only architecture docs (ROADMAP, PHASE0-SPIKE, PHASE1-IMPLEMENTATION) exist as planning artifacts.

**Constraints**:
- Single machine (Linux Wayland COSMIC desktop), no CI or automation requirements
- `/dev/uinput` requires `input` group membership
- Wayland prohibits reading global cursor position — all positioning relies on internal coordinate tracking
- Screenshot methods must work non-interactively (no user-in-the-loop dialog)

## Goals / Non-Goals

**Goals:**
- Confirm or reject each Phase 1 technical assumption with measured evidence
- Identify environment-specific issues (permissions, compositor quirks) before they block development
- Quantify AT-SPI2 coverage on real COSMIC applications to right-size Phase 2 planning
- Produce a go/no-go conclusion document that feeds directly into PHASE1-IMPLEMENTATION.md Step 0

**Non-Goals:**
- Writing reusable/production code — spike scripts are throwaway
- Cross-platform testing — COSMIC only
- Building any MCP server functionality
- Making visual or intelligent decisions — pure technical verification

## Decisions

### Decision 1: Script-based spike, not interactive exploration

Each test is a self-contained script (Python or bash one-liner) that can be copied, pasted, and run. This avoids "do this in a Python REPL" ambiguity and ensures each result is reproducible.

**Alternatives considered**: Interactive REPL exploration. Rejected because results must be recorded and tests should be re-runnable if environment changes.

### Decision 2: Write-once conclusion document as primary deliverable

Results are recorded in a single `SPIKE-RESULTS.md` markdown file with a structured table format. This is the artifact that determines whether Phase 1 proceeds.

**Format**: Each of the 6 tests gets a row with Test ID, Status (✅/⚠️/❌), and Notes.

### Decision 3: Test 0.5 (AT-SPI2 coverage) and 0.6 (screenshot) are advisory, not blocking

AT-SPI2 coverage and screenshot feasibility inform Phase 2 planning but do not block Phase 1 implementation. Only tests 0.1-0.4 (uinput, keyboard, resolution, tracking) are hard gates for P1.

**Rationale**: P1 does not use AT-SPI2 or screenshots. Discovering issues now is valuable for P2 planning but shouldn't halt P1.

### Decision 4: Resolution detection uses multi-method fallback

Test 0.3 tries 4 methods in priority order: wlr-randr → COSMIC DBus → KMS/sysfs → manual config. First available method wins. If all fail, P1 can proceed with a manual `config.yaml` entry.

**Alternatives considered**: Requiring one specific method. Rejected because COSMIC compositor APIs may change.

### Decision 5: Tests run in dependency order, blocking on environment prep first

Environment setup (`sudo usermod -aG input $USER` + re-login) must complete before any uinput tests (0.1-0.4). Tests 0.5 and 0.6 can run in parallel with each other but after their pip dependencies are installed.

**Execution order**: `env prep` → `0.1 (uinput mouse)` → `0.2 (keyboard)` → `0.3 (resolution) & 0.4 (tracking)` → `0.5 (AT-SPI2) & 0.6 (screenshot)`.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| `/dev/uinput` inaccessible even with group membership due to udev rules or Wayland security policy | Test first with `ls -la /dev/uinput` before installing dependencies |
| COSMIC compositor applies pointer acceleration that skews coordinate tracking beyond usable threshold | Test 0.4 measures cumulative error; if >50px offset, document as ⚠️ and evaluate calibration strategies in P1 |
| AT-SPI2 provides near-zero coverage on COSMIC-native applications | Results inform P2 strategy — if coverage is very low, P2 must emphasize visual recognition over accessibility tree |
| Screenshot portal requires interactive user consent on COSMIC | Test 0.6 explicitly passes `interactive: false`; if rejected, document and explore PipeWire-based alternatives in P2 |
| Python-evdev version incompatibility with current kernel | Check `evdev` version compatibility before installing |

## Open Questions

- Will COSMIC's compositor expose DBus interfaces for output info in stable releases? (determined by test 0.3)
- Does Edge on Linux expose its UI through AT-SPI2? (determined by test 0.5)
- Is `dasbus` sufficient for AT-SPI2 enumeration, or will we need the heavier `pyatspi2` with GObject dependencies? (determined by test 0.5)
