## 1. Backend — cursor position query + startup warning

- [x] 1.1 `src/backends/base.py`: Add `get_cursor_position() -> tuple[int, int]` abstract method to `InputBackend`
- [x] 1.2 `src/backends/uinput.py`: Implement `get_cursor_position()` returning `(self._x, self._y)`
- [x] 1.3 `src/backends/uinput.py`: Add startup warning `print("[ai-gui-mcp] cursor position unknown, tracking assumes (0,0)", file=sys.stderr)` at end of `__init__()`

## 2. Models — new action + drag params

- [x] 2.1 `src/models.py`: Add `"cursor"` to `ScreenAction.action` Literal
- [x] 2.2 `src/models.py`: Rename `MouseAction` drag params: remove `dx`/`dy` dependency, add `x1`, `y1`, `x2`, `y2` as `Optional[int]` fields (**BREAKING**)

## 3. Server — tool schemas + routing

- [x] 3.1 `src/server.py`: Update `screen` tool `inputSchema` — add `"cursor"` to `action` enum, update description
- [x] 3.2 `src/server.py`: Update `mouse` tool `inputSchema` — replace `dx`/`dy` drag description with `x1`/`y1`/`x2`/`y2`
- [x] 3.3 `src/server.py`: Add `cursor` handler in `_handle_screen()` — call `backend.get_cursor_position()` and return `{"x": x, "y": y}`
- [x] 3.4 `src/server.py`: Rewrite drag handler in `_handle_mouse()` — use `(x1, y1, x2, y2)` directly, remove `dx`/`dy` conversion

## 4. Tests — update + new coverage

- [x] 4.1 `src/tests/test_mouse.py`: Add `TestGetCursorPosition` class — test initial (0,0), test after move_abs
- [x] 4.2 `src/tests/test_mouse.py`: Add `TestStartupWarning` — verify stderr output on init
- [x] 4.3 `src/tests/test_mouse.py`: Update `TestDrag` — verify new `drag(x1,y1,x2,y2)` signature
- [x] 4.4 `src/tests/test_batch.py`: Add `test_cursor_in_batch` — verify `screen(action="cursor")` works in batch
- [x] 4.5 `src/tests/test_batch.py`: Add `test_batch_results_array` — verify results array contains correct values for each step

## 5. Verification

- [x] 5.1 Run `lsp_diagnostics` on all changed files — zero errors
- [x] 5.2 Run `pytest src/tests/` — all tests pass
- [x] 5.3 Run `python -m src.server` smoke test — verify startup warnings appear on stderr
