"""Virtualized content cards and asynchronous, bounded poster caching."""
from collections import OrderedDict

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, QRect, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QAbstractItemView, QListView, QMenu, QStyledItemDelegate, QStyle

from .icons import icon
from .storage import data_directory


class ArtworkCache(QObject):
    changed = Signal()

    def __init__(self, parent=None, directory=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        disk = QNetworkDiskCache(self)
        disk.setCacheDirectory(str((directory or data_directory()) / "artwork"))
        disk.setMaximumCacheSize(80 * 1024 * 1024)
        self.manager.setCache(disk)
        self.memory = OrderedDict()
        self.pending = {}
        self.failed = set()

    def get(self, url):
        if not url.startswith(("http://", "https://")):
            return None
        if url in self.memory:
            self.memory.move_to_end(url)
            return self.memory[url]
        if url in self.pending or url in self.failed or len(self.pending) >= 24:
            return None
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(15000)
        request.setRawHeader(b"User-Agent", b"VLC/3.0.21 LibVLC/3.0.21")
        reply = self.manager.get(request)
        self.pending[url] = reply
        reply.downloadProgress.connect(lambda received, total, r=reply: r.abort() if received > 5 * 1024 * 1024 or total > 5 * 1024 * 1024 else None)
        reply.finished.connect(lambda u=url, r=reply: self._finish(u, r))
        return None

    def _finish(self, url, reply):
        self.pending.pop(url, None)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            raw = bytes(reply.readAll())
            pixmap = QPixmap()
            if len(raw) <= 5 * 1024 * 1024 and pixmap.loadFromData(raw):
                self.memory[url] = pixmap.scaled(440, 660, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                while len(self.memory) > 180:
                    self.memory.popitem(last=False)
            else:
                self.failed.add(url)
        else:
            self.failed.add(url)
        if len(self.failed) > 2000:
            self.failed.clear()
        reply.deleteLater()
        self.changed.emit()

    def close(self):
        for reply in list(self.pending.values()):
            reply.blockSignals(True)
            reply.abort()
            reply.deleteLater()
        self.pending.clear()


class ContentModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.items):
            return None
        item = self.items[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return item.display_name
        if role == Qt.ItemDataRole.UserRole:
            return item
        return None

    def set_items(self, items):
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def refresh(self):
        if self.items:
            self.dataChanged.emit(self.index(0), self.index(len(self.items) - 1))


class CardDelegate(QStyledItemDelegate):
    def __init__(self, library, artwork, compact=False, parent=None):
        super().__init__(parent)
        self.library, self.artwork, self.compact = library, artwork, compact
        self.heart = icon("heart", "#d9e9df", 18)
        self.heart_active = icon("heart-filled", "#74edb0", 18)
        self.placeholder = icon("tv" if compact else "film", "#527a60", 40)

    def sizeHint(self, option, index):
        return QSize(182, 177 if self.compact else 300)

    def paint(self, painter, option, index):
        item = index.data(Qt.ItemDataRole.UserRole)
        if item is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = option.rect.adjusted(2, 2, -8, -8)
        highlighted = bool(option.state & (QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus))
        painter.setPen(QPen(QColor("#5bb987" if highlighted else "#253b2d"), 1))
        painter.setBrush(QColor("#142019"))
        painter.drawRoundedRect(outer, 10, 10)
        poster = outer.adjusted(1, 1, -1, -73)
        pixmap = self.artwork.get(item.artwork)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(poster), 9, 9)
        painter.setClipPath(clip)
        if pixmap:
            target_ratio = poster.width() / max(1, poster.height())
            image_ratio = pixmap.width() / max(1, pixmap.height())
            source = QRectF(pixmap.rect())
            if image_ratio > target_ratio:
                width = source.height() * target_ratio
                source.setLeft((pixmap.width() - width) / 2)
                source.setWidth(width)
            else:
                height = source.width() / target_ratio
                source.setTop((pixmap.height() - height) / 2)
                source.setHeight(height)
            painter.drawPixmap(QRectF(poster), pixmap, source)
        else:
            gradient = QLinearGradient(poster.topLeft(), poster.bottomRight())
            gradient.setColorAt(0, QColor("#263e2e"))
            gradient.setColorAt(1, QColor("#122219"))
            painter.fillRect(poster, gradient)
            self.placeholder.paint(painter, QRect(poster.center().x() - 21, poster.center().y() - 21, 42, 42))
        painter.setClipping(False)
        heart_rect = QRect(outer.right() - 36, outer.top() + 8, 28, 28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(8, 19, 12, 215))
        painter.drawEllipse(heart_rect)
        (self.heart_active if self.library.is_favorite(item) else self.heart).paint(painter, heart_rect.adjusted(5, 5, -5, -5))
        checkpoint = self.library.checkpoint(item)
        if checkpoint and checkpoint["duration"]:
            ratio = min(1, checkpoint["position"] / checkpoint["duration"])
            track = QRect(poster.left(), poster.bottom() - 4, poster.width(), 4)
            painter.fillRect(track, QColor("#163a25"))
            painter.fillRect(QRect(track.left(), track.top(), int(track.width() * ratio), 4), QColor("#68e7a7"))
        title_rect = QRect(outer.left() + 11, poster.bottom() + 10, outer.width() - 22, 36)
        painter.setPen(QColor("#e0eee4"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(title_rect, Qt.TextFlag.TextWordWrap, item.display_name)
        kind = {"live": "TV AO VIVO", "movie": "FILME", "series": "SÉRIE", "episode": "EPISÓDIO"}[item.kind]
        caption = f"{kind}  ·  {item.year}" if item.year else kind
        if checkpoint:
            caption = "CONTINUAR ASSISTINDO"
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#8cae97"))
        painter.drawText(QRect(outer.left() + 11, outer.bottom() - 22, outer.width() - 22, 16), Qt.AlignmentFlag.AlignLeft, caption)
        painter.restore()


class Gallery(QListView):
    open_requested = Signal(object)
    favorite_requested = Signal(object)
    remove_progress_requested = Signal(object)

    def __init__(self, library, artwork, compact=False, horizontal=False, parent=None):
        super().__init__(parent)
        self.library = library
        self.setObjectName("gallery")
        self.content_model = ContentModel(self)
        self.setModel(self.content_model)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setItemDelegate(CardDelegate(library, artwork, compact, self))
        self.setGridSize(QSize(182, 177 if compact else 300))
        self.setSpacing(4)
        if horizontal:
            self.setFlow(QListView.Flow.LeftToRight)
            self.setWrapping(False)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setFixedHeight(193 if compact else 316)
        artwork.changed.connect(self.viewport().update)
        self.clicked.connect(lambda index: self.open_requested.emit(index.data(Qt.ItemDataRole.UserRole)))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def set_items(self, items):
        self.content_model.set_items(items)
        self.scrollToTop()

    def mouseReleaseEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and event.button() == Qt.MouseButton.LeftButton:
            rect = self.visualRect(index).adjusted(2, 2, -8, -8)
            target = QRect(rect.right() - 36, rect.top() + 8, 28, 28)
            if target.contains(event.position().toPoint()):
                self.favorite_requested.emit(index.data(Qt.ItemDataRole.UserRole))
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        item = self.currentIndex().data(Qt.ItemDataRole.UserRole)
        if item and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.open_requested.emit(item)
        elif item and event.key() == Qt.Key.Key_F:
            self.favorite_requested.emit(item)
        else:
            super().keyPressEvent(event)

    def _context_menu(self, position):
        index = self.indexAt(position)
        if not index.isValid():
            return
        item = index.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("Abrir", lambda: self.open_requested.emit(item))
        menu.addAction("Remover dos favoritos" if self.library.is_favorite(item) else "Adicionar aos favoritos", lambda: self.favorite_requested.emit(item))
        if self.library.checkpoint(item) and item.kind != "series":
            menu.addAction("Remover de continuar assistindo", lambda: self.remove_progress_requested.emit(item))
        menu.exec(self.viewport().mapToGlobal(position))
