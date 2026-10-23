import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from . import __version__
from .icons import icon
from .login import LoginWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SmartIPTV")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SmartIPTV")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(icon("tv", "#5ce5ac", 64))
    window = LoginWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(500, app.quit)
    return app.exec()
