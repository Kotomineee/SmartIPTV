"""Application preferences kept on this computer."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .icons import icon
from .login import label


class Switch(QAbstractButton):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(50, 30)
        self.setAccessibleName(text)
        self.setToolTip(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#8ae9bc" if self.hasFocus() else "#496358"), 1))
        painter.setBrush(QColor("#65dfad" if self.isChecked() else "#243b33"))
        painter.drawRoundedRect(QRectF(1, 3, 48, 24), 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#10271e" if self.isChecked() else "#adc5bc"))
        painter.drawEllipse(QRectF(28 if self.isChecked() else 5, 7, 16, 16))


class SettingsPage(QWidget):
    def __init__(self, library, refresh, logout, notify, parent=None):
        super().__init__(parent)
        self.library, self.notify = library, notify
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(20)
        self.auto_next = Switch("Reproduzir próximo episódio")
        self.auto_next.setChecked(library.auto_next_enabled)
        self.auto_next.toggled.connect(self._save)
        self._card(layout, "Reprodução", "Reproduzir próximo episódio", "Ao terminar um episódio, continuar automaticamente para o próximo disponível.", self.auto_next)
        self._card(layout, "Biblioteca", "Atualizar conteúdos", "Carregue os canais, filmes e séries mais recentes da sua playlist.", refresh)
        logout_button = QPushButton("Sair da conta")
        logout_button.setObjectName("secondary")
        logout_button.setIcon(icon("logout"))
        logout_button.clicked.connect(logout)
        self.logout = logout_button
        self._card(layout, "Conta", "Sair da conta", "Volte à tela de login para entrar com outra conta.", logout_button)
        layout.addStretch()

    def _card(self, layout, heading, title, description, control):
        card = QFrame()
        card.setObjectName("settingsCard")
        body = QVBoxLayout(card)
        body.setContentsMargins(24, 20, 24, 22)
        body.setSpacing(15)
        body.addWidget(label(heading.upper(), "eyebrow"))
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label(title, "sectionTitle", True))
        text.addWidget(label(description, "muted", True))
        row.addLayout(text, 1)
        row.addSpacing(20)
        row.addWidget(control)
        body.addLayout(row)
        layout.addWidget(card)

    def _save(self, enabled):
        try:
            self.library.set_auto_next(enabled)
        except Exception:
            self.auto_next.blockSignals(True)
            self.auto_next.setChecked(not enabled)
            self.auto_next.blockSignals(False)
            self.notify("Não foi possível salvar a preferência neste computador.", True)
