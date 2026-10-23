"""Small vector icons, rendered at the device's pixel density."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "server": '<rect x="4" y="3" width="16" height="7" rx="2"/><rect x="4" y="14" width="16" height="7" rx="2"/><path d="M8 6.5h.01M8 17.5h.01M16 6.5h1M16 17.5h1"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4.5 21v-2a7.5 7.5 0 0 1 15 0v2"/>',
    "lock": '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="m3 3 18 18M10.6 5.1A13.2 13.2 0 0 1 12 5c6.5 0 10 7 10 7a19 19 0 0 1-3.2 4.1M6.2 6.2A22 22 0 0 0 2 12s3.5 7 10 7a12.4 12.4 0 0 0 5.8-1.8M10 10a2.8 2.8 0 0 0 4 4"/>',
    "arrow": '<path d="M4 12h15m-6-6 6 6-6 6"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "play": '<path d="m9 6 9 6-9 6Z"/>',
    "tv": '<rect x="3" y="5" width="18" height="13" rx="3"/><path d="M8 22h8M12 18v4m-2-13 5 3-5 3Z"/>',
}


def icon(name: str, color: str = "#889695", size: int = 24) -> QIcon:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
