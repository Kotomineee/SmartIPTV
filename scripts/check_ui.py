"""Exercise the login's UI flow without network access or real credentials."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit
from smartiptv.login import LoginWindow

app = QApplication([])
window = LoginWindow()
window.show()
app.processEvents()
assert all(not f.edit.text() for f in (window.server, window.username, window.password))
QTest.mouseClick(window.submit, Qt.MouseButton.LeftButton)
assert window.server.edit.hasFocus() and window.feedback.text()
window.server.edit.setText("https://example.com:8080")
QTest.keyClick(window.server.edit, Qt.Key.Key_Tab)
assert window.username.edit.hasFocus()
window.username.edit.setText("demonstracao")
QTest.keyClick(window.username.edit, Qt.Key.Key_Tab)
assert window.password.edit.hasFocus()
window.password.edit.setText(" senha ficticia ")
QTest.mouseClick(window.password.reveal, Qt.MouseButton.LeftButton)
assert window.password.edit.echoMode() == QLineEdit.EchoMode.Normal
assert window.password.edit.text() == " senha ficticia "
QTest.mouseClick(window.password.reveal, Qt.MouseButton.LeftButton)
assert window.password.edit.echoMode() == QLineEdit.EchoMode.Password
QTest.keyClick(window.password.edit, Qt.Key.Key_Return)
assert window.feedback.property("success") is True
assert "autenticação" in window.feedback.text()
window.resize(560, 760)
app.processEvents()
assert not window.hero.isVisible()
window.close()
print("Login UI checks passed.")
