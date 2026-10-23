"""Small vector icons, rendered at the device's pixel density."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "heart-filled": '<path fill="#74edb0" d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0l-1 1-1-1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
    "home": '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
    "film": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4m-4 8h4M17 8h4m-4 8h4"/>',
    "series": '<rect x="5" y="6" width="16" height="15" rx="2"/><path d="M17 2H3v15m8-7 5 3-5 3Z"/>',
    "heart": '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0l-1 1-1-1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5M6.5 6a8 8 0 0 1 13 1M4.5 17a8 8 0 0 0 13 1"/>',
    "logout": '<path d="M9 4H4v16h5m5-13 5 5-5 5m-5-5h14"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "full": '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
    "back": '<path d="M20 12H4m6-6-6 6 6 6"/>',
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
