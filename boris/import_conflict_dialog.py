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
    QRadioButton,
    QButtonGroup,
    QPushButton,
    QFrame,
)

from . import config as cfg


class TypeConflictDialog(QDialog):
    """
    Shown when one or more CSV behaviors disagree with the project ethogram's own
    Point/State classification for that behavior. For each conflicting behavior, the coder
    picks whether to keep the project's type (skip that behavior's rows) or use the CSV's
    type (update the ethogram to match, then import those rows).
    """

    def __init__(self, conflicts: dict):
        super().__init__()
        self.setWindowTitle(cfg.programName)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self._groups: dict = {}

        layout = QVBoxLayout()
        layout.addWidget(
            QLabel(
                "The CSV's Behavior type disagrees with the project ethogram for the behavior(s) below.\n"
                "Choose which version to keep for each one:"
            )
        )

        # conflict.csv_type is the internal "STATE"/"POINT" category, not BORIS's own ethogram
        # wording ("State event"/"Point event") - showing the raw internal string next to the
        # properly-worded project type read as inconsistent/confusing; normalize both to the
        # same vocabulary so the two options are easy to compare at a glance.
        csv_type_label = {"STATE": "State event", "POINT": "Point event"}

        for code, conflict in conflicts.items():
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            v = QVBoxLayout()
            v.addWidget(QLabel(f"<b>{code}</b> - {conflict.row_count} row(s)"))

            group = QButtonGroup(self)
            project_rb = QRadioButton(f"Keep this project's current type ({conflict.ethogram_type}) - skip these rows")
            csv_rb = QRadioButton(
                f"Use the model's CSV type ({csv_type_label.get(conflict.csv_type, conflict.csv_type)}) - "
                "update the ethogram and import"
            )
            project_rb.setChecked(True)
            group.addButton(project_rb, 0)
            group.addButton(csv_rb, 1)
            v.addWidget(project_rb)
            v.addWidget(csv_rb)
            frame.setLayout(v)
            layout.addWidget(frame)

            self._groups[code] = group

        buttons_layout = QHBoxLayout()
        ok_button = QPushButton("Continue import")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel import")
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(ok_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)

    def get_resolutions(self) -> dict:
        """{behavior_code: "skip" | "use_csv"}"""
        return {code: ("skip" if group.checkedId() == 0 else "use_csv") for code, group in self._groups.items()}
