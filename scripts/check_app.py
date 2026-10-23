"""Complete UI regression checks against a local, fictional provider."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit
from smartiptv.app import Controller
from smartiptv.models import Content
from smartiptv.player import PlayerWindow
from tests.provider import Provider


def wait_until(condition, description, timeout=12000):
    for _ in range(timeout // 30):
        app.processEvents()
        if condition():
            return
        QTest.qWait(30)
    raise AssertionError(description)


def screenshot(window, name):
    directory = os.environ.get("SMARTIPTV_SCREENSHOT_DIR")
    if directory:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        app.processEvents()
        assert window.grab().save(str(path / name))


app = QApplication([])
app.setApplicationName("SmartIPTV")
app.setStyle("Fusion")
for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
    font = Path("C:/Windows/Fonts") / name
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))

provider = Provider().start()
directory = tempfile.TemporaryDirectory(prefix="smartiptv-ui-")
controller = None
try:
    controller = Controller(app, directory.name, auto_login=False)
    login = controller.login
    app.processEvents()
    assert all(not f.edit.text() for f in (login.server, login.username, login.password))
    assert not login.remember.isChecked()
    assert login.password.edit.echoMode() == QLineEdit.EchoMode.Password
    screenshot(login, "SmartIPTV-1.0.0-login.png")
    QTest.mouseClick(login.submit, Qt.MouseButton.LeftButton)
    assert login.server.edit.hasFocus() and "endereço" in login.feedback.text()
    login.server.edit.setText(provider.url)
    QTest.keyClick(login.server.edit, Qt.Key.Key_Tab)
    assert login.username.edit.hasFocus()
    login.username.edit.setText("demo")
    QTest.keyClick(login.username.edit, Qt.Key.Key_Tab)
    assert login.password.edit.hasFocus()
    login.password.edit.setText("wrong-password")
    QTest.mouseClick(login.password.reveal, Qt.MouseButton.LeftButton)
    assert login.password.edit.echoMode() == QLineEdit.EchoMode.Normal
    QTest.mouseClick(login.password.reveal, Qt.MouseButton.LeftButton)
    login.remember.setChecked(True)
    QTest.mouseClick(login.submit, Qt.MouseButton.LeftButton)
    wait_until(lambda: login.submit.isEnabled(), "Rejected login did not unlock form")
    assert controller.browser is None and "não aceitos" in login.feedback.text()
    assert not controller.sessions.path.exists()
    login.password.edit.setText("demopass")
    QTest.keyClick(login.password.edit, Qt.Key.Key_Return)
    wait_until(lambda: controller.browser is not None, "Login did not open catalog")
    window = controller.browser
    wait_until(lambda: len(window.catalog["movie"]["items"]) == 80, "Catalog did not load")
    assert not login.isVisible()
    assert controller.sessions.load().password == "demopass"
    screenshot(window, "SmartIPTV-1.0.0-inicio.png")
    for tab in ("live", "movie", "series"):
        QTest.mouseClick(window.nav[tab], Qt.MouseButton.LeftButton)
        assert window.current_tab == tab and window.categories.count() == 3
        assert window.grid.content_model.rowCount() > 0
    window.navigate("movie")
    window.categories.setCurrentRow(1)
    assert all("1" in item.categories for item in window.grid.content_model.items)
    window.search.setText("alem")
    wait_until(lambda: all("Além" in i.name for i in window.grid.content_model.items), "Accent-insensitive search failed")
    assert window.grid.content_model.items
    window.search.clear()
    QTest.qWait(250)
    screenshot(window, "SmartIPTV-1.0.0-filmes.png")
    index = window.grid.model().index(0)
    item = index.data(Qt.ItemDataRole.UserRole)
    card = window.grid.visualRect(index).adjusted(2, 2, -8, -8)
    QTest.mouseClick(window.grid.viewport(), Qt.MouseButton.LeftButton, pos=card.topRight() + QPoint(-22, 22))
    assert controller.library.is_favorite(item) and window.detail_dialog is None
    window.navigate("favorites")
    assert len(window.grid.content_model.items) == 1
    window.navigate("series")
    series = window.grid.content_model.items[0]
    window.open_content(series)
    detail = window.detail_dialog
    wait_until(lambda: detail.watch.isEnabled(), "Series episodes did not load")
    assert detail.seasons.count() == 2
    detail.seasons.setCurrentIndex(1)
    assert detail.episode_list.count() == 3
    episode = detail.episode_list.item(1).data(Qt.ItemDataRole.UserRole)
    assert episode.season == 2 and episode.episode == 2
    screenshot(detail, "SmartIPTV-1.0.0-serie.png")
    detail.reject()
    app.processEvents()
    controller.library.record_progress(episode, 300000, 1200000)
    window.navigate("continue")
    assert window.grid.content_model.items[0].uid == episode.uid
    screenshot(window, "SmartIPTV-1.0.0-continuar.png")
    controller.library.record_progress(episode, 1200000, 1200000, True)
    window.library_updated()
    assert not window.grid.content_model.items

    fixture = ROOT / "tests" / "assets" / "resume.mp4"
    assert fixture.exists(), "Synthetic media fixture is missing"
    movie = Content("movie", "fixture", "Verificação local do reprodutor")
    player = PlayerWindow(window.client, controller.library, movie, parent=window, source_override=QUrl.fromLocalFile(str(fixture)).toString())
    player.audio.setMuted(True)
    player.show()
    wait_until(lambda: player.player.position() >= 1300, "Local video failed to start", 15000)
    assert player.player.duration() > 15000
    player.player.pause()
    player.flush_progress()
    assert controller.library.checkpoint(movie)["position"] >= 1000
    player.close()
    player.deleteLater()
    controller.library.record_progress(movie, 7000, 20000)
    resumed = PlayerWindow(window.client, controller.library, movie, parent=window, source_override=QUrl.fromLocalFile(str(fixture)).toString())
    resumed.audio.setMuted(True)
    resumed.show()
    wait_until(lambda: resumed.player.position() >= 7000 and not resumed.pending_resume, "Video did not resume", 15000)
    resumed.player.setPosition(resumed.player.duration() - 500)
    wait_until(lambda: resumed.finished, "Video completion not detected", 5000)
    assert controller.library.checkpoint(movie) is None
    resumed.close()
    resumed.deleteLater()

    window.close()
    login.close()
    controller.shutdown()
    controller = Controller(app, directory.name, auto_login=True)
    wait_until(lambda: controller.browser is not None, "Saved session did not auto-authenticate")
    wait_until(lambda: len(controller.browser.catalog["movie"]["items"]) == 80, "Restored catalog did not load")
    assert controller.library.is_favorite(item)
    controller.logout()
    assert controller.browser is None and controller.login.isVisible()
    assert not controller.sessions.path.exists() and not controller.login.password.edit.text()
    print("UI checks passed: login, categories, search, favorites, series, media resume, completion, session restore and logout.")
finally:
    if controller:
        if controller.browser:
            controller.browser.close()
        controller.login.close()
        controller.shutdown()
        controller.tasks.pool.waitForDone(30000)
    provider.close()
    directory.cleanup()
