"""A blurred snapshot keeps the catalog quiet while details stay sharp."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGraphicsBlurEffect, QLabel, QWidget


class DetailBackdrop(QWidget):
    dismiss_requested = Signal()

    def __init__(self, parent):
        # Grab before this widget joins the parent's child tree; grab() may
        # flush pending layout events, including resize events on new children.
        snapshot = parent.grab()
        super().__init__(parent)
        self.setObjectName("detailsBackdrop")
        self.pressed_button = None
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Capture before showing this layer or the details panel. Blurring a
        # snapshot avoids repainting thousands of catalog cards on every frame.
        self.image = QLabel(self)
        self.image.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.image.setScaledContents(True)
        self.image.setPixmap(snapshot)
        self.blur = QGraphicsBlurEffect(self.image)
        self.blur.setBlurRadius(12 * snapshot.devicePixelRatio())
        self.blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        self.image.setGraphicsEffect(self.blur)
        self.shade = QWidget(self)
        self.shade.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.shade.setStyleSheet("background: rgba(2, 6, 7, 140);")
        self.setGeometry(parent.rect())

    def mousePressEvent(self, event):
        self.pressed_button = event.button()
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()
        if self.pressed_button == event.button():
            self.pressed_button = None
            # Keep the layer in place for the entire gesture. Hiding it on
            # press would send the release to a card or menu underneath.
            self.dismiss_requested.emit()

    def resizeEvent(self, event):
        self.image.setGeometry(self.rect())
        self.shade.setGeometry(self.rect())
        super().resizeEvent(event)
