"""Embedded single-stream player with durable movie/episode checkpoints."""
import ctypes
import os
from pathlib import Path

import PySide6
from PySide6.QtCore import QLocale, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QActionGroup, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QBoxLayout, QHBoxLayout, QMenu, QPushButton, QSizePolicy, QSlider,
    QToolButton, QVBoxLayout, QWidget,
)

from .icons import icon
from .login import label


def timestamp(milliseconds):
    seconds = max(0, int(milliseconds) // 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def _private_media_logging():
    # FFmpeg's native format dump can include credentials from a stream URL.
    if os.name == "nt":
        for path in Path(PySide6.__file__).parent.glob("avutil-*.dll"):
            try:
                native = ctypes.WinDLL(str(path))
                native.av_log_set_level.argtypes = [ctypes.c_int]
                native.av_log_set_level.restype = None
                native.av_log_set_level(-8)
            except (OSError, AttributeError):
                pass


class PlayerWidget(QWidget):
    library_changed = Signal()
    back_requested = Signal()
    episode_finished = Signal(object)

    def __init__(self, client, library, item, restart=False, parent=None, source_override=None):
        super().__init__(parent)
        self.client, self.library, self.item = client, library, item
        checkpoint = library.checkpoint(item)
        self.pending_resume = 0 if restart or not checkpoint else checkpoint["position"]
        self.finished = False
        self.closing = False
        self.fullscreen_state = None
        self.setObjectName("playerRoot")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 14, 22, 18)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        self.back = self._button("back", "Voltar ao catálogo", self.back_requested.emit)
        heading.addWidget(self.back)
        self.title_label = label(item.display_name, "sectionTitle")
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title_label.setToolTip(item.display_name)
        heading.addWidget(self.title_label, 1)
        layout.addLayout(heading)
        self.video = QVideoWidget()
        self.video.setMinimumSize(0, 0)
        self.video.setStyleSheet("background: #000;")
        layout.addWidget(self.video, 1)
        feedback = QHBoxLayout()
        self.status = label("Conectando à transmissão…", "muted", True)
        feedback.addWidget(self.status, 1)
        self.retry = QPushButton("Tentar novamente")
        self.retry.setObjectName("secondary")
        self.retry.clicked.connect(self._retry)
        self.retry.hide()
        feedback.addWidget(self.retry)
        layout.addLayout(feedback)

        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 10000)
        self.seek.setEnabled(False)
        self.seek.setAccessibleName("Posição da reprodução")
        self.seek.sliderReleased.connect(self._seek)
        layout.addWidget(self.seek)
        self.controls = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.controls.setSpacing(8)
        self.left_controls = QWidget()
        left = QHBoxLayout(self.left_controls)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(7)
        self.pause = self._button("pause", "Pausar", self.toggle_pause)
        self.rewind = self._button("rewind", "Voltar 10 segundos", lambda: self.skip(-10000))
        self.forward = self._button("forward", "Avançar 10 segundos", lambda: self.skip(10000))
        self.rewind.setEnabled(False)
        self.forward.setEnabled(False)
        self.time_label = label("00:00 / " + ("AO VIVO" if item.kind == "live" else "00:00"), "playerTime")
        for button in (self.pause, self.rewind, self.forward):
            left.addWidget(button)
        left.addWidget(self.time_label)
        left.addStretch()
        self.controls.addWidget(self.left_controls, 1)
        self.right_controls = QWidget()
        right = QHBoxLayout(self.right_controls)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(9)
        right.addStretch()
        self.mute = self._button("volume", "Silenciar", self.toggle_mute)
        right.addWidget(self.mute)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(90)
        self.volume.setAccessibleName("Volume")
        right.addWidget(self.volume)
        self.audio_button = self._button("music", "Faixa de áudio")
        self.subtitle_button = self._button("subtitles", "Legendas")
        self.audio_menu = QMenu(self.audio_button)
        self.subtitle_menu = QMenu(self.subtitle_button)
        for button, menu in ((self.audio_button, self.audio_menu), (self.subtitle_button, self.subtitle_menu)):
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            right.addWidget(button)
        self.audio_menu.aboutToShow.connect(lambda: self._track_menu(False))
        self.subtitle_menu.aboutToShow.connect(lambda: self._track_menu(True))
        self.fullscreen = self._button("full", "Tela cheia", self.toggle_fullscreen)
        right.addWidget(self.fullscreen)
        self.controls.addWidget(self.right_controls)
        layout.addLayout(self.controls)

        _private_media_logging()
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.volume.valueChanged.connect(self._volume)
        self.audio.mutedChanged.connect(self._mute_changed)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(self._duration)
        self.player.seekableChanged.connect(self._seekable)
        self.player.mediaStatusChanged.connect(self._status)
        self.player.playbackStateChanged.connect(self._state)
        self.player.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.flush_progress)
        self.source = QUrl(source_override) if source_override else QUrl(client.playback_url(item))
        for key, callback in (("Space", self.toggle_pause), ("F", self.toggle_fullscreen),
                              ("Escape", self.escape), ("Left", lambda: self.skip(-10000)),
                              ("Right", lambda: self.skip(10000))):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
        QTimer.singleShot(0, self._start)

    def _button(self, symbol, text, callback=None):
        button = QToolButton()
        button.setObjectName("playerButton")
        button.setIcon(icon(symbol, "#dcece8", 22))
        button.setToolTip(text)
        button.setAccessibleName(text)
        button.setFixedSize(38, 38)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            button.clicked.connect(callback)
        return button

    def resizeEvent(self, event):
        self.controls.setDirection(QBoxLayout.Direction.TopToBottom if event.size().width() < 700 else QBoxLayout.Direction.LeftToRight)
        super().resizeEvent(event)

    def _start(self):
        if self.closing:
            return
        self.player.setSource(self.source)
        self.player.play()
        self.timer.start()

    def load_item(self, item, restart=False, source_override=None):
        # Reuse the decoding surface between episodes. Destroying a video sink
        # while the previous decoder is draining can block some video drivers.
        self.flush_progress()
        self.timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.item = item
        checkpoint = self.library.checkpoint(item)
        self.pending_resume = 0 if restart or not checkpoint else checkpoint["position"]
        self.finished = False
        self.title_label.setText(item.display_name)
        self.title_label.setToolTip(item.display_name)
        self.seek.setEnabled(False)
        self.rewind.setEnabled(False)
        self.forward.setEnabled(False)
        self.seek.setValue(0)
        self.retry.hide()
        self.status.setText("Conectando à transmissão…")
        self.status.show()
        self.source = QUrl(source_override) if source_override else QUrl(self.client.playback_url(item))
        self._position(0)
        QTimer.singleShot(0, self._start)

    def _retry(self):
        self.retry.hide()
        self.finished = False
        self.pending_resume = self.player.position() or self.pending_resume
        self.player.stop()
        self.player.setSource(QUrl())
        self.status.setText("Tentando conectar novamente…")
        self._start()

    def _position(self, value):
        duration = self.player.duration()
        self.time_label.setText(f"{timestamp(value)} / {'AO VIVO' if self.item.kind == 'live' else timestamp(duration)}")
        if duration > 0 and not self.seek.isSliderDown():
            self.seek.setValue(min(10000, int(value * 10000 / duration)))

    def _duration(self, _value):
        self._position(self.player.position())
        self._apply_resume()

    def _seekable(self, value):
        enabled = value and self.item.kind != "live"
        for widget in (self.seek, self.rewind, self.forward):
            widget.setEnabled(enabled)
        self._apply_resume()

    def _apply_resume(self):
        if self.pending_resume and self.player.isSeekable() and self.player.duration() > 0:
            position = min(self.pending_resume, max(0, self.player.duration() - 1000))
            self.pending_resume = 0
            self.player.setPosition(position)

    def _seek(self):
        if self.seek.isEnabled() and self.player.duration():
            self.pending_resume = 0
            self.finished = False
            self.player.setPosition(int(self.seek.value() * self.player.duration() / 10000))
            self.flush_progress()

    def skip(self, milliseconds):
        if self.seek.isEnabled():
            self.pending_resume = 0
            self.finished = False
            self.player.setPosition(max(0, min(self.player.duration(), self.player.position() + milliseconds)))

    def _status(self, status):
        if self.closing:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia and not self.finished:
            self.finished = True
            self.flush_progress()
            self.status.setText("Reprodução concluída.")
            self.status.show()
            self.library_changed.emit()
            self.episode_finished.emit(self.item)
        elif status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._apply_resume()
            self.status.hide()
        elif status in (QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.StalledMedia):
            self.status.setText("Carregando a transmissão…")
            self.status.show()

    def _state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        text = "Pausar" if playing else "Reproduzir"
        self.pause.setToolTip(text)
        self.pause.setAccessibleName(text)
        self.pause.setIcon(icon("pause" if playing else "play", "#dcece8", 22))
        if not playing and not self.closing:
            self.flush_progress()

    def _error(self, _error, _message):
        if self.closing:
            return
        self.flush_progress()
        self.status.setText("Não foi possível reproduzir. Confira a conexão, o limite de telas da conta ou tente outro conteúdo.")
        self.status.show()
        self.retry.show()

    def flush_progress(self):
        if self.pending_resume:
            return
        position = self.player.duration() if self.finished else self.player.position()
        try:
            self.library.record_progress(self.item, position, self.player.duration(), self.finished)
        except Exception:
            self.status.setText("Não foi possível salvar o progresso neste computador.")
            self.status.show()

    def toggle_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.flush_progress()
        else:
            if self.finished:
                self.finished = False
                self.player.setPosition(0)
            self.player.play()

    def toggle_mute(self):
        if self.volume.value() == 0:
            self.volume.setValue(70)
            self.audio.setMuted(False)
            return
        self.audio.setMuted(not self.audio.isMuted())

    def _volume(self, value):
        self.audio.setVolume(value / 100)
        if value > 0:
            self.audio.setMuted(False)
        self._mute_changed(self.audio.isMuted())

    def _mute_changed(self, muted):
        silent = muted or self.volume.value() == 0
        self.mute.setIcon(icon("muted" if silent else "volume", "#dcece8", 22))
        text = "Ativar som" if silent else "Silenciar"
        self.mute.setToolTip(text)
        self.mute.setAccessibleName(text)

    @staticmethod
    def track_name(metadata, index):
        title = metadata.stringValue(QMediaMetaData.Key.Title).strip()
        language = metadata.value(QMediaMetaData.Key.Language)
        if isinstance(language, QLocale.Language):
            language = QLocale(language).nativeLanguageName() if language != QLocale.Language.AnyLanguage else ""
        elif language:
            locale = QLocale(str(language))
            language = locale.nativeLanguageName() if locale.language() != QLocale.Language.C else str(language)
        return " · ".join(part for part in (title, str(language or "")) if part) or f"Faixa {index + 1}"

    def _track_menu(self, subtitles):
        menu = self.subtitle_menu if subtitles else self.audio_menu
        menu.clear()
        old_group = getattr(menu, "track_group", None)
        if old_group:
            old_group.deleteLater()
        group = QActionGroup(menu)
        group.setExclusive(True)
        menu.track_group = group
        tracks = self.player.subtitleTracks() if subtitles else self.player.audioTracks()
        active = self.player.activeSubtitleTrack() if subtitles else self.player.activeAudioTrack()
        setter = self.player.setActiveSubtitleTrack if subtitles else self.player.setActiveAudioTrack
        if subtitles:
            action = menu.addAction("Desativadas")
            action.setCheckable(True)
            action.setChecked(active == -1)
            group.addAction(action)
            action.triggered.connect(lambda _checked: setter(-1))
        for index, metadata in enumerate(tracks):
            action = menu.addAction(self.track_name(metadata, index))
            action.setData(index)
            action.setCheckable(True)
            action.setChecked(active == index)
            group.addAction(action)
            action.triggered.connect(lambda _checked, i=index: setter(i))
        if not tracks:
            menu.addAction("Nenhuma legenda disponível" if subtitles else "Nenhuma faixa de áudio disponível").setEnabled(False)

    def toggle_fullscreen(self):
        window = self.window()
        if self.fullscreen_state is not None:
            self.leave_fullscreen()
        else:
            self.fullscreen_state = window.windowState()
            window.showFullScreen()
            self.fullscreen.setToolTip("Sair da tela cheia")
            self.fullscreen.setAccessibleName("Sair da tela cheia")

    def leave_fullscreen(self):
        if self.fullscreen_state is not None:
            self.window().setWindowState(self.fullscreen_state)
            self.fullscreen_state = None
            self.fullscreen.setToolTip("Tela cheia")
            self.fullscreen.setAccessibleName("Tela cheia")

    def escape(self):
        if self.fullscreen_state is not None:
            self.leave_fullscreen()
        else:
            self.back_requested.emit()

    def shutdown(self):
        if self.closing:
            return
        self.closing = True
        self.flush_progress()
        self.leave_fullscreen()
        self.timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.player.setVideoOutput(None)
        self.player.setAudioOutput(None)
        self.library_changed.emit()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
