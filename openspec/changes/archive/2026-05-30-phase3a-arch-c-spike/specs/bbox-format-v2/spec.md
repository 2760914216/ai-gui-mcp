## ADDED Requirements

### Requirement: All bbox fields use [x1, y1, x2, y2] pixel coordinate format

All bbox (bounding box) fields in public and internal data models SHALL use the format `[x1, y1, x2, y2]` where (x1, y1) is the top-left corner and (x2, y2) is the bottom-right corner, both in absolute pixel coordinates relative to the containing image or screen. Coordinates SHALL be inclusive (the pixel at x2, y2 is part of the element).

This replaces the previous `[x, y, w, h]` format where (x, y) is top-left and (w, h) is width and height.

#### Scenario: ParsedElement bbox format

- **WHEN** a `ParsedElement` is created
- **THEN** its `bbox` field SHALL be a list of exactly 4 integers in the order [x1, y1, x2, y2]
- **AND** x1 < x2 and y1 < y2 for any non-empty bounding box
- **AND** all coordinates SHALL be relative to the full screenshot

#### Scenario: LayoutRegion bbox format

- **WHEN** a `LayoutRegion` is created
- **THEN** its `bbox` field SHALL be [x1, y1, x2, y2] in pixel coordinates

#### Scenario: UIElement bbox format (internal model)

- **WHEN** a `UIElement` is created with a bounding box
- **THEN** its `bbox` field SHALL be [x1, y1, x2, y2] in pixel coordinates

#### Scenario: Conversion from [x,y,w,h] to [x1,y1,x2,y2]

- **WHEN** legacy data in [x, y, w, h] format needs to be converted
- **THEN** the conversion SHALL compute: x2 = x + w, y2 = y + h
- **AND** this conversion SHALL only be applied during data migration, not in the model definitions

#### Scenario: Bbox validation

- **WHEN** a bbox is validated
- **THEN** x1 MUST be >= 0, y1 MUST be >= 0
- **AND** x2 MUST be >= x1, y2 MUST be >= y1
- **AND** x2 MUST NOT exceed screen width, y2 MUST NOT exceed screen height
