"""
BORIS
Behavioral Observation Research Interactive Software
Copyright 2012-2026 Olivier Friard

This file is part of BORIS.

  BORIS is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 3 of the License, or
  any later version.

  BORIS is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program; if not see <http://www.gnu.org/licenses/>.

"""

import bisect
import csv
import logging
from dataclasses import dataclass, field
from decimal import Decimal as dec
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from . import config as cfg
from . import import_conflict_dialog

logger = logging.getLogger(__name__)

# columns used from the BORIS tabular "Export events" CSV (see SPEC.md §3)
COL_OBSERVATION_ID = "Observation id"
COL_SUBJECT = "Subject"
COL_BEHAVIOR = "Behavior"
COL_BEHAVIOR_TYPE = "Behavior type"
COL_TIME = "Time"
COL_COMMENT = "Comment"

START, STOP, POINT = "START", "STOP", "POINT"


@dataclass
class ParsedRow:
    observation_id: str
    subject_raw: str
    behavior_raw: str
    behavior_type: str  # START / STOP / POINT, as read from the CSV
    time: dec
    comment: str


@dataclass
class SkippedRow:
    row: ParsedRow
    reason: str


@dataclass
class TypeConflict:
    behavior_code: str  # matched project ethogram code
    ethogram_type: str  # cfg.STATE_EVENT / cfg.POINT_EVENT (or *_WITH_CODING_MAP variant)
    csv_type: str  # "STATE" or "POINT", as implied by the CSV rows for this behavior
    row_count: int


@dataclass
class MatchResult:
    events: list = field(default_factory=list)  # [time, subject, code, modifier, comment] rows, ready to insert
    skipped: list = field(default_factory=list)  # list[SkippedRow]
    type_conflicts: dict = field(default_factory=dict)  # behavior_code -> TypeConflict
    subject_free_count: int = 0


class MalformedCsvError(Exception):
    pass


def parse_csv(csv_path: Path) -> list:
    """
    Read a BORIS tabular events export CSV into a list of ParsedRow.
    Raises MalformedCsvError if required columns are missing.
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {COL_OBSERVATION_ID, COL_SUBJECT, COL_BEHAVIOR, COL_BEHAVIOR_TYPE, COL_TIME}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise MalformedCsvError(f"Missing required column(s): {', '.join(sorted(missing))}")

        rows = []
        for line_no, raw in enumerate(reader, start=2):  # header is line 1
            behavior_type = (raw.get(COL_BEHAVIOR_TYPE) or "").strip().upper()
            if behavior_type not in (START, STOP, POINT):
                raise MalformedCsvError(f"Line {line_no}: unrecognized Behavior type {raw.get(COL_BEHAVIOR_TYPE)!r} (expected START/STOP/POINT)")
            try:
                time_value = dec(str(raw.get(COL_TIME, "")).strip()).quantize(dec(".001"))
            except Exception as e:
                raise MalformedCsvError(f"Line {line_no}: unparseable Time value {raw.get(COL_TIME)!r}") from e

            rows.append(
                ParsedRow(
                    observation_id=(raw.get(COL_OBSERVATION_ID) or "").strip(),
                    subject_raw=(raw.get(COL_SUBJECT) or "").strip(),
                    behavior_raw=(raw.get(COL_BEHAVIOR) or "").strip(),
                    behavior_type=behavior_type,
                    time=time_value,
                    comment=(raw.get(COL_COMMENT) or "").strip(),
                )
            )
    return rows


def filter_for_observation(rows: list, observation_id: str) -> list:
    return [r for r in rows if r.observation_id == observation_id]


def distinct_observation_ids(rows: list) -> list:
    """Distinct 'Observation id' values, in order of first appearance."""
    seen: dict = {}
    for r in rows:
        seen.setdefault(r.observation_id, None)
    return list(seen)


def match_behavior_code(label: str, ethogram: dict) -> str | None:
    """Case/whitespace-insensitive match of a CSV behavior label against the project's ethogram.
    Returns the matched ethogram *code* (canonical project casing), or None."""
    normalized = " ".join(label.split()).casefold()
    for entry in ethogram.values():
        if " ".join(str(entry[cfg.BEHAVIOR_CODE]).split()).casefold() == normalized:
            return entry[cfg.BEHAVIOR_CODE]
    return None


def match_subject_name(name: str, subjects: dict) -> str | None:
    """Case-insensitive match of a CSV subject name against the project's subject list.
    Returns the matched subject *name* (canonical project casing), or None (including for blank input)."""
    if not name:
        return None
    normalized = name.casefold()
    for entry in subjects.values():
        if str(entry[cfg.SUBJECT_NAME]).casefold() == normalized:
            return entry[cfg.SUBJECT_NAME]
    return None


def ethogram_type_category(ethogram_type: str) -> str:
    """Map an ethogram entry's "type" field to "STATE" or "POINT"."""
    if ethogram_type in cfg.STATE_EVENT_TYPES:
        return "STATE"
    if ethogram_type in cfg.POINT_EVENT_TYPES:
        return "POINT"
    return "UNKNOWN"


def detect_type_conflicts(rows: list, ethogram: dict) -> dict:
    """First pass: for every behavior label that matches the ethogram, check whether the CSV's
    own Behavior type (START/STOP vs POINT) agrees with what the ethogram says that behavior is.
    Returns {behavior_code: TypeConflict} for every mismatching behavior code found."""
    csv_type_by_code: dict = {}
    count_by_code: dict = {}
    for r in rows:
        code = match_behavior_code(r.behavior_raw, ethogram)
        if code is None:
            continue
        csv_category = "POINT" if r.behavior_type == POINT else "STATE"
        csv_type_by_code.setdefault(code, csv_category)
        count_by_code[code] = count_by_code.get(code, 0) + 1

    ethogram_type_by_code = {entry[cfg.BEHAVIOR_CODE]: entry["type"] for entry in ethogram.values()}

    conflicts = {}
    for code, csv_category in csv_type_by_code.items():
        ethogram_type = ethogram_type_by_code.get(code, "")
        if ethogram_type_category(ethogram_type) != csv_category:
            conflicts[code] = TypeConflict(
                behavior_code=code,
                ethogram_type=ethogram_type,
                csv_type=csv_category,
                row_count=count_by_code[code],
            )
    return conflicts


def build_import_plan(rows: list, ethogram: dict, subjects: dict, conflict_resolutions: dict | None = None) -> MatchResult:
    """
    Second pass: build the actual BORIS event rows to insert.

    conflict_resolutions: {behavior_code: "skip" | "use_csv"} for any code detect_type_conflicts()
    flagged. A code with resolution "skip" (or no resolution at all, when it was never in
    conflict) is only imported if its CSV type category actually matches the ethogram; "use_csv"
    means the caller has already updated the ethogram's type to match the CSV and rows should be
    imported as such.
    """
    conflict_resolutions = conflict_resolutions or {}
    result = MatchResult()

    # group rows by (subject_raw, matched_code) to pair START/STOP in chronological order
    groups: dict = {}
    for r in rows:
        code = match_behavior_code(r.behavior_raw, ethogram)
        if code is None:
            result.skipped.append(SkippedRow(r, f"Unknown behavior label {r.behavior_raw!r} (no match in project ethogram)"))
            continue

        if code in conflict_resolutions and conflict_resolutions[code] == "skip":
            result.skipped.append(SkippedRow(r, f"Behavior type conflict for {code!r}: kept project's type, row skipped"))
            continue

        groups.setdefault((r.subject_raw, code), []).append(r)

    for (subject_raw, code), group_rows in groups.items():
        subject_name = match_subject_name(subject_raw, subjects)
        if subject_name is None:
            result.subject_free_count += len(group_rows) if group_rows[0].behavior_type == POINT else len(group_rows) // 2
        resolved_subject = subject_name or ""

        point_rows = [r for r in group_rows if r.behavior_type == POINT]
        for r in sorted(point_rows, key=lambda r: r.time):
            result.events.append([r.time, resolved_subject, code, "", r.comment])

        pair_rows = sorted((r for r in group_rows if r.behavior_type in (START, STOP)), key=lambda r: r.time)
        i = 0
        while i < len(pair_rows):
            if i + 1 >= len(pair_rows) or pair_rows[i].behavior_type != START or pair_rows[i + 1].behavior_type != STOP:
                result.skipped.append(
                    SkippedRow(pair_rows[i], f"Malformed START/STOP sequence for {code!r} / subject {subject_raw!r} - could not pair")
                )
                i += 1
                continue
            start_row, stop_row = pair_rows[i], pair_rows[i + 1]
            result.events.append([start_row.time, resolved_subject, code, "", start_row.comment])
            result.events.append([stop_row.time, resolved_subject, code, "", stop_row.comment])
            i += 2

    return result


def insert_events(self, obs_id: str, events: list) -> None:
    """
    Insert already-matched BORIS event rows [time, subject, code, modifier, comment] directly into
    the project, bypassing write_event.write_event() - that function is a full live-coding state
    machine (toggle-based state open/close inference, pops up a modal modifier-selection dialog
    per call when a behavior has modifiers configured, assumes self.dw_player[0] is a live player)
    and is not suitable for a bulk import loop. This mirrors write_event's own "add event" insertion
    shape exactly (see boris/write_event.py:496-505) without the interactive side effects, then does
    one batched UI refresh instead of one per row.
    """
    obs_type = self.pj[cfg.OBSERVATIONS][obs_id][cfg.TYPE]
    event_list = self.pj[cfg.OBSERVATIONS][obs_id][cfg.EVENTS]
    for time_, subject, code, modifier, comment in events:
        if obs_type == cfg.MEDIA:
            bisect.insort(event_list, [time_, subject, code, modifier, comment, cfg.NA])
        elif obs_type == cfg.LIVE:
            bisect.insort(event_list, [time_, subject, code, modifier, comment])
        else:
            raise MalformedCsvError(f"Importing model outputs into a {obs_type!r} observation is not supported")

    self.load_tw_events(obs_id)
    self.project_changed()


def _apply_use_csv_resolutions(self, conflicts: dict, resolutions: dict) -> list:
    """Mutate the ethogram type for every conflict resolved as 'use_csv'. Returns the list of
    behavior codes that were changed, for the summary message."""
    category_to_ethogram_type = {"STATE": cfg.STATE_EVENT, "POINT": cfg.POINT_EVENT}
    changed = []
    for code, conflict in conflicts.items():
        if resolutions.get(code) == "use_csv":
            for entry in self.pj[cfg.ETHOGRAM].values():
                if entry[cfg.BEHAVIOR_CODE] == code:
                    entry["type"] = category_to_ethogram_type[conflict.csv_type]
                    changed.append(code)
                    break
    if changed:
        self.load_behaviors_in_twEthogram([entry[cfg.BEHAVIOR_CODE] for entry in self.pj[cfg.ETHOGRAM].values()])
    return changed


def import_model_outputs_activated(self) -> None:
    """Entry point for the "Import model outputs" button (FR-1..FR-6, FR-10..FR-12 happy path)."""
    if not self.observationId:
        QMessageBox.warning(self, cfg.programName, "Open an observation before importing model outputs.")
        return

    csv_path, _ = QFileDialog.getOpenFileName(self, "Import model outputs", "", "CSV files (*.csv)")
    if not csv_path:
        return

    try:
        all_rows = parse_csv(Path(csv_path))
    except MalformedCsvError as e:
        QMessageBox.critical(self, cfg.programName, f"Could not parse this file:\n{e}")
        return

    rows = filter_for_observation(all_rows, self.observationId)
    if not rows:
        candidate_ids = distinct_observation_ids(all_rows)
        if not candidate_ids:
            QMessageBox.warning(self, cfg.programName, "This CSV has no rows with an Observation id.")
            return

        # BORIS observation names and the model pipeline's own "Observation id" values are
        # independent naming schemes (a coder might name an observation after the video file,
        # while the CSV uses e.g. "P26_20231010_FIT") - they won't coincidentally match, so let
        # the coder pick the right one from what's actually in the file instead of erroring out.
        chosen, ok = QInputDialog.getItem(
            self,
            cfg.programName,
            f"No rows match the active observation's id ({self.observationId!r}).\n"
            "Pick the Observation id to import from this CSV instead:",
            candidate_ids,
            0,
            False,
        )
        if not ok:
            return
        rows = filter_for_observation(all_rows, chosen)

    existing_events = self.pj[cfg.OBSERVATIONS][self.observationId][cfg.EVENTS]
    if existing_events:
        answer = QMessageBox.question(
            self,
            cfg.programName,
            f"This observation already has {len(existing_events)} event(s).\n"
            "Importing will replace them all. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

    ethogram = self.pj[cfg.ETHOGRAM]
    subjects = self.pj[cfg.SUBJECTS]

    conflicts = detect_type_conflicts(rows, ethogram)
    resolutions: dict = {}
    ethogram_changed: list = []
    if conflicts:
        dlg = import_conflict_dialog.TypeConflictDialog(conflicts)
        if not dlg.exec_():
            return
        resolutions = dlg.get_resolutions()
        ethogram_changed = _apply_use_csv_resolutions(self, conflicts, resolutions)

    plan = build_import_plan(rows, ethogram, subjects, resolutions)

    self.pj[cfg.OBSERVATIONS][self.observationId][cfg.EVENTS] = []
    try:
        insert_events(self, self.observationId, plan.events)
    except MalformedCsvError as e:
        QMessageBox.critical(self, cfg.programName, str(e))
        return

    summary = [f"Imported {len(plan.events)} event(s)."]
    if plan.subject_free_count:
        summary.append(f"{plan.subject_free_count} loaded without a subject (no matching cat name in the CSV).")
    if ethogram_changed:
        summary.append(f"Updated ethogram type for: {', '.join(ethogram_changed)}.")
    if plan.skipped:
        summary.append(f"Skipped {len(plan.skipped)} row(s):")
        for skipped in plan.skipped[:10]:
            summary.append(f"  - {skipped.reason}")
        if len(plan.skipped) > 10:
            summary.append(f"  ... and {len(plan.skipped) - 10} more.")

    QMessageBox.information(self, cfg.programName, "\n".join(summary))
