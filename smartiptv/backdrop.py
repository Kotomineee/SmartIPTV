"""A blurred snapshot keeps the catalog quiet while details stay sharp."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsBlurEffect, QLabel, QWidget


class DetailBackdrop(QWidget):
    def __init__(self, parent):
        # Grab before this widget joins the parent's child tree; grab() may
        # flush pending layout events, including resize events on new children.
        snapshot = parent.grab()
        super().__init__(parent)
        self.setObjectName("detailsBackdrop")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Capture before showing this layer or the details panel. Blurring a
        # snapshot avoids repainting thousands of catalog cards on every frame.
        self.image = QLabel(self)
        self.image.setScaledContents(True)
        self.image.setPixmap(snapshot)
        self.blur = QGraphicsBlurEffect(self.image)
        self.blur.setBlurRadius(12 * snapshot.devicePixelRatio())
        self.blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        self.image.setGraphicsEffect(self.blur)
        self.shade = QWidget(self)
        self.shade.setStyleSheet("background: rgba(2, 6, 7, 140);")
        self.setGeometry(parent.rect())

    def resizeEvent(self, event):
        self.image.setGeometry(self.rect())
        self.shade.setGeometry(self.rect())
        super().resizeEvent(event)
