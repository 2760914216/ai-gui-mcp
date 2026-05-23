"""Tests for batch tool execution in the MCP server.

Tests batch sequential execution, early stop on error, mixed operations,
and pydantic validation.
"""

from unittest.mock import patch, MagicMock
import pytest

from src.models import BatchAction, BatchRequest, MouseAction, KeyboardAction, ScreenAction
from src.server import set_backend, _handle_batch, _handle_mouse, _handle_keyboard, _handle_screen


@pytest.fixture(autouse=True)
def mock_backend():
    """Inject a mock backend before every test."""
    backend = MagicMock()
    backend.screen_size.return_value = (1920, 1080)
    backend.get_cursor_position.return_value = (0, 0)
    set_backend(backend)
    return backend


class TestBatchSuccess:
    def test_all_succeed(self):
        """Batch with 3 mouse clicks should complete all."""
        request = BatchRequest(actions=[
            BatchAction(tool="mouse", args={"action": "move", "x": 100, "y": 100}),
            BatchAction(tool="mouse", args={"action": "move", "x": 200, "y": 200}),
            BatchAction(tool="mouse", args={"action": "move", "x": 300, "y": 300}),
        ])
        result = _handle_batch(request)
        assert '"completed": 3' in result
        assert '"total": 3' in result

    def test_mixed_operations(self):
        """Batch with mixed mouse, keyboard, and screen actions."""
        request = BatchRequest(actions=[
            BatchAction(tool="mouse", args={"action": "move", "x": 100, "y": 100}),
            BatchAction(tool="keyboard", args={"action": "type", "text": "hello"}),
            BatchAction(tool="screen", args={"action": "size"}),
        ])
        result = _handle_batch(request)
        assert '"completed": 3' in result
        assert '"total": 3' in result


class TestBatchError:
    def test_error_stops_batch(self):
        """Batch should stop at the first failing action."""
        request = BatchRequest(actions=[
            BatchAction(tool="mouse", args={"action": "move", "x": 100, "y": 100}),
            BatchAction(tool="mouse", args={"action": "click", "x": -1, "y": 100}),
            BatchAction(tool="mouse", args={"action": "move", "x": 300, "y": 300}),
        ])
        result = _handle_batch(request)
        assert '"completed": 1' in result
        assert '"total": 3' in result
        assert '"error"' in result

    def test_invalid_tool_validation(self):
        """Pydantic should reject invalid tool names before execution."""
        with pytest.raises(Exception):
            BatchRequest(actions=[
                BatchAction(tool="invalid_tool", args={}),
            ])

    def test_missing_required_params(self):
        """Keyboard type without text should fail."""
        request = BatchRequest(actions=[
            BatchAction(tool="keyboard", args={"action": "type"}),
        ])
        result = _handle_batch(request)
        assert '"completed": 0' in result
        assert '"error"' in result


class TestBatchScreen:
    def test_screen_size_in_batch(self):
        """Screen action should work within batch."""
        request = BatchRequest(actions=[
            BatchAction(tool="screen", args={"action": "size"}),
        ])
        result = _handle_batch(request)
        assert '"completed": 1' in result


class TestBatchCursor:
    def test_cursor_in_batch(self, mock_backend):
        """screen(action='cursor') should work within batch."""
        import json
        mock_backend.get_cursor_position.return_value = (100, 200)
        request = BatchRequest(actions=[
            BatchAction(tool="mouse", args={"action": "move", "x": 100, "y": 200}),
            BatchAction(tool="screen", args={"action": "cursor"}),
        ])
        result = _handle_batch(request)
        data = json.loads(result)
        assert data["completed"] == 2
        assert data["total"] == 2
        assert "results" in data
        cursor_result = json.loads(data["results"][1])
        assert cursor_result["x"] == 100
        assert cursor_result["y"] == 200


class TestBatchResultsArray:
    def test_results_array_contents(self, mock_backend):
        """Verify results array contains correct values for each step."""
        import json
        mock_backend.get_cursor_position.return_value = (50, 60)
        request = BatchRequest(actions=[
            BatchAction(tool="screen", args={"action": "size"}),
            BatchAction(tool="mouse", args={"action": "move", "x": 50, "y": 60}),
            BatchAction(tool="screen", args={"action": "cursor"}),
        ])
        result = _handle_batch(request)
        data = json.loads(result)
        assert data["completed"] == 3
        assert data["total"] == 3
        assert len(data["results"]) == 3
        size_result = json.loads(data["results"][0])
        assert "width" in size_result
        assert "height" in size_result
        assert "moved to" in data["results"][1]
        cursor_result = json.loads(data["results"][2])
        assert cursor_result["x"] == 50
        assert cursor_result["y"] == 60


class TestBatchEmpty:
    def test_empty_actions_rejected(self):
        """Pydantic should reject empty actions list."""
        with pytest.raises(Exception):
            BatchRequest(actions=[])


class TestBatchModel:
    def test_mouse_action_model_validation(self):
        """MouseAction should validate action enum."""
        with pytest.raises(Exception):
            MouseAction(action="invalid_action")

    def test_keyboard_action_model_validation(self):
        """KeyboardAction should validate action enum."""
        with pytest.raises(Exception):
            KeyboardAction(action="unknown")

    def test_screen_action_model_validation(self):
        """ScreenAction should validate action enum."""
        ScreenAction(action="size")
        with pytest.raises(Exception):
            ScreenAction(action="nonsense")

    def test_batch_action_model_validation(self):
        """BatchAction should validate tool enum."""
        BatchAction(tool="mouse", args={})
        BatchAction(tool="keyboard", args={})
        BatchAction(tool="screen", args={})
        with pytest.raises(Exception):
            BatchAction(tool="network", args={})
