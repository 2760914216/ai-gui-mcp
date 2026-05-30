## ADDED Requirements

### Requirement: Grounding DINO-T open-vocabulary UI element detection

The spike script SHALL load Grounding DINO-T (`IDEA-Research/grounding-dino-tiny`) and run open-vocabulary object detection on COSMIC screenshots using a user-configurable text prompt. Detection SHALL output bounding boxes in `[x1, y1, x2, y2]` pixel coordinates, natural-language labels, and confidence scores for each detected region.

#### Scenario: Detection on a single COSMIC screenshot with default prompt

- **WHEN** the script is invoked with `--image vscode.png --text-prompt "button. input field. checkbox. tab. menu item. link. dialog. sidebar. toolbar. text."`
- **THEN** Grounding DINO-T SHALL output at least one detected bbox region with label and confidence score
- **AND** all bbox coordinates SHALL be within the image dimensions (0..2559, 0..1599)

#### Scenario: Detection threshold controls recall/precision tradeoff

- **WHEN** the script is invoked with `--box-threshold 0.15 --text-threshold 0.15`
- **THEN** more regions SHALL be detected than with default thresholds of 0.25
- **AND** low-confidence regions SHALL have confidence < 0.25

#### Scenario: Detection on a scaled image

- **WHEN** the script is invoked with `--img-scale 0.5`
- **THEN** the screenshot SHALL be resized to 1280×800 before detection
- **AND** output bbox coordinates SHALL be mapped back to original 2560×1600 coordinates

### Requirement: Qwen3-VL-4B element description on cropped regions

The spike script SHALL load Qwen3-VL-4B-Instruct with Q4_K_M quantization and run element description inference on each cropped bbox region from Grounding DINO-T output. Description SHALL return element type (mapped to `ParsedElement.type` enum values), text content, and confidence.

#### Scenario: Single region description

- **WHEN** a cropped region image (with 1.2× boundary expansion) is passed to Qwen3-VL-4B with prompt "Identify this UI element. Output JSON: {type: string, text: string|null, confidence: float}"
- **THEN** the model SHALL return a JSON object with type, text, and confidence fields
- **AND** type SHALL be one of: button, input, checkbox, radio, tab, menuitem, link, window, dialog, sidebar, toolbar, panel, list, table, form, text, unknown

#### Scenario: Small region skipped

- **WHEN** a bbox region has width < 32 or height < 32 pixels (after 1.2× expansion)
- **THEN** the description stage SHALL skip that region
- **AND** the element SHALL be assigned type "unknown" with confidence 0.0

#### Scenario: Description confidence extraction

- **WHEN** Qwen3-VL-4B returns a confidence value outside [0.0, 1.0] range
- **THEN** the script SHALL clamp confidence to [0.0, 1.0]

### Requirement: Pipeline orchestration (detect → describe → merge)

The spike script SHALL orchestrate detection and description stages sequentially for each screenshot: run Grounding DINO-T detection first, then for each detected bbox region crop and describe via Qwen3-VL-4B, then merge results with deduplication into a single element list.

#### Scenario: Full pipeline run on one screenshot

- **WHEN** the script is invoked with `--image COMIC-setting.png` (without `--skip-describe`)
- **THEN** it SHALL run Grounding DINO-T detection → crop N regions → run Qwen3-VL-4B description on each → merge results
- **AND** the merged element count SHALL be ≤ the detected region count (dedup may reduce)

#### Scenario: Detection-only mode

- **WHEN** the script is invoked with `--skip-describe`
- **THEN** it SHALL run only Grounding DINO-T detection
- **AND** output elements SHALL have type "unknown" and null text

#### Scenario: Duplicate element removal

- **WHEN** two detected elements have IoU > 0.5
- **THEN** the element with lower confidence SHALL be removed
- **AND** a warning with code "duplicate_element" SHALL be added to the output

#### Scenario: Detection yields zero elements

- **WHEN** Grounding DINO-T detects zero elements on a screenshot
- **THEN** the output SHALL contain an empty elements list
- **AND** `overall_quality` SHALL be "low"
- **AND** a warning with code "dense_ui_possible_misses" SHALL be added

### Requirement: AnalysisResult-compatible JSON output

The spike script SHALL output a JSON file for each screenshot that conforms to the `AnalysisResult` schema defined in `src/models.py`. The output SHALL include snapshot_id, overall_quality, warnings, layout_summary (with screen_kind="unknown" as default), and elements[] array.

#### Scenario: Output includes all required fields

- **WHEN** the pipeline completes for a screenshot
- **THEN** the JSON output SHALL contain fields: snapshot_id, overall_quality, warnings, layout_summary, elements
- **AND** elements[] items SHALL each contain: id, type, bbox, text, confidence
- **AND** bbox SHALL use `[x1, y1, x2, y2]` format with integer coordinates

#### Scenario: Output naming convention

- **WHEN** processing screenshot `COMIC-setting.png`
- **THEN** the analysis JSON SHALL be saved as `docs/spike-results/pipeline-round1/COMIC-setting_analysis.json`

### Requirement: Visual verification output

The spike script SHALL produce bbox overlay images and element text mappings for human review, using the existing `scripts/visualize_bboxes.py` script. Each screenshot SHALL produce a color-coded annotated PNG with numbered bbox labels and a companion text file mapping index numbers to element details.

#### Scenario: Annotated image generation

- **WHEN** the pipeline completes with at least one detected element
- **THEN** an annotated PNG SHALL be saved to `docs/spike-results/pipeline-round1/{name}_annotated.png`
- **AND** bbox rectangles SHALL be color-coded by element type
- **AND** each bbox SHALL have an index number label at its top-left corner

#### Scenario: Element text mapping

- **WHEN** the pipeline completes
- **THEN** a text file SHALL be saved to `docs/spike-results/pipeline-round1/{name}_elements.txt`
- **AND** each line SHALL map an index number to its element type, text, and confidence

#### Scenario: Zero elements still produces output files

- **WHEN** detection yields zero elements
- **THEN** an empty annotated PNG (original image without overlay) SHALL still be saved
- **AND** the elements text file SHALL contain "No elements detected"

### Requirement: User feedback pause points

The spike script SHALL support a single-image tuning mode that pauses after each run for user feedback, and a batch mode that runs all 8 screenshots and presents a summary comparison table.

#### Scenario: Single-image tuning mode

- **WHEN** the script is invoked with `--single --image COMIC-setting.png`
- **THEN** it SHALL process only that one image
- **AND** after producing output files, it SHALL print a brief result summary (element count, quality, notable issues)
- **AND** it SHALL NOT proceed to other images

#### Scenario: Batch mode summary

- **WHEN** the script is invoked without `--single` flag on the 8-image test directory
- **THEN** it SHALL process all 8 screenshots
- **AND** after completion, it SHALL print a summary table with columns: Screenshot, Elements, Quality, notable warnings
