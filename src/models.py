"""Pydantic models for MCP tool input validation and perception output.

Defines the data structures for mouse, keyboard, screen, and batch actions
(input validation) as well as perception output models (ScreenState,
SnapshotResult, AnalysisResult, etc.) and internal models (ScreenSnapshot,
UIElement, CursorInfo).

Used by the MCP server to validate tool inputs and serialize perception results.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Public-facing perception models (P3A) ───────────────────────────

class ScreenState(BaseModel):
    """Public model for immediate state queries (size/cursor).

    Replaces the combination of ScreenInfo + CursorInfo as the
    public-facing contract for screen(size) and screen(cursor).
    """
    width: int = 0
    height: int = 0
    cursor_x: int = 0
    cursor_y: int = 0
    cursor_source: Literal["tracked", "detected"] = "tracked"


class SnapshotResult(BaseModel):
    """Public return type for screen(action="snapshot").

    A lightweight observation handle — does NOT embed raw image data.
    Raw images are retrieved via screen(action="image", snapshot_id).
    """
    snapshot_id: str
    created_at: str  # ISO 8601
    screen: ScreenState
    has_image: bool
    image_format: Optional[str] = None  # e.g. "png"
    note: Optional[str] = None


class AnalysisWarning(BaseModel):
    """Structured quality signal for AnalysisResult.warnings[]."""
    code: Literal[
        "image_unavailable",
        "provider_timeout",
        "dense_ui_possible_misses",
        "ocr_low_confidence",
        "partial_parse",
        "unsupported_layout",
        "low_visibility_elements",
        "duplicate_element",
        "hallucinated_element",
        "model_parse_error",
    ]
    severity: Literal["low", "medium", "high"]
    message: str


class ScreenKind(BaseModel):
    """High-level screen classification."""
    kind: Literal["ide", "browser", "settings", "dialog", "file_manager", "terminal", "unknown"]
    detail: Optional[str] = None


class LayoutRegion(BaseModel):
    """A rectangular region of the screen with a semantic type."""
    id: str
    type: Literal[
        "sidebar", "toolbar", "editor", "content",
        "dialog", "panel", "list", "table", "form", "unknown",
    ]
    bbox: list[int]  # [x1, y1, x2, y2]
    detail: Optional[str] = None


class ActiveDialogInfo(BaseModel):
    """Information about a visible dialog or popup."""
    present: bool = False
    region_ref: Optional[str] = None
    element_ref: Optional[str] = None


class LayoutSummary(BaseModel):
    """High-level layout characterization of the screen."""
    screen_kind: ScreenKind = Field(default_factory=lambda: ScreenKind(kind="unknown"))
    main_regions: list[LayoutRegion] = []
    active_dialog: ActiveDialogInfo = Field(default_factory=ActiveDialogInfo)
    notes: Optional[str] = None


class ParsedElement(BaseModel):
    """A single GUI element identified by the vision parser.

    Flat list organization with parent_id/children_ids for local hierarchy
    and region_ref for global layout membership.
    """
    id: str
    type: Literal[
        "button", "input", "checkbox", "radio", "tab", "menuitem", "link",
        "window", "dialog", "sidebar", "toolbar", "panel", "list", "table",
        "form", "text", "unknown",
    ]
    bbox: list[int]  # [x1, y1, x2, y2]
    text: Optional[str] = None
    description: Optional[str] = None
    confidence: Optional[float] = None  # 0.0-1.0, null for accessibility
    parent_id: Optional[str] = None
    children_ids: list[str] = []
    region_ref: Optional[str] = None


class AnalysisResult(BaseModel):
    """Primary P3A output — structured GUI understanding result.

    Contains layout summary, flat element list, quality assessment,
    and structured warnings. Does NOT include a top-level 'source' field.
    """
    snapshot_id: str
    overall_quality: Literal["high", "medium", "low"]
    warnings: list[AnalysisWarning] = []
    layout_summary: LayoutSummary = Field(default_factory=LayoutSummary)
    elements: list[ParsedElement] = []


# ── Internal perception models (retained from P2) ───────────────────

class ScreenInfo(BaseModel):
    """Screen resolution metadata (internal model)."""
    width: int
    height: int


class CursorInfo(BaseModel):
    """Cursor position and its detection method (internal model)."""
    x: int
    y: int
    source: Literal["tracked", "detected"]


class UIElement(BaseModel):
    """A single GUI element discovered via accessibility tree or visual recognition.

    Internal model — replaced by ParsedElement in the public API.
    All fields except `id` are optional to support minimum-viable elements
    where only identity is known without position or role.
    """
    id: str
    role: Optional[str] = None
    name: Optional[str] = None
    bbox: Optional[list[int]] = None  # [x1, y1, x2, y2]
    states: Optional[list[str]] = None
    parent: Optional[str] = None  # parent element id
    confidence: Optional[float] = None  # 0.0-1.0, null for accessibility tree


class ScreenSnapshot(BaseModel):
    """Internal model for ScreenBackend.capture() return values.

    NOT used as a public MCP tool response — PerceptionService transforms
    it into SnapshotResult / AnalysisResult for public output.
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

    action: Literal["size", "cursor", "snapshot", "analyze", "image"]


class BatchAction(BaseModel):
    """A single action within a batch request."""

    tool: Literal["mouse", "keyboard", "screen"]
    args: dict = Field(default_factory=dict)


class BatchRequest(BaseModel):
    """A batch of mixed mouse/keyboard/screen actions."""

    actions: list[BatchAction] = Field(..., min_length=1)
