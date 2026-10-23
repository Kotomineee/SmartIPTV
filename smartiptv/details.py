from PySide6.QtCore import QEvent, Qt, QSize, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QToolButton, QVBoxLayout, QWidget

from .icons import icon
from .backdrop import DetailBackdrop
from .login import label
from .player import timestamp
from .theme import THEME


class DetailDialog(QFrame):
    play_requested = Signal(object, bool, object)
    favorite_requested = Signal(object)
    finished = Signal(int)

    def __init__(self, item, client, library, tasks, artwork, parent=None, content_left=0):
        super().__init__(parent)
        self.item, self.client, self.library, self.tasks, self.artwork = item, client, library, tasks, artwork
        self.task_id = None
        self.episodes = []
        self.dismissed = False
        self.backdrop = None
        self.content_left = content_left
        self.setObjectName("detailPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle(item.name)
        self.setStyleSheet(THEME)
        self.resize(850, 660 if item.kind == "series" else 530)
        self.setMinimumWidth(650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(18)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close = QToolButton()
        close.setIcon(icon("close", "#b7c9c3"))
        close.setToolTip("Fechar detalhes")
        close.setAccessibleName("Fechar detalhes")
        close.clicked.connect(self.reject)
        close_row.addWidget(close)
        layout.addLayout(close_row)
        top = QHBoxLayout()
        top.setSpacing(26)
        self.poster = QLabel()
        self.poster.setFixedSize(180, 250 if item.kind != "live" else 150)
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster.setStyleSheet("background: #1d3325; border-radius: 10px;")
        self.poster.setPixmap(icon("tv" if item.kind == "live" else "film", "#639574", 48).pixmap(QSize(48, 48)))
        top.addWidget(self.poster, 0, Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(12)
        info.addWidget(label({"live": "TV AO VIVO", "movie": "FILME", "series": "SÉRIE", "episode": "EPISÓDIO"}[item.kind], "eyebrow"))
        info.addWidget(label(item.name, "detailTitle", True))
        caption = " · ".join(value for value in (item.year, f"Nota {item.rating}" if item.rating and item.rating != "0" else "") if value)
        self.caption = label(caption, "muted", True)
        info.addWidget(self.caption)
        self.plot = label(item.plot or ("Carregando informações…" if item.kind in ("movie", "series") else "Transmissão ao vivo do seu provedor."), "body", True)
        self.plot.setMaximumHeight(155)
        info.addWidget(self.plot)
        self.favorite = QPushButton()
        self.favorite.setObjectName("secondary")
        self.favorite.clicked.connect(self._favorite)
        top.addLayout(info, 1)
        layout.addLayout(top)
        self.feedback = label("", "muted", True)
        self.feedback.setVisible(item.kind == "series")
        layout.addWidget(self.feedback)
        self.retry = QPushButton("Carregar novamente")
        self.retry.setObjectName("secondary")
        self.retry.clicked.connect(self._load)
        self.retry.hide()
        layout.addWidget(self.retry)
        self.seasons = QComboBox()
        self.seasons.setAccessibleName("Temporada")
        self.seasons.currentIndexChanged.connect(self._season_changed)
        self.episode_list = QListWidget()
        self.episode_list.setObjectName("episodes")
        self.episode_list.setAccessibleName("Episódios da temporada")
        self.episode_list.itemDoubleClicked.connect(lambda _item: self._play_selected())
        if item.kind == "series":
            layout.addWidget(self.seasons)
            layout.addWidget(self.episode_list, 1)
        else:
            self.seasons.hide()
            self.episode_list.hide()
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        secondary = QHBoxLayout()
        secondary.setSpacing(10)
        checkpoint = library.checkpoint(item)
        self.restart = QPushButton("Assistir do início")
        self.restart.setObjectName("secondary")
        self.restart.setVisible(bool(checkpoint) and item.kind != "series")
        self.restart.clicked.connect(lambda: self._play(self.item, True))
        secondary.addWidget(self.restart)
        self.resume = QPushButton("Continuar episódio")
        self.resume.setObjectName("secondary")
        self.resume.setVisible(item.kind == "series" and bool(checkpoint))
        self.resume.clicked.connect(lambda: self._play(checkpoint["item"]))
        secondary.addWidget(self.resume)
        self.watch = QPushButton("Assistir episódio" if item.kind == "series" else "Continuar assistindo" if checkpoint else "Assistir agora")
        self.watch.setObjectName("submit")
        self.watch.setIcon(icon("play", "#08231a"))
        self.watch.setEnabled(item.kind != "series")
        self.watch.clicked.connect(self._play_selected)
        buttons.addWidget(self.watch)
        self.favorite.setMinimumHeight(self.watch.sizeHint().height())
        buttons.addWidget(self.favorite)
        buttons.addStretch()
        info.addLayout(buttons)
        secondary.addStretch()
        info.addLayout(secondary)
        info.addStretch()
        self._update_favorite()
        artwork.changed.connect(self._update_artwork)
        self._update_artwork()
        self._load()
        self.finished.connect(self._cancel)

    def open(self):
        self._center()
        self.backdrop = DetailBackdrop(self.parentWidget())
        self.backdrop.show()
        self.backdrop.raise_()
        QApplication.instance().installEventFilter(self)
        self.show()
        self.raise_()
        self.setFocus()

    def _center(self):
        parent = self.parentWidget()
        if parent:
            available = parent.width() - self.content_left
            width = min(850, available - 32)
            height = min(710 if self.item.kind == "series" else max(390, self.sizeHint().height()), parent.height() - 24)
            self.setGeometry(self.content_left + (available - width) // 2, (parent.height() - height) // 2, width, height)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and watched is self.parentWidget():
            self._center()
            if self.backdrop:
                self.backdrop.setGeometry(self.parentWidget().rect())
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape and not QApplication.activePopupWidget():
            self.reject()
            return True
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(watched, QWidget):
            popup = QApplication.activePopupWidget()
            if popup and (self.isAncestorOf(popup) or self.isAncestorOf(popup.parentWidget())):
                return False
            if watched is not self and not self.isAncestorOf(watched):
                self.reject()
        return super().eventFilter(watched, event)

    def _finish(self, result):
        if self.dismissed:
            return
        self.dismissed = True
        QApplication.instance().removeEventFilter(self)
        self.hide()
        if self.backdrop:
            self.backdrop.hide()
            self.backdrop.deleteLater()
            self.backdrop = None
        self.finished.emit(result)

    def accept(self):
        self._finish(1)

    def reject(self):
        self._finish(0)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.reject()
        super().closeEvent(event)

    def _update_artwork(self):
        pixmap = self.artwork.get(self.item.artwork)
        if pixmap:
            self.poster.setPixmap(pixmap.scaled(self.poster.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _favorite(self):
        self.favorite_requested.emit(self.item)
        self._update_favorite()

    def _update_favorite(self):
        active = self.library.is_favorite(self.item)
        self.favorite.setText("Remover dos favoritos" if active else "Adicionar aos favoritos")
        self.favorite.setIcon(icon("heart", "#6fe8aa" if active else "#a0bca9"))

    def _load(self):
        if self.task_id:
            self.tasks.cancel(self.task_id)
        self.retry.hide()
        if self.item.kind == "series":
            self.feedback.setText("Carregando temporadas e episódios…")
            self.task_id = self.tasks.submit(lambda: self.client.series_details(self.item), self._series_loaded, self._failed)
        elif self.item.kind == "movie":
            self.task_id = self.tasks.submit(lambda: self.client.movie_details(self.item), self._movie_loaded, self._movie_failed)

    def _movie_loaded(self, info):
        if not isinstance(info, dict):
            info = {}
        self.plot.setText(str(info.get("plot") or info.get("description") or self.item.plot or "Este título não possui sinopse informada pelo provedor.")[:1800])
        self._center()

    def _movie_failed(self, _message):
        self.plot.setText(self.item.plot or "Informações adicionais indisponíveis. Você pode tentar reproduzir o conteúdo.")
        self._center()

    def _series_loaded(self, payload):
        self.episodes = payload["episodes"]
        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        self.plot.setText(str(info.get("plot") or self.item.plot or "Sinopse não informada pelo provedor.")[:1800])
        self.seasons.blockSignals(True)
        self.seasons.clear()
        for season in sorted({ep.season for ep in self.episodes}):
            self.seasons.addItem(f"Temporada {season}", season)
        checkpoint = self.library.checkpoint(self.item)
        if checkpoint:
            index = self.seasons.findData(checkpoint["item"].season)
            if index >= 0:
                self.seasons.setCurrentIndex(index)
        self.seasons.blockSignals(False)
        self._season_changed()
        self.feedback.setText(f"{len(self.episodes)} episódios disponíveis." if self.episodes else "O provedor ainda não disponibilizou episódios para esta série.")
        self.watch.setEnabled(bool(self.episodes))

    def _season_changed(self, _index=None):
        self.episode_list.clear()
        checkpoint = self.library.checkpoint(self.item)
        for episode in self.episodes:
            if episode.season != self.seasons.currentData():
                continue
            progress = self.library.checkpoint(episode)
            suffix = f"  ·  Continuar em {timestamp(progress['position'])}" if progress else ""
            row = QListWidgetItem(f"{episode.episode:02}   {episode.name}{suffix}")
            row.setData(Qt.ItemDataRole.UserRole, episode)
            row.setToolTip(episode.name)
            self.episode_list.addItem(row)
            if checkpoint and checkpoint["item"].uid == episode.uid:
                self.episode_list.setCurrentItem(row)
        if self.episode_list.currentRow() < 0 and self.episode_list.count():
            self.episode_list.setCurrentRow(0)

    def _failed(self, message):
        self.feedback.setText(message)
        self.feedback.show()
        self.retry.show()

    def _play_selected(self):
        if self.item.kind != "series":
            self._play(self.item)
        elif self.episode_list.currentItem():
            self._play(self.episode_list.currentItem().data(Qt.ItemDataRole.UserRole))

    def _play(self, item, restart=False):
        self.accept()
        self.play_requested.emit(item, restart, self.episodes)

    def _cancel(self, _result=None):
        if self.task_id:
            self.tasks.cancel(self.task_id)
