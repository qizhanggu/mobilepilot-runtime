# Infrastructure exclusions

The 36-task pre-frozen list produced 30 valid pairs. The six omitted tasks are deliberately split into two evidence classes.

## A. Actually run; infrastructure failure observed before Agent takeover (4)

| Task | Initialization failure | Before first action | Model call | Evidence file |
| --- | --- | --- | --- | --- |
| OsmAndMarker | `/data/data/net.osmand/databases` missing during `initialize_task` | YES | NO | `artifacts/evaluation/androidworld-v22-final-frozen36-20260817/runs.jsonl` |
| OsmAndTrack | tracks directory missing during initial `is_successful` | YES | NO | `artifacts/evaluation/androidworld-v22-final-frozen36-continuation-20260817/runs.jsonl` |
| RecipeAddMultipleRecipes | Broccoli databases directory missing during `initialize_task` | YES | NO | `artifacts/evaluation/androidworld-v22-final-frozen36-continuation2-20260817/runs.jsonl` |
| RecipeAddMultipleRecipesFromImage | host SQLite reports `no such module: FTS4` during `initialize_task` | YES | NO | `artifacts/evaluation/androidworld-v22-final-frozen36-continuation3-20260817/runs.jsonl` |

These records were emitted by the outer runner before a trace/model/action loop existed. They contain no Agent execution or model-usage fields.

## B. Not run; excluded as the same confirmed Broccoli validator family (2)

| Task | Actually run | Shared dependency evidence | Observed failure that supports exclusion |
| --- | --- | --- | --- |
| RecipeDeleteDuplicateRecipes2 | NO | inherits the same `_RecipeApp`; same Broccoli DB path/table and `SQLiteApp.initialize_task/_clear_db` path | RecipeAddMultipleRecipesFromImage FTS4 initialization failure |
| RecipeDeleteMultipleRecipesWithConstraint | NO | inherits the same `_RecipeApp`; same Broccoli DB path/table and `SQLiteApp.initialize_task/_clear_db` path | RecipeAddMultipleRecipesFromImage FTS4 initialization failure |

Code evidence: `.local/android_world/android_world/task_evals/single/recipe.py` defines one `_RecipeApp` with `/data/data/com.flauschcode.broccoli/databases/broccoli`; both delete tasks and the observed failing add task inherit this family. `.local/android_world/android_world/task_evals/common_validators/sqlite_validators.py` routes initialization through `_clear_db` and host-side SQLite operations.

Correct wording: **four tasks actually observed pre-action infrastructure failures; two additional Recipe tasks were not run after the shared Broccoli/FTS4 validator defect was confirmed.** The latter must never be described as observed `infrastructure_error` runs.
