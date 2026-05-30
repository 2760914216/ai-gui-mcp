## MODIFIED Requirements

### Requirement: UIElement model for structured GUI elements

The existing `UIElement` SHALL be retained as an internal/perception model. The new `ParsedElement` (defined in `gui-parser-result`) SHALL be the public-facing element model for `AnalysisResult`.

#### Scenario: UIElement continues to serve internal providers

- **WHEN** a provider (accessibility or vision) discovers elements
- **THEN** it MAY use `UIElement` as an internal representation
- **AND** `PerceptionService` SHALL convert `UIElement` to `ParsedElement` for public output

#### Scenario: ParsedElement replaces UIElement in public API

- **WHEN** `AnalysisResult.elements` is populated
- **THEN** each element SHALL be a `ParsedElement` with fields: `id`, `type` (controlled enum), `bbox` ([x1,y1,x2,y2]), `text`, `description`, `confidence`, `parent_id`, `children_ids`, `region_ref`

#### Scenario: Minimum viable UIElement

- **WHEN** only element identity is known without position or role
- **THEN** a `UIElement` with only `id` populated (and all others defaulting to None) SHALL be valid

#### Scenario: UIElement bbox format

- **WHEN** a `UIElement` has a bounding box
- **THEN** its `bbox` field SHALL be a list of 4 ints in [x1, y1, x2, y2] format
