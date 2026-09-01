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
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QStackedWidget,
)

from . import config as cfg

ACTION_SKIP = "Skip"
ACTION_MAP = "Map to existing"
ACTION_ADD = "Add as new"

_PAGE_SKIP, _PAGE_MAP, _PAGE_ADD = 0, 1, 2


class MappingDialog(QDialog):
    """
    Reusable map-or-add dialog for both behavior and subject mismatches (FR-4, FR-5): one table
    row per unmatched CSV label, each mapped to an existing project item, added as a new one, or
    skipped. Many-to-one is free - several labels can pick the same existing item, or type the
    same "new" name to be merged into one new item (see model_import.apply_*_resolutions).

    Laid out as an explicit table (label -> action -> target), not a single dropdown mixing
    "Skip"/"Add as new" sentinels together with real project item names - user testing (someone
    not BORIS-native) found that ambiguous: it wasn't clear which names came from the CSV/model
    and which were already in the project. Column headers say so directly instead.

    The "target" (existing-item combo vs. new-name field) is a single QStackedWidget per row that
    swaps to match the chosen action, rather than two always-visible columns - showing a stale
    existing-item name or pre-filled new-name text next to "Skip" made no sense and just added
    width/clutter for information that wasn't relevant to that row's choice.

    Skip is the default action for every row (not "add as new"): declining to resolve a label
    should never silently mutate the project just because the coder didn't touch a row. A skipped
    behavior label is dropped (its rows are excluded, same as an unmatched label in M2); a skipped
    subject name loads subject-free, per FR-5.
    """

    def __init__(self, kind: str, unmatched_labels: list, existing_items: list):
        super().__init__()
        self.setWindowTitle(cfg.programName)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self._labels = list(unmatched_labels)
        self._stacks: list = []  # one QStackedWidget per row, indexed like self._labels

        noun = "behavior" if kind == "behavior" else "subject"
        skip_consequence = "those rows are dropped" if kind == "behavior" else "those events load without a subject"
        sorted_items = sorted(existing_items)
        action_items = [ACTION_SKIP, ACTION_ADD] + ([ACTION_MAP] if sorted_items else [])

        layout = QVBoxLayout()
        layout.addWidget(
            QLabel(
                f"The model's CSV has {noun} label(s) that don't match this project (beyond case/whitespace).\n"
                f"For each one: map it to a {noun} already in this project, add it as a new one, or skip it "
                f"({skip_consequence})."
            )
        )

        self.table = QTableWidget(len(self._labels), 3)
        self.table.setHorizontalHeaderLabels(["From the model's CSV", "Action", "Target"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)

        for row, label in enumerate(self._labels):
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, label_item)

            action_combo = QComboBox()
            action_combo.addItems(action_items)
            self.table.setCellWidget(row, 1, action_combo)

            stack = QStackedWidget()
            stack.insertWidget(_PAGE_SKIP, QLabel("(not needed)"))
            map_combo = QComboBox()
            map_combo.addItems(sorted_items)
            stack.insertWidget(_PAGE_MAP, map_combo)
            new_name_edit = QLineEdit(label)
            stack.insertWidget(_PAGE_ADD, new_name_edit)
            stack.setCurrentIndex(_PAGE_SKIP)
            self.table.setCellWidget(row, 2, stack)
            self._stacks.append(stack)

            def _on_action_change(_index, action_combo=action_combo, stack=stack):
                stack.setCurrentIndex({ACTION_SKIP: _PAGE_SKIP, ACTION_MAP: _PAGE_MAP, ACTION_ADD: _PAGE_ADD}[action_combo.currentText()])

            action_combo.currentIndexChanged.connect(_on_action_change)

        layout.addWidget(self.table)

        buttons_layout = QHBoxLayout()
        ok_button = QPushButton("Continue import")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel import")
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(ok_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)
        self.resize(600, min(100 + 36 * len(self._labels), 520))

    def get_resolutions(self) -> dict:
        """{raw_label: ("map", existing_item) | ("add", new_name) | ("skip", None)}"""
        resolutions = {}
        for row, label in enumerate(self._labels):
            action = self.table.cellWidget(row, 1).currentText()
            if action == ACTION_SKIP:
                resolutions[label] = ("skip", None)
            elif action == ACTION_ADD:
                new_name_edit: QLineEdit = self._stacks[row].widget(_PAGE_ADD)
                resolutions[label] = ("add", new_name_edit.text().strip() or label)
            else:  # ACTION_MAP
                map_combo: QComboBox = self._stacks[row].widget(_PAGE_MAP)
                resolutions[label] = ("map", map_combo.currentText())
        return resolutions
