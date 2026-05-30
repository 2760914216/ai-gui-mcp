from __future__ import annotations

# pyright: reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportAny=false, reportUnusedCallResult=false, reportUnusedParameter=false, reportUnknownArgumentType=false

import builtins
import sys
import types
from unittest.mock import MagicMock

import pytest
from PIL import Image

from src.providers.qwen_vl.descriptor import (
    ElementDescription,
    QwenTypeMapper,
    QwenVLDescriptor,
    constrain_by_category,
)


@pytest.fixture
def fake_ml_modules(monkeypatch: pytest.MonkeyPatch):
    fake_torch = types.SimpleNamespace(
        float16="float16",
        cuda=types.SimpleNamespace(empty_cache=MagicMock()),
    )
    fake_transformers = types.SimpleNamespace(
        Qwen2VLForConditionalGeneration=MagicMock(),
        AutoProcessor=MagicMock(),
        BitsAndBytesConfig=MagicMock(),
    )

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    return fake_torch, fake_transformers


class TestElementDescription:
    def test_dataclass(self):
        elem = ElementDescription(type="button", text="Submit", confidence=0.91)
        assert elem.type == "button"
        assert elem.text == "Submit"
        assert elem.confidence == 0.91


class TestQwenTypeMapper:
    def test_interactive_types(self):
        types_ = constrain_by_category("interactive")
        assert types_ == QwenTypeMapper.INTERACTIVE_TYPES
        assert len(types_) == 7

    def test_structural_types(self):
        types_ = constrain_by_category("structural")
        assert types_ == QwenTypeMapper.STRUCTURAL_TYPES
        assert len(types_) == 8

    def test_unknown_types(self):
        types_ = constrain_by_category("unknown")
        assert types_ == QwenTypeMapper.ALL_TYPES
        assert len(types_) == 17


class TestQwenVLDescriptor:
    def test_init_stores_config(self, fake_ml_modules):
        descriptor = QwenVLDescriptor(
            model_path="/tmp/qwen3-vl-4b",
            quantization="none",
            max_tokens_per_region=96,
        )

        assert descriptor._model_path == "/tmp/qwen3-vl-4b"
        assert descriptor._quantization == "none"
        assert descriptor._max_tokens == 96
        assert descriptor._model is None
        assert descriptor._processor is None
        assert descriptor.is_initialized is False

    def test_init_import_guard(self, monkeypatch: pytest.MonkeyPatch):
        original_import = builtins.__import__

        def selective_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "torch":
                raise ImportError("No module named 'torch'")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", selective_import)

        with pytest.raises(ImportError, match="pip install ai-gui-mcp\\[vision\\]"):
            QwenVLDescriptor(model_path="/tmp/qwen")

    def test_initialize_loads_model(self, fake_ml_modules):
        _, fake_transformers = fake_ml_modules
        mock_model = MagicMock()
        mock_processor = MagicMock()

        fake_transformers.Qwen2VLForConditionalGeneration.from_pretrained.return_value = mock_model
        fake_transformers.AutoProcessor.from_pretrained.return_value = mock_processor

        descriptor = QwenVLDescriptor(model_path="/tmp/qwen", quantization="q4")
        descriptor.initialize()

        assert descriptor._model is mock_model
        assert descriptor._processor is mock_processor
        assert descriptor.is_initialized is True
        fake_transformers.BitsAndBytesConfig.assert_called_once_with(load_in_4bit=True)

    def test_describe_returns_parsed_element(self, fake_ml_modules):
        descriptor = QwenVLDescriptor(model_path="/tmp/qwen")
        descriptor._model = MagicMock()
        descriptor._processor = MagicMock()
        descriptor._processor.apply_chat_template.return_value = "prompt"
        descriptor._processor.return_value = {"input_ids": [1, 2, 3]}
        descriptor._model.generate.return_value = [[7, 8, 9]]
        descriptor._processor.batch_decode.return_value = [
            '{"type":"button","text":"Submit","confidence":0.92}'
        ]

        image = Image.new("RGB", (64, 64), color="white")
        result = descriptor.describe(image, coarse_category="interactive")

        assert isinstance(result, ElementDescription)
        assert result.type == "button"
        assert result.text == "Submit"
        assert result.confidence == pytest.approx(0.92)

    def test_describe_constrains_interactive(self, fake_ml_modules):
        descriptor = QwenVLDescriptor(model_path="/tmp/qwen")
        descriptor._model = MagicMock()
        descriptor._processor = MagicMock()
        descriptor._processor.apply_chat_template.return_value = "prompt"
        descriptor._processor.return_value = {"input_ids": [1]}
        descriptor._model.generate.return_value = [[1]]
        descriptor._processor.batch_decode.return_value = [
            '{"type":"button","text":null,"confidence":0.7}'
        ]

        image = Image.new("RGB", (48, 48), color="white")
        descriptor.describe(image, coarse_category="interactive")

        messages = descriptor._processor.apply_chat_template.call_args.args[0]
        prompt_text = messages[0]["content"][1]["text"]
        assert "button" in prompt_text
        assert "input" in prompt_text
        assert "window" not in prompt_text

    def test_describe_constrains_structural(self, fake_ml_modules):
        descriptor = QwenVLDescriptor(model_path="/tmp/qwen")
        descriptor._model = MagicMock()
        descriptor._processor = MagicMock()
        descriptor._processor.apply_chat_template.return_value = "prompt"
        descriptor._processor.return_value = {"input_ids": [1]}
        descriptor._model.generate.return_value = [[1]]
        descriptor._processor.batch_decode.return_value = [
            '{"type":"panel","text":null,"confidence":0.8}'
        ]

        image = Image.new("RGB", (48, 48), color="white")
        descriptor.describe(image, coarse_category="structural")

        messages = descriptor._processor.apply_chat_template.call_args.args[0]
        prompt_text = messages[0]["content"][1]["text"]
        assert "panel" in prompt_text
        assert "toolbar" in prompt_text
        assert "checkbox" not in prompt_text

    def test_describe_handles_bad_json(self, fake_ml_modules):
        descriptor = QwenVLDescriptor(model_path="/tmp/qwen")
        descriptor._model = MagicMock()
        descriptor._processor = MagicMock()
        descriptor._processor.apply_chat_template.return_value = "prompt"
        descriptor._processor.return_value = {"input_ids": [1]}
        descriptor._model.generate.return_value = [[1]]
        descriptor._processor.batch_decode.return_value = ["not-json"]

        image = Image.new("RGB", (48, 48), color="white")
        result = descriptor.describe(image, coarse_category="unknown")

        assert result == ElementDescription(type="unknown", text=None, confidence=0.0)

    def test_describe_validates_type_in_constrained_set(self, fake_ml_modules):
        descriptor = QwenVLDescriptor(model_path="/tmp/qwen")
        descriptor._model = MagicMock()
        descriptor._processor = MagicMock()
        descriptor._processor.apply_chat_template.return_value = "prompt"
        descriptor._processor.return_value = {"input_ids": [1]}
        descriptor._model.generate.return_value = [[1]]
        descriptor._processor.batch_decode.return_value = [
            '{"type":"window","text":"Main","confidence":0.88}'
        ]

        image = Image.new("RGB", (48, 48), color="white")
        result = descriptor.describe(image, coarse_category="interactive")

        assert result.type == "unknown"
        assert result.text == "Main"
        assert result.confidence == pytest.approx(0.88)

    def test_shutdown_releases_memory(self, fake_ml_modules):
        fake_torch, _ = fake_ml_modules

        descriptor = QwenVLDescriptor(model_path="/tmp/qwen")
        descriptor._model = MagicMock()
        descriptor._processor = MagicMock()
        descriptor.shutdown()

        assert descriptor._model is None
        assert descriptor._processor is None
        fake_torch.cuda.empty_cache.assert_called_once()

    def test_max_tokens_configurable(self, fake_ml_modules):
        descriptor = QwenVLDescriptor(model_path="/tmp/qwen", max_tokens_per_region=123)
        descriptor._model = MagicMock()
        descriptor._processor = MagicMock()
        descriptor._processor.apply_chat_template.return_value = "prompt"
        descriptor._processor.return_value = {"input_ids": [1]}
        descriptor._model.generate.return_value = [[1]]
        descriptor._processor.batch_decode.return_value = [
            '{"type":"text","text":"OK","confidence":0.75}'
        ]

        image = Image.new("RGB", (48, 48), color="white")
        descriptor.describe(image, coarse_category="unknown")

        assert descriptor._model.generate.call_args.kwargs["max_new_tokens"] == 123
