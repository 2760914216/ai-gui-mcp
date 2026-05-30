# arch-c-spike-validation Specification

## Purpose
TBD - created by archiving change phase3a-arch-c-spike. Update Purpose after archive.
## Requirements
### Requirement: Spike validation harness loads Qwen3-VL-8B with configurable quantization

The spike validation script SHALL load Qwen3-VL-8B-Instruct via HuggingFace transformers with configurable quantization settings. It MUST support at minimum `load_in_8bit=True` (bitsandbytes INT8) and `device_map="auto"` with `torch_dtype=torch.float16` as fallback.

#### Scenario: INT8 quantization succeeds

- **WHEN** bitsandbytes is installed and GPU has sufficient VRAM for INT8
- **THEN** the model SHALL load with `load_in_8bit=True` without OOM
- **AND** inference SHALL complete within a reasonable time

#### Scenario: INT8 quantization fails, fallback to FP16 with CPU offload

- **WHEN** bitsandbytes INT8 fails (missing library or OOM)
- **THEN** the script SHALL fall back to `torch_dtype=torch.float16` with `device_map="auto"`
- **AND** SHALL log a warning about the fallback

### Requirement: Structured prompt produces JSON output with bbox elements

The spike script SHALL use a two-stage prompt strategy. The first stage SHALL request screen classification and layout regions. The second stage SHALL request detailed elements within each region. Both stages MUST instruct the model to output bbox as `[x1, y1, x2, y2]` pixel coordinates with origin at image top-left (0, 0).

#### Scenario: First stage coarse parsing

- **WHEN** a full screenshot (2560×1600 or scaled) is sent to the model with coarse parsing prompt
- **THEN** the model SHALL output JSON containing `screen_kind` (one of: ide, browser, settings, dialog, file_manager, terminal, unknown)
- **AND** the output SHALL contain `layout_regions` array where each region has `type`, `id`, `bbox` in [x1, y1, x2, y2] format

#### Scenario: Second stage fine parsing

- **WHEN** a cropped region image is sent with fine parsing prompt
- **THEN** the model SHALL output JSON containing `elements` array
- **AND** each element SHALL have: `id`, `type`, `bbox` ([x1,y1,x2,y2] in cropped image coordinates), `text` (optional), `confidence` (optional)

#### Scenario: Anti-duplication instruction

- **WHEN** the prompt instructs "Do not duplicate elements. Each UI element should appear exactly once."
- **THEN** the model SHOULD NOT repeat the same element in its output

### Requirement: Robust JSON parsing with raw output fallback

The spike script SHALL implement JSON extraction from model output that handles common formatting issues: markdown code fences (```json), trailing commas, and missing closing brackets. When JSON parsing fails, the raw model output SHALL be logged.

#### Scenario: Clean JSON output

- **WHEN** model outputs a properly formatted JSON block wrapped in ```json fence
- **THEN** the script SHALL successfully extract and parse the JSON

#### Scenario: Malformed JSON output

- **WHEN** model outputs malformed JSON that cannot be parsed
- **THEN** the script SHALL log the raw output to a file
- **AND** the script SHALL return a partial or empty result with a `model_parse_error` warning

### Requirement: Visualization script renders bbox overlays on test images

The visualization script SHALL take an AnalysisResult JSON file and the corresponding original screenshot, draw every element's bbox as a colored rectangle on the image, label each rectangle with its element index number, and save the annotated image alongside a text file mapping index numbers to element details.

#### Scenario: Bbox overlay rendering

- **WHEN** an AnalysisResult with 10 elements and the original screenshot are provided
- **THEN** the script SHALL produce a PNG image with 10 colored rectangles overlaid
- **AND** each rectangle SHALL have its index number (1, 2, 3...) displayed near the top-left corner

#### Scenario: Text mapping file

- **WHEN** the visualization script runs
- **THEN** it SHALL output a `.txt` file where each line follows format: `[N] type=button text="Save" bbox=[x1,y1,x2,y2] confidence=0.92`

### Requirement: Parameter configurability for iterative tuning

The spike script SHALL accept command-line arguments for: model path, image path, quantization mode (int8/fp16/int4), max new tokens, image scale factor, and output path. Default values SHALL be documented.

#### Scenario: Single image test for time estimation

- **WHEN** the script is invoked with `--image test.png --quantize int8 --max-tokens 2048`
- **THEN** it SHALL run inference and report elapsed time in seconds
- **AND** it SHALL save the AnalysisResult JSON to the specified output path

### Requirement: AnalysisWarning codes extended for spike diagnostics

The `AnalysisWarning.code` enumeration SHALL be extended with: `duplicate_element` (VLM repeated the same element), `hallucinated_element` (element appears to be non-existent), `model_parse_error` (VLM output could not be parsed as JSON).

#### Scenario: Duplicate element detection

- **WHEN** two elements in the output have IoU > 0.5
- **THEN** a warning with code `duplicate_element` SHALL be added to AnalysisResult.warnings
- **AND** the duplicate element with lower confidence SHALL be removed or merged

#### Scenario: Model parse error

- **WHEN** VLM output cannot be parsed as valid JSON after all recovery attempts
- **THEN** a warning with code `model_parse_error` SHALL be added
- **AND** `overall_quality` SHALL be at most "low"

