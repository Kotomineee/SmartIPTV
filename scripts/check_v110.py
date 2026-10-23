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
from PySide6.QtWidgets import QApplication, QLabel, QStyle, QStyleOptionComboBox, QWidget
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


def click_visible(widget, position=None):
    position = position if position is not None else widget.rect().center()
    global_position = widget.mapToGlobal(position)
    root = widget.window()
    receiver = root.childAt(root.mapFromGlobal(global_position))
    assert receiver is not None, "No visible click target"
    QTest.mouseClick(receiver, Qt.MouseButton.LeftButton, pos=receiver.mapFromGlobal(global_position))
    app.processEvents()


def dismiss_at(window, widget, position=None):
    app.processEvents()
    detail = window.detail_dialog
    position = position if position is not None else widget.rect().center()
    global_position = widget.mapToGlobal(position)
    root = window.library_root
    receiver = root.childAt(root.mapFromGlobal(global_position))
    assert receiver is detail.backdrop, f"Outside target was {receiver}: point {global_position}, panel {detail.geometry()}"
    local_position = receiver.mapFromGlobal(global_position)
    QTest.mousePress(receiver, Qt.MouseButton.LeftButton, pos=local_position)
    assert window.detail_dialog is detail, "The layer disappeared before the click ended"
    QTest.mouseRelease(receiver, Qt.MouseButton.LeftButton, pos=local_position)
    app.processEvents()
    assert window.detail_dialog is None, "Outside click did not close details"
    assert not any(w.isVisible() for w in window.library_root.findChildren(QWidget, "detailsBackdrop"))


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

        # One outside click dismisses only. A separate new click can act.
        window.navigate("movie")
        movie = window.grid.content_model.items[0]
        other_index = window.grid.model().index(1)
        other_movie = other_index.data(Qt.ItemDataRole.UserRole)
        other_rect = window.grid.visualRect(other_index)
        card_position = other_rect.topLeft() + QPoint(45, 35)
        selected_before = window.grid.currentIndex()
        window.open_content(movie)
        dismiss_at(window, window.grid.viewport(), card_position)
        assert window.grid.currentIndex() == selected_before and window.current_tab == "movie"
        click_visible(window.grid.viewport(), card_position)
        assert window.detail_dialog.item.uid == other_movie.uid
        QTest.keyClick(window.detail_dialog, Qt.Key.Key_Escape)
        assert window.detail_dialog is None

        # Favorite hearts react on release, so both halves of the click must be blocked.
        card = window.grid.visualRect(window.grid.model().index(0)).adjusted(2, 2, -8, -8)
        heart_position = card.topRight() + QPoint(-22, 22)
        favorite_before = controller.library.is_favorite(movie)
        window.open_content(movie)
        dismiss_at(window, window.grid.viewport(), heart_position)
        assert controller.library.is_favorite(movie) == favorite_before

        category_before = window.categories.currentRow()
        category_position = window.categories.visualItemRect(window.categories.item(1)).center()
        window.open_content(movie)
        dismiss_at(window, window.categories.viewport(), category_position)
        assert window.categories.currentRow() == category_before
        click_visible(window.categories.viewport(), category_position)
        assert window.categories.currentRow() == 1

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

        # A sidebar click first closes details; only the next click changes tabs.
        window.navigate("series")
        series = window.grid.content_model.items[0]
        window.open_content(series)
        detail = window.detail_dialog
        wait_until(lambda: detail.watch.isEnabled(), "Episode list failed")
        assert not detail.isWindow()
        episodes = list(detail.episodes)
        assert list(detail.seasons.buttons) == [1, 2]
        assert "2 temporadas" in detail.caption.text()
        assert not detail.feedback.isVisible() and "episódios disponíveis" not in detail.feedback.text()
        assert all(button.isVisible() for button in detail.seasons.buttons.values())
        QTest.mouseClick(detail.seasons.buttons[2], Qt.MouseButton.LeftButton)
        assert detail.seasons.current_season() == 2
        assert detail.episode_list.count() == 3
        assert all(detail.episode_list.item(i).data(Qt.ItemDataRole.UserRole).season == 2 for i in range(3))
        assert window.detail_dialog is detail
        screenshot(window, "detalhes")
        dismiss_at(window, window.nav["settings"])
        assert window.current_tab == "series" and not window.nav["settings"].isChecked()
        click_visible(window.nav["settings"])
        assert window.detail_dialog is None and window.current_tab == "settings"
        assert window.refresh.parentWidget() is not window.library_root
        assert window.pages.currentWidget() is window.settings_page
        assert not window.settings_page.auto_next.isChecked()
        QTest.mouseClick(window.settings_page.auto_next, Qt.MouseButton.LeftButton)

        # A remembered episode selects its season; many seasons wrap visibly.
        controller.library.record_progress(episodes[4], 5000, 20000)
        window.open_content(series)
        detail = window.detail_dialog
        wait_until(lambda: detail.watch.isEnabled(), "Remembered series failed")
        assert detail.seasons.current_season() == 2
        assert detail.episode_list.currentItem().data(Qt.ItemDataRole.UserRole).uid == episodes[4].uid
        assert "Continuar em" in detail.episode_list.currentItem().data(Qt.ItemDataRole.UserRole + 1)
        detail.seasons.set_seasons(range(1, 25), 2)
        app.processEvents()
        assert all(detail.seasons.rect().contains(button.geometry()) for button in detail.seasons.buttons.values())
        detail._series_loaded({"episodes": episodes[:3], "info": {}})
        assert "1 temporada" in detail.caption.text() and "1 temporadas" not in detail.caption.text()
        assert list(detail.seasons.buttons) == [1] and detail.seasons.current_season() == 1
        detail._series_loaded({"episodes": [], "info": {}})
        assert not detail.watch.isEnabled() and detail.episode_list.count() == 0
        assert detail.feedback.isVisible() and not detail.seasons.buttons
        detail.reject()
        window.navigate("continue")
        window.resize(1040, 700)
        app.processEvents()
        option = QStyleOptionComboBox()
        window.sort.initStyleOption(option)
        text_rect = window.sort.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, window.sort)
        assert text_rect.width() >= window.sort.fontMetrics().horizontalAdvance("Assistidos recentemente"), "Sort text clipped"
        screenshot(window, "continuar")
        window.resize(1380, 900)
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
        # Clicks choose the actual point, rather than moving one page step.
        for fraction in (.76, .23):
            QTest.mouseClick(player.seek, Qt.MouseButton.LeftButton, pos=QPoint(round(player.seek.width() * fraction), player.seek.height() // 2))
            assert abs(player.player.position() / player.player.duration() - fraction) < .035, "Timeline click inaccurate"
        QTest.mousePress(player.seek, Qt.MouseButton.LeftButton, pos=QPoint(player.seek.width() // 3, player.seek.height() // 2))
        QTest.mouseMove(player.seek, QPoint(player.seek.width() // 2, player.seek.height() // 2))
        QTest.mouseRelease(player.seek, Qt.MouseButton.LeftButton, pos=QPoint(player.seek.width() // 2, player.seek.height() // 2))
        assert abs(player.player.position() / player.player.duration() - .5) < .035, "Timeline drag broken"
        QTest.mouseClick(player.volume, Qt.MouseButton.LeftButton, pos=QPoint(68, player.volume.height() // 2))
        assert abs(player.audio.volume() - .79) < .04, "Forward volume click inaccurate"
        QTest.mouseClick(player.volume, Qt.MouseButton.LeftButton, pos=QPoint(22, player.volume.height() // 2))
        assert abs(player.audio.volume() - .21) < .04, "Volume click inaccurate"
        QTest.mouseClick(player.volume, Qt.MouseButton.LeftButton, pos=QPoint(0, player.volume.height() // 2))
        assert player.audio.volume() == 0
        QTest.keyClick(player.volume, Qt.Key.Key_End)
        assert player.audio.volume() == 1
        player.volume.setValue(25)
        before = player.player.position()
        player.skip(10000)
        assert player.player.position() >= before + 9500
        player.skip(-10000)
        assert player.player.position() <= before + 500
        player.toggle_fullscreen()
        assert window.isFullScreen()
        player.hide_controls_timer.setInterval(180)
        player.hide_controls_timer.start()
        wait_until(lambda: player.header.isHidden() and player.footer.isHidden(), "Fullscreen controls did not hide")
        assert player.video.geometry() == player.rect(), "Fullscreen video is inset"
        assert player.video.cursor().shape() == Qt.CursorShape.BlankCursor
        QTest.mouseMove(player.video, QPoint(35, 35))
        wait_until(lambda: player.header.isVisible() and player.footer.isVisible(), "Mouse did not reveal controls")
        assert player.video.geometry() == player.rect(), "Controls resized video"
        player.audio_menu.popup(player.audio_button.mapToGlobal(QPoint(0, 0)))
        QTest.qWait(250)
        assert player.footer.isVisible(), "Controls hid under the audio menu"
        player.audio_menu.close()
        wait_until(lambda: player.footer.isHidden(), "Controls stayed after closing audio menu")
        QTest.mouseMove(player.video, QPoint(55, 55))
        wait_until(lambda: player.footer.isVisible(), "Controls did not return")
        QTest.mousePress(player.volume, Qt.MouseButton.LeftButton, pos=player.volume.rect().center())
        QTest.qWait(250)
        assert player.footer.isVisible(), "Controls hid during volume drag"
        QTest.mouseRelease(player.volume, Qt.MouseButton.LeftButton, pos=player.volume.rect().center())
        player.escape()
        assert not window.isFullScreen() and window.player_window is player
        assert player.header.isVisible() and player.footer.isVisible()
        assert not player.hide_controls_timer.isActive()
        assert player.video.cursor().shape() != Qt.CursorShape.BlankCursor
        app.processEvents()
        assert player.video.height() < player.height()
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
        window.player_window.toggle_fullscreen()
        end_current()
        wait_until(lambda: window.player_window.item.uid == episodes[3].uid, "Next season did not start")
        assert window.isFullScreen() and window.player_window.fullscreen_state is not None
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
        print("UI checks passed: visible season tabs, episode resume, season count, complete sort text, click/drag seeking and volume, fullscreen overlays and idle cursor, menu/drag visibility, outside-click isolation, audio, subtitles and cross-season autoplay.")
    finally:
        if controller.browser:
            controller.browser.close()
        controller.login.close()
        controller.shutdown()
        controller.tasks.pool.waitForDone(30000)
        provider.close()
