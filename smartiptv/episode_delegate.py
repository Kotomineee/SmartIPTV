"""Compact episode rows with a distinct number and optional resume hint."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyle, QStyledItemDelegate


class EpisodeDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(240, 64 if index.data(Qt.ItemDataRole.UserRole + 1) else 48)

    def paint(self, painter, option, index):
        episode = index.data(Qt.ItemDataRole.UserRole)
        if not episode:
            return
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 2, -4, -2)
        if option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#244334" if option.state & QStyle.StateFlag.State_Selected else "#192f25"))
            painter.drawRoundedRect(rect, 8, 8)
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#76e8b4"))
        painter.drawText(QRect(rect.x() + 10, rect.y(), 38, rect.height()), Qt.AlignmentFlag.AlignCenter, str(episode.episode))
        font.setBold(False)
        painter.setFont(font)
        hint = index.data(Qt.ItemDataRole.UserRole + 1)
        title = QRect(rect.x() + 62, rect.y() + (7 if hint else 0), max(0, rect.width() - 78), 24 if hint else rect.height())
        painter.setPen(QColor("#e1eee7"))
        painter.drawText(title, Qt.AlignmentFlag.AlignVCenter, painter.fontMetrics().elidedText(episode.name, Qt.TextElideMode.ElideRight, title.width()))
        if hint:
            painter.setPen(QColor("#93b4a3"))
            painter.drawText(title.translated(0, 23), Qt.AlignmentFlag.AlignVCenter, hint)
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("#65dfad"))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        painter.restore()
