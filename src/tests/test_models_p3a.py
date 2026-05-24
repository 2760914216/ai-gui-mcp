"""Tests for P3A public-facing perception models.

Covers ScreenState, SnapshotResult, AnalysisWarning, ScreenKind,
LayoutRegion, ActiveDialogInfo, LayoutSummary, ParsedElement,
AnalysisResult, and ScreenAction validation.
"""

import pytest

from src.models import (
    ScreenState,
    SnapshotResult,
    AnalysisWarning,
    ScreenKind,
    LayoutRegion,
    ActiveDialogInfo,
    LayoutSummary,
    ParsedElement,
    AnalysisResult,
    ScreenAction,
)


# ═══════════════════════════════════════════════════════════════════════
# ScreenState
# ═══════════════════════════════════════════════════════════════════════

class TestScreenState:
    def test_valid_creation(self):
        state = ScreenState(width=2560, height=1600, cursor_x=100, cursor_y=200)
        assert state.width == 2560
        assert state.height == 1600
        assert state.cursor_x == 100
        assert state.cursor_y == 200

    def test_default_values(self):
        state = ScreenState()
        assert state.width == 0
        assert state.height == 0
        assert state.cursor_x == 0
        assert state.cursor_y == 0
        assert state.cursor_source == "tracked"

    def test_cursor_source_tracked(self):
        state = ScreenState(cursor_source="tracked")
        assert state.cursor_source == "tracked"

    def test_cursor_source_detected(self):
        state = ScreenState(cursor_source="detected")
        assert state.cursor_source == "detected"

    def test_invalid_cursor_source(self):
        with pytest.raises(Exception):
            ScreenState(cursor_source="invalid")

    def test_model_dump_json(self):
        state = ScreenState(width=1920, height=1080, cursor_x=50, cursor_y=75)
        json_str = state.model_dump_json()
        assert '"width":1920' in json_str
        assert '"height":1080' in json_str
        assert '"cursor_x":50' in json_str
        assert '"cursor_y":75' in json_str
        assert '"cursor_source":"tracked"' in json_str


# ═══════════════════════════════════════════════════════════════════════
# SnapshotResult
# ═══════════════════════════════════════════════════════════════════════

class TestSnapshotResult:
    def test_valid_creation_all_fields(self):
        screen = ScreenState(width=2560, height=1600, cursor_x=10, cursor_y=20)
        result = SnapshotResult(
            snapshot_id="snap-001",
            created_at="2025-05-24T12:00:00Z",
            screen=screen,
            has_image=True,
            image_format="png",
            note="captured via portal",
        )
        assert result.snapshot_id == "snap-001"
        assert result.created_at == "2025-05-24T12:00:00Z"
        assert result.screen.width == 2560
        assert result.has_image is True
        assert result.image_format == "png"
        assert result.note == "captured via portal"

    def test_minimal_creation(self):
        screen = ScreenState()
        result = SnapshotResult(
            snapshot_id="snap-min",
            created_at="2025-01-01T00:00:00Z",
            screen=screen,
            has_image=False,
        )
        assert result.snapshot_id == "snap-min"
        assert result.has_image is False
        assert result.image_format is None
        assert result.note is None

    def test_has_image_true(self):
        result = SnapshotResult(
            snapshot_id="snap-img",
            created_at="2025-05-24T00:00:00Z",
            screen=ScreenState(width=1920, height=1080),
            has_image=True,
            image_format="png",
        )
        assert result.has_image is True
        assert result.image_format == "png"

    def test_has_image_false(self):
        result = SnapshotResult(
            snapshot_id="snap-no-img",
            created_at="2025-05-24T00:00:00Z",
            screen=ScreenState(),
            has_image=False,
        )
        assert result.has_image is False

    def test_model_dump_json_no_raw_image(self):
        """SnapshotResult does not embed base64 image data."""
        result = SnapshotResult(
            snapshot_id="snap-json",
            created_at="2025-05-24T00:00:00Z",
            screen=ScreenState(width=800, height=600),
            has_image=True,
            image_format="png",
        )
        json_str = result.model_dump_json()
        assert '"snapshot_id":"snap-json"' in json_str
        assert '"has_image":true' in json_str
        assert "base64" not in json_str
        assert "screenshot" not in json_str


# ═══════════════════════════════════════════════════════════════════════
# AnalysisWarning
# ═══════════════════════════════════════════════════════════════════════

class TestAnalysisWarning:
    def test_valid_creation(self):
        warning = AnalysisWarning(
            code="provider_timeout",
            severity="high",
            message="Vision provider timed out after 10s",
        )
        assert warning.code == "provider_timeout"
        assert warning.severity == "high"
        assert warning.message == "Vision provider timed out after 10s"

    @pytest.mark.parametrize("code", [
        "image_unavailable",
        "provider_timeout",
        "dense_ui_possible_misses",
        "ocr_low_confidence",
        "partial_parse",
        "unsupported_layout",
        "low_visibility_elements",
    ])
    def test_valid_code_values(self, code):
        warning = AnalysisWarning(code=code, severity="low", message="test")
        assert warning.code == code

    def test_invalid_code_raises(self):
        with pytest.raises(Exception):
            AnalysisWarning(code="nonexistent_code", severity="low", message="bad")

    @pytest.mark.parametrize("severity", ["low", "medium", "high"])
    def test_valid_severity_values(self, severity):
        warning = AnalysisWarning(
            code="partial_parse", severity=severity, message="test"
        )
        assert warning.severity == severity

    def test_invalid_severity_raises(self):
        with pytest.raises(Exception):
            AnalysisWarning(code="partial_parse", severity="critical", message="bad")


# ═══════════════════════════════════════════════════════════════════════
# ScreenKind
# ═══════════════════════════════════════════════════════════════════════

class TestScreenKind:
    @pytest.mark.parametrize("kind", [
        "ide", "browser", "settings", "dialog",
        "file_manager", "terminal", "unknown",
    ])
    def test_valid_kind_values(self, kind):
        sk = ScreenKind(kind=kind)
        assert sk.kind == kind
        assert sk.detail is None

    def test_unknown_default(self):
        """Default factory in LayoutSummary uses kind='unknown'."""
        sk = ScreenKind(kind="unknown")
        assert sk.kind == "unknown"

    def test_detail_optional(self):
        sk = ScreenKind(kind="ide", detail="VS Code with split editor")
        assert sk.detail == "VS Code with split editor"

    def test_detail_none_by_default(self):
        sk = ScreenKind(kind="browser")
        assert sk.detail is None

    def test_invalid_kind_raises(self):
        with pytest.raises(Exception):
            ScreenKind(kind="game")


# ═══════════════════════════════════════════════════════════════════════
# LayoutRegion
# ═══════════════════════════════════════════════════════════════════════

class TestLayoutRegion:
    def test_valid_creation(self):
        region = LayoutRegion(
            id="region-1",
            type="sidebar",
            bbox=[0, 0, 300, 1080],
        )
        assert region.id == "region-1"
        assert region.type == "sidebar"
        assert region.bbox == [0, 0, 300, 1080]
        assert region.detail is None

    @pytest.mark.parametrize("region_type", [
        "sidebar", "toolbar", "editor", "content",
        "dialog", "panel", "list", "table", "form", "unknown",
    ])
    def test_type_enum_validation(self, region_type):
        region = LayoutRegion(id="r", type=region_type, bbox=[0, 0, 100, 100])
        assert region.type == region_type

    def test_invalid_type_raises(self):
        with pytest.raises(Exception):
            LayoutRegion(id="r", type="header", bbox=[0, 0, 100, 100])

    def test_bbox_four_ints(self):
        region = LayoutRegion(id="r", type="content", bbox=[10, 20, 800, 600])
        assert len(region.bbox) == 4
        assert all(isinstance(v, int) for v in region.bbox)

    def test_detail_with_value(self):
        region = LayoutRegion(
            id="r", type="editor", bbox=[300, 0, 1200, 1080],
            detail="Main code editor area",
        )
        assert region.detail == "Main code editor area"


# ═══════════════════════════════════════════════════════════════════════
# ActiveDialogInfo
# ═══════════════════════════════════════════════════════════════════════

class TestActiveDialogInfo:
    def test_defaults(self):
        info = ActiveDialogInfo()
        assert info.present is False
        assert info.region_ref is None
        assert info.element_ref is None

    def test_present_true(self):
        info = ActiveDialogInfo(
            present=True,
            region_ref="region-dialog-1",
            element_ref="elem-dialog-1",
        )
        assert info.present is True
        assert info.region_ref == "region-dialog-1"
        assert info.element_ref == "elem-dialog-1"

    def test_present_false_with_no_refs(self):
        info = ActiveDialogInfo(present=False)
        assert info.present is False
        assert info.region_ref is None
        assert info.element_ref is None


# ═══════════════════════════════════════════════════════════════════════
# LayoutSummary
# ═══════════════════════════════════════════════════════════════════════

class TestLayoutSummary:
    def test_default_factory_populates(self):
        summary = LayoutSummary()
        assert summary.screen_kind.kind == "unknown"
        assert summary.screen_kind.detail is None
        assert summary.active_dialog.present is False
        assert summary.main_regions == []
        assert summary.notes is None

    def test_valid_creation_with_regions(self):
        regions = [
            LayoutRegion(id="r1", type="sidebar", bbox=[0, 0, 300, 1080]),
            LayoutRegion(id="r2", type="editor", bbox=[300, 0, 1200, 1080]),
        ]
        summary = LayoutSummary(
            screen_kind=ScreenKind(kind="ide", detail="VS Code"),
            main_regions=regions,
            active_dialog=ActiveDialogInfo(present=False),
            notes="Two-panel layout",
        )
        assert summary.screen_kind.kind == "ide"
        assert len(summary.main_regions) == 2
        assert summary.main_regions[0].id == "r1"
        assert summary.notes == "Two-panel layout"


# ═══════════════════════════════════════════════════════════════════════
# ParsedElement
# ═══════════════════════════════════════════════════════════════════════

class TestParsedElement:
    def test_minimum_viable_element(self):
        elem = ParsedElement(id="e1", type="button", bbox=[10, 20, 100, 30])
        assert elem.id == "e1"
        assert elem.type == "button"
        assert elem.bbox == [10, 20, 100, 30]
        assert elem.text is None
        assert elem.description is None
        assert elem.confidence is None
        assert elem.parent_id is None
        assert elem.children_ids == []
        assert elem.region_ref is None

    def test_all_fields_populated(self):
        elem = ParsedElement(
            id="e2",
            type="input",
            bbox=[50, 60, 200, 30],
            text="Search...",
            description="Main search input",
            confidence=0.92,
            parent_id="e1",
            children_ids=["e3", "e4"],
            region_ref="region-toolbar",
        )
        assert elem.id == "e2"
        assert elem.type == "input"
        assert elem.text == "Search..."
        assert elem.description == "Main search input"
        assert elem.confidence == 0.92
        assert elem.parent_id == "e1"
        assert elem.children_ids == ["e3", "e4"]
        assert elem.region_ref == "region-toolbar"

    @pytest.mark.parametrize("elem_type", [
        "button", "input", "checkbox", "radio", "tab", "menuitem", "link",
        "window", "dialog", "sidebar", "toolbar", "panel", "list", "table",
        "form", "text", "unknown",
    ])
    def test_type_enum_all_17_values(self, elem_type):
        elem = ParsedElement(id="e", type=elem_type, bbox=[0, 0, 10, 10])
        assert elem.type == elem_type

    def test_invalid_type_raises(self):
        with pytest.raises(Exception):
            ParsedElement(id="e", type="slider", bbox=[0, 0, 10, 10])

    def test_optional_fields_default_none(self):
        elem = ParsedElement(id="e", type="text", bbox=[0, 0, 50, 20])
        assert elem.text is None
        assert elem.description is None
        assert elem.confidence is None
        assert elem.parent_id is None
        assert elem.region_ref is None

    def test_children_ids_default_empty_list(self):
        elem = ParsedElement(id="e", type="panel", bbox=[0, 0, 100, 100])
        assert elem.children_ids == []


# ═══════════════════════════════════════════════════════════════════════
# AnalysisResult
# ═══════════════════════════════════════════════════════════════════════

class TestAnalysisResult:
    def test_complete_creation(self):
        warning = AnalysisWarning(
            code="ocr_low_confidence", severity="medium", message="Low OCR"
        )
        elem = ParsedElement(id="btn1", type="button", bbox=[10, 20, 80, 30])
        region = LayoutRegion(id="r1", type="toolbar", bbox=[0, 0, 1920, 50])
        layout = LayoutSummary(
            screen_kind=ScreenKind(kind="browser"),
            main_regions=[region],
            active_dialog=ActiveDialogInfo(present=False),
        )
        result = AnalysisResult(
            snapshot_id="snap-analysis",
            overall_quality="high",
            warnings=[warning],
            layout_summary=layout,
            elements=[elem],
        )
        assert result.snapshot_id == "snap-analysis"
        assert result.overall_quality == "high"
        assert len(result.warnings) == 1
        assert result.warnings[0].code == "ocr_low_confidence"
        assert result.layout_summary.screen_kind.kind == "browser"
        assert len(result.elements) == 1
        assert result.elements[0].id == "btn1"

    def test_empty_creation_with_defaults(self):
        result = AnalysisResult(
            snapshot_id="snap-empty",
            overall_quality="low",
        )
        assert result.snapshot_id == "snap-empty"
        assert result.overall_quality == "low"
        assert result.warnings == []
        assert result.layout_summary.screen_kind.kind == "unknown"
        assert result.layout_summary.main_regions == []
        assert result.layout_summary.active_dialog.present is False
        assert result.elements == []

    def test_no_source_field_exists(self):
        """AnalysisResult does NOT have a top-level 'source' field."""
        result = AnalysisResult(
            snapshot_id="snap-nosrc",
            overall_quality="medium",
        )
        assert not hasattr(result, "source") or "source" not in result.model_fields

    @pytest.mark.parametrize("quality", ["high", "medium", "low"])
    def test_overall_quality_enum(self, quality):
        result = AnalysisResult(snapshot_id="snap", overall_quality=quality)
        assert result.overall_quality == quality

    def test_invalid_overall_quality_raises(self):
        with pytest.raises(Exception):
            AnalysisResult(snapshot_id="snap", overall_quality="excellent")


# ═══════════════════════════════════════════════════════════════════════
# ScreenAction — "analyze" and "image" accepted
# ═══════════════════════════════════════════════════════════════════════

class TestScreenAction:
    def test_analyze_action_accepted(self):
        action = ScreenAction(action="analyze")
        assert action.action == "analyze"

    def test_image_action_accepted(self):
        action = ScreenAction(action="image")
        assert action.action == "image"

    @pytest.mark.parametrize("action", ["size", "cursor", "snapshot", "analyze", "image"])
    def test_all_valid_actions(self, action):
        sa = ScreenAction(action=action)
        assert sa.action == action

    def test_invalid_action_raises(self):
        with pytest.raises(Exception):
            ScreenAction(action="record")
