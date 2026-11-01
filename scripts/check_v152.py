"""Confirm decoded resume frames, entry points and time-only timeline hover."""
import os
from pathlib import Path
import sys
import tempfile

NATIVE = os.environ.get("SMARTIPTV_NATIVE_CHECK") == "1"
os.environ["QT_QPA_PLATFORM"] = "windows" if NATIVE else "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QEvent, QEventLoop, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from smartiptv.app import Controller
from smartiptv.player import timestamp
from smartiptv.storage import Library
from tests.media import headless_video
from tests.provider import Provider

app = QApplication([]); app.setStyle("Fusion")


def wait_for(condition, message, timeout=16000):
    if condition(): return
    loop, timer, deadline = QEventLoop(), QTimer(), QTimer()
    timer.setInterval(25); timer.timeout.connect(lambda: loop.quit() if condition() else None)
    deadline.setSingleShot(True); deadline.timeout.connect(loop.quit)
    timer.start(); deadline.start(timeout); loop.exec(); timer.stop(); deadline.stop()
    assert condition(), message


def hover(slider, point):
    # Deliver to the owned widget explicitly: QTest.mouseMove on a native
    # window can hit another desktop app when this test runs in background.
    app.processEvents()
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(point), QPointF(slider.mapToGlobal(point)),
                        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(slider, event)


with tempfile.TemporaryDirectory(prefix="smartiptv-v152-") as directory:
    provider = Provider(ROOT / "tests/assets/resume.mp4").start()
    controller = Controller(app, directory, auto_login=False)
    try:
        login = controller.login
        login.server.edit.setText(provider.url); login.username.edit.setText("demo"); login.password.edit.setText("demopass")
        login.validate_form()
        wait_for(lambda: controller.browser is not None, "Login failed")
        window, library = controller.browser, controller.library
        wait_for(lambda: bool(window.catalog.get("series", {}).get("items")), "Catalog failed")
        series = window.catalog["series"]["items"][0]
        episodes = window.client.series_details(series)["episodes"]
        episode = episodes[1]

        for method in ("continue", "double_click", "watch"):
            library.record_progress(episode, 10000, 90000)
            window.open_content(series)
            detail = window.detail_dialog
            wait_for(lambda: detail.watch.isEnabled(), "Episode list failed")
            assert detail.episode_list.currentItem().data(Qt.ItemDataRole.UserRole).uid == episode.uid
            if method == "continue":
                QTest.mouseClick(detail.resume, Qt.MouseButton.LeftButton)
            elif method == "watch":
                QTest.mouseClick(detail.watch, Qt.MouseButton.LeftButton)
            else:
                rect = detail.episode_list.visualItemRect(detail.episode_list.currentItem())
                QTest.mouseClick(detail.episode_list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
                QTest.mouseDClick(detail.episode_list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
            player = window.player_window
            assert player and player.pending_resume == 10000
            assert window.artwork.suspended, "Posters still downloading during playback"
            if not NATIVE: headless_video(player)
            player.audio.setMuted(True)
            # Simulate a backend rejecting the first request despite metadata
            # being available. The target must survive and be tried again.
            original = player.player.setPosition
            requests = []
            def delayed_seek(value):
                requests.append(value)
                if len(requests) > 1: original(value)
            player.player.setPosition = delayed_seek
            player._apply_resume()
            assert not requests, "Seek attempted before media was ready"
            player.flush_progress()
            assert library.checkpoint(episode)["position"] == 10000
            wait_for(lambda: not player.pending_resume and player.player.position() >= 9000, f"{method}: decoded frame did not confirm resume")
            assert len(requests) >= 2, "Ignored seek was never retried"
            player.player.pause(); player.flush_progress()
            assert library.checkpoint(episode)["position"] >= 9000
            restored = Library(directory)
            restored.select_account(window.client.credentials)
            assert restored.checkpoint(episode)["position"] >= 9000
            restored.close()

            # Hover uses the exact same style-aware mapping as a click; it
            # shows only a timestamp and cannot move playback or save progress.
            saved = library.checkpoint(episode)["position"]
            saved_at = library.checkpoint(episode)["updated"]
            player.flush_progress(); player.flush_progress()
            assert library.checkpoint(episode)["updated"] == saved_at, "Paused playback rewrote an unchanged checkpoint"
            before = player.player.position()
            for fraction in (0.0, .25, .75, 1.0):
                point = QPoint(round((player.seek.width() - 1) * fraction), player.seek.height() // 2)
                hover(player.seek, point)
                expected = timestamp(int(player.seek._value_at(point) * player.player.duration() / 10000))
                assert player.seek.hover_label.text() == expected
                assert player.seek.hover_label.isVisible()
                assert player.seek.hover_label.geometry().bottom() < player.seek.mapToGlobal(QPoint()).y()
                assert player.player.position() == before
                assert library.checkpoint(episode)["position"] == saved
            for y in (0, player.seek.height() - 1):
                hover(player.seek, QPoint(player.seek.width() // 2, y))
                assert player.seek.hover_label.geometry().bottom() < player.seek.mapToGlobal(QPoint()).y(), "Hover timestamp moved below the bar"
            QTest.mouseMove(player.pause, player.pause.rect().center())
            player.toggle_fullscreen()
            app.processEvents()
            hover(player.seek, player.seek.rect().center())
            assert player.seek.hover_label.text() == timestamp(int(player.seek._value_at(player.seek.rect().center()) * player.player.duration() / 10000))
            assert player.seek.hover_label.geometry().bottom() < player.seek.mapToGlobal(QPoint()).y()
            player.leave_fullscreen()
            window.leave_player()
            assert not window.artwork.suspended, "Poster loading did not resume on returning to catalog"

        # Closing before any decoded frame must preserve the previous session.
        library.record_progress(episode, 10000, 90000)
        window.play(episode, episodes=episodes)
        window.leave_player()
        assert library.checkpoint(episode)["position"] == 10000
        # Switching episodes must not carry the previous resume target forward.
        window.play(episode, episodes=episodes)
        player = window.player_window
        player.load_item(episodes[2], restart=True)
        assert not player.pending_resume and not player.resume_ready
        window.leave_player()
        print("Windows 1.5.2 checks passed: confirmed resume via Continue/double-click/Watch, retry after ignored seek, durable progress, early-exit protection, episode isolation and time-only hover without seeking in window/fullscreen.")
    finally:
        if controller.browser: controller.browser.close()
        controller.login.close(); controller.shutdown(); provider.close()
