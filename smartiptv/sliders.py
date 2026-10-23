"""Sliders with absolute click positioning and native handle/keyboard support."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class ClickSlider(QSlider):
    keyboardCommitted = Signal()

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._absolute_drag = False

    def _value_at(self, point):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        style = self.style()
        groove = style.subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self)
        handle = style.subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
        start = groove.x() + handle.width() // 2
        span = max(1, groove.width() - handle.width())
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), round(point.x()) - start, span, option.upsideDown)

    def mousePressEvent(self, event):
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
            if not handle.contains(event.position().toPoint()):
                self._absolute_drag = True
                self.setFocus(Qt.FocusReason.MouseFocusReason)
                self.setSliderDown(True)
                self.setSliderPosition(self._value_at(event.position()))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._absolute_drag:
            self.setSliderPosition(self._value_at(event.position()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._absolute_drag and event.button() == Qt.MouseButton.LeftButton:
            self.setSliderPosition(self._value_at(event.position()))
            self._absolute_drag = False
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        previous = self.value()
        super().keyPressEvent(event)
        if self.value() != previous:
            self.keyboardCommitted.emit()
