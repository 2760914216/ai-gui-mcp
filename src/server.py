"""MCP Server entry point — registers 4 tools and routes actions to InputBackend.

Tools: mouse, keyboard, screen, batch
All inputs validated through pydantic models before reaching the backend.
"""

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.config import load_config, _deep_get
from src.backends.uinput import UInputBackend
from src.models import MouseAction, KeyboardAction, ScreenAction, BatchRequest, CursorInfo

_backend = None
_screen_backend = None
app = Server("ai-gui-mcp")


def set_backend(backend):
    global _backend
    _backend = backend


def get_backend():
    if _backend is None:
        raise RuntimeError("Backend not initialized. Call set_backend() first.")
    return _backend


def set_screen_backend(backend):
    global _screen_backend
    _screen_backend = backend


def get_screen_backend():
    if _screen_backend is None:
        raise RuntimeError("Screen backend not initialized. Call set_screen_backend() first.")
    return _screen_backend


def _create_backend(config: dict):
    backend_name = _deep_get(config, "input.backend", "uinput")
    if backend_name == "uinput":
        return UInputBackend(config=config)
    raise ValueError(f"Unknown input backend: {backend_name}")


def _create_screen_backend(config: dict):
    method = _deep_get(config, "perception.screenshot.method", "xdg-desktop-portal")
    if method == "xdg-desktop-portal":
        from src.backends.portal import XdgPortalBackend
        return XdgPortalBackend(config=config)
    raise ValueError(f"Unknown screen backend method: {method}")


# ── Tool definitions ──────────────────────────────────────────────

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="mouse",
            description="Simulate mouse actions: move, click, double-click, right-click, scroll, drag, button down/up",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["move", "move_rel", "click", "dbl_click", "right_click", "down", "up", "scroll", "drag"],
                        "description": "Mouse operation type",
                    },
                    "x": {"type": "integer", "description": "Absolute X coordinate"},
                    "y": {"type": "integer", "description": "Absolute Y coordinate"},
                    "dx": {"type": "integer", "description": "Relative X delta for move_rel / scroll"},
                    "dy": {"type": "integer", "description": "Relative Y delta for move_rel / scroll"},
                    "x1": {"type": "integer", "description": "Drag start X coordinate (for action=drag)"},
                    "y1": {"type": "integer", "description": "Drag start Y coordinate (for action=drag)"},
                    "x2": {"type": "integer", "description": "Drag end X coordinate (for action=drag)"},
                    "y2": {"type": "integer", "description": "Drag end Y coordinate (for action=drag)"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left",
                        "description": "Mouse button (default: left)",
                    },
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="keyboard",
            description="Simulate keyboard actions: type text, press key combo, key down/up",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["type", "press", "down", "up"],
                        "description": "Keyboard operation type",
                    },
                    "text": {"type": "string", "description": "Text to type (for action=type)"},
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keys for combo (for action=press), e.g. ['ctrl','s']",
                    },
                    "key": {"type": "string", "description": "Single key name (for action=down/up)"},
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="screen",
            description="Get screen information (size, cursor position, snapshot)",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["size", "cursor", "snapshot"],
                        "description": "Screen operation: size (resolution), cursor (tracked position), snapshot (full-screen capture as base64 PNG)",
                    },
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="batch",
            description="Execute multiple mouse/keyboard/screen actions sequentially. Stops on first error.",
            inputSchema={
                "type": "object",
                "properties": {
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool": {
                                    "type": "string",
                                    "enum": ["mouse", "keyboard", "screen"],
                                },
                                "args": {
                                    "type": "object",
                                    "description": "Arguments for the tool (depends on tool type)",
                                },
                            },
                            "required": ["tool", "args"],
                        },
                        "description": "Ordered list of actions to execute",
                    },
                },
                "required": ["actions"],
            },
        ),
    ]


# ── Coordinate clamping ───────────────────────────────────────────

def _clamp_coord(value: int, maximum: int, label: str) -> int:
    if not (0 <= value < maximum):
        raise ValueError(
            f"Coordinate {label}={value} out of bounds (0 <= {label} < {maximum})"
        )
    return value


def _validate_coords(x: int | None, y: int | None) -> None:
    if x is None or y is None:
        return
    backend = get_backend()
    width, height = backend.screen_size()
    _clamp_coord(x, width, "x")
    _clamp_coord(y, height, "y")


# ── Action routing ────────────────────────────────────────────────

def _handle_mouse(action: MouseAction) -> str:
    backend = get_backend()
    if action.action in ("move",):
        if action.x is None or action.y is None:
            raise ValueError(f"mouse action '{action.action}' requires x and y parameters")
        _validate_coords(action.x, action.y)

    if action.action == "move":
        backend.move_abs(action.x, action.y)
        return f"Mouse moved to ({action.x}, {action.y})"
    elif action.action == "move_rel":
        dx = action.dx or 0
        dy = action.dy or 0
        backend.move_rel(dx, dy)
        return f"Mouse moved relatively by ({dx}, {dy})"
    elif action.action == "click":
        if action.x is not None and action.y is not None:
            _validate_coords(action.x, action.y)
            backend.click(action.x, action.y, button=action.button)
            return f"Mouse {action.button} clicked at ({action.x}, {action.y})"
        else:
            backend.mouse_down(button=action.button)
            backend.mouse_up(button=action.button)
            return f"Mouse {action.button} clicked at current position"
    elif action.action == "dbl_click":
        if action.x is not None and action.y is not None:
            _validate_coords(action.x, action.y)
            backend.dbl_click(action.x, action.y, button=action.button)
            return f"Mouse {action.button} double-clicked at ({action.x}, {action.y})"
        else:
            backend.mouse_down(button=action.button)
            backend.mouse_up(button=action.button)
            backend.mouse_down(button=action.button)
            backend.mouse_up(button=action.button)
            return f"Mouse {action.button} double-clicked at current position"
    elif action.action == "right_click":
        if action.x is not None and action.y is not None:
            _validate_coords(action.x, action.y)
            backend.right_click(action.x, action.y)
            return f"Mouse right-clicked at ({action.x}, {action.y})"
        else:
            backend.mouse_down(button="right")
            backend.mouse_up(button="right")
            return "Mouse right-clicked at current position"
    elif action.action == "down":
        backend.mouse_down(button=action.button)
        return f"Mouse {action.button} button down"
    elif action.action == "up":
        backend.mouse_up(button=action.button)
        return f"Mouse {action.button} button up"
    elif action.action == "scroll":
        dy = action.dy or 0
        dx = action.dx or 0
        backend.scroll(dy, dx)
        return f"Mouse scrolled (dy={dy}, dx={dx})"
    elif action.action == "drag":
        if action.x1 is None or action.y1 is None or action.x2 is None or action.y2 is None:
            raise ValueError("mouse drag requires x1,y1 (start) and x2,y2 (end) parameters")
        _validate_coords(action.x1, action.y1)
        _validate_coords(action.x2, action.y2)
        backend.drag(action.x1, action.y1, action.x2, action.y2)
        return f"Mouse dragged from ({action.x1},{action.y1}) to ({action.x2},{action.y2})"


def _handle_keyboard(action: KeyboardAction) -> str:
    backend = get_backend()
    if action.action == "type":
        if not action.text:
            raise ValueError("keyboard type action requires 'text' parameter")
        backend.type_text(action.text)
        return f"Typed: {action.text}"
    elif action.action == "press":
        if not action.keys:
            raise ValueError("keyboard press action requires 'keys' parameter")
        backend.press_combo(action.keys)
        return f"Pressed combo: {'+'.join(action.keys)}"
    elif action.action == "down":
        if not action.key:
            raise ValueError("keyboard down action requires 'key' parameter")
        backend.key_down(action.key)
        return f"Key down: {action.key}"
    elif action.action == "up":
        if not action.key:
            raise ValueError("keyboard up action requires 'key' parameter")
        backend.key_up(action.key)
        return f"Key up: {action.key}"


def _handle_screen(action: ScreenAction) -> str:
    import json
    backend = get_backend()
    if action.action == "size":
        w, h = backend.screen_size()
        return json.dumps({"width": w, "height": h})
    elif action.action == "cursor":
        x, y = backend.get_cursor_position()
        return json.dumps({"x": x, "y": y})
    elif action.action == "snapshot":
        return _handle_screen_snapshot(backend, get_screen_backend())


def _handle_screen_snapshot(input_backend, screen_backend) -> str:
    import time

    t_start = time.perf_counter()

    try:
        snapshot = screen_backend.capture()
    except Exception as e:
        return _build_error_snapshot(input_backend, str(e))

    cursor_x, cursor_y = input_backend.get_cursor_position()
    snapshot.cursor = CursorInfo(x=cursor_x, y=cursor_y, source="tracked")

    latency_ms = (time.perf_counter() - t_start) * 1000
    if snapshot.note is None:
        snapshot.note = f"snapshot captured via xdg-desktop-portal; latency={latency_ms:.0f}ms"

    return snapshot.model_dump_json(exclude_none=False)


def _build_error_snapshot(input_backend, error: str) -> str:
    import json
    w, h = input_backend.screen_size()
    cx, cy = input_backend.get_cursor_position()
    return json.dumps({
        "screen": {"width": w, "height": h},
        "cursor": {"x": cx, "y": cy, "source": "tracked"},
        "screenshot": None,
        "elements": [],
        "source": "screenshot",
        "note": f"screenshot unavailable: {error}",
    }, ensure_ascii=False)


def _handle_batch(request: BatchRequest) -> str:
    import json
    completed = 0
    total = len(request.actions)
    results = []
    for i, item in enumerate(request.actions):
        try:
            if item.tool == "mouse":
                mouse_action = MouseAction(**item.args)
                result = _handle_mouse(mouse_action)
            elif item.tool == "keyboard":
                keyboard_action = KeyboardAction(**item.args)
                result = _handle_keyboard(keyboard_action)
            elif item.tool == "screen":
                screen_action = ScreenAction(**item.args)
                result = _handle_screen(screen_action)
            results.append(result)
            completed += 1
        except Exception as e:
            return json.dumps({
                "results": results,
                "completed": completed,
                "total": total,
                "error": str(e),
            }, ensure_ascii=False)
    return json.dumps({
        "results": results,
        "completed": completed,
        "total": total,
    }, ensure_ascii=False)


# ── Call tool dispatcher ──────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "mouse":
            action = MouseAction(**arguments)
            result = _handle_mouse(action)
        elif name == "keyboard":
            action = KeyboardAction(**arguments)
            result = _handle_keyboard(action)
        elif name == "screen":
            action = ScreenAction(**arguments)
            result = _handle_screen(action)
        elif name == "batch":
            request = BatchRequest(**arguments)
            result = _handle_batch(request)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ── Entry point ───────────────────────────────────────────────────

async def main():
    config = load_config("config.yaml")
    backend = _create_backend(config)
    set_backend(backend)
    screen_backend = _create_screen_backend(config)
    set_screen_backend(screen_backend)
    # Log detected vs configured resolution
    w, h = backend.screen_size()
    config_w = _deep_get(config, "screen.width")
    config_h = _deep_get(config, "screen.height")
    if config_w and config_h and (w != config_w or h != config_h):
        import sys
        print(f"[ai-gui-mcp] screen: {w}x{h} (detected from KMS), config: {config_w}x{config_h} — using detected", file=sys.stderr)
    else:
        import sys
        print(f"[ai-gui-mcp] screen: {w}x{h}", file=sys.stderr)
    async with stdio_server() as (read, write):
        await app.run(
            read,
            write,
            app.create_initialization_options(),
        )


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
