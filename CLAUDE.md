# Project: BORIS in-app model-output import (fork)

## What we're building
A visible "Import model outputs" button in BORIS's observation window. It parses a BORIS tabular events CSV (START/STOP = state, POINT = point) and is ethogram- and subject-agnostic (reads the open project's ethogram and subjects at runtime). It imports only the active observation's rows; behaviors auto-match the ethogram case/whitespace-insensitively (map-or-add, many-to-one, for the rest); subjects auto-match project subjects case-insensitively (subject map-or-add, many-to-one, for the rest); known cats are pre-assigned, the rest load subject-free with the track ID kept. If the observation already has events, warn before overwriting. Then a fast subject-assignment UI: active subject (colored, one at a time), click to stamp, double-click to unassign, keyboard too, plus assign-by-track.

## Ground truth
- Event model + key calls + button/dialog hook locations: NOTES.md (from code + a real .boris fixture)
- Feature spec: found in Notion page called BORIS × Model-Output Importer — Scope & Requirements
- Sample model output: linked in the Notion page; local copy at `C:\Users\naree\Downloads\first5_current_system_boris_2026-08-25-20260828T054112Z-1-001\first5_current_system_boris_2026-08-25\ALL5_CURRENT_PREDICTED_BORIS_FOR_AUDIT.csv` (same folder also has per-video CSVs, `EXPORT_MANIFEST.csv`, `CURRENT_PREDICTION_EVENT_AUDIT.csv`, and `README_CURRENT_SYSTEM.txt`)

## Setup / run
- (fill in after M0: exact install + launch commands, pinned version/tag, system deps like mpv)

## Rules
- Nothing hard-coded: read ethogram and subjects from the open project.
- Keep changes small and isolated; list touched files in NOTES.md.
- State behaviors must be inserted as correct start/stop pairs, in time order.
- Import overwrites the target observation's events; always confirm first if it is non-empty.
- New UI must be additive: never break normal coding; keep Edit event working.
- Add tests for the parser, ethogram check, and subject matching; smoke-test the UI.

## Working discipline
- After each milestone (M0-M6): run the tests, then commit with a message like "M2: <summary>". One commit per milestone.
- Keep a PROGRESS.md worklog. After each milestone, append a dated entry: milestone id, what changed, key files touched, anything left open.
- After committing, remind me to review the diff and (optionally) sync PROGRESS.md to this Notion page.
