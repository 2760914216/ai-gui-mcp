## 1. New Data Models

- [ ] 1.1 Add `ScreenState` pydantic model to `src/models.py` — fields: width, height, cursor_x, cursor_y, cursor_source (Literal["tracked","detected"])
- [ ] 1.2 Add `SnapshotResult` pydantic model to `src/models.py` — fields: snapshot_id (str), created_at (str), screen (ScreenState), has_image (bool), image_format (str|None), note (str|None)
- [ ] 1.3 Add `AnalysisWarning` pydantic model to `src/models.py` — fields: code (controlled enum per spec), severity (Literal["low","medium","high"]), message (str)
- [ ] 1.4 Add `ScreenKind`, `LayoutRegion`, `ActiveDialogInfo`, `LayoutSummary` pydantic models to `src/models.py` — per spec `gui-parser-result`
- [ ] 1.5 Add `ParsedElement` pydantic model to `src/models.py` — fields: id, type (controlled enum 17 values), bbox [x,y,w,h], text, description, confidence, parent_id, children_ids, region_ref
- [ ] 1.6 Add `AnalysisResult` pydantic model to `src/models.py` — fields: snapshot_id, overall_quality, warnings, layout_summary, elements (NO source field)
- [ ] 1.7 Extend `ScreenAction.action` Literal from `["size","cursor","snapshot"]` to `["size","cursor","snapshot","analyze","image"]`
- [ ] 1.8 Run pydantic model unit tests: valid/invalid data, enum constraints, model_dump_json — verify all models pass validation

## 2. Observation Store

- [ ] 2.1 Create `src/stores/__init__.py`
- [ ] 2.2 Create `src/stores/observation.py` with `ObservationStore` class — dict-based storage keyed by snapshot_id
- [ ] 2.3 Implement `create(image_bytes, metadata) -> snapshot_id` — generates `snap_{uuid_short}`, stores ObservationRecord
- [ ] 2.4 Implement `get(snapshot_id) -> ObservationRecord | None`
- [ ] 2.5 Implement `put_analysis(snapshot_id, AnalysisResult)` and `get_analysis(snapshot_id) -> AnalysisResult | None`
- [ ] 2.6 Implement triple eviction policy: max_count (default 16) + TTL (default 300s) + memory_budget (default 256MB)
- [ ] 2.7 Implement eviction hook: when snapshot evicted, evict associated cached analysis
- [ ] 2.8 Add unit tests: create/get, analysis cache hit/miss, count eviction, TTL eviction, memory budget eviction, analysis co-eviction

## 3. Perception Service (Skeleton)

- [ ] 3.1 Create `src/services/__init__.py`
- [ ] 3.2 Create `src/services/perception.py` with `PerceptionService` class
- [ ] 3.3 Implement `__init__(input_backend, screen_backend, observation_store)` — store references, wrap `screen_backend` as internal ScreenshotProvider
- [ ] 3.4 Implement `snapshot() -> SnapshotResult` — calls `screen_backend.capture()`, creates ObservationRecord in store, returns SnapshotResult (no base64 image in output)
- [ ] 3.5 Implement `image(snapshot_id) -> dict` — retrieves raw image from store, returns `{snapshot_id, mime_type, image_base64}`
- [ ] 3.6 Implement `analyze(snapshot_id=None) -> AnalysisResult` — if no snapshot_id, first call snapshot() internally; if cached analysis exists, return it; else return placeholder AnalysisResult with `overall_quality="low"` and `image_unavailable` warning (VisionProvider stub until P3A-4)
- [ ] 3.7 Handle capture failure: `snapshot()` still returns a SnapshotResult with `has_image=false` and descriptive note
- [ ] 3.8 Handle image retrieval failure: `image()` raises error for unknown/expired snapshot_id
- [ ] 3.9 Add unit tests: perception_service.snapshot() returns handle, image() returns raw, analyze() caches and returns, capture failure still produces handle, unknown snapshot_id raises error

## 4. Server Integration

- [ ] 4.1 In `src/server.py` `main()`: initialize `ObservationStore`, `PerceptionService` (with existing `InputBackend` and `ScreenBackend`)
- [ ] 4.2 Store `PerceptionService` as module-level `_perception_service` with setter/getter (same pattern as `_backend`/`_screen_backend`)
- [ ] 4.3 Refactor `_handle_screen_snapshot()`: delegate to `PerceptionService.snapshot()`, serialize SnapshotResult to JSON — remove direct `screen_backend.capture()` calls
- [ ] 4.4 Add `_handle_screen_analyze(snapshot_id=None)`: delegate to `PerceptionService.analyze()`, serialize AnalysisResult to JSON
- [ ] 4.5 Add `_handle_screen_image(snapshot_id)`: delegate to `PerceptionService.image()`, serialize image payload to JSON
- [ ] 4.6 Update `_handle_screen()` routing: add `analyze` and `image` branches alongside existing `size`/`cursor`/`snapshot`
- [ ] 4.7 Update `list_tools()` screen tool inputSchema: action enum to `["size","cursor","snapshot","analyze","image"]`, add optional `snapshot_id` parameter for `analyze`, required `snapshot_id` for `image`
- [ ] 4.8 Remove `_build_error_snapshot()` — error handling moves to PerceptionService
- [ ] 4.9 Add integration tests: server screen(size/cursor) unchanged, snapshot returns handle (no screenshot field), image returns base64 payload, analyze returns analysis result structure, batch with new screen actions

## 5. Provider Abstraction (Screenshot + Accessibility)

- [ ] 5.1 Create `src/providers/__init__.py`
- [ ] 5.2 Create `src/providers/screenshot.py` with `ScreenshotProvider(ABC)` — abstract methods: `capture() -> RawImage`, `screen_size() -> tuple[int,int]`
- [ ] 5.3 Create adapter class `PortalScreenshotProvider(ScreenshotProvider)` wrapping existing `XdgPortalBackend` — delegates capture and screen_size
- [ ] 5.4 Create `src/providers/a11y.py` with `AccessibilityProvider(ABC)` — abstract methods: `is_available() -> bool`, `get_tree(max_depth, max_nodes) -> A11yTree`
- [ ] 5.5 Create `NullAccessibilityProvider(AccessibilityProvider)` — `is_available()` always returns False, `get_tree()` returns empty tree
- [ ] 5.6 Update `PerceptionService.__init__()` to accept `ScreenshotProvider` and `AccessibilityProvider` (default to `NullAccessibilityProvider`) instead of raw `ScreenBackend`
- [ ] 5.7 Update `PerceptionService.snapshot()` to use `ScreenshotProvider.capture()` instead of `ScreenBackend.capture()`
- [ ] 5.8 Update `src/server.py` `main()`: instantiate `PortalScreenshotProvider` (wrapping existing `XdgPortalBackend`), pass to `PerceptionService`
- [ ] 5.9 Add unit tests: PortalScreenshotProvider delegates correctly, NullAccessibilityProvider always returns empty, PerceptionService accepts providers, provider injection paths work

## 6. Vision Provider (Stub + Spike Prep)

- [ ] 6.1 Create `src/providers/vision.py` with `VisionProvider(ABC)` — abstract method: `parse(image: RawImage, a11y_hints: A11yTree | None) -> AnalysisResult`
- [ ] 6.2 Create `DummyVisionProvider(VisionProvider)` stub — returns `AnalysisResult` with `overall_quality="low"`, empty elements, `image_unavailable` warning (used before real model integration)
- [ ] 6.3 Wire `VisionProvider` into `PerceptionService.__init__()` (optional, defaults to `DummyVisionProvider`)
- [ ] 6.4 Update `PerceptionService.analyze()` to call `VisionProvider.parse()` instead of returning placeholder directly
- [ ] 6.5 Create P3A Spike acceptance test set: 10-15 COSMIC screenshots covering IDE, browser, settings, file manager, dialog scenarios
- [ ] 6.6 Document P3A Spike plan in `docs/PHASE3A-SPIKE.md`: candidate models (OmniParser v2, UI-TARS, cloud VLM), evaluation metrics (element recall/precision, region classification accuracy, latency ceiling), go/no-go criteria per spec `gui-parser-result`

## 7. Configuration

- [ ] 7.1 Add `perception.service` section to `config.yaml`: `snapshot_max_count: 16`, `snapshot_ttl_sec: 300`, `snapshot_memory_budget_mb: 256`
- [ ] 7.2 Add `perception.providers` section to `config.yaml`: `screenshot.backend: "xdg-desktop-portal"`, `accessibility.enabled: true`, `vision.backend: "dummy"` (stub until Spike)
- [ ] 7.3 Update `src/server.py` `main()` to read perception config and pass to ObservationStore / PerceptionService initialization
- [ ] 7.4 Verify config defaults work when `config.yaml` has no `perception.service` section (all three eviction limits use hardcoded defaults)

## 8. Test Suite & Regression

- [ ] 8.1 Run existing P1 test suite (`pytest src/tests/test_mouse.py src/tests/test_keyboard.py -v`) — all must pass with zero regressions
- [ ] 8.2 Run existing P2 perception tests (`pytest src/tests/test_perception.py -v`) — all must pass; ScreenSnapshot model tests remain valid (internal model unchanged)
- [ ] 8.3 Run existing batch tests (`pytest src/tests/test_batch.py -v`) — all must pass; batch with screen actions unchanged
- [ ] 8.4 Add `src/tests/test_models_p3a.py` — unit tests for ScreenState, SnapshotResult, AnalysisResult, ParsedElement, AnalysisWarning model validation
- [ ] 8.5 Add `src/tests/test_observation_store.py` — unit tests for ObservationStore: create/get/put_analysis/get_analysis, all three eviction policies
- [ ] 8.6 Add `src/tests/test_perception_service.py` — unit tests for PerceptionService: snapshot returns handle, image returns raw, analyze caches, capture failure still produces handle
- [ ] 8.7 Add `src/tests/test_providers.py` — unit tests for PortalScreenshotProvider, NullAccessibilityProvider, DummyVisionProvider
- [ ] 8.8 Run full test suite (`pytest src/tests/ -v`) — zero failures, zero regressions
- [ ] 8.9 Run `lsp_diagnostics` on `src/models.py`, `src/server.py`, `src/services/perception.py`, `src/stores/observation.py`, `src/providers/*` — zero errors

## 9. Documentation

- [ ] 9.1 Update `docs/ROADMAP.md` — mark Phase 3A (Intelligence Layer) as in-progress, link to change artifacts
- [ ] 9.2 Update `AGENTS.md` — add P3A change path and relevant docs
- [ ] 9.3 Update `docs/FUTURE-REFERENCE.md` — move P3A open questions from "pending" to "decided" where resolved by this change
- [ ] 9.4 Create `docs/PHASE3A-SPIKE.md` — spike plan per task 6.6 (if not already created there)
- [ ] 9.5 Archive this change after all tasks complete and verification passes
