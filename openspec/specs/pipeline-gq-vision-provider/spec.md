## Purpose

Define the Pipeline GQ VisionProvider — a local two-stage pipeline that combines Grounding DINO-T open-vocabulary UI element detection with Qwen3-VL-4B crop-region description to produce structured `AnalysisResult` output. This capability replaces the `DummyVisionProvider` stub and enables `screen(action="analyze")` to return real GUI parsing results.

## ADDED Requirements

### Requirement: PipelineGQVisionProvider implements VisionProvider interface

The system SHALL provide a `PipelineGQVisionProvider` class that implements the `VisionProvider` abstract interface, accepting a `RawImage` and optional `A11yTree` and returning an `AnalysisResult`.

#### Scenario: PipelineGQ parses a COSMIC screenshot

- **WHEN** `PipelineGQVisionProvider.parse(image)` is called with a valid 2560×1600 COSMIC screenshot
- **THEN** it SHALL return an `AnalysisResult` with `snapshot_id` set, `elements` containing detected UI elements, and `overall_quality` set to "medium" or "high"
- **AND** each element SHALL have `id`, `type`, `bbox`, and `confidence` populated

#### Scenario: PipelineGQ returns partial results on detection failure

- **WHEN** GDINO detects zero elements from the screenshot
- **THEN** the result SHALL contain `elements: []` and `overall_quality: "low"`
- **AND** SHALL NOT include a warning (empty elements is a valid outcome)

#### Scenario: PipelineGQ respects effort configuration

- **WHEN** `PipelineGQVisionProvider` is initialized with `effort="low"`
- **THEN** it SHALL use GDINO box_threshold=0.17 for high-precision detection
- **WHEN** initialized with `effort="high"`
- **THEN** it SHALL use GDINO box_threshold=0.13 for high-coverage detection

### Requirement: Two-stage pipeline — GDINO detection then Qwen description

The system SHALL implement GUI parsing as a sequential two-stage pipeline: Stage 1 (GDINO detection) produces bounding boxes, Stage 2 (Qwen description) classifies each cropped region.

#### Scenario: Detection stage uses open-vocabulary text prompt

- **WHEN** Stage 1 runs Grounding DINO-T inference
- **THEN** it SHALL accept a configurable `text_prompt` parameter (e.g., `"button. input field. checkbox. tab. menu item."`)
- **AND** return detected bounding boxes with labels and detection confidence scores

#### Scenario: Description stage operates on cropped regions

- **WHEN** Stage 2 processes each detected bbox
- **THEN** it SHALL crop the region from the screenshot at 1.2× the bbox dimensions
- **AND** SHALL skip regions where the shortest side is below `min_crop_size` (32px for full-screen, 16px for sub-1024×768)
- **AND** invoke Qwen3-VL-4B to output element type, text, and confidence for each crop

#### Scenario: Zero-element detection skips description stage

- **WHEN** GDINO detects zero elements
- **THEN** the description stage SHALL be skipped entirely
- **AND** the pipeline returns immediately with empty elements list

### Requirement: Type classification via coarse-to-fine label mapping

The system SHALL determine `ParsedElement.type` through a two-stage mapping: GDINO label determines a coarse category (interactive / structural / unknown), constraining Qwen's fine-grained type selection.

#### Scenario: GDINO label maps to interactive category

- **WHEN** a GDINO label contains "button", "text", "input", "check", or "radio"
- **THEN** the coarse category SHALL be "interactive"
- **AND** Qwen's type selection SHALL be constrained to {button, input, checkbox, radio, tab, menuitem, link}

#### Scenario: GDINO label maps to structural category

- **WHEN** a GDINO label contains "window", "menu", "sidebar", "toolbar", "panel", "list", or "table"
- **THEN** the coarse category SHALL be "structural"
- **AND** Qwen's type selection SHALL be constrained to {window, dialog, sidebar, toolbar, panel, list, table, form}

#### Scenario: Unknown GDINO label falls back to unconstrained selection

- **WHEN** a GDINO label does not match any coarse-category keyword
- **THEN** the coarse category SHALL be "unknown"
- **AND** Qwen SHALL select from the full 17-value type enum

### Requirement: Confidence uses GDINO detection score

The system SHALL populate `ParsedElement.confidence` with the GDINO detection score for each element, until Qwen description confidence is reliable enough to contribute.

#### Scenario: Confidence reflects detection quality

- **WHEN** GDINO detects an element with box_confidence=0.23
- **THEN** `ParsedElement.confidence` SHALL be 0.23
- **AND** the Qwen output confidence SHALL NOT override this value

#### Scenario: Element-level confidence is a single numeric field

- **WHEN** a `ParsedElement` is produced by the vision pipeline
- **THEN** it SHALL contain a single `confidence` field (float, 0.0–1.0)
- **AND** SHALL NOT expose separate detection and classification confidence fields

### Requirement: Post-processing pipeline for quality control

The system SHALL apply a three-stage post-processing pipeline to raw GDINO detections before Qwen description: area filtering, IoU deduplication, and min-size cropping.

#### Scenario: Oversized bounding boxes are filtered

- **WHEN** a detected bbox covers >50% of the total screen area
- **THEN** it SHALL be removed from the elements list before description

#### Scenario: Duplicate bounding boxes are merged

- **WHEN** two detected bboxes have IoU > 0.5
- **THEN** the element with lower GDINO confidence SHALL be removed
- **AND** a warning with code `duplicate_element` SHALL be added

#### Scenario: Crop size adapts to input resolution

- **WHEN** the input image resolution is ≤ 1024×768
- **THEN** `min_crop_size` SHALL be 16px
- **WHEN** the input image resolution is > 1024×768
- **THEN** `min_crop_size` SHALL be 32px

### Requirement: Model lazy-loading and idle shutdown

The system SHALL NOT load models into GPU memory at import or construction time. Model loading SHALL be deferred until `initialize()` is called. The system SHALL support unloading models via `shutdown()` to free GPU memory after a configurable idle period.

#### Scenario: Construction does not load models

- **WHEN** `PipelineGQVisionProvider(config)` is instantiated
- **THEN** no CUDA/GPU allocation SHALL occur
- **AND** `parse()` SHALL implicitly call `initialize()` on first invocation if not already initialized

#### Scenario: Idle shutdown after timeout

- **WHEN** `idle_shutdown_sec` seconds have elapsed since the last `parse()` call
- **THEN** the orchestrator MAY call `shutdown()` to unload models and free GPU memory

#### Scenario: Import guard prevents GPU-less import failures

- **WHEN** PyTorch or transformers are not installed
- **THEN** instantiating `PipelineGQVisionProvider` SHALL raise `ImportError` with installation instructions
- **AND** the error SHALL mention `pip install ai-gui-mcp[vision]`

### Requirement: Configuration-driven provider selection

The system SHALL select the active `VisionProvider` implementation based on `config.yaml`'s `perception.providers.vision.backend` field, supporting at minimum `"dummy"` and `"pipeline_gq"`.

#### Scenario: Backend selects dummy provider

- **WHEN** `config.yaml` has `vision.backend: "dummy"`
- **THEN** `server.py` SHALL instantiate `DummyVisionProvider`

#### Scenario: Backend selects pipeline_gq provider

- **WHEN** `config.yaml` has `vision.backend: "pipeline_gq"`
- **THEN** `server.py` SHALL instantiate `PipelineGQVisionProvider` with the `pipeline_gq` config section

#### Scenario: PipelineGQ parameters are fully configurable

- **WHEN** `config.yaml` specifies pipeline_gq parameters (model paths, thresholds, prompt text, etc.)
- **THEN** `PipelineGQVisionProvider` SHALL use the configured values rather than hardcoded defaults
