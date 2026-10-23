from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget, QCheckBox,
)

from . import __version__
from .icons import icon
from .validation import server_error


STYLE = """
QWidget { color: #edf5f2; font-family: 'Segoe UI'; font-size: 14px; }
QWidget#root { background: #0b1011; }
QFrame#formCard { background: #121a1c; border: 1px solid #273335; border-radius: 20px; }
QLabel { background: transparent; border: none; }
QLabel#brand { font-size: 22px; font-weight: 700; letter-spacing: -0.6px; }
QLabel#eyebrow { color: #67dfb1; font-size: 11px; font-weight: 600; letter-spacing: 2px; }
QLabel#heroTitle { font-size: 46px; font-weight: 650; letter-spacing: -1.7px; }
QLabel#heroDescription { color: #9aaba7; font-size: 15px; }
QLabel#formTitle { font-size: 29px; font-weight: 650; letter-spacing: -0.8px; }
QLabel#muted { color: #91a19e; font-size: 13px; }
QLabel#fieldLabel { color: #d3dfdc; font-size: 13px; font-weight: 600; }
QLabel#helper { color: #7f9390; font-size: 11px; }
QLabel#version { color: #859995; font-size: 11px; }
QLabel#pill { color: #a8bdba; background: #172321; border: 1px solid #2d413b; border-radius: 11px; padding: 5px 12px; font-size: 11px; }
QFrame#inputBox { border: 1px solid #334241; border-radius: 9px; background: #0d1416; }
QFrame#inputBox[focused="true"] { border: 1px solid #65dfad; background: #101c1b; }
QFrame#inputBox[invalid="true"] { border: 1px solid #ef9e9a; }
QLineEdit { background: transparent; color: #edf5f2; border: none; selection-background-color: #36795f; padding: 0; font-size: 14px; }
QToolButton { border: none; border-radius: 5px; background: transparent; padding: 4px; }
QToolButton:hover { background: #24332f; }
QToolButton:focus { border: 1px solid #67dfb1; }
QPushButton#submit { color: #08231a; background: #65dfad; border: 1px solid #65dfad; border-radius: 9px; font-size: 14px; font-weight: 700; padding: 12px; }
QPushButton#submit:hover { background: #80ecc0; border-color: #80ecc0; }
QPushButton#submit:pressed { background: #45bd8d; }
QPushButton#submit:focus { border: 2px solid #e3fff0; padding: 11px; }
QLabel#notice { color: #9baba7; font-size: 12px; }
QLabel#feedback { color: #f2aaa4; font-size: 12px; }
QLabel#feedback[success="true"] { color: #80e6b9; }
QCheckBox { color: #b7c9c3; font-size: 12px; spacing: 9px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #4a6258; border-radius: 4px; background: #0d1416; }
QCheckBox::indicator:checked { background: #65dfad; border: 4px solid #285842; }
QCheckBox::indicator:focus { border-color: #e3fff0; }
QPushButton:disabled { background: #2b4840; color: #97b8aa; border-color: #2b4840; }
"""


def label(text: str, name: str, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


class InputField(QFrame):
    def __init__(self, name: str, placeholder: str, symbol: str, password: bool = False):
        super().__init__()
        self.setObjectName("inputBox")
        self.setProperty("focused", False)
        self.setProperty("invalid", False)
        self.setFixedHeight(50)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 10, 0)
        layout.setSpacing(12)
        glyph = QLabel()
        glyph.setPixmap(icon(symbol).pixmap(QSize(18, 18)))
        glyph.setFixedSize(18, 20)
        layout.addWidget(glyph)
        self.edit = QLineEdit()
        self.edit.setObjectName(name)
        self.edit.setAccessibleName(name)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setMaxLength(2048 if name == "Servidor" else 512)
        self.edit.installEventFilter(self)
        self.setFocusProxy(self.edit)
        layout.addWidget(self.edit, 1)
        self.reveal = None
        if password:
            self.edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.edit.setInputMethodHints(Qt.InputMethodHint.ImhHiddenText | Qt.InputMethodHint.ImhNoPredictiveText)
            self.reveal = QToolButton()
            self.reveal.setCheckable(True)
            self.reveal.setIcon(icon("eye"))
            self.reveal.setIconSize(QSize(19, 19))
            self.reveal.setFixedSize(30, 32)
            self.reveal.setCursor(Qt.CursorShape.PointingHandCursor)
            self.reveal.setToolTip("Mostrar senha")
            self.reveal.setAccessibleName("Mostrar senha")
            self.reveal.toggled.connect(self._toggle_password)
            layout.addWidget(self.reveal)

    def _toggle_password(self, visible: bool) -> None:
        self.edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.reveal.setIcon(icon("eye-off" if visible else "eye"))
        text = "Ocultar senha" if visible else "Mostrar senha"
        self.reveal.setToolTip(text)
        self.reveal.setAccessibleName(text)

    def set_state(self, name: str, value: bool) -> None:
        self.setProperty(name, value)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn:
            self.set_state("focused", True)
        elif event.type() == QEvent.Type.FocusOut:
            self.set_state("focused", False)
        return super().eventFilter(watched, event)


class ScreenArtwork(QWidget):
    """Resolution-independent illustration; no remote or copyrighted artwork."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(200)
        self.setMaximumHeight(250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.width() / 2 - 184, self.height() / 2 - 106)
        # Fine orbital lines behind a simple, abstract media screen.
        p.setPen(QPen(QColor("#1d3631"), 1))
        p.drawEllipse(QRectF(-15, -6, 400, 235))
        p.drawEllipse(QRectF(-42, -24, 454, 270))
        p.setPen(QPen(QColor("#37594d"), 1))
        p.setBrush(QColor("#142522"))
        p.drawRoundedRect(QRectF(15, 20, 338, 185), 15, 15)
        gradient = QLinearGradient(20, 20, 340, 180)
        gradient.setColorAt(0, QColor("#24483a"))
        gradient.setColorAt(1, QColor("#10211e"))
        p.setBrush(gradient)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(23, 28, 322, 169), 10, 10)
        p.setBrush(QColor("#2d5d48"))
        p.drawEllipse(QRectF(170, 45, 140, 140))
        p.setBrush(QColor("#3d7a59"))
        p.drawEllipse(QRectF(216, 24, 88, 88))
        p.setBrush(QColor("#78dfac"))
        p.drawEllipse(QRectF(153, 81, 62, 62))
        path = QPainterPath()
        path.moveTo(179, 100)
        path.lineTo(195, 112)
        path.lineTo(179, 124)
        path.closeSubpath()
        p.setBrush(QColor("#163a2b"))
        p.drawPath(path)
        p.setPen(QPen(QColor("#6b8b7c"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(43, 174), QPointF(322, 174))
        p.setPen(QPen(QColor("#83e4b5"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(43, 174), QPointF(148, 174))
        p.setBrush(QColor("#83e4b5"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(145, 170, 8, 8))
        # Offset mini cards hint at a collection, without pretending to load one.
        for x, y, color in [(0, 155, "#17342b"), (297, 0, "#284635")]:
            p.setPen(QPen(QColor("#496f59"), 1))
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, y, 64, 48), 8, 8)
            p.setPen(QPen(QColor("#88b49b"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x + 15, y + 18), QPointF(x + 48, y + 18))
            p.drawLine(QPointF(x + 15, y + 28), QPointF(x + 36, y + 28))
        p.end()


class LoginWindow(QMainWindow):
    login_requested = Signal(str, str, str, bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"SmartIPTV — {__version__}")
        self.resize(1120, 820)
        self.setMinimumSize(560, 800)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        self.setStyleSheet(STYLE)
        page = QVBoxLayout(root)
        page.setContentsMargins(42, 28, 42, 22)
        page.setSpacing(18)

        header = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setPixmap(icon("tv", "#65dfad", 32).pixmap(QSize(32, 32)))
        header.addWidget(brand_icon)
        header.addSpacing(4)
        header.addWidget(label("SmartIPTV", "brand"))
        header.addStretch()
        header.addWidget(label(f"v{__version__}", "pill"))
        page.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(54)
        self.hero = QWidget()
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(16)
        hero_layout.addStretch()
        hero_layout.addWidget(label("SUA PRÓXIMA EXPERIÊNCIA", "eyebrow"))
        hero_layout.addWidget(label("Sua playlist.\nSeu espaço.", "heroTitle"))
        hero_layout.addWidget(label("Um novo lugar para seus canais,\nfilmes e séries favoritos.", "heroDescription"))
        hero_layout.addWidget(ScreenArtwork())
        hero_layout.addStretch()
        body.addWidget(self.hero, 1)

        self.card = QFrame()
        self.card.setObjectName("formCard")
        self.card.setMaximumWidth(460)
        self.card.setMinimumWidth(400)
        form = QVBoxLayout(self.card)
        form.setContentsMargins(32, 26, 32, 22)
        form.setSpacing(0)
        form.addWidget(label("ACESSO XTREAM", "eyebrow"))
        form.addSpacing(12)
        form.addWidget(label("Bem-vindo ao SmartIPTV", "formTitle", True))
        form.addSpacing(9)
        form.addWidget(label("Preencha os dados do seu provedor.", "muted", True))
        form.addSpacing(24)

        self.server = InputField("Servidor", "http://seu-servidor.com:porta", "server")
        self.username = InputField("Usuário", "Seu usuário", "user")
        self.password = InputField("Senha", "Sua senha", "lock", password=True)
        for caption, field in [("Servidor", self.server), ("Usuário", self.username), ("Senha", self.password)]:
            heading = label(caption, "fieldLabel")
            heading.setBuddy(field.edit)
            form.addWidget(heading)
            form.addSpacing(8)
            form.addWidget(field)
            if field is self.server:
                form.addSpacing(7)
                form.addWidget(label("Endereço do servidor, incluindo a porta se houver.", "helper", True))
            form.addSpacing(16)
            field.edit.textChanged.connect(lambda _text, f=field: self._clear_feedback(f))
            field.edit.returnPressed.connect(self.validate_form)

        self.remember = QCheckBox("Manter conectado nesse computador")
        self.remember.setAccessibleName("Manter conectado nesse computador")
        form.addWidget(self.remember)
        form.addSpacing(18)
        self.submit = QPushButton("Entrar")
        self.submit.setObjectName("submit")
        self.submit.setIcon(icon("arrow", "#08231a", 20))
        self.submit.setIconSize(QSize(20, 20))
        self.submit.setMinimumHeight(48)
        self.submit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit.clicked.connect(self.validate_form)
        form.addWidget(self.submit)
        form.addSpacing(12)
        self.feedback = label("", "feedback", True)
        self.feedback.setAccessibleName("Resultado da validação")
        self.feedback.setMinimumHeight(38)
        form.addWidget(self.feedback)
        form.addSpacing(10)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #293634;")
        form.addWidget(divider)
        form.addSpacing(16)
        form.addWidget(label("Use os dados de acesso fornecidos pelo seu provedor.", "notice", True))
        body.addWidget(self.card, 1, Qt.AlignmentFlag.AlignVCenter)
        page.addLayout(body, 1)
        footer = QHBoxLayout()
        footer.addWidget(label("SMARTIPTV  /  DESKTOP", "version"))
        footer.addStretch()
        footer.addWidget(label("Feito para a sua playlist.", "version"))
        page.addLayout(footer)
        QWidget.setTabOrder(self.server.edit, self.username.edit)
        QWidget.setTabOrder(self.username.edit, self.password.edit)
        QWidget.setTabOrder(self.password.edit, self.password.reveal)
        QWidget.setTabOrder(self.password.reveal, self.remember)
        QWidget.setTabOrder(self.remember, self.submit)
        self.server.edit.setFocus()

    def resizeEvent(self, event):
        self.hero.setVisible(event.size().width() >= 940)
        super().resizeEvent(event)

    def _clear_feedback(self, field: InputField) -> None:
        field.set_state("invalid", False)
        self.feedback.clear()

    def validate_form(self) -> bool:
        if not self.submit.isEnabled():
            return False
        errors = [
            (self.server, server_error(self.server.edit.text())),
            (self.username, None if self.username.edit.text().strip() else "Informe seu usuário."),
            (self.password, None if self.password.edit.text() else "Informe sua senha."),
        ]
        for field, error in errors:
            field.set_state("invalid", bool(error))
        first = next(((field, error) for field, error in errors if error), None)
        self.feedback.setProperty("success", False)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)
        if first:
            field, message = first
            self.feedback.setText(message)
            field.edit.setFocus()
            return False
        self.feedback.setText("Conectando ao servidor…")
        self.login_requested.emit(self.server.edit.text().strip().rstrip("/"), self.username.edit.text().strip(), self.password.edit.text(), self.remember.isChecked())
        return True

    def set_busy(self, busy):
        self.submit.setEnabled(not busy)
        self.submit.setText("Conectando…" if busy else "Entrar")
        for field in (self.server, self.username, self.password):
            field.setEnabled(not busy)
        self.remember.setEnabled(not busy)

    def show_error(self, message):
        self.set_busy(False)
        self.feedback.setProperty("success", False)
        self.feedback.setText(message)

    def fill_session(self, credentials):
        self.server.edit.setText(credentials.server)
        self.username.edit.setText(credentials.username)
        self.password.edit.setText(credentials.password)
        self.remember.setChecked(True)
