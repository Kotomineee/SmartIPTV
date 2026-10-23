"""Visible season buttons that wrap instead of hiding seasons in a menu."""
from math import ceil

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QPushButton, QSizePolicy, QWidget


class SeasonTabs(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Temporadas disponíveis")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.buttons = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.idClicked.connect(self.currentChanged.emit)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self.columns = 0

    def set_seasons(self, seasons, selected=None):
        for button in self.buttons.values():
            self.group.removeButton(button)
            self.grid.removeWidget(button)
            button.hide()
            button.deleteLater()
        self.buttons.clear()
        for season in seasons:
            button = QPushButton(f"T{season}")
            button.setObjectName("seasonTab")
            button.setAccessibleName(f"Temporada {season}")
            button.setToolTip(f"Temporada {season}")
            button.setCheckable(True)
            button.setFixedSize(max(46, button.fontMetrics().horizontalAdvance(button.text()) + 24), 34)
            self.group.addButton(button, season)
            self.buttons[season] = button
        if self.buttons:
            self.buttons.get(selected, next(iter(self.buttons.values()))).setChecked(True)
        self._arrange()

    def current_season(self):
        return self.group.checkedId() if self.group.checkedButton() else None

    def sizeHint(self):
        return QSize(200, self.minimumHeight())

    def resizeEvent(self, event):
        self._arrange()
        super().resizeEvent(event)

    def _arrange(self):
        width = max((b.width() for b in self.buttons.values()), default=46)
        columns = max(1, self.width() // (width + 8))
        for column in range(self.columns + 1):
            self.grid.setColumnStretch(column, 0)
        self.columns = columns
        for index, button in enumerate(self.buttons.values()):
            self.grid.addWidget(button, index // columns, index % columns)
            button.show()
        self.grid.setColumnStretch(columns, 1)
        rows = ceil(len(self.buttons) / columns)
        self.setFixedHeight(rows * 34 + max(0, rows - 1) * 8)
