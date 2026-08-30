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
