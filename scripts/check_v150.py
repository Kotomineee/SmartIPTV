"""Windows player gestures, manual next and grouped resume using fictional media."""
import os
from pathlib import Path
import sys
import tempfile

NATIVE_CHECK = os.environ.get("SMARTIPTV_NATIVE_CHECK") == "1"
os.environ["QT_QPA_PLATFORM"] = "windows" if NATIVE_CHECK else "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from smartiptv import __version__
from smartiptv.app import Controller
from smartiptv.storage import Library
from tests.media import headless_video
from tests.provider import Provider

app = QApplication([])
app.setStyle("Fusion")


def wait_for(condition, message, timeout=12000):
    if condition():
        return
    loop, poll, deadline = QEventLoop(), QTimer(), QTimer()
    poll.setInterval(25)
    poll.timeout.connect(lambda: loop.quit() if condition() else None)
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start(); deadline.start(timeout); loop.exec(); poll.stop(); deadline.stop()
    assert condition(), message


def capture(window, name):
    if directory := os.environ.get("SMARTIPTV_SCREENSHOT_DIR"):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(path / f"SmartIPTV-{__version__}-{name}.png"))


with tempfile.TemporaryDirectory(prefix="smartiptv-v150-") as directory:
    provider = Provider(ROOT / "tests/assets/resume.mp4").start()
    controller = Controller(app, directory, auto_login=False)
    try:
        form = controller.login
        form.server.edit.setText(provider.url); form.username.edit.setText("demo"); form.password.edit.setText("demopass")
        form.validate_form()
        wait_for(lambda: controller.browser is not None, "Test login failed")
        window = controller.browser
        wait_for(lambda: len(window.catalog.get("series", {}).get("items", [])) > 0, "Catalog did not load")
        series = window.catalog["series"]["items"][0]
        episodes = window.client.series_details(series)["episodes"]
        controller.library.set_auto_next(False)

        def start(item, queue=None):
            window.play(item, True, queue)
            player = window.player_window
            player.test_sink = player.video.videoSink() if NATIVE_CHECK else headless_video(player)
            player.audio.setMuted(True)
            wait_for(lambda: player.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState and player.player.position() > 1000, "Test video did not play")
            return player

        player = start(episodes[0], episodes)
        assert player.next_episode.isVisible() and player.next_episode.isEnabled()
        playing, paused = QMediaPlayer.PlaybackState.PlayingState, QMediaPlayer.PlaybackState.PausedState

        # One click toggles playback; the second click of a double-click must
        # not create a delayed pause after changing the window mode.
        QTest.mouseClick(player.video, Qt.MouseButton.LeftButton, pos=player.video.rect().center())
        wait_for(lambda: player.player.playbackState() == paused, "Video click did not pause")
        QTest.mouseClick(player.video, Qt.MouseButton.LeftButton, pos=player.video.rect().center())
        wait_for(lambda: player.player.playbackState() == playing, "Video click did not resume")
        QTest.mouseClick(player.video, Qt.MouseButton.LeftButton, pos=player.video.rect().center())
        QTest.mouseDClick(player.video, Qt.MouseButton.LeftButton, pos=player.video.rect().center())
        QTest.mouseRelease(player.video, Qt.MouseButton.LeftButton, pos=player.video.rect().center())
        assert window.isFullScreen()
        QTest.qWait(app.doubleClickInterval() + 150)
        assert player.player.playbackState() == playing, "Double-click also paused playback"
        capture(window, "fullscreen-next")

        # Exercise QWindow events as well: on Windows the actual decoded
        # surface receives native mouse events instead of QWidget events.
        surface = next(w for w in app.allWindows() if w.metaObject().className() == "QVideoWindow" and window.windowHandle().isAncestorOf(w))
        QTest.mouseClick(surface, Qt.MouseButton.LeftButton, pos=QPoint(surface.width() // 2, surface.height() // 2))
        wait_for(lambda: player.player.playbackState() == paused, "Native video surface click did not pause")
        # QWindow QTest events use a synthetic clock. Separate gestures in
        # that clock too, so the earlier single-click is not counted as the
        # first half of this new double-click after fullscreen changes.
        QTest.mouseMove(surface, QPoint(surface.width() // 2, surface.height() // 2), delay=app.doubleClickInterval() + 100)
        QTest.mouseDClick(surface, Qt.MouseButton.LeftButton, pos=QPoint(surface.width() // 2, surface.height() // 2))
        assert not window.isFullScreen()
        QTest.qWait(app.doubleClickInterval() + 100)
        assert player.player.playbackState() == paused, "Paused double-click resumed unexpectedly"
        QTest.mouseClick(player.pause, Qt.MouseButton.LeftButton)
        QTest.qWait(app.doubleClickInterval() + 100)
        assert player.player.playbackState() == playing, "Control button also activated the video gesture"

        QTest.mousePress(player.video, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
        QTest.mouseRelease(player.video, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
        QTest.mouseClick(player.video, Qt.MouseButton.RightButton, pos=player.video.rect().center())
        QTest.qWait(app.doubleClickInterval() + 100)
        assert player.player.playbackState() == playing, "Dragging/right-click toggled playback"

        # Manual next does not depend on autoplay, reuses the player and
        # crosses seasons without double-advancing or leaving fullscreen.
        player = start(episodes[2], episodes)
        player.toggle_fullscreen()
        QTest.mouseClick(player.next_episode, Qt.MouseButton.LeftButton)
        wait_for(lambda: window.player_window.item.uid == episodes[3].uid and player.player.position() > 1000, "Manual next did not cross seasons")
        assert window.player_window is player and window.isFullScreen()
        assert not controller.library.auto_next_enabled
        assert controller.library.checkpoint(episodes[2]) is not None
        player.leave_fullscreen()

        # A pending single-click is discarded when an episode is replaced.
        QTest.mouseClick(player.video, Qt.MouseButton.LeftButton, pos=player.video.rect().center())
        window.next_episode(); window.next_episode()
        wait_for(lambda: player.item.uid == episodes[4].uid and player.player.position() > 1000, "Manual next did not load exactly one episode")
        assert player.player.playbackState() == playing
        window.leave_player()

        player = start(episodes[0])
        wait_for(lambda: window.episode_task is None and player.next_episode.isEnabled(), "Continue Watching did not retrieve the next episode")
        window.leave_player()
        player = start(episodes[-1], episodes)
        assert player.next_episode.isVisible() and not player.next_episode.isEnabled(), "Last episode incorrectly loops"
        window.leave_player()
        for kind in ("movie", "live"):
            player = start(window.catalog[kind]["items"][0])
            assert player.next_episode.isHidden(), "Movie/live player shows episode navigation"
            window.leave_player()

        player = start(episodes[0], episodes)
        window.next_episode(); window.leave_player(); QTest.qWait(100)
        assert window.player_window is None, "Queued manual next reopened the player after Back"

        # Existing per-episode rows remain durable, but the visible resume
        # list exposes only the latest episode of each series.
        with controller.library.db:
            controller.library.db.execute("DELETE FROM progress WHERE account=?", (controller.library.account,))
        controller.library.progress.clear()
        for item in (episodes[1], episodes[5]):
            controller.library.record_progress(item, 5000, 90000)
        movie = window.catalog["movie"]["items"][0]
        controller.library.record_progress(movie, 7000, 90000)
        window.navigate("continue")
        assert {item.uid for item in window.grid.content_model.items} == {episodes[5].uid, movie.uid}, ("Resume grid mismatch", [item.uid for item in window.grid.content_model.items], [item.uid for item in controller.library.continuing()], window.current_tab, window.search.text(), window.closed)
        assert controller.library.checkpoint(episodes[1])["position"] == 5000
        capture(window, "continue-grouped")
        controller.library.record_progress(episodes[0], 9000, 90000)
        window.render()
        assert {item.uid for item in window.grid.content_model.items} == {episodes[0].uid, movie.uid}, "Older-number replay did not become the most recent episode"
        restored = Library(directory)
        try:
            restored.select_account(window.client.credentials)
            assert {item.uid for item in restored.continuing()} == {episodes[0].uid, movie.uid}
        finally:
            restored.close()
        print("Windows 1.5.0 checks passed: single/native video clicks, double-click fullscreen, control isolation, manual cross-season next, queued next cancellation, last-episode bounds and one latest resume card per series.")
    finally:
        if controller.browser:
            controller.browser.close()
        controller.login.close()
        controller.shutdown()
        provider.close()
