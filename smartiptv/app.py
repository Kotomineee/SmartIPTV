import sys
import re
import tempfile

from PySide6.QtCore import QObject, QTimer, qInstallMessageHandler
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .icons import icon
from .login import LoginWindow
from .browser import BrowserWindow
from .client import Credentials, XtreamClient
from .storage import Library, SessionStore
from .tasks import Tasks


class Controller(QObject):
    def __init__(self, app, directory=None, auto_login=True):
        super().__init__(app)
        self.app = app
        self.library = Library(directory)
        self.sessions = SessionStore(directory)
        self.tasks = Tasks(self)
        self.closed = False
        self.browser = None
        self.login = LoginWindow()
        self.login.login_requested.connect(self.authenticate)
        self.login.remember.toggled.connect(self._remember_changed)
        self.login.show()
        app.aboutToQuit.connect(self.shutdown)
        if auto_login:
            QTimer.singleShot(0, self.restore_session)

    def _remember_changed(self, checked):
        if not checked:
            try:
                self.sessions.clear()
            except OSError:
                self.login.show_error("Não foi possível remover a sessão salva. Confira a permissão da pasta do aplicativo.")

    def restore_session(self):
        try:
            credentials = self.sessions.load()
        except OSError as exc:
            self.login.show_error(str(exc))
            return
        if credentials:
            self.login.fill_session(credentials)
            self.login.validate_form()

    def authenticate(self, server, username, password, remember):
        self.login.set_busy(True)
        client = XtreamClient(Credentials(server, username, password))
        self.tasks.submit(client.authenticate, lambda _account: self._authenticated(client, remember), self.login.show_error)

    def _authenticated(self, client, remember):
        try:
            self.library.select_account(client.credentials)
        except Exception:
            self.login.show_error("Não foi possível abrir a biblioteca local. Confira a permissão da pasta do aplicativo.")
            return
        warning = ""
        try:
            self.sessions.save(client.credentials) if remember else self.sessions.clear()
        except OSError:
            warning = "Login realizado, mas não foi possível atualizar a sessão salva no Windows."
        self.browser = BrowserWindow(client, self.library, self.tasks)
        self.browser.logout_requested.connect(self.logout)
        self.browser.show()
        self.login.set_busy(False)
        self.login.hide()
        self.login.password.edit.clear()
        self.login.password.reveal.setChecked(False)
        if warning:
            self.browser.notify(warning, True)

    def logout(self):
        warning = ""
        try:
            self.sessions.clear()
        except OSError:
            warning = "Não foi possível apagar a sessão salva. Desmarque manter conectado e tente novamente."
        self.tasks.cancel_all()
        self.login.password.edit.clear()
        self.login.remember.setChecked(False)
        self.login.feedback.clear()
        self.login.show()
        if self.browser:
            self.browser.close()
            self.browser.deleteLater()
            self.browser = None
        if warning:
            self.login.show_error(warning)

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        if self.browser:
            self.browser.shutdown()
        self.tasks.cancel_all()
        self.library.close()


def _qt_message(_kind, _context, message):
    # FFmpeg errors may contain authenticated media URLs; never echo those URLs.
    if sys.stderr is not None:
        safe = re.sub(r"https?://[^\s\]\)]+", "[endereço omitido]", message)
        try:
            sys.stderr.write(safe + "\n")
        except (OSError, UnicodeError):
            pass


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SmartIPTV")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SmartIPTV")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(icon("tv", "#5ce5ac", 64))
    qInstallMessageHandler(_qt_message)
    smoke = "--smoke-test" in sys.argv
    temporary = tempfile.TemporaryDirectory(prefix="smartiptv-smoke-") if smoke else None
    try:
        controller = Controller(app, temporary.name if temporary else None, auto_login=not smoke)
    except (OSError, ValueError):
        QMessageBox.critical(None, "SmartIPTV", "Não foi possível abrir os dados locais do aplicativo.")
        return 1
    if smoke:
        from PySide6.QtMultimedia import QMediaFormat
        if not QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode):
            controller.shutdown()
            return 1
        QTimer.singleShot(500, app.quit)
    result = app.exec()
    if temporary:
        temporary.cleanup()
    return result
