"""Pydantic models for MCP tool input validation.

Defines the data structures for mouse, keyboard, screen, and batch actions.
Used by the MCP server to validate tool inputs before routing to the backend.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


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

    action: Literal["size", "cursor"]


class BatchAction(BaseModel):
    """A single action within a batch request."""

    tool: Literal["mouse", "keyboard", "screen"]
    args: dict = Field(default_factory=dict)


class BatchRequest(BaseModel):
    """A batch of mixed mouse/keyboard/screen actions."""

    actions: list[BatchAction] = Field(..., min_length=1)
