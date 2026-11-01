"""Pixel scrolling remains bounded, responsive and cancellable with real widgets."""
import os
from pathlib import Path
import sys
import tempfile
os.environ["QT_QPA_PLATFORM"] = "windows" if os.environ.get("SMARTIPTV_NATIVE_CHECK") == "1" else "offscreen"
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QEventLoop, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from smartiptv.app import Controller
from tests.provider import Provider
app=QApplication([]);app.setStyle("Fusion")


def wait_for(condition, message):
    loop,poll,deadline=QEventLoop(),QTimer(),QTimer()
    poll.setInterval(25);poll.timeout.connect(lambda:loop.quit() if condition() else None)
    deadline.setSingleShot(True);deadline.timeout.connect(loop.quit)
    poll.start();deadline.start(12000);loop.exec();poll.stop();deadline.stop()
    assert condition(),message


def wheel(widget, angle=-120, pixels=0):
    pos=widget.rect().center()
    event=QWheelEvent(QPointF(pos), QPointF(widget.mapToGlobal(pos)), QPoint(0,pixels), QPoint(0,angle),
                      Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False)
    QApplication.sendEvent(widget,event)


with tempfile.TemporaryDirectory(prefix="smartiptv-v153-") as directory:
    provider=Provider().start();controller=Controller(app,directory,auto_login=False)
    try:
        login=controller.login
        login.server.edit.setText(provider.url);login.username.edit.setText("demo");login.password.edit.setText("demopass")
        login.validate_form();wait_for(lambda:controller.browser is not None,"Login failed")
        window=controller.browser
        wait_for(lambda:len(window.catalog.get("movie",{}).get("items",[]))==80,"Catalog failed")
        window.navigate("movie");app.processEvents()
        view=window.grid;bar=view.verticalScrollBar()
        assert bar.maximum()>500
        wheel(view.viewport())
        assert bar.value()==0,"Wheel still jumped instantly"
        QTest.qWait(50)
        assert 0<bar.value()<96,"No intermediate scrolling positions"
        QTest.qWait(180)
        assert bar.value()==96,"One notch must move less than a poster row"
        for _ in range(4):wheel(view.viewport())
        QTest.qWait(220)
        assert bar.value()==480,"Rapid scrolling lost or magnified wheel steps"
        wheel(view.viewport());QTest.qWait(40)
        before=bar.value();wheel(view.viewport(),angle=120);QTest.qWait(220)
        assert bar.value()<before,"Changing direction did not respond promptly"
        before=bar.value();wheel(view.viewport(),angle=0,pixels=-19)
        assert bar.value()==before+19,"Trackpad pixel precision changed"
        QTest.qWait(200)
        assert bar.value()==before+19,"Trackpad left a trailing animation"
        wheel(view.viewport());QTest.qWait(40)
        QTest.keyClick(view,Qt.Key.Key_PageDown);after_key=bar.value();QTest.qWait(220)
        assert bar.value()==after_key,"Wheel animation fought keyboard navigation"
        wheel(view.viewport());window.navigate("series");QTest.qWait(220)
        assert bar.value()==0,"Old catalog kept scrolling after tab change"
        window.navigate("home");app.processEvents()
        home=window.home_scroll.verticalScrollBar()
        assert home.maximum()>0
        wheel(window.home_galleries["movie"].viewport());QTest.qWait(220)
        assert 0<home.value()<=96,"Poster row wheel did not scroll its page smoothly"
        print("Windows 1.5.3 checks passed: short animated wheel steps, rapid/reverse scrolling, native trackpad deltas, keyboard cancellation, tab isolation and home poster-row scrolling.")
    finally:
        if controller.browser:controller.browser.close()
        controller.login.close();controller.shutdown();provider.close()
