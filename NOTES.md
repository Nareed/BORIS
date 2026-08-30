# NOTES — code recon for the model-output importer (M1)

Sourced from reading `boris/*.py` plus the real fixture [tests/files/test.boris](tests/files/test.boris). Line numbers are current as of this branch; re-check if `boris/core.py`/`boris/config.py` move around.

## 1. Observation window & events widget

There is **one `QMainWindow`** — `MainWindow(MainWindow, Ui_MainWindow)` in [boris/core.py:207](boris/core.py:207), UI built by generated `Ui_MainWindow.setupUi()` in [boris/core_ui.py:25](boris/core_ui.py:25). BORIS does not open a separate coding window; starting an observation reveals/populates dock widgets inside this same window.

- **Central widget** ([core_ui.py:388](boris/core_ui.py:388)): a logo panel and a status panel `w_obs_info` (labels `lbFocalSubject`, `lbCurrentStates`, button `pb_live_obs`). Both hidden until an observation starts.
- **Video**: dynamic `DW_player(QDockWidget)` docks ([boris/player_dock_widget.py:85](boris/player_dock_widget.py:85)), created in [boris/observation_operations.py:1421](boris/observation_operations.py:1421).
- **Ethogram dock**: `self.dwEthogram` → `self.twEthogram` (QTableWidget), [core_ui.py:544](boris/core_ui.py:544).
- **Subjects dock**: `self.dwSubjects` → `self.twSubjects` (QTableWidget), [core_ui.py:614](boris/core_ui.py:614).
- **Events widget**: `self.dwEvents` → `self.tv_events`, a **QTableView** (not QTableWidget), [core_ui.py:604](boris/core_ui.py:604), model `TableModel(QAbstractTableModel)` at [core.py:166](boris/core.py:166). Rows are never inserted incrementally: any change to the events list triggers `load_tw_events(obs_id)` ([core.py:2313](boris/core.py:2313)) → `populate_tv_events(...)` ([core.py:2251](boris/core.py:2251)), which rebuilds a fresh `TableModel` from `self.pj[OBSERVATIONS][obs_id][EVENTS]` and calls `self.tv_events.setModel(model)` ([core.py:2308](boris/core.py:2308)).
- **Toolbar**: `self.toolBar` ([core_ui.py:540](boris/core_ui.py:540)) — see §6 for why this is the import-button hook point.

## 2. In-memory event model

Whole project lives in `self.pj` (set in `load_project`, [core.py:2797](boris/core.py:2797)). Each observation ([observation_operations.py:1064](boris/observation_operations.py:1064)) has an `"events"` list. **Confirmed against the real fixture** ([tests/files/test.boris:39-53](tests/files/test.boris:39)):

```json
"events": [
  [22.425, "", "p", "", ""],
  [199.96, "", "p", "", ""]
]
```

Each event is a plain Python **list** (`[time, subject, code, modifier, comment]` for LIVE/legacy; MEDIA adds a trailing frame index, IMAGES adds trailing image index + path — [config.py:324-343](boris/config.py:324)). `time` is a `decimal.Decimal` in memory, plain JSON number on disk. Field-index constants: `EVENT_TIME_FIELD_IDX=0`, `EVENT_SUBJECT_FIELD_IDX=1`, `EVENT_BEHAVIOR_FIELD_IDX=2`, `EVENT_MODIFIER_FIELD_IDX=3`, `EVENT_COMMENT_FIELD_IDX=4` ([config.py:349-354](boris/config.py:349)).

**⚠ STATE event pairing — no explicit start/stop flag.** A state behavior (`"type": "State event"` in the ethogram, e.g. code `"s"`) is stored as **two ordinary event rows with the identical code**; BORIS pairs them by chronological order per (subject, code) — first occurrence = start, second = stop, odd count = UNPAIRED. Confirmed in the fixture, observation `"2 video"` ([tests/files/test.boris:814-828](tests/files/test.boris:814)):
```json
"events": [
  [10.0, "subject1", "s", "", ""],
  [170.0, "subject1", "s", "", ""]
]
```
and in observation `"modifiers"` ([tests/files/test.boris:722-771](tests/files/test.boris:722)), where a modifier value round-trips across a start/stop pair (both rows of a pair carry the same modifier: `"m1"`/`"m1"`, `"None"`/`"None"`). **Implication for the importer (FR-2/FR-6):** when converting a CSV START+STOP pair into BORIS events, insert two list entries with the same behavior code, the same subject, the same modifier, at their respective times — do NOT invent a separate "is_start" field. Insertion order across the whole list must keep every (subject, code) pair's start before its stop in time order (`bisect.insort`, see §3, already guarantees overall time-sortedness, but cross-check pairing after insert — BORIS's own UNPAIRED detection is the safety net).

Ethogram entry shape confirmed in fixture ([tests/files/test.boris:1396-1436](tests/files/test.boris:1396)): `{"type": "Point event"|"State event", "key", "code", "description", "category", "modifiers": {...}, "excluded", "coding map"}`. Subject entry shape ([tests/files/test.boris:5-16](tests/files/test.boris:5)): `{"key", "name", "description"}`.

## 3. Key calls: adding an event, setting its subject

Appending happens in [boris/write_event.py:37](boris/write_event.py:37), `write_event(self, event: dict, mem_time: dec)`:
- LIVE/MEDIA: `bisect.insort(self.pj[OBSERVATIONS][obsId][EVENTS], [mem_time, subject, code, modifier_str, comment])` ([write_event.py:496-505](boris/write_event.py:496)) — keeps the list time-sorted on insert.
- IMAGES: `.append(...)` then explicit `.sort(...)` ([write_event.py:507-514](boris/write_event.py:507)).
- Editing an existing row overwrites `EVENTS[event["row"]]` in place ([write_event.py:456-493](boris/write_event.py:456)).
- After any change: `self.load_tw_events(self.observationId)` ([write_event.py:517](boris/write_event.py:517)) refreshes the events widget (§1).

**Subject on a new event**: `self.currentSubject` (string, `""` = none) is set only via `update_subject(subject)` ([core.py:1631](boris/core.py:1631)). A coded-behavior event dict built by `full_event(self, behavior_idx)` ([core.py:4763](boris/core.py:4763)) is a copy of the ethogram entry and carries **no** `"subject"` key. In `write_event`:
```python
# write_event.py:120
subject = event.get(cfg.SUBJECT, self.currentSubject)
```
so a freshly-coded event's subject always falls back to `self.currentSubject`. **For the importer**: build each event dict with `event["subject"]` pre-populated to the resolved CSV/mapped subject name before calling `write_event`, so this line picks it up directly instead of falling back to whatever the UI's current focal subject happens to be — this is exactly the `.get(..., default)` escape hatch import code should use.

## 4. How the ethogram and subject list are read

On project load, `project_functions.open_project_json(...)` ([project_functions.py:1336](boris/project_functions.py:1336)) does `json.loads(...)`, then `util.convert_time_to_decimal(pj)` ([utilities.py:416-437](boris/utilities.py:416)) walks every event and converts JSON time numbers back to `Decimal`. `MainWindow.load_project(...)` ([core.py:2785](boris/core.py:2785)):
```python
self.pj = dict(pj)
self.load_behaviors_in_twEthogram([...pj[cfg.ETHOGRAM][x][cfg.BEHAVIOR_CODE]...])  # core.py:2800
self.load_subjects_in_twSubjects([...pj[cfg.SUBJECTS][x][cfg.SUBJECT_NAME]...])    # core.py:2801
```
`pj[ETHOGRAM]` (JSON key `"behaviors_conf"`) and `pj[SUBJECTS]` (JSON key `"subjects_conf"`) are dicts keyed by an arbitrary string index (`"0"`, `"1"`, …) — **for the importer, iterate `.values()` and match on the `code`/`name` field, not the dict key.** `load_subjects_in_twSubjects` ([core.py:4487-4509](boris/core.py:4487)) also rebuilds `self.subject_name_index` (subject name → pj-key), reusable for the importer's subject lookups instead of re-deriving it.

## 5. Saving events into the .boris JSON

`save_project_json(self, project_file_name)` ([core.py:3282](boris/core.py:3282)):
```python
json.dumps(self.pj, default=util.decimal_default, indent=file_indentation)  # core.py:3320
```
`decimal_default` ([utilities.py:936-939](boris/utilities.py:936)) converts each in-memory `Decimal` time to a rounded `float`; no tuple→list step needed since events are already plain lists. **Importer doesn't need to call this directly** — inserting into `self.pj[OBSERVATIONS][obs_id][EVENTS]` via `write_event` (or matching its list shape) is sufficient; the existing Save/Save As entry points ([core.py:3455](boris/core.py:3455), [core.py:3366](boris/core.py:3366)) handle serialization unchanged.

## 6. Modal dialogs — pattern to follow for confirm/mapping prompts

Two patterns, both ending in PySide6's `.exec_()`/`.exec()` (blocks until closed, returns `Accepted`/`Rejected`):

- **Custom `QDialog` subclass**, built then `.exec_()`'d by the caller — use this for the **overwrite-confirmation** and **behavior/subject map-or-add** dialogs (FR-4, FR-5, FR-11), since they need to show data and return structured results. Model: `select_modifiers.ModifiersList(QDialog)` ([select_modifiers.py:45](boris/select_modifiers.py:45)), invoked from [write_event.py:278-284](boris/write_event.py:278):
  ```python
  modifiers_selector = select_modifiers.ModifiersList(code, modifiers_dict, currentModifiers)
  r = modifiers_selector.exec_()
  if r:
      selected_modifiers = modifiers_selector.get_modifiers()
  ```
  Same shape: `edit_event.DlgEditEvent` ([edit_event.py:43](boris/edit_event.py:43)), `observation.Observation` ([observation.py:101](boris/observation.py:101)).
- **Module-level function** building a dialog internally, returning plain data — use this for a simpler one-off like the **file picker** (a `QFileDialog.getOpenFileName(...)` call is enough, no custom class needed). Model: `select_subj_behav.choose_obs_subj_behav_category(...)` ([select_subj_behav.py:36](boris/select_subj_behav.py:36)).

A plain `QMessageBox.question(...)` (Yes/No) is the natural choice for the overwrite-confirmation prompt specifically (FR-11) — simplest correct tool, no custom dialog class needed there.

## 7. Where the "Import model outputs" button goes (FR-1)

`self.toolBar` ([core_ui.py:540](boris/core_ui.py:540)) is **always visible** — never hidden by the startup `setVisible(False)` calls that hide the docks — making it the correct home for a control that must be "a clear, visible element in the observation window... enabled while an observation is open" (FR-1), not tucked in a menu.

Precedent for adding a custom widget directly in `MainWindow.__init__`, commented out at [core.py:357-375](boris/core.py:357):
```python
self.tb_export = QToolButton()
...
self.toolBar.addWidget(self.tb_export)
```
To add the real button:
1. Add a `QAction`/`QToolButton` to `self.toolBar` (in `MainWindow.__init__`, [core.py:348-429](boris/core.py:348), following the `tb_export` template — avoids touching Designer-generated `core_ui.py`).
2. Wire `.triggered` in `connections.connections(self)` ([connections.py:56](boris/connections.py:56), called from [core.py:434](boris/core.py:434)).
3. Register enable/disable state in `menu_options.update_menu(self)` ([menu_options.py:50](boris/menu_options.py:50)) — gate on "an observation is open" per FR-1, same pattern used for other observation-only actions.

## 8. Test suite — known issues (found while verifying M0/M1, not fixed here)

- **Run tests from inside `tests/`**, matching `tests/Makefile` (`pytest -s -vv`), not from the repo root — several tests use fixture paths relative to `tests/` (e.g. `files/test.boris`) and fail with `FileNotFoundError` otherwise.
- **`boris/utilities.py` calls `sys.exit(5)` at import time** if it can't resolve libmpv via `%PATH%` ([utilities.py:106](boris/utilities.py:106)). Normally [boris/core.py:28](boris/core.py:28) prepends `boris/misc` to `PATH` before anything imports `utilities`, but pytest imports submodules directly and never goes through `core.py`, so the whole pytest process dies unless `boris/misc` (where `libmpv-2.dll` lives after the auto-download) is put on `PATH` manually first, e.g. `PATH="$PWD/boris/misc:$PATH" pytest ...` from `tests/`.
- **`tests/test_observation_gui.py` and `tests/test_preferences_gui.py`** still `import PyQt5.QtCore` — stale from before this fork's PySide6 migration; PyQt5 isn't a dependency anymore. Currently excluded via `--ignore`, not fixed.
- **36 pre-existing test failures** remain even after the two fixes above and running from the right cwd (down from 81 failing when run incorrectly from repo root). They span `test_export_observation.py`, `test_time_budget.py`, `test_otx_parser.py`, `test_irr.py`, `test_project_functions.py`, `test_utilities.py`/`test_utilities2.py`, and `test_boris_cli.py` — unrelated to each other and to this milestone's changes. Likely cause: the `numpy`/`pandas`/`scipy` versions pinned in `pyproject.toml` are notably newer than what `requirements.lock`/`requirements-dev.lock` show (those lock files are themselves stale, predating the `uv`/PySide6 migration — see [CLAUDE.md](CLAUDE.md) setup notes) — i.e. dependency drift, not anything touched in M0/M1. Not triaged individually; flagging for whoever picks up test-suite health as its own task.

## 9. Open items for M2+

- OQ-1 (track-ID column name) still unresolved upstream in the spec — parser should treat any unmatched/blank Subject as subject-free and not assume a specific column name yet.
- No CSV parser exists in this codebase yet — will be new code under `boris/`, not adapting an existing importer.
- Fixtures available for tests: [tests/files/test.boris](tests/files/test.boris), [tests/files/test2.boris](tests/files/test2.boris), plus modifier/edge-case variants in the same folder.
