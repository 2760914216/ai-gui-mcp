## ADDED Requirements

### Requirement: batch tool accepts a list of mixed actions
The `batch` tool SHALL accept a parameter `actions: list[BatchAction]` where each item contains `tool` (mouse/keyboard/screen) and `args` (dict of parameters for that tool), and SHALL execute them sequentially in order.

#### Scenario: Batch with mixed mouse and keyboard actions
- **WHEN** `batch(actions=[...])` is called with a mouse click followed by a keyboard type
- **THEN** the mouse click executes first, then the keyboard type executes second

### Requirement: batch execution stops on first error
The batch executor SHALL execute actions sequentially and SHALL stop at the first failure, returning a response indicating how many actions completed and which one failed.

#### Scenario: Third action fails
- **WHEN** `batch(actions=[action1, action2, action3])` is called and `action3` fails with an error
- **THEN** `action1` and `action2` execute successfully, the batch returns `{"results": [<result1>, <result2>], "completed": 2, "total": 3, "error": "<error detail>"}`

#### Scenario: All actions succeed
- **WHEN** `batch(actions=[action1, action2, action3])` is called and all succeed
- **THEN** the batch returns `{"results": [<result1>, <result2>, <result3>], "completed": 3, "total": 3}`

### Requirement: batch validates each action via pydantic
The batch executor SHALL validate each item's `tool` field as `Literal["mouse","keyboard","screen"]` and SHALL report validation errors before any action is executed.

#### Scenario: Invalid tool name in batch
- **WHEN** `batch(actions=[{"tool":"invalid","args":{}}])` is called
- **THEN** a pydantic validation error is returned, no backend actions are executed

### Requirement: batch supports screen actions
The batch executor SHALL support `tool: "screen"` with `action: "size"` and `action: "cursor"` in the actions list, returning screen size or cursor position results inline.

#### Scenario: Screen size in batch
- **WHEN** `batch(actions=[{"tool":"screen","args":{"action":"size"}}])` is called
- **THEN** the screen size query executes and the batch completes successfully

#### Scenario: Cursor position in batch
- **WHEN** `batch(actions=[{"tool":"screen","args":{"action":"cursor"}}])` is called
- **THEN** the cursor position is returned as `{"x": int, "y": int}` and the batch completes successfully
