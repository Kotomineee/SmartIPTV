"""Series favorites and episode-list navigation, using a fictional local provider."""
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "windows" if os.environ.get("SMARTIPTV_NATIVE_CHECK") == "1" else "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from smartiptv import __version__
from smartiptv.app import Controller
from tests.provider import Provider

app = QApplication([])
app.setStyle("Fusion")


def wait_for(condition, message):
    if condition():
        return
    loop, poll, deadline = QEventLoop(), QTimer(), QTimer()
    poll.setInterval(25)
    poll.timeout.connect(lambda: loop.quit() if condition() else None)
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start(); deadline.start(12000); loop.exec(); poll.stop(); deadline.stop()
    assert condition(), message


def capture(window, name):
    if directory := os.environ.get("SMARTIPTV_SCREENSHOT_DIR"):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(path / f"SmartIPTV-{__version__}-{name}.png"))


with tempfile.TemporaryDirectory(prefix="smartiptv-v151-") as directory:
    provider = Provider(ROOT / "tests/assets/resume.mp4").start()
    controller = Controller(app, directory, auto_login=False)
    try:
        form = controller.login
        form.server.edit.setText(provider.url); form.username.edit.setText("demo"); form.password.edit.setText("demopass")
        form.validate_form()
        wait_for(lambda: controller.browser is not None, "Login failed")
        window, library = controller.browser, controller.library
        wait_for(lambda: bool(window.catalog.get("series", {}).get("items")), "Catalog failed")
        series = window.catalog["series"]["items"][0]
        movie = window.catalog["movie"]["items"][0]
        episode = window.client.series_details(series)["episodes"][4]
        library.record_progress(episode, 300000, 1200000)
        library.record_progress(movie, 7000, 90000)

        window.navigate("continue")
        def card(item):
            index = next(i for i, value in enumerate(window.grid.content_model.items) if value.uid == item.uid)
            return window.grid.visualRect(window.grid.model().index(index))

        # Clicking a resume card opens its parent series, including the saved
        # season and selected episode, without starting a stream.
        QTest.mouseClick(window.grid.viewport(), Qt.MouseButton.LeftButton, pos=card(episode).topLeft() + QPoint(50, 90))
        detail = window.detail_dialog
        assert detail is not None and detail.item == series
        wait_for(lambda: detail.watch.isEnabled(), "Episode list failed")
        assert detail.seasons.current_season() == episode.season
        assert detail.episode_list.currentItem().data(Qt.ItemDataRole.UserRole).uid == episode.uid
        assert window.player_window is None and not provider.media_requests
        capture(window, "resume-series-episodes")
        detail.reject(); app.processEvents()

        # The resume heart and the catalog heart refer to the same series.
        rect = card(episode).adjusted(2, 2, -8, -8)
        QTest.mouseClick(window.grid.viewport(), Qt.MouseButton.LeftButton, pos=rect.topRight() + QPoint(-22, 22))
        assert window.detail_dialog is None and library.is_favorite(series) and library.is_favorite(episode)
        assert list(library.favorites.values()) == [series]
        window.navigate("favorites")
        assert window.grid.content_model.items == [series]
        capture(window, "series-favorite-only")
        window.toggle_favorite(episode)
        assert not library.favorites

        # A legacy episode-only favorite migrates on login/reopen. A genuine
        # series favorite wins over episode metadata when both are present.
        library.toggle_favorite(series)
        library.toggle_favorite(movie)
        with library.db:
            library.db.execute("INSERT INTO favorites VALUES (?,?,?,?)", (library.account, episode.uid, json.dumps(episode.to_dict()), 1))
        library.select_account(window.client.credentials)
        window.render()
        assert set(item.uid for item in window.grid.content_model.items) == {series.uid, movie.uid}
        assert library.favorites[series.uid] == series
        assert library.checkpoint(episode)["position"] == 300000

        # Saved episode metadata can still open its series while a catalog
        # refresh is unavailable; movies keep their normal detail page.
        catalog = window.catalog
        window.catalog = {}
        window.open_content(episode)
        detail = window.detail_dialog
        wait_for(lambda: detail.watch.isEnabled(), "Saved series fallback failed")
        assert detail.item.kind == "series" and detail.item.id == series.id
        detail.reject(); window.catalog = catalog; app.processEvents()
        window.navigate("continue")
        QTest.mouseClick(window.grid.viewport(), Qt.MouseButton.LeftButton, pos=card(movie).topLeft() + QPoint(50, 90))
        assert window.detail_dialog.item == movie and window.player_window is None
        assert not provider.media_requests
        print("Windows 1.5.1 checks passed: resume cards open series episodes, favorite hearts target the series, legacy duplicates migrate, saved progress and movie navigation remain intact.")
    finally:
        if controller.browser:
            controller.browser.close()
        controller.login.close()
        controller.shutdown()
        provider.close()
