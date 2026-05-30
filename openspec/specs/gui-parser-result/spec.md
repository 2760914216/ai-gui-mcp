## Purpose

Define the structured output models for GUI parsing results — `AnalysisResult`, `ParsedElement`, `LayoutSummary`, `AnalysisWarning`, and related types — consumed by the P3A intelligence layer and returned by `screen(action="analyze")`.
## Requirements
### Requirement: AnalysisResult as P3A primary output

The system SHALL define an `AnalysisResult` pydantic model as the primary structured output of the GUI parser. It SHALL NOT include a top-level `source` field.

#### Scenario: AnalysisResult structure

- **WHEN** a GUI parser produces an `AnalysisResult`
- **THEN** it SHALL contain: `snapshot_id` (str), `overall_quality` (Literal["high","medium","low"]), `warnings` (list of AnalysisWarning), `layout_summary` (LayoutSummary), and `elements` (list of ParsedElement)

### Requirement: ParsedElement with flat list organization

The system SHALL define a `ParsedElement` model with a flat identifier-based hierarchy: `parent_id` and `children_ids` for local structure, `region_ref` for global layout membership.

#### Scenario: ParsedElement fields

- **WHEN** a `ParsedElement` is created
- **THEN** it SHALL have: `id` (str), `type` (controlled enum), `bbox` (list of 4 ints [x1,y1,x2,y2]), `text` (str or null), `description` (str or null), `confidence` (float or null), `parent_id` (str or null), `children_ids` (list of str), `region_ref` (str or null)

#### Scenario: Minimum viable element

- **WHEN** only element identity and position are known
- **THEN** a `ParsedElement` with only `id`, `type`, and `bbox` populated SHALL be valid

#### Scenario: Element type controlled enum

- **WHEN** a `ParsedElement.type` is set
- **THEN** it MUST be one of: `button`, `input`, `checkbox`, `radio`, `tab`, `menuitem`, `link`, `window`, `dialog`, `sidebar`, `toolbar`, `panel`, `list`, `table`, `form`, `text`, `unknown`

### Requirement: LayoutSummary with screen classification and region detection

The system SHALL define a `LayoutSummary` model providing a high-level characterization of the screen.

#### Scenario: LayoutSummary structure

- **WHEN** a `LayoutSummary` is created
- **THEN** it SHALL contain: `screen_kind` (ScreenKind with `kind` and optional `detail`), `main_regions` (list of LayoutRegion), `active_dialog` (ActiveDialogInfo), `notes` (str or null)

#### Scenario: ScreenKind classification

- **WHEN** `screen_kind.kind` is set
- **THEN** it MUST be one of: `ide`, `browser`, `settings`, `dialog`, `file_manager`, `terminal`, `unknown`

#### Scenario: LayoutRegion fields

- **WHEN** a `LayoutRegion` is created
- **THEN** it SHALL contain: `id` (str), `type` (one of: `sidebar`, `toolbar`, `editor`, `content`, `dialog`, `panel`, `list`, `table`, `form`, `unknown`), `bbox` (list of 4 ints [x1,y1,x2,y2]), `detail` (str or null)

#### Scenario: ActiveDialog detection

- **WHEN** a dialog or popup is visible and has focus
- **THEN** `active_dialog.present` SHALL be `true`
- **AND** `active_dialog.region_ref` and `active_dialog.element_ref` SHALL reference the dialog's region or element

### Requirement: Structured warnings with controlled codes

The system SHALL use structured `AnalysisWarning` objects rather than plain text for quality signals.

#### Scenario: AnalysisWarning fields

- **WHEN** an `AnalysisWarning` is created
- **THEN** it SHALL contain: `code` (controlled enum), `severity` (Literal["low","medium","high"]), `message` (str)

#### Scenario: Warning code enumeration

- **WHEN** a `warning.code` is set
- **THEN** it MUST be one of: `image_unavailable`, `provider_timeout`, `dense_ui_possible_misses`, `ocr_low_confidence`, `partial_parse`, `unsupported_layout`, `low_visibility_elements`, `duplicate_element`, `hallucinated_element`, `model_parse_error`

### Requirement: Best-effort parsing with quality indicators

The system SHALL treat GUI parsing as best-effort. Partial results SHALL be returned when full parsing is not possible, with quality and confidence indicating trustworthiness.

#### Scenario: Partial parse with medium quality

- **WHEN** the parser identifies most but not all interactive elements on a dense screen
- **THEN** `overall_quality` SHALL be `"medium"`
- **AND** a warning with code `dense_ui_possible_misses` SHALL be included
- **AND** `elements` SHALL contain all identified elements

#### Scenario: Low-quality parse still returns elements

- **WHEN** OCR or vision parsing produces low-confidence results
- **THEN** `overall_quality` SHALL be `"low"`
- **AND** `elements` MAY still contain elements with low `confidence` values
- **AND** the system SHALL NOT raise an error or return an empty result

#### Scenario: Element-level confidence for vision-sourced elements

- **WHEN** an element is identified via visual recognition
- **THEN** its `confidence` field SHALL contain a numeric value (0.0 to 1.0)
- **WHEN** an element is identified via accessibility tree
- **THEN** its `confidence` field SHALL be `null`

### Requirement: ScreenState for immediate state queries

The system SHALL define a `ScreenState` model for `size` and `cursor` queries, independent of perception results.

#### Scenario: ScreenState from size query

- **WHEN** `screen(action="size")` is called
- **THEN** the response SHALL contain `width` and `height` fields

#### Scenario: ScreenState from cursor query

- **WHEN** `screen(action="cursor")` is called
- **THEN** the response SHALL contain `cursor_x`, `cursor_y`, and `cursor_source` fields
- **AND** `cursor_source` SHALL be `"tracked"` on Wayland/COSMIC

### Requirement: Post-processing deduplication by IoU

The system SHOULD detect and remove duplicate elements from VLM output. Two elements SHALL be considered duplicates when their bbox IoU (Intersection over Union) exceeds 0.5.

#### Scenario: Duplicate elements with different confidence

- **WHEN** two ParsedElements have IoU > 0.5
- **THEN** the element with lower confidence SHALL be removed from the elements list
- **AND** a warning with code `duplicate_element` SHALL be added

#### Scenario: Duplicate elements with equal confidence

- **WHEN** two ParsedElements have IoU > 0.5 and equal confidence
- **THEN** the element appearing later in the list SHALL be removed
- **AND** a warning with code `duplicate_element` SHALL be added

