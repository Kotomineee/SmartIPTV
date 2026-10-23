"""Exercise v1.1 behavior with real Qt media decoding and a local provider."""
import os
from pathlib import Path
import sys
import tempfile
import faulthandler

faulthandler.dump_traceback_later(30, repeat=True)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QWheelEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from smartiptv.app import Controller
from smartiptv import __version__
from tests.provider import Provider
from tests.media import headless_video


app = QApplication([])
app.setStyle("Fusion")
for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
    font = Path("C:/Windows/Fonts") / name
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
app.setFont(QFont("Segoe UI", 10))


def wait_until(condition, description, timeout=12000):
    if condition():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(25)
    poll.timeout.connect(lambda: loop.quit() if condition() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(timeout)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert condition(), description


def screenshot(window, name):
    directory = os.environ.get("SMARTIPTV_SCREENSHOT_DIR")
    if directory:
        app.processEvents()
        assert window.grab().save(str(Path(directory) / f"SmartIPTV-{__version__}-{name}.png"))


def wheel(widget):
    position = widget.rect().center()
    event = QWheelEvent(QPointF(position), QPointF(widget.mapToGlobal(position)), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)
    app.processEvents()


with tempfile.TemporaryDirectory(prefix="smartiptv-v110-") as directory:
    provider = Provider(ROOT / "tests/assets/resume.mp4").start()
    controller = Controller(app, directory, auto_login=False)
    try:
        login = controller.login
        assert not login.server.edit.placeholderText()
        texts = [widget.text() for widget in login.findChildren(QLabel)]
        assert not any("incluindo a porta" in text or "Feito para a sua playlist" in text or "/  DESKTOP" in text for text in texts)
        login.remember.setChecked(True)
        login.remember.setFocus()
        screenshot(login, "login")
        login.server.edit.setText(provider.url)
        login.username.edit.setText("demo")
        login.password.edit.setText("demopass")
        login.validate_form()
        wait_until(lambda: controller.browser is not None, "Login failed")
        window = controller.browser
        real_play = window.play
        def play_for_headless(*args, **kwargs):
            real_play(*args, **kwargs)
            headless_video(window.player_window)
        window.play = play_for_headless
        wait_until(lambda: len(window.catalog["movie"]["items"]) == 80, "Catalog failed")
        wait_until(lambda: window.account_task is None, "Account refresh failed")
        assert "0 de 2" in window.account_connections.text()
        assert "informado" not in window.account_expiration.text() and "—" not in window.account_expiration.text()
        provider.active_connections = "1"
        window.refresh_account()
        wait_until(lambda: "1 de 2" in window.account_connections.text(), "Active connections stale")

        # Opening details blurs only the background; actions stay usable.
        window.navigate("movie")
        window.open_content(window.grid.content_model.items[0])
        movie_detail = window.detail_dialog
        wait_until(lambda: "Carregando" not in movie_detail.plot.text(), "Movie details failed")
        assert movie_detail.backdrop.isVisible()
        screenshot(window, "filme-detalhes")
        QTest.mouseClick(movie_detail.favorite, Qt.MouseButton.LeftButton)
        assert controller.library.is_favorite(movie_detail.item) and window.detail_dialog is movie_detail
        QTest.mouseClick(movie_detail.favorite, Qt.MouseButton.LeftButton)
        window.resize(1040, 700)
        app.processEvents()
        assert movie_detail.backdrop.geometry() == window.library_root.rect()
        screenshot(window, "filme-detalhes-compacto")
        QTest.mouseClick(movie_detail.watch, Qt.MouseButton.LeftButton)
        assert window.detail_dialog is None and window.player_window is not None
        assert not any(w.isVisible() for w in window.library_root.findChildren(QWidget, "detailsBackdrop"))
        window.leave_player()
        window.resize(1380, 900)
        app.processEvents()

        # The Home wheel always scrolls the page, including over a row's scrollbar.
        window.navigate("home")
        app.processEvents()
        row = window.home_galleries["movie"]
        vertical = window.home_scroll.verticalScrollBar()
        horizontal = row.horizontalScrollBar()
        vertical.setValue(0)
        horizontal.setValue(0)
        wheel(row.viewport())
        assert vertical.value() > 0 and horizontal.value() == 0
        before = vertical.value()
        wheel(horizontal)
        assert vertical.value() > before and horizontal.value() == 0
        horizontal.setValue(100)
        assert horizontal.value() == 100
        screenshot(window, "inicio")

        # The very click that dismisses details also opens the requested sidebar tab.
        window.navigate("series")
        series = window.grid.content_model.items[0]
        window.open_content(series)
        detail = window.detail_dialog
        wait_until(lambda: detail.watch.isEnabled(), "Episode list failed")
        assert not detail.isWindow()
        episodes = list(detail.episodes)
        QTest.mouseClick(detail.seasons, Qt.MouseButton.LeftButton)
        QTest.keyClick(detail.seasons, Qt.Key.Key_Down)
        QTest.keyClick(detail.seasons, Qt.Key.Key_Return)
        assert window.detail_dialog is detail
        screenshot(window, "detalhes")
        QTest.mouseClick(window.nav["settings"], Qt.MouseButton.LeftButton)
        assert window.detail_dialog is None and window.current_tab == "settings"
        assert window.refresh.parentWidget() is not window.library_root
        assert window.pages.currentWidget() is window.settings_page
        assert not window.settings_page.auto_next.isChecked()
        QTest.mouseClick(window.settings_page.auto_next, Qt.MouseButton.LeftButton)
        assert controller.library.auto_next_enabled
        screenshot(window, "configuracoes")
        QTest.mouseClick(window.settings_page.auto_next, Qt.MouseButton.LeftButton)

        # Playback is a child page; returning keeps category, search, sort and scroll.
        window.navigate("movie")
        window.categories.setCurrentRow(1)
        window.sort.setCurrentIndex(1)
        window.search.setText("a")
        QTest.qWait(270)
        window.grid.verticalScrollBar().setValue(12)
        app.processEvents()
        context = (window.categories.currentRow(), window.search.text(), window.sort.currentIndex(), window.grid.verticalScrollBar().value())
        movie = window.grid.content_model.items[0]
        window.play(movie, True)
        player = window.player_window
        player.audio.setMuted(True)
        wait_until(lambda: player.player.position() > 1000, "Embedded playback failed")
        assert window.window_pages.currentWidget() is player and not player.isWindow()
        assert len([w for w in app.topLevelWidgets() if w.isVisible() and w.objectName() != "QTipLabel"]) == 1
        wait_until(lambda: len(player.player.audioTracks()) == 2 and len(player.player.subtitleTracks()) == 1, "Media tracks missing")
        player._track_menu(False)
        player.audio_menu.actions()[1].trigger()
        wait_until(lambda: player.player.activeAudioTrack() == 1, "Audio selection failed")
        player._track_menu(True)
        player.subtitle_menu.actions()[1].trigger()
        wait_until(lambda: player.player.activeSubtitleTrack() == 0, "Subtitle selection failed")
        player.player.setPosition(3000)
        wait_until(lambda: "SmartIPTV" in player.test_sink.subtitleText(), "Subtitle not rendered")
        assert player.test_sink.videoFrame().isValid(), "No video frame decoded"
        screenshot(window, "player")
        player._track_menu(True)
        player.subtitle_menu.actions()[0].trigger()
        wait_until(lambda: player.player.activeSubtitleTrack() == -1, "Subtitle disable failed")
        player.toggle_mute()
        assert not player.audio.isMuted()
        player.volume.setValue(25)
        assert abs(player.audio.volume() - .25) < .01
        player.toggle_pause()
        before = player.player.position()
        player.skip(10000)
        assert player.player.position() >= before + 9500
        player.skip(-10000)
        assert player.player.position() <= before + 500
        player.toggle_fullscreen()
        assert window.isFullScreen()
        player.escape()
        assert not window.isFullScreen() and window.player_window is player
        player.escape()
        app.processEvents()
        assert window.player_window is None and window.window_pages.currentWidget() is window.library_root
        assert (window.categories.currentRow(), window.search.text(), window.sort.currentIndex(), window.grid.verticalScrollBar().value()) == context
        assert controller.library.checkpoint(movie)["position"] >= 1000

        def end_current():
            current = window.player_window
            wait_until(lambda: current.player.duration() > 15000 and current.player.isSeekable() and current.player.position() >= 200, "Episode failed to load")
            current.audio.setMuted(True)
            current.player.setPosition(current.player.duration() - 450)
            current.player.play()
            return current

        # Off: completion stays in the same episode. On: cross-season and normal next.
        window.play(episodes[2], True, episodes)
        current = end_current()
        wait_until(lambda: current.finished, "Episode did not finish")
        QTest.qWait(200)
        assert window.player_window is current
        controller.library.set_auto_next(True)
        window.play(episodes[2], True, episodes)
        end_current()
        wait_until(lambda: window.player_window.item.uid == episodes[3].uid, "Next season did not start")
        assert controller.library.progress[episodes[2].uid]["finished"]
        end_current()
        wait_until(lambda: window.player_window.item.uid == episodes[4].uid, "Next episode did not start")
        window.leave_player()

        # Continue Watching obtains the queue again; the last episode never loops.
        window.play(episodes[-1], True)
        wait_until(lambda: window.episode_task is None, "Continue queue not loaded")
        current = end_current()
        wait_until(lambda: current.finished, "Last episode did not finish")
        QTest.qWait(200)
        assert window.player_window is current and "último episódio" in current.status.text()
        window.leave_player()

        provider.failed_media.add("101.mp4")
        window.play(episodes[0], True, episodes)
        failed = window.player_window
        wait_until(lambda: failed.retry.isVisible(), "Playback failure not reported")
        assert window.player_window is failed and failed.item.uid == episodes[0].uid and not failed.finished
        window.leave_player()
        provider.failed_media.clear()

        # A queued next request is invalidated by Back; logout closes active media.
        window.play(episodes[0], True, episodes)
        current = window.player_window
        current.finished = True
        window._episode_ended(current.item, window.play_generation)
        window.leave_player()
        QTest.qWait(100)
        assert window.player_window is None
        window.play(movie, True)
        current = window.player_window
        wait_until(lambda: current.player.position() >= 1200, "Logout fixture did not play")
        window.leave_player()
        window.navigate("settings")
        QTest.mouseClick(window.settings_page.logout, Qt.MouseButton.LeftButton)
        assert controller.browser is None and login.isVisible()
        assert not controller.sessions.path.exists()
        assert controller.library.auto_next_enabled
        print("v1.1 checks passed: Home wheel, outside dismissal, account refresh, settings, embedded playback, catalog position, audio, subtitles, fullscreen, cross-season autoplay, last episode and cancellation.")
    finally:
        if controller.browser:
            controller.browser.close()
        controller.login.close()
        controller.shutdown()
        controller.tasks.pool.waitForDone(30000)
        provider.close()
