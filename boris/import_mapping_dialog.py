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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
)

from . import config as cfg

SKIP = "-- Skip (leave unresolved) --"
ADD_NEW = "-- Add as new --"


class MappingDialog(QDialog):
    """
    Reusable map-or-add dialog for both behavior and subject mismatches (FR-4, FR-5): one row per
    unmatched CSV label, each mapped to an existing project item, added as a new one, or skipped.
    Many-to-one is free - several labels can pick the same existing item, or type the same "new"
    name to be merged into one new item (see model_import.apply_*_resolutions).

    Skip is the default for every row (not "add as new"): declining to resolve a label should
    never silently mutate the project just because the coder didn't touch a row. A skipped
    behavior label is dropped (its rows are excluded, same as an unmatched label in M2); a skipped
    subject name loads subject-free, per FR-5.
    """

    def __init__(self, kind: str, unmatched_labels: list, existing_items: list):
        super().__init__()
        self.setWindowTitle(cfg.programName)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self._rows: dict = {}

        noun = "behavior" if kind == "behavior" else "subject"
        skip_consequence = "those rows are dropped" if kind == "behavior" else "those events load without a subject"
        layout = QVBoxLayout()
        layout.addWidget(
            QLabel(
                f"The CSV has {noun} label(s) that don't match this project (beyond case/whitespace).\n"
                f"For each one: map it to an existing {noun}, add it as new, or skip it ({skip_consequence})."
            )
        )

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        sorted_items = sorted(existing_items)

        for label in unmatched_labels:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            row_layout = QHBoxLayout()
            row_layout.addWidget(QLabel(f"<b>{label}</b>"))

            combo = QComboBox()
            combo.addItem(SKIP)
            combo.addItem(ADD_NEW)
            combo.addItems(sorted_items)
            row_layout.addWidget(combo)

            new_name_edit = QLineEdit(label)
            new_name_edit.setEnabled(False)
            row_layout.addWidget(new_name_edit)

            def _on_change(index, combo=combo, new_name_edit=new_name_edit):
                new_name_edit.setEnabled(combo.currentText() == ADD_NEW)

            combo.currentIndexChanged.connect(_on_change)

            frame.setLayout(row_layout)
            scroll_layout.addWidget(frame)
            self._rows[label] = (combo, new_name_edit)

        scroll_widget.setLayout(scroll_layout)
        scroll_area = QScrollArea()
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        buttons_layout = QHBoxLayout()
        ok_button = QPushButton("Continue import")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel import")
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(ok_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)
        self.resize(500, min(80 + 60 * len(unmatched_labels), 600))

    def get_resolutions(self) -> dict:
        """{raw_label: ("map", existing_item) | ("add", new_name) | ("skip", None)}"""
        resolutions = {}
        for label, (combo, new_name_edit) in self._rows.items():
            if combo.currentText() == SKIP:
                resolutions[label] = ("skip", None)
            elif combo.currentText() == ADD_NEW:
                resolutions[label] = ("add", new_name_edit.text().strip() or label)
            else:
                resolutions[label] = ("map", combo.currentText())
        return resolutions
