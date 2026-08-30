# SPEC — Import model outputs into BORIS

Implementation spec for the "Import model outputs" feature. Product framing, full requirements text, and rationale live in the Notion page *BORIS × Model-Output Importer — Scope & Requirements* (linked from [CLAUDE.md](CLAUDE.md)); this file translates that into what to actually build, grounded in the code recon in [NOTES.md](NOTES.md). Requirement IDs (FR-*, NFR-*, OQ-*) match the Notion page so both stay cross-referenceable.

## 1. One-liner

Add an in-app button to BORIS that imports a computer-vision model's cat-behavior detections (a BORIS tabular events CSV) into the active observation — pre-filling the cat where the model already knows it, and making manual cat assignment fast where it doesn't.

## 2. Decisions made this session (beyond the Notion spec)

The Notion spec is "ready for development, decisions locked" except OQ-1. Reading the actual code (NOTES.md) surfaced four more implementation-level questions with no natural answer in either doc; resolved by interview:

- **OQ-1 / track ID → deferred entirely to M5.** Until the model team finalizes the track-ID column name, the importer does not look for one at all. Any CSV row with a blank or unmapped Subject loads subject-free, full stop — no guessed column names, no partial track support. `assign-by-track` (§7, FR-7, FR-8) is not built in M2-M4; it lands in M5 alongside real track-ID reading.
- **Subject colors → hash-derived from name.** BORIS's project schema has no color field on subjects (only on behaviors — confirmed against both `test.boris` and the real `test-projects.boris`, NOTES.md §2). Since there's nowhere to persist or read a subject color from the project, the importer computes one deterministically from the subject name (e.g. a stable hash → index into a fixed palette), so a subject's color is always the same across imports/sessions without needing new project-file fields.
- **Stamping UI → built into the existing events table.** The fast subject-assignment interaction (click to stamp, double-click to unassign) is implemented directly on BORIS's existing `tv_events` QTableView (NOTES.md §1) via row coloring + click handling, not a separate new widget/dialog. Coders already look at this table; reusing it means one events view, not two.
- **Active-subject key → reuses `self.currentSubject`.** Pressing a subject key during import review sets the same `self.currentSubject` that live coding uses (`update_subject`, NOTES.md §3), rather than inventing a second parallel "active subject" concept. Simpler mental model for coders, less state to keep in sync.
- **Behavior-type conflicts (found during M2 implementation, not in the original spec) → ask, don't guess.** M2's happy path has no map-or-add UI yet (that's M3), but a row can still disagree with the ethogram on Point-vs-State (FR-12's "flag any conflict"). Rather than silently picking a side, `TypeConflictDialog` lists each conflicting behavior and lets the coder choose per-behavior: keep the project's type (skip those rows) or use the CSV's type (update the ethogram, then import). See `boris/import_conflict_dialog.py`.
- **Stamp gesture (found during M4 implementation) → a "Stamping mode" toggle, not plain click/double-click.** `tv_events` already uses plain click for row selection (read by Edit event/Delete/Copy) and double-click to seek the video to that event's time - both would have silently misfired had stamping used them directly, since `self.currentSubject` (the reused "active subject" state) is commonly set during ordinary live coding too, unrelated to import review. Resolved: a checkable toolbar toggle, default off; while off, `tv_events` is unchanged from before this feature existed. See NOTES.md §7c.
- **Subject colors: rank by position in the project's subject list, not independent hashing.** The original plan (OQ-9) was to hash each name independently into the palette. A test caught that this collides often - only 6 distinct colors for 10 real project subjects against an 18-color palette. Fixed by ranking each subject alphabetically among the project's own subject list instead, which guarantees distinct colors within one project (cycles only if there are more subjects than palette colors). `subject_color()` now takes the full subject-name list as a parameter, not just the one name.

## 3. Input format (from the Notion spec §4, "from a real sample")

BORIS tabular "Export events" CSV. Columns:
```
__video_index, Observation id, Observation date, Description, Observation duration,
Observation type, Source, Time offset (s), Media duration (s), FPS, Subject, Behavior,
Behavioral category, Behavior type, Time, Media file name, Image index, Image file path, Comment
```
What the importer actually uses:
- **Observation id** — filter to rows matching the active observation's id (exact string match against `self.observationId`); if the CSV has rows for other observations too, that's expected (multi-observation export) and those rows are simply skipped (FR-10). If *zero* rows match, tell the user and abort — don't silently import nothing.
- **Behavior type** — `START`/`STOP` → one state event pair; `POINT` → one point event. This is how the importer knows point-vs-state per row without needing the ethogram in advance (FR-12).
- **Time** — seconds, millisecond precision. Becomes `EVENT_TIME_FIELD_IDX` (as a `Decimal`, matching BORIS's in-memory type — NOTES.md §2).
- **Subject** — cat name when known; blank when not (until M5, "blank" also covers "the model gave a track ID with no name").
- **Behavior** — matched against the open project's ethogram.
- **Behavioral category, Comment, Image index/path** — carried through where present but not required for matching logic.
- **Observation duration, FPS** — informational only; the importer keys off `Time` and the active observation's own media, per the spec.

## 4. Where things hook in (see NOTES.md for the underlying mechanism + file:line)

| Piece | Hook point |
|---|---|
| "Import model outputs" button | `self.toolBar` ([core_ui.py:540](boris/core_ui.py:540)), added in `MainWindow.__init__` per the `tb_export` precedent — NOTES.md §7. Wired in `connections.connections(self)`, enable-state in `menu_options.update_menu(self)`. |
| File picker | Plain `QFileDialog.getOpenFileName(...)`, filtered to `*.csv` — no custom dialog class needed (NOTES.md §6). |
| Overwrite confirmation (FR-11) | Plain `QMessageBox.question(...)` Yes/No — simplest correct tool (NOTES.md §6). |
| Behavior / subject map-or-add (FR-4, FR-5) | One reusable custom `QDialog` subclass (see §9 file layout), following the `ModifiersList`/`DlgEditEvent` pattern: build with the mismatched labels + candidate targets, `.exec_()`, read back a `{model_label: mapped_code_or_name}` dict (NOTES.md §6). |
| Event insertion | **Corrected during M2** (see NOTES.md §3): `write_event()` is a full live-coding state machine — it can pop up a modal modifier-selection dialog per call and assumes a live player is attached — not safe to call in a bulk-import loop. `boris/model_import.py:insert_events()` instead builds rows with the same list shape directly via `bisect.insort`, then does one batched `load_tw_events`/`project_changed` call. |
| State event pairing | Insert two list entries with the identical behavior code, same subject, same modifier, at their respective START/STOP times — BORIS has no explicit start/stop flag, pairing is purely chronological per (subject, code) (NOTES.md §2, the critical gotcha). |
| Ethogram / subject read | Iterate `self.pj[cfg.ETHOGRAM].values()` / `self.pj[cfg.SUBJECTS].values()`, match on `code`/`name`, not the dict key (NOTES.md §4). Reuse `self.subject_name_index` rather than rebuilding it. |
| Fast subject-assignment ("stamping") | Extend `TableModel` ([core.py:166](boris/core.py:166)) with a per-row subject→color lookup for background painting, and hook click/double-click on `tv_events` for stamp/unassign (§2 decision: built into the existing table, not a new widget). |

## 5. Functional requirements

(Copied from Notion, annotated only where this session's decisions or code recon narrow the "how".)

- **FR-1** — Visible "Import model outputs" control in the observation window (toolbar, not a menu), enabled only while an observation is open.
- **FR-2** — Parse the CSV per §3: START+STOP → state event pair, POINT → single event.
- **FR-3** — Ethogram check: auto-match after normalizing case + trimming whitespace. Anything beyond that is a mismatch.
- **FR-4** — Behavior mismatch → map-or-add prompt; many-to-one allowed; no silent auto-add.
- **FR-5** — Subjects: auto-assign on case-insensitive name match; mismatches → subject map-or-add (many-to-one); unmatched/unmapped → subject-free (and, until M5, that's the end of it — no track ID retained yet, per §2 decision).
- **FR-6** — Insert events into the active observation at the given times, preserving millisecond precision and the CSV's time offset.
- **FR-7** — *(Deferred to M5 per §2 decision.)* Read track ID + confidence once the column is finalized; carry into comment/modifier.
- **FR-8** — Fast subject assignment (§7 below): active-subject stamping, clicks, keyboard, color-coding, double-tap unassign, one active subject at a time. Assign-by-track is part of M5, not M2-M4. Edit event must keep working unmodified.
- **FR-9** — Imported/edited events save into the `.boris` project and behave like normally-coded events — true for free, since insertion goes through the same `pj[OBSERVATIONS][obs_id][EVENTS]` list and `write_event`/save path everything else uses (NOTES.md §2, §5).
- **FR-10** — Multi-observation CSVs: import only rows matching the active observation's id (§3).
- **FR-11** — Re-import overwrites the target observation's events; confirm first if it already has ≥1 event.
- **FR-12** — Ethogram- and subject-agnostic; point-vs-state comes from `Behavior type`, cross-checked against the project's own definition of that behavior — flag any conflict (e.g. CSV says POINT for a code the project's ethogram defines as a State event) rather than silently trusting either side.

## 6. Non-functional requirements

- **NFR-1** — Small, isolated changes; keep NOTES.md's "touched files" list current (see §9).
- **NFR-2** — Deterministic: same CSV + same project → same events, same subject colors (hash-derived, not random).
- **NFR-3** — Times as BORIS expects — `Decimal`, not float, when building event lists (NOTES.md §2).
- **NFR-4** — Tests: CSV parser, ethogram-match logic, subject-match logic (unit); UI smoke-test (manual, or `pytest-qt` if it's worth adding — not currently a dependency).
- **NFR-5** — Fail clearly on malformed CSV without corrupting the open observation — validate/parse fully into a staging structure *before* touching `self.pj`, only committing to the project dict once parsing + matching are known-good.
- **NFR-6** — BORIS version pinned at `v9.14` (done, M0 — see CLAUDE.md).

## 7. Fast subject-assignment UX

Runs after import (matched/mapped events already arrive colored); mainly for unmatched leftovers and corrections. Replaces right-click → Edit event for bulk cat attribution.

- **Active subject**: click a subject or press its key (§2: same `update_subject`/`self.currentSubject` as live coding) → becomes active, highlighted in its (hash-derived) color. Only one active at a time.
- **Stamp**: with a subject active, click an event row (or multi-select several) in `tv_events` → assigns it, row takes the subject's color.
- **Unassign**: double-click an assigned row → clears subject, back to neutral.
- **Keyboard or mouse**: both paths work — keyboard-first coders press subject keys; mouse-only coders just click.
- **Color legend**: per subject, from the hash-derived palette; unassigned rows render neutral.
- **Assign-by-track**: *M5, once OQ-1 resolves* (§2 decision) — out of scope for M2-M4.
- Edit event continues to work unmodified alongside this (FR-8).

## 8. Workflow

1. Open project (ethogram + subjects already defined), start an observation, as usual.
2. Click "Import model outputs" → file picker → select the CSV.
3. Importer filters to rows for the active observation (§3); if none match, tell the user and stop.
4. If the observation already has events, warn that import will overwrite them (FR-11); coder confirms.
5. Behavior check: auto-match case/whitespace-insensitively; map-or-add prompt for the rest (FR-3/FR-4).
6. Subject check: auto-match case-insensitively; map-or-add prompt for the rest (FR-5).
7. Events load: matched/mapped rows arrive with subjects filled and colored; the rest load subject-free, neutral.
8. Coder uses the stamping UX (§7) to assign/fix the rest.
9. Save; continue with normal BORIS analysis/export — nothing downstream needs to know these events came from an import.

## 9. Proposed file layout for M2+

New modules (naming follows the existing one-file-per-dialog convention, e.g. `select_modifiers.py`, `edit_event.py`):

- `boris/model_import.py` — **built in M2.** CSV parsing (§3), observation-id filtering, behavior/subject auto-match logic, event-list construction (including START/STOP pairing), direct event insertion, orchestration of the workflow in §8. The parsing/matching functions are unit-tested without a running QApplication (NFR-4, `tests/test_model_import.py`).
- `boris/import_conflict_dialog.py` — **built in M2** (not originally planned - see §2's behavior-type-conflict decision). `TypeConflictDialog`: per-behavior skip-vs-use-CSV-type choice.
- `boris/import_mapping_dialog.py` — **built in M3.** One reusable `QDialog` subclass for both the behavior map-or-add and subject map-or-add prompts, parameterized by `kind`.
- `boris/event_stamping.py` — the `tv_events` extensions for §7: subject→color hashing, row-coloring hook into `TableModel`, click/double-click handling wired onto `tv_events`.
- Touch `boris/core.py` (toolbar button + `TableModel`/`tv_events` wiring), `boris/connections.py` (signal wiring), `boris/menu_options.py` (enable-state).

Test fixtures (NFR-4): [tests/files/test.boris](tests/files/test.boris) for state-pairing edge cases; the user-supplied `test-projects.boris` (NOTES.md §9 — matches the sample CSV's cats/behaviors) once it has at least one real observation added, for an end-to-end import test.

## 10. Milestones

(M0/M1 done — see [PROGRESS.md](PROGRESS.md).)

- **M2 — Import happy path. Done.** Button + file picker; filter to active observation; case-insensitive auto-match for both behaviors and subjects (unmatched behavior → skipped + reported, unmatched subject → subject-free, no mapping prompts yet); overwrite warning; behavior-type conflict dialog (skip vs. use-CSV-type, see §2); direct event insertion (not `write_event`, see §4); unit tests for parser/matching/pairing/conflicts. Manual verification (app launch, actual click-through/render/save) is on the user — see NOTES.md §7a for touched files.
- **M3 — Mapping / mismatch handling. Done, user-verified.** One reusable `MappingDialog` for both behavior and subject map-or-add, both many-to-one, plus a third "Skip" option (default, not "add") so an untouched row never silently mutates the project. Summary dialog now also reports what auto-matched cleanly, not just what needed help. 27 unit tests, full suite re-run clean. See NOTES.md §7b for touched files.
- **M4 — Fast subject assignment. Done.** §7 UX built into the existing events table, gated behind a "Stamping mode" toggle (see §2 - plain click/double-click were already spoken for, discovered before implementing). Active subject reuses `self.currentSubject` (same as live coding). Colors are rank-based within the project's subject list, not independent hashing (see §2 - a test caught real collisions with the original approach). Color legend reuses the existing `twSubjects` dock. No assign-by-track yet (that's M5). 6 new unit tests, full suite clean, app launch verified. Not yet manually click-tested by the user.
- **M5 — Unknown-cat / track-ID variant.** Once OQ-1 resolves: read the real track-ID column, carry it into comment/modifier (FR-7), add assign-by-track to the M4 UI.
- **M6 — Pilot.** One real session end-to-end with actual coder feedback.

## 11. Risks (from the Notion spec, unchanged)

- Overwrite destroys manual coding → the confirmation popup (FR-11) is the guard.
- Fork drifts from upstream → small isolated changes, NOTES.md tracks touch points.
- Wrong-observation import from a multi-observation CSV → filtered by Observation id (FR-10).
- State-event pairing errors → insert in time order per (subject, code); BORIS's own UNPAIRED detection is a safety net; add tests specifically for this.
- New UI breaks normal coding → additive only; Edit event must keep working; smoke-test.
- Track-ID mis-attribution → deferred to M5 by this session's decision, so not a near-term risk; revisit its risk profile when M5 starts.

## 12. Out of scope

Automatic cat ID/re-ID, multi-camera fusion, live/real-time detection, changes to BORIS analysis/export behavior, a standalone external converter.
