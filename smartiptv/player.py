"""Single-stream player with durable movie/episode checkpoints."""
import ctypes
import os
from pathlib import Path
import PySide6
from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QPushButton, QSlider, QVBoxLayout, QWidget

from .icons import icon
from .login import label
from .theme import THEME


def timestamp(milliseconds):
    seconds = max(0, int(milliseconds) // 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def _private_media_logging():
    # FFmpeg's native format dump can print credentials embedded in stream URLs.
    # User-facing failures are reported through QMediaPlayer.errorOccurred instead.
    if os.name == "nt":
        for path in Path(PySide6.__file__).parent.glob("avutil-*.dll"):
            try:
                native = ctypes.WinDLL(str(path))
                native.av_log_set_level.argtypes = [ctypes.c_int]
                native.av_log_set_level.restype = None
                native.av_log_set_level(-8)
            except (OSError, AttributeError):
                pass


class PlayerWindow(QMainWindow):
    library_changed = Signal()

    def __init__(self, client, library, item, restart=False, parent=None, source_override=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.client, self.library, self.item = client, library, item
        checkpoint = library.checkpoint(item)
        self.pending_resume = 0 if restart or not checkpoint else checkpoint["position"]
        self.finished = False
        self.closing = False
        self.setWindowTitle(f"{item.display_name} — SmartIPTV")
        self.resize(1100, 760)
        self.setMinimumSize(740, 500)
        self.setStyleSheet(THEME)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(13)
        heading = QHBoxLayout()
        back = QPushButton("Voltar ao catálogo")
        back.setObjectName("secondary")
        back.setIcon(icon("back"))
        back.clicked.connect(self.close)
        heading.addWidget(back)
        heading.addStretch()
        heading.addWidget(label("AO VIVO" if item.kind == "live" else "SMARTIPTV PLAYER", "eyebrow"))
        layout.addLayout(heading)
        self.title_label = label(item.display_name, "sectionTitle", True)
        layout.addWidget(self.title_label)
        self.video = QVideoWidget()
        self.video.setStyleSheet("background: #000;")
        layout.addWidget(self.video, 1)
        self.status = label("Conectando à transmissão…", "muted", True)
        layout.addWidget(self.status)
        timeline = QHBoxLayout()
        self.elapsed = label("00:00", "muted")
        self.duration = label("AO VIVO" if item.kind == "live" else "00:00", "muted")
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 10000)
        self.seek.setEnabled(False)
        self.seek.setAccessibleName("Posição da reprodução")
        self.seek.sliderReleased.connect(self._seek)
        timeline.addWidget(self.elapsed)
        timeline.addWidget(self.seek, 1)
        timeline.addWidget(self.duration)
        layout.addLayout(timeline)
        controls = QHBoxLayout()
        self.pause = QPushButton("Pausar")
        self.pause.setObjectName("secondary")
        self.pause.setIcon(icon("pause", "#8ce5b0"))
        self.pause.clicked.connect(self.toggle_pause)
        controls.addWidget(self.pause)
        self.retry = QPushButton("Tentar novamente")
        self.retry.setObjectName("secondary")
        self.retry.clicked.connect(self._retry)
        self.retry.hide()
        controls.addWidget(self.retry)
        controls.addStretch()
        controls.addWidget(label("Volume", "muted"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(105)
        self.volume.setAccessibleName("Volume")
        controls.addWidget(self.volume)
        fullscreen = QPushButton("Tela cheia")
        fullscreen.setObjectName("secondary")
        fullscreen.setIcon(icon("full"))
        fullscreen.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(fullscreen)
        layout.addLayout(controls)
        self.player = QMediaPlayer(self)
        _private_media_logging()
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
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
        QTimer.singleShot(0, self._start)

    def _start(self):
        if self.closing:
            return
        self.player.setSource(self.source)
        self.player.play()
        self.timer.start()

    def _retry(self):
        self.retry.hide()
        self.finished = False
        self.pending_resume = self.player.position() or self.pending_resume
        self.player.stop()
        self.player.setSource(QUrl())
        self.status.setText("Tentando conectar novamente…")
        self._start()

    def _position(self, value):
        self.elapsed.setText(timestamp(value))
        duration = self.player.duration()
        if duration > 0 and not self.seek.isSliderDown():
            self.seek.setValue(min(10000, int(value * 10000 / duration)))

    def _duration(self, value):
        if self.item.kind != "live":
            self.duration.setText(timestamp(value))
        self._apply_resume()

    def _seekable(self, value):
        self.seek.setEnabled(value and self.item.kind != "live")
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

    def _status(self, status):
        if self.closing:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.finished = True
            self.flush_progress()
            self.status.setText("Reprodução concluída.")
            self.library_changed.emit()
        elif status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._apply_resume()
            self.status.setText("Ao vivo" if self.item.kind == "live" else "Seu progresso é salvo automaticamente.")
        elif status in (QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.StalledMedia):
            self.status.setText("Carregando a transmissão…")

    def _state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.pause.setText("Pausar" if playing else "Reproduzir")
        self.pause.setIcon(icon("pause" if playing else "play", "#8ce5b0"))
        if not playing and not self.closing:
            self.flush_progress()

    def _error(self, error, _message):
        if self.closing:
            return
        self.flush_progress()
        self.status.setText("Não foi possível reproduzir. Confira a conexão, o limite de telas da conta ou tente outro conteúdo.")
        self.retry.show()

    def flush_progress(self):
        if self.pending_resume:
            return
        position = self.player.duration() if self.finished else self.player.position()
        try:
            self.library.record_progress(self.item, position, self.player.duration(), self.finished)
        except Exception:
            self.status.setText("Não foi possível salvar o progresso neste computador.")

    def toggle_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.flush_progress()
        else:
            if self.finished:
                self.finished = False
                self.player.setPosition(0)
            self.player.play()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.showNormal() if self.isFullScreen() else self.close()
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_pause()
        elif event.key() == Qt.Key.Key_F:
            self.toggle_fullscreen()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.seek.isEnabled():
            self.finished = False
            self.player.setPosition(max(0, self.player.position() + (10000 if event.key() == Qt.Key.Key_Right else -10000)))
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closing = True
        self.flush_progress()
        self.timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.library_changed.emit()
        super().closeEvent(event)
