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
from src.models import (
    MouseAction, KeyboardAction, ScreenAction, BatchRequest,
    ScreenState, SnapshotResult, AnalysisResult,
)

_backend = None
_screen_backend = None
_perception_service = None
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


def set_perception_service(service):
    global _perception_service
    _perception_service = service


def get_perception_service():
    if _perception_service is None:
        raise RuntimeError("PerceptionService not initialized. Call set_perception_service() first.")
    return _perception_service


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
            description="Get screen information (size, cursor position, snapshot, analyze, image)",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["size", "cursor", "snapshot", "analyze", "image"],
                        "description": "Screen operation: size (resolution), cursor (tracked position), snapshot (observation handle), analyze (AI-powered GUI understanding via vision model), image (raw base64 PNG on demand)",
                    },
                    "snapshot_id": {
                        "type": "string",
                        "description": "Snapshot identifier — optional for analyze, required for image",
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
        state = ScreenState(width=w, height=h)
        return state.model_dump_json()

    elif action.action == "cursor":
        x, y = backend.get_cursor_position()
        state = ScreenState(cursor_x=x, cursor_y=y, cursor_source="tracked")
        return state.model_dump_json()

    elif action.action == "snapshot":
        service = get_perception_service()
        result = service.snapshot()
        return result.model_dump_json()

    elif action.action == "analyze":
        service = get_perception_service()
        result = service.analyze()
        return result.model_dump_json()

    elif action.action == "image":
        raise ValueError("screen image action requires 'snapshot_id' parameter")

    return json.dumps({"error": f"Unknown screen action: {action.action}"})


def _handle_screen_analyze(snapshot_id: str | None = None) -> str:
    service = get_perception_service()
    result = service.analyze(snapshot_id=snapshot_id)
    return result.model_dump_json()


def _handle_screen_image(snapshot_id: str) -> str:
    import json
    service = get_perception_service()
    payload = service.image(snapshot_id)
    return json.dumps(payload, ensure_ascii=False)


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
                if screen_action.action == "analyze":
                    snapshot_id = item.args.get("snapshot_id")
                    result = _handle_screen_analyze(snapshot_id)
                elif screen_action.action == "image":
                    snapshot_id = item.args.get("snapshot_id")
                    if not snapshot_id:
                        raise ValueError("screen image action requires 'snapshot_id'")
                    result = _handle_screen_image(snapshot_id)
                else:
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
            if action.action == "analyze":
                result = _handle_screen_analyze(arguments.get("snapshot_id"))
            elif action.action == "image":
                snapshot_id = arguments.get("snapshot_id")
                if not snapshot_id:
                    raise ValueError("screen image action requires 'snapshot_id'")
                result = _handle_screen_image(snapshot_id)
            else:
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

    from src.stores.observation import ObservationStore
    from src.services.perception import PerceptionService
    from src.providers.screenshot import PortalScreenshotProvider
    from src.config import load_vision_config

    max_count = _deep_get(config, "perception.service.snapshot_max_count", 16)
    ttl_sec = _deep_get(config, "perception.service.snapshot_ttl_sec", 300)
    mem_mb = _deep_get(config, "perception.service.snapshot_memory_budget_mb", 256)

    store = ObservationStore(
        max_count=max_count,
        ttl_sec=ttl_sec,
        memory_budget_mb=mem_mb,
    )
    screenshot_provider = PortalScreenshotProvider(screen_backend)

    vision_config = load_vision_config(config)
    vision_provider = None

    if vision_config.backend == "pipeline_gq":
        from src.providers.vision import PipelineGQVisionProvider
        import sys
        try:
            vp = PipelineGQVisionProvider(vision_config)
            vision_provider = vp
            print("[ai-gui-mcp] vision backend: pipeline_gq (lazy-load on first analyze)", file=sys.stderr)
        except ImportError as exc:
            print(f"[ai-gui-mcp] WARNING: {exc}", file=sys.stderr)
            print("[ai-gui-mcp] falling back to dummy vision provider", file=sys.stderr)
            from src.providers.vision import DummyVisionProvider
            vision_provider = DummyVisionProvider()

    if vision_provider is None:
        from src.providers.vision import DummyVisionProvider
        vision_provider = DummyVisionProvider()

    perception = PerceptionService(
        input_backend=backend,
        screenshot_provider=screenshot_provider,
        observation_store=store,
        vision_provider=vision_provider,
    )
    set_perception_service(perception)

    import time as _time
    _last_analyze = _time.time()
    _orig_analyze = perception.analyze
    _vp = vision_provider
    _idle_sec = vision_config.idle_shutdown_sec

    def _analyze_with_reset(snapshot_id=None):
        nonlocal _last_analyze
        _last_analyze = _time.time()
        return _orig_analyze(snapshot_id)

    perception.analyze = _analyze_with_reset

    if _idle_sec > 0:

        async def _idle_loop():
            nonlocal _last_analyze
            while True:
                await asyncio.sleep(_idle_sec)
                elapsed = _time.time() - _last_analyze
                if elapsed >= _idle_sec:
                    from src.providers.vision import PipelineGQVisionProvider
                    if isinstance(_vp, PipelineGQVisionProvider):
                        _vp.shutdown()

        asyncio.create_task(_idle_loop())

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
