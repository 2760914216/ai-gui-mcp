"""Pydantic models for MCP tool input validation and perception output.

Defines the data structures for mouse, keyboard, screen, and batch actions
(input validation) as well as ScreenSnapshot, UIElement, and CursorInfo
for perception backends (output models).

Used by the MCP server to validate tool inputs and serialize perception results.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Perception output models ────────────────────────────────────────

class ScreenInfo(BaseModel):
    """Screen resolution metadata."""
    width: int
    height: int


class CursorInfo(BaseModel):
    """Cursor position and its detection method."""
    x: int
    y: int
    source: Literal["tracked", "detected"]


class UIElement(BaseModel):
    """A single GUI element discovered via accessibility tree or visual recognition.

    All fields except `id` are optional to support minimum-viable elements
    where only identity is known without position or role.
    """
    id: str
    role: Optional[str] = None
    name: Optional[str] = None
    bbox: Optional[list[int]] = None  # [x, y, w, h]
    states: Optional[list[str]] = None
    parent: Optional[str] = None  # parent element id
    confidence: Optional[float] = None  # 0.0-1.0, null for accessibility tree


class ScreenSnapshot(BaseModel):
    """Unified return type for all ScreenBackend.capture() implementations.

    Contains screen metadata, cursor info, optional base64 screenshot,
    optional structured elements, and a source indicator.
    """
    screen: ScreenInfo
    cursor: CursorInfo
    screenshot: Optional[str] = None  # base64-encoded PNG
    elements: list[UIElement] = []
    source: Literal["screenshot", "accessibility", "vision"]
    note: Optional[str] = None


# ── Tool input models ───────────────────────────────────────────────

class MouseAction(BaseModel):
    """Parameters for the mouse tool."""

    action: Literal[
        "move", "move_rel", "click", "dbl_click", "right_click",
        "down", "up", "scroll", "drag",
    ]
    x: Optional[int] = Field(default=None, description="Absolute X coordinate")
    y: Optional[int] = Field(default=None, description="Absolute Y coordinate")
    dx: Optional[int] = Field(default=None, description="Relative X delta for move_rel / scroll")
    dy: Optional[int] = Field(default=None, description="Relative Y delta for move_rel / scroll")
    x1: Optional[int] = Field(default=None, description="Drag start X coordinate")
    y1: Optional[int] = Field(default=None, description="Drag start Y coordinate")
    x2: Optional[int] = Field(default=None, description="Drag end X coordinate")
    y2: Optional[int] = Field(default=None, description="Drag end Y coordinate")
    button: Literal["left", "right", "middle"] = Field(default="left")


class KeyboardAction(BaseModel):
    """Parameters for the keyboard tool."""

    action: Literal["type", "press", "down", "up"]
    text: Optional[str] = Field(default=None, description="Text to type (action=type)")
    keys: Optional[list[str]] = Field(default=None, description="Keys for combo (action=press)")
    key: Optional[str] = Field(default=None, description="Single key (action=down/up)")


class ScreenAction(BaseModel):
    """Parameters for the screen tool."""

    action: Literal["size", "cursor", "snapshot"]


class BatchAction(BaseModel):
    """A single action within a batch request."""

    tool: Literal["mouse", "keyboard", "screen"]
    args: dict = Field(default_factory=dict)


class BatchRequest(BaseModel):
    """A batch of mixed mouse/keyboard/screen actions."""

    actions: list[BatchAction] = Field(..., min_length=1)
