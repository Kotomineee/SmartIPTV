"""Short, bounded pixel scrolling; trackpads keep their native pixel deltas."""
from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QVariantAnimation
from PySide6.QtWidgets import QAbstractItemView


class SmoothScroll(QObject):
    def __init__(self, view, step=96):
        super().__init__(view)
        self.view, self.step = view, step
        self.bar = view.verticalScrollBar()
        if isinstance(view, QAbstractItemView):
            view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.target = self.bar.value()
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(lambda value: self.bar.setValue(round(value)))
        self.bar.sliderPressed.connect(self.stop)
        self.bar.actionTriggered.connect(self.stop)
        self.bar.rangeChanged.connect(self.stop)
        for widget in (view, view.viewport(), self.bar):
            widget.installEventFilter(self)

    def stop(self, *_args):
        self.animation.stop()
        self.target = self.bar.value()

    def wheel(self, event):
        pixels, angle = event.pixelDelta().y(), event.angleDelta().y()
        if not pixels and not angle:
            return False
        if pixels:
            self.stop()
            self.bar.setValue(self.bar.value() - pixels)
            self.target = self.bar.value()
        else:
            delta = -angle / 120 * self.step
            running = self.animation.state() == QAbstractAnimation.State.Running
            base = self.target if running and (self.target-self.bar.value()) * delta >= 0 else self.bar.value()
            self.animation.stop()
            self.target = max(self.bar.minimum(), min(self.bar.maximum(), base + delta))
            self.animation.setStartValue(self.bar.value())
            self.animation.setEndValue(round(self.target))
            self.animation.start()
        event.accept()
        return True

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            return self.wheel(event)
        if event.type() in (QEvent.Type.Hide, QEvent.Type.KeyPress):
            self.stop()
        return False
