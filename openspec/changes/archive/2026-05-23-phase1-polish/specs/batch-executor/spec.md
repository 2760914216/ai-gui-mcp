## MODIFIED Requirements

### Requirement: batch execution stops on first error
The batch executor SHALL execute actions sequentially and SHALL stop at the first failure, returning a response containing the results of all successfully completed actions, the count of completed actions, the total count, and the error message from the failed action.

#### Scenario: Third action fails
- **WHEN** `batch(actions=[action1, action2, action3])` is called and `action3` fails with an error
- **THEN** `action1` and `action2` execute successfully, the batch returns `{"results": [<result1>, <result2>], "completed": 2, "total": 3, "error": "<error detail>"}`

#### Scenario: All actions succeed
- **WHEN** `batch(actions=[action1, action2, action3])` is called and all succeed
- **THEN** the batch returns `{"results": [<result1>, <result2>, <result3>], "completed": 3, "total": 3}`

### Requirement: batch supports screen actions
The batch executor SHALL support `tool: "screen"` with `action: "size"` or `action: "cursor"` in the actions list, returning their results inline in the results array.

#### Scenario: Screen size in batch
- **WHEN** `batch(actions=[{"tool":"screen","args":{"action":"size"}}])` is called
- **THEN** the screen size query executes and its result appears in the `results` array, e.g. `["2560x1600"]`

#### Scenario: Screen cursor in batch
- **WHEN** `batch(actions=[{"tool":"screen","args":{"action":"cursor"}}])` is called
- **THEN** the cursor position query executes and its result appears in the `results` array
