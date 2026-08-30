# PROGRESS

## 2026-08-30 — M0-M1: environment setup docs + code recon (NOTES.md)

**What changed:**
- Confirmed environment fix from an earlier session (Anaconda base env's conda `Library\bin` conflicted with PySide6; fixed by installing `uv` and running `uv sync` for an isolated `.venv`) and recorded the exact commands, pinned version (`v9.14`, matches upstream's latest stable tag and PyPI release), and mpv notes into CLAUDE.md's Setup/run section.
- Wrote NOTES.md: observation window/events widget structure, in-memory event model (verified against the real fixture `tests/files/test.boris`, including how STATE start/stop pairs are stored with no explicit flag — just two same-code rows paired by chronological order), the `write_event`/`update_subject`/`full_event` calls, ethogram/subject read paths, save-to-.boris serialization, the two dialog patterns used in this codebase, and the toolbar hook point for the future "Import model outputs" button.
- Fixed a real bug in `boris/player_dock_widget.py`: bare `import config`/`import gui_utilities`/`import ipc_mpv` instead of package-relative imports — this broke importing several test modules entirely.

**Key files touched:** `CLAUDE.md`, `NOTES.md` (new), `boris/player_dock_widget.py`.

**Left open:**
- Test suite has 36 pre-existing failures unrelated to this milestone (likely numpy/pandas/scipy version drift vs. what the tests expect) — logged in NOTES.md §8, not triaged or fixed.
- Two stale test files (`tests/test_observation_gui.py`, `tests/test_preferences_gui.py`) still import PyQt5 and are currently excluded via `--ignore` rather than updated.
- OQ-1 (unknown-cat track-ID column name) still unresolved upstream in the spec.
- M2 (import happy path) not started.

## 2026-08-30 — Spec interview + M2: import happy path

**What changed:**
- Interviewed on four implementation-level gaps the Notion spec didn't cover; wrote `SPEC.md` (track ID deferred entirely to M5, subject colors hash-derived from name, fast-assignment UI built into the existing events table, active-subject key reuses `self.currentSubject`). Mirrored to the Notion page (OQ-9/10/11, Progress log).
- Implemented M2: "Import model outputs" `QToolButton` on the always-visible toolbar (enabled only while an observation is open); file picker; parses the BORIS tabular events CSV; filters to the active observation's rows; case-insensitive auto-match for behaviors and subjects; overwrite confirmation when the observation already has events; a new `TypeConflictDialog` (per-behavior skip-vs-use-CSV-type choice) for when the CSV's START/STOP-vs-POINT disagrees with the ethogram — a decision added this session, not in the original spec; direct event insertion (see correction below); a summary dialog reporting imported/skipped/subject-free counts.
- **Correction to M1's own NOTES.md**: `write_event()` turns out to be a full live-coding state machine (state-toggle inference, a modal modifier dialog per call, assumes a live player) — unsafe to call in a bulk-import loop. Verified by reading the whole function, not just the append lines. The importer builds event rows directly instead, matching `write_event`'s own list shape via `bisect.insort`, with one batched UI refresh at the end.
- Added `tests/test_model_import.py`: 16 unit tests for CSV parsing, ethogram/subject matching, START/STOP pairing, malformed-sequence detection, and type-conflict detection/resolution — all pass, no QApplication needed. Full suite re-run: still exactly the same 36 pre-existing failures, no regressions.
- Launched the app to confirm the new button doesn't crash startup; actual click-through/import/visual verification is left to the user (no native-GUI automation tool available on this side).

**Key files touched:** `SPEC.md`, `NOTES.md`, `boris/model_import.py` (new), `boris/import_conflict_dialog.py` (new), `boris/core.py`, `boris/connections.py`, `boris/menu_options.py`, `tests/test_model_import.py` (new).

**Left open:**
- User still needs to manually try the import in the running app (button click, file picker, verify events render/save) — not yet confirmed end-to-end by a human.
- M3 (behavior/subject map-or-add for non-case/whitespace mismatches) not started — currently those rows are just skipped and reported.
- `test-projects.boris` has zero observations; needs one created (matching the sample CSV's `Observation id`, e.g. `P26_20231010_FIT`) before the sample CSV can actually be imported into it.
- 36 pre-existing test failures and the two stale PyQt5 test files, same as M0-M1.

## 2026-08-30 — M2 fix + M3: map-or-add dialogs

**What changed:**
- User ran M2 end-to-end against their own real project/CSV/video (`manual-tests/`, not committed) and confirmed it works — events imported, rendered, and saved correctly. Two follow-ups from that test:
  - Hit a real gap: the CSV's `Observation id` didn't match the BORIS observation's own name (independent naming schemes - one's the model pipeline's id, the other's whatever the coder typed). Fixed by implementing FR-10's "or prompt to choose" fallback (`distinct_observation_ids()` + a `QInputDialog` picker) instead of hard-erroring.
  - Asked why imported events show `NA` in the Frame index column vs `0` for live-coded ones. Answer: that column is mpv's live `estimated_frame_number` at coding time, not derivable from Time during a bulk import - `NA` is the correct, honest value (matches BORIS's own sentinel); `0` would be actively wrong (falsely claims every event is at the video's first frame). Offered an optional `round(Time * FPS)` estimate; not requested yet.
- Implemented M3: one reusable `MappingDialog` for both behavior and subject map-or-add (FR-4/FR-5), replacing the "skip and report" fallback for labels that don't match beyond case/whitespace. Many-to-one works two ways: map several labels to the same existing item, or add several as the same new name (detected and merged into one new ethogram/subject entry rather than duplicated). New ethogram entries get their type inferred from that label's own CSV rows.
- 8 new unit tests (24 total in `tests/test_model_import.py`), all passing. Full suite re-run: same 36 pre-existing failures, no regressions. App launch re-verified.
- Ticked M0/M1/M2 in the Notion page's Milestones checklist and added Progress log entries there mirroring this file.

**Key files touched:** `boris/model_import.py`, `boris/import_mapping_dialog.py` (new), `NOTES.md`, `SPEC.md`.

**Left open:**
- M3's dialogs haven't been manually click-tested by the user yet (unit-tested only).
- M4 (fast subject assignment UX) not started.
- Same 36 pre-existing test failures, two stale PyQt5 test files, and OQ-1 (track-ID column) as before.

## 2026-08-30 — M3 user-verified + skip option + auto-match reporting

**What changed:**
- User manually tested M3's map-to-existing and add-as-new paths against a purpose-built CSV (`manual-tests/files/mapping-test.csv`, not committed) - both work.
- Added a third "Skip" option to `MappingDialog`, and made it the *default* (previously defaulted to "Add as new" pre-filled with the raw label, meaning an untouched row would silently mutate the project). Skip for a behavior drops those rows (same as M2's original unmatched-behavior path); skip for a subject loads it subject-free (FR-5). No changes needed to `build_import_plan()` - a skipped label is just left out of the mapping dict, so it falls straight into logic that already existed.
- Added `auto_matched_behavior_codes()`/`auto_matched_subject_names()`: the summary dialog now leads with what matched cleanly on its own, not just problems that needed a dialog.
- 3 new unit tests (27 total), full suite re-run clean, app launch re-verified.

**Key files touched:** `boris/import_mapping_dialog.py`, `boris/model_import.py`, `NOTES.md`, `SPEC.md`.

**Left open:** same as before - M4 not started; 36 pre-existing test failures, two stale PyQt5 test files, OQ-1.

## 2026-08-30 — M4: fast subject assignment

**What changed:**
- Before implementing, found that `tv_events` already uses plain click (row selection, read by Edit event/Delete/Copy) and double-click (seeks the video to that event's time). The original plan to use those directly for stamp/unassign would have silently misfired during ordinary live coding, since the reused "active subject" state (`self.currentSubject`) is commonly set outside of import review too. Flagged to the user before writing code; resolved with a checkable "Stamping mode" toolbar toggle, default off - `tv_events` is unchanged from before this feature while it's off.
- Built the stamping logic (`boris/event_stamping.py`): click stamps the selected row(s) with the focal subject when the toggle is on; double-click unassigns; both fall through to original behavior when the toggle is off. `TableModel` now paints every row with a subject in that subject's color (live-coded or imported, not just imported). The existing `twSubjects` dock doubles as the color legend (reused, not a new widget).
- Second correction, this one caught by a test rather than inspection: subject colors were originally independent-hashed per name, which a test showed collides badly (only 6 distinct colors for 10 real project subjects). Fixed to rank subjects by position in the project's own subject list instead, guaranteeing distinct colors within one project.
- 6 new unit tests (33 total across the importer + stamping), full suite re-run clean, app launch re-verified.

**Key files touched:** `boris/event_stamping.py` (new), `boris/core.py`, `boris/connections.py`, `boris/menu_options.py`, `tests/test_event_stamping.py` (new), `NOTES.md`, `SPEC.md`.

**Left open:** not yet manually click-tested by the user; assign-by-track is M5; same 36 pre-existing test failures, two stale PyQt5 test files, OQ-1 as before.
