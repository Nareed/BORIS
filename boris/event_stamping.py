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

import hashlib

from PySide6.QtGui import QColor

from . import config as cfg

# Qualitative, visually-distinct palette (not tied to any BORIS theme). Order is arbitrary but
# fixed - what matters is that it never changes, since color assignment must be deterministic
# (NFR-2) and reproducible across sessions.
_PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe",
    "#008080", "#e6beff", "#9a6324", "#800000", "#aaffc3",
    "#808000", "#ffd8b1", "#000075",
]  # fmt: skip

# out of 255 - "faded", not the solid palette color; applied by subject_qcolor() so both the
# events-table coloring and the twSubjects legend get the same muted look
FADE_ALPHA = 60

# events-table rows use this instead of FADE_ALPHA while stamping mode is off - present ("super
# super faded"), not gone, so a coder can still tell at a glance who's assigned without the
# color competing for attention during normal coding
FADE_ALPHA_OFF = 18

BASE_BUTTON_STYLE = (
    "QToolButton { border: 1px solid palette(mid); border-radius: 4px; padding: 4px 10px; "
    "background-color: palette(button); } "
    "QToolButton:hover { background-color: palette(light); } "
    "QToolButton:pressed { background-color: palette(dark); }"
)

STAMPING_ON_STYLE = (
    "QToolButton { border: 2px solid #1b5e20; border-radius: 4px; padding: 4px 10px; "
    "background-color: #43a047; color: white; font-weight: bold; } "
    "QToolButton:hover { background-color: #4caf50; } "
    "QToolButton:pressed { background-color: #2e7d32; }"
)


def subject_color(name: str, subject_names) -> str:
    """
    Deterministic hex color for a subject name (SPEC.md §2 - hash-derived, since BORIS's project
    schema has no color field for subjects), chosen by `name`'s position among `subject_names`
    sorted alphabetically - not by hashing `name` in isolation. Pure independent hashing collides
    far too often to be a usable "color legend" even for a modest subject count (e.g. only ~6
    distinct colors out of 10 real project subjects with an 18-color palette, confirmed by test);
    ranking within the actual project's subject list guarantees every subject gets a distinct
    color as long as there are no more subjects than palette colors (cycles beyond that). Sorting
    by name rather than by the project dict's own key order keeps assignment stable even if
    subjects get reindexed (dict keys aren't guaranteed stable, the names themselves are, once
    resolved to their canonical casing by match_subject_name upstream).
    Returns "" for a blank/subject-free name - callers should treat that as "no color".
    """
    if not name:
        return ""
    sorted_names = sorted(set(subject_names))
    try:
        index = sorted_names.index(name)
    except ValueError:
        # not in the known list (shouldn't normally happen) - fall back to a hash so callers
        # still get a deterministic color rather than an error
        index = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return _PALETTE[index % len(_PALETTE)]


def subject_qcolor(name: str, subject_names, alpha: int = FADE_ALPHA):
    """subject_color() as a faded QColor (see FADE_ALPHA), or None for a blank name."""
    hex_color = subject_color(name, subject_names)
    if not hex_color:
        return None
    color = QColor(hex_color)
    color.setAlpha(alpha)
    return color


def colorize_subjects_table(self) -> None:
    """
    Color each subject row in twSubjects by its hash-derived color - this table is the "color
    legend" for the fast subject-assignment feature (SPEC.md §7), reusing the existing subjects
    dock rather than building a separate legend widget. Row 0 is always the "no focal subject"
    placeholder (see load_subjects_in_twSubjects) and stays uncolored.
    """
    subject_names = [entry[cfg.SUBJECT_NAME] for entry in self.pj[cfg.SUBJECTS].values()]
    name_col = cfg.subjectsFields.index(cfg.SUBJECT_NAME)
    for row in range(1, self.twSubjects.rowCount()):
        name_item = self.twSubjects.item(row, name_col)
        if name_item is None:
            continue
        color = subject_qcolor(name_item.text(), subject_names)
        if color is None:
            continue
        for col in range(self.twSubjects.columnCount()):
            item = self.twSubjects.item(row, col)
            if item is not None:
                item.setBackground(color)


def on_stamping_mode_toggled(self, checked: bool) -> None:
    """
    Make the toggle's on/off state unmistakable (text + a distinct green style when on), and
    gate the events-table row coloring behind it: colors are only shown while stamping mode is
    on (TableModel.stamping_mode_active), so tv_events isn't tinted at all during normal coding.
    Mutates the live model in place and forces a repaint rather than rebuilding it - toggling the
    mode shouldn't need a full reload_tw_events().
    """
    self.tb_stamping_mode.setText(f"Stamping mode: {'ON' if checked else 'OFF'}")
    self.tb_stamping_mode.setStyleSheet(STAMPING_ON_STYLE if checked else BASE_BUTTON_STYLE)
    model = self.tv_events.model()
    if model is not None:
        model.stamping_mode_active = checked
        model.layoutChanged.emit()


def _apply_subject_to_selected_rows(self, subject: str) -> None:
    selected_rows = {index.row() for index in self.tv_events.selectionModel().selectedIndexes()}
    if not selected_rows:
        return
    events = self.pj[cfg.OBSERVATIONS][self.observationId][cfg.EVENTS]
    for view_row in selected_rows:
        event_idx = self.tv_idx2events_idx[view_row]
        events[event_idx][cfg.EVENT_SUBJECT_FIELD_IDX] = subject
    self.load_tw_events(self.observationId)
    self.project_changed()


def on_tv_events_clicked(self) -> None:
    """
    Stamp: with stamping mode on and a focal subject active, clicking (or multi-selecting then
    clicking) event row(s) assigns them to self.currentSubject. Reuses the SAME state live coding
    uses for the focal subject (SPEC.md §2) - "activate a subject" already works via BORIS's
    existing subject-key/twSubjects-click mechanisms, this only adds what happens when an event
    row is then clicked.

    Gated behind tb_stamping_mode (a checkable toolbar toggle, default off): tv_events.clicked has
    no handler otherwise, so normal row selection (used by Edit event, Delete, Copy, ...) is
    completely unaffected when the toggle is off.
    """
    if not self.tb_stamping_mode.isChecked():
        return
    if not self.currentSubject:
        return
    _apply_subject_to_selected_rows(self, self.currentSubject)


def on_tv_events_double_clicked(self) -> None:
    """
    Unassign: with stamping mode on, double-clicking event row(s) clears their subject.
    With stamping mode off, falls through to the existing tv_events_doubleClicked() (seeks the
    video player to that event's time) unchanged - double-click already had a meaning before this
    feature existed, and stamping mode must not silently change it while off.
    """
    if self.tb_stamping_mode.isChecked():
        _apply_subject_to_selected_rows(self, "")
    else:
        self.tv_events_doubleClicked()
