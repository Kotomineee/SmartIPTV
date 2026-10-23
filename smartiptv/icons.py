"""Small vector icons, rendered at the device's pixel density."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "settings": '<path d="m9 3-1 3-3 1-2 4 2 2v4l4 3 3-1 3 1 4-3v-4l2-2-2-4-3-1-1-3Z"/><circle cx="12" cy="12" r="3"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "rewind": '<path d="M4 9a8 8 0 1 1 0 7M4 3v6h6"/><text x="8" y="15" font-size="7" fill="currentColor" stroke-width=".4">10</text>',
    "forward": '<path d="M20 9a8 8 0 1 0 0 7M20 3v6h-6"/><text x="8" y="15" font-size="7" fill="currentColor" stroke-width=".4">10</text>',
    "volume": '<path d="M4 9h4l5-4v14l-5-4H4ZM17 8a6 6 0 0 1 0 8M20 5a10 10 0 0 1 0 14"/>',
    "muted": '<path d="M4 9h4l5-4v14l-5-4H4ZM17 9l5 6m0-6-5 6"/>',
    "music": '<path d="M10 17V5l10-2v12M10 8l10-2"/><ellipse cx="6" cy="18" rx="4" ry="3"/><ellipse cx="16" cy="16" rx="4" ry="3"/>',
    "subtitles": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M10 10a3 3 0 1 0 0 4m9-4a3 3 0 1 0 0 4"/>',
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
