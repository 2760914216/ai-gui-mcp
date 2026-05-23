## 1. Data Models

- [x] 1.1 Add `ScreenInfo`, `CursorInfo`, `UIElement`, `ScreenSnapshot` pydantic models to `src/models.py` — define fields per spec `screen-perception-models`
- [x] 1.2 Add `"snapshot"` to `ScreenAction.action` Literal enum (if not already present)

## 2. ScreenBackend Abstract Interface

- [x] 2.1 Create `src/backends/screen.py` with `ScreenBackend(ABC)` class — define `capture() -> ScreenSnapshot`, `screen_size() -> tuple[int,int]`, `close()` as abstract methods
- [x] 2.2 Export `ScreenBackend` from `src/backends/__init__.py`

## 3. XdgPortalBackend Implementation

- [x] 3.1 Create `src/backends/portal.py` with `XdgPortalBackend(ScreenBackend)` class skeleton — `__init__`, `screen_size()`, `close()`
- [x] 3.2 Implement `capture()` method using dbus-python + GLib.MainLoop thread bridge pattern — call `org.freedesktop.portal.Screenshot` with `interactive=false`, subscribe to `Response` signal, wait ≤10s, read PNG from returned `file://` URI
- [x] 3.3 Inside `capture()`: convert PNG bytes to base64, build and return a `ScreenSnapshot` with `source="screenshot"`, `elements=[]`, `cursor={source: "tracked"}`
- [x] 3.4 Graceful error handling: timeout → raise with descriptive message; portal unavailable → raise with `"xdg-desktop-portal not available"`; dbus-python not installed → raise with install hint
- [x] 3.5 Implement `screen_size()` via KMS/sysfs (same approach as `UInputBackend`)

## 4. Server Integration

- [x] 4.1 In `server.py` `_create_backend()`: add `ScreenBackend` initialization alongside `InputBackend`, defaulting to `XdgPortalBackend`
- [x] 4.2 Refactor `_handle_screen_snapshot(backend)` to accept `ScreenBackend`, call `backend.capture()`, serialize `ScreenSnapshot` model to JSON — remove `from spike.p2_screenshot_dbus_python import capture_screenshot`
- [x] 4.3 Update `_handle_screen()` routing: for `action="snapshot"`, pass `ScreenBackend` (not `InputBackend`) to `_handle_screen_snapshot()`
- [x] 4.4 Update `list_tools()` screen tool description to mention `snapshot` action

## 5. Cleanup

- [x] 5.1 Remove entire `spike/` directory (verification scripts) — spike results are already documented in `docs/PHASE2-SPIKE-RESULTS.md`
- [x] 5.2 Remove any `spike`-related entries from `pyproject.toml` optional-dependencies if present
- [x] 5.3 Update `config.yaml`: add `perception.screenshot` section with `method: xdg-desktop-portal` and `timeout_ms: 10000`

## 6. Verification

- [x] 6.1 Run existing P1 test suite (`pytest src/tests/ -v`) — all 51 tests must pass with zero regressions
- [x] 6.2 Add unit test for `ScreenSnapshot` model validation (valid/invalid data)
- [x] 6.3 Add unit test for `XdgPortalBackend.screen_size()` (mock KMS path read)
- [x] 6.4 Add unit test for `XdgPortalBackend.capture()` error paths (mock dbus unavailable, timeout)
- [x] 6.5 Run `lsp_diagnostics` on `src/models.py`, `src/backends/screen.py`, `src/backends/portal.py`, `src/server.py` — zero errors
- [x] 6.6 Manual integration test: start MCP server, call `screen(action="snapshot")` — verify returned JSON contains valid base64 screenshot with correct resolution
