from __future__ import annotations

# pyright: reportUnknownMemberType=false, reportAny=false, reportInvalidCast=false, reportUnknownVariableType=false

import json
from dataclasses import dataclass
from typing import ClassVar
from typing import Protocol
from typing import cast

from PIL import Image


@dataclass
class ElementDescription:
    type: str
    text: str | None
    confidence: float


class _QwenModel(Protocol):
    def generate(self, **kwargs: object) -> object:
        ...


class _QwenProcessor(Protocol):
    def apply_chat_template(
        self,
        conversation: object,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str:
        ...

    def __call__(
        self,
        *,
        text: list[str],
        images: list[Image.Image],
        return_tensors: str,
    ) -> dict[str, object]:
        ...

    def batch_decode(self, generated_ids: object, skip_special_tokens: bool) -> list[str]:
        ...


INTERACTIVE_TYPES = ["button", "input", "checkbox", "radio", "tab", "menuitem", "link"]
STRUCTURAL_TYPES = ["window", "dialog", "sidebar", "toolbar", "panel", "list", "table", "form"]
ALL_TYPES = INTERACTIVE_TYPES + STRUCTURAL_TYPES + ["text", "unknown"]


class QwenTypeMapper:
    INTERACTIVE_TYPES: ClassVar[list[str]] = INTERACTIVE_TYPES
    STRUCTURAL_TYPES: ClassVar[list[str]] = STRUCTURAL_TYPES
    ALL_TYPES: ClassVar[list[str]] = ALL_TYPES


def constrain_by_category(coarse: str) -> list[str]:
    if coarse == "interactive":
        return INTERACTIVE_TYPES
    if coarse == "structural":
        return STRUCTURAL_TYPES
    return ALL_TYPES


class QwenVLDescriptor:
    def __init__(self, model_path: str, quantization: str = "q4", max_tokens_per_region: int = 64):
        try:
            __import__("torch")
            __import__("transformers")
        except ImportError as exc:
            raise ImportError("Missing vision deps. Install: pip install ai-gui-mcp[vision]") from exc

        self._model_path: str = model_path
        self._quantization: str = quantization
        self._max_tokens: int = max_tokens_per_region
        self._model: _QwenModel | None = None
        self._processor: _QwenProcessor | None = None

    def initialize(self):
        import torch
        from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration

        if self._quantization == "q4":
            quant_config = BitsAndBytesConfig(load_in_4bit=True)
            model_obj: object = cast(
                object,
                Qwen3VLForConditionalGeneration.from_pretrained(
                    self._model_path,
                    device_map="auto",
                    trust_remote_code=True,
                    quantization_config=quant_config,
                ),
            )
            self._model = cast(_QwenModel, model_obj)
        elif self._quantization == "none":
            model_obj = cast(
                object,
                Qwen3VLForConditionalGeneration.from_pretrained(
                    self._model_path,
                    device_map="auto",
                    trust_remote_code=True,
                    torch_dtype=torch.float16,
                ),
            )
            self._model = cast(_QwenModel, model_obj)
        else:
            raise ValueError(f"Unsupported quantization: {self._quantization}")
        processor_obj: object = cast(
            object,
            AutoProcessor.from_pretrained(
                self._model_path,
                trust_remote_code=True,
            ),
        )
        self._processor = cast(_QwenProcessor, processor_obj)

    def _build_prompt(self, coarse_category: str, allowed_types: list[str]) -> str:
        type_scope = ", ".join(allowed_types)
        return (
            "Identify this UI element. "
            f"You must choose from these types only: [{type_scope}]. "
            "Output EXACTLY this JSON format (no markdown, no extra text):\n"
            '{"type": "<one of the allowed types>", '
            '"text": "<visible text or null>", '
            '"confidence": <0.0-1.0>}'
        )

    def _parse_response(self, response_text: str) -> dict[str, object]:
        assistant_idx = response_text.rfind("assistant\n")
        if assistant_idx >= 0:
            response_text = response_text[assistant_idx + len("assistant\n"):]
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON object found")
        return cast(dict[str, object], json.loads(response_text[start : end + 1]))

    def describe(self, crop: Image.Image, coarse_category: str) -> ElementDescription:
        if not self.is_initialized:
            raise RuntimeError("QwenVLDescriptor is not initialized")

        model = self._model
        processor = self._processor
        if model is None or processor is None:
            raise RuntimeError("QwenVLDescriptor is not initialized")

        allowed_types = constrain_by_category(coarse_category)
        prompt = self._build_prompt(coarse_category, allowed_types)

        system_text = (
            "You are a precise UI element analyzer. Identify the given UI element "
            "crop and output ONLY a JSON object. Do not include any other text."
        )
        messages = [
            {"role": "system", "content": [{"type": "text", "text": system_text}]},
            {"role": "user", "content": [
                {"type": "image", "image": crop},
                {"type": "text", "text": prompt},
            ]},
        ]
        prompt_text = processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
        )
        model_inputs = processor(
            text=[prompt_text],
            images=[crop],
            return_tensors="pt",
            padding=True,
        )
        model_inputs = model_inputs.to(model.device)
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=self._max_tokens,
            do_sample=False,
            repetition_penalty=1.1,
        )
        response_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        try:
            payload = self._parse_response(response_text)
        except Exception:
            return ElementDescription(type="unknown", text=None, confidence=0.0)

        parsed_type_obj = payload.get("type", "unknown")
        parsed_type = parsed_type_obj if isinstance(parsed_type_obj, str) else "unknown"
        if parsed_type not in allowed_types:
            parsed_type = "unknown"

        parsed_text_obj = payload.get("text")
        parsed_conf_obj = payload.get("confidence", 0.0)
        if isinstance(parsed_conf_obj, (int, float, str)):
            try:
                parsed_conf = float(parsed_conf_obj)
            except ValueError:
                parsed_conf = 0.0
        else:
            parsed_conf = 0.0

        if parsed_conf < 0.0:
            parsed_conf = 0.0
        if parsed_conf > 1.0:
            parsed_conf = 1.0

        parsed_text = parsed_text_obj if isinstance(parsed_text_obj, str) else None

        return ElementDescription(type=parsed_type, text=parsed_text, confidence=parsed_conf)

    def shutdown(self):
        import torch

        self._model = None
        self._processor = None
        if hasattr(torch, "cuda") and hasattr(torch.cuda, "empty_cache"):
            torch.cuda.empty_cache()

    @property
    def is_initialized(self) -> bool:
        return self._model is not None and self._processor is not None
