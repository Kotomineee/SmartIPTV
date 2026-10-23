"""Catalog window: provider categories, virtual grids and a local library."""
import unicodedata
from urllib.parse import urlsplit

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QPushButton, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from . import __version__
from .details import DetailDialog
from .gallery import ArtworkCache, Gallery
from .icons import icon
from .login import label
from .player import PlayerWindow
from .theme import THEME


def searchable(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


class BrowserWindow(QMainWindow):
    logout_requested = Signal()

    NAVIGATION = [("home", "Início", "home"), ("live", "TV ao vivo", "tv"), ("movie", "Filmes", "film"), ("series", "Séries", "series"), ("continue", "Continuar assistindo", "clock"), ("favorites", "Favoritos", "heart")]

    def __init__(self, client, library, tasks, parent=None, artwork_directory=None, autoload=True):
        super().__init__(parent)
        self.client, self.library, self.tasks = client, library, tasks
        self.artwork = ArtworkCache(self, artwork_directory)
        self.catalog = {kind: {"categories": [], "items": []} for kind in ("live", "movie", "series")}
        self.names = {}
        self.current_tab = "home"
        self.catalog_task = None
        self.player_window = None
        self.detail_dialog = None
        self.closed = False
        self.setWindowTitle(f"SmartIPTV — {__version__}")
        self.resize(1380, 900)
        self.setMinimumSize(1040, 700)
        self.setStyleSheet(THEME)
        root = QWidget()
        root.setObjectName("libraryRoot")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(228)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(15, 28, 15, 24)
        side.setSpacing(8)
        brand = QPushButton("SmartIPTV")
        brand.setIcon(icon("tv", "#65dfad", 30))
        brand.setIconSize(QSize(30, 30))
        brand.setStyleSheet("QPushButton {color:#edf5f2; background:transparent; border:none; text-align:left; font-size:21px; font-weight:700; padding:0 8px 20px;}")
        brand.clicked.connect(lambda: self.navigate("home"))
        side.addWidget(brand)
        side.addSpacing(24)
        side.addWidget(label("  SUA BIBLIOTECA", "eyebrow"))
        side.addSpacing(10)
        self.nav = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, title, symbol in self.NAVIGATION:
            button = QPushButton(title)
            button.setObjectName("nav")
            button.setIcon(icon(symbol, "#93b7a0"))
            button.setIconSize(QSize(19, 19))
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: self.navigate(k))
            group.addButton(button)
            side.addWidget(button)
            self.nav[key] = button
        self.nav["home"].setChecked(True)
        side.addStretch()
        side.addWidget(label("CONECTADO AO PROVEDOR", "eyebrow"))
        side.addWidget(label(urlsplit(client.credentials.server).hostname or "Servidor Xtream", "muted", True))
        side.addSpacing(16)
        logout = QPushButton("Sair da conta")
        logout.setObjectName("secondary")
        logout.setIcon(icon("logout"))
        logout.clicked.connect(self.logout_requested.emit)
        side.addWidget(logout)
        side.addSpacing(5)
        side.addWidget(label(f"SmartIPTV  ·  v{__version__}", "version"))
        shell.addWidget(sidebar)

        main = QVBoxLayout()
        main.setContentsMargins(28, 28, 25, 18)
        main.setSpacing(17)
        heading = QHBoxLayout()
        heading.setSpacing(18)
        self.page_title = label("Início", "pageTitle")
        heading.addWidget(self.page_title)
        heading.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Buscar no catálogo…")
        self.search.setAccessibleName("Buscar no catálogo")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(350)
        self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(220)
        self.search_timer.timeout.connect(self.render)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        heading.addWidget(self.search, 1)
        self.refresh = QPushButton("Atualizar")
        self.refresh.setObjectName("secondary")
        self.refresh.setIcon(icon("refresh"))
        self.refresh.clicked.connect(self.load_catalog)
        heading.addWidget(self.refresh)
        main.addLayout(heading)
        self.subtitle = label("Carregando seu catálogo…", "muted", True)
        main.addWidget(self.subtitle)
        self.message = label("", "body", True)
        self.message.hide()
        main.addWidget(self.message)
        self.pages = QStackedWidget()
        main.addWidget(self.pages, 1)
        shell.addLayout(main, 1)
        self.galleries = []
        self._build_home()
        self._build_grid()
        if autoload:
            QTimer.singleShot(0, self.load_catalog)

    def _gallery(self, compact=False, horizontal=False):
        gallery = Gallery(self.library, self.artwork, compact, horizontal)
        gallery.open_requested.connect(self.open_content)
        gallery.favorite_requested.connect(self.toggle_favorite)
        gallery.remove_progress_requested.connect(self.remove_progress)
        self.galleries.append(gallery)
        return gallery

    def _build_home(self):
        self.home_scroll = QScrollArea()
        self.home_scroll.setWidgetResizable(True)
        self.home_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("homeBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 6, 10)
        layout.setSpacing(20)
        banner = QFrame()
        banner.setObjectName("heroBanner")
        content = QVBoxLayout(banner)
        content.setContentsMargins(26, 23, 26, 23)
        content.setSpacing(9)
        content.addWidget(label("SEU CATÁLOGO, DO SEU JEITO", "eyebrow"))
        content.addWidget(label("O próximo play começa aqui.", "bannerTitle", True))
        content.addWidget(label("Descubra o que chegou e volte às suas histórias favoritas.", "bannerText", True))
        self.catalog_count = label("Conectando à sua biblioteca…", "bannerText")
        content.addSpacing(5)
        content.addWidget(self.catalog_count)
        layout.addWidget(banner)
        self.home_galleries = {}
        for kind, title, description in [
            ("movie", "Filmes recém-adicionados", "As inclusões mais recentes do seu provedor."),
            ("series", "Séries atualizadas", "Novas séries e títulos com atualizações recentes."),
            ("live", "Canais recém-adicionados", "Mais opções para acompanhar ao vivo."),
        ]:
            row = QHBoxLayout()
            row.addWidget(label(title, "sectionTitle"))
            row.addStretch()
            more = QPushButton("Ver todos  →")
            more.setObjectName("secondary")
            more.clicked.connect(lambda _checked=False, k=kind: self.navigate(k))
            row.addWidget(more)
            layout.addLayout(row)
            layout.addWidget(label(description, "muted", True))
            gallery = self._gallery(kind == "live", True)
            self.home_galleries[kind] = gallery
            layout.addWidget(gallery)
        layout.addStretch()
        self.home_scroll.setWidget(body)
        self.pages.addWidget(self.home_scroll)

    def _build_grid(self):
        self.grid_page = QWidget()
        content = QHBoxLayout(self.grid_page)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(20)
        self.categories = QListWidget()
        self.categories.setObjectName("categories")
        self.categories.setAccessibleName("Categorias do provedor")
        self.categories.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.categories.setFixedWidth(210)
        self.categories.currentRowChanged.connect(lambda _row: self.render())
        content.addWidget(self.categories)
        center = QVBoxLayout()
        center.setSpacing(14)
        tools = QHBoxLayout()
        self.result_count = label("", "muted")
        tools.addWidget(self.result_count)
        tools.addStretch()
        self.sort = QComboBox()
        self.sort.addItems(["Mais recentes", "Nome A–Z"])
        self.sort.setAccessibleName("Ordenação do catálogo")
        self.sort.currentIndexChanged.connect(lambda _index: self.render())
        tools.addWidget(self.sort)
        center.addLayout(tools)
        self.result_pages = QStackedWidget()
        self.grid = self._gallery()
        self.result_pages.addWidget(self.grid)
        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.addStretch()
        self.empty_title = label("Seu catálogo aparecerá aqui", "sectionTitle", True)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        self.empty_description = label("Use Atualizar para carregar os conteúdos do provedor.", "muted", True)
        self.empty_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_description)
        empty_layout.addStretch()
        self.result_pages.addWidget(self.empty)
        center.addWidget(self.result_pages, 1)
        content.addLayout(center, 1)
        self.pages.addWidget(self.grid_page)

    def load_catalog(self):
        if self.catalog_task:
            self.tasks.cancel(self.catalog_task)
        self.refresh.setEnabled(False)
        self.refresh.setText("Carregando…")
        self.subtitle.setText("Atualizando canais, filmes e séries do provedor…")
        self.catalog_task = self.tasks.submit(self.client.catalog, self._catalog_loaded, self._catalog_failed)

    def _catalog_loaded(self, catalog):
        self.catalog_task = None
        self.catalog = catalog
        self.names = {item.uid: searchable(item.name) for section in catalog.values() for item in section["items"]}
        self.refresh.setEnabled(True)
        self.refresh.setText("Atualizar")
        self.message.hide()
        self.catalog_count.setText("  ·  ".join(f"{len(catalog[k]['items']):,} {name}".replace(",", ".") for k, name in (("live", "canais"), ("movie", "filmes"), ("series", "séries"))))
        for kind, gallery in self.home_galleries.items():
            gallery.set_items(sorted(catalog[kind]["items"], key=lambda item: item.added, reverse=True)[:18])
        self._fill_categories()
        self.render()

    def _catalog_failed(self, message):
        self.catalog_task = None
        self.refresh.setEnabled(True)
        self.refresh.setText("Atualizar")
        self.notify(message, True)
        self.render()

    def notify(self, text, error=False):
        self.message.setText(text)
        self.message.setStyleSheet("color: #f1aaa4;" if error else "color: #82e4b0;")
        self.message.setVisible(bool(text))

    def navigate(self, tab):
        self.current_tab = tab
        self.nav[tab].setChecked(True)
        self.page_title.setText(dict((k, name) for k, name, _ in self.NAVIGATION)[tab])
        self.sort.setItemText(0, "Assistidos recentemente" if tab == "continue" else "Mais recentes")
        self._fill_categories()
        self.render()

    def _fill_categories(self):
        self.categories.blockSignals(True)
        self.categories.clear()
        section = self.catalog.get(self.current_tab)
        self.categories.setVisible(section is not None)
        if section:
            all_item = QListWidgetItem("Todas as categorias")
            all_item.setData(Qt.ItemDataRole.UserRole, None)
            self.categories.addItem(all_item)
            for category in section["categories"]:
                row = QListWidgetItem(category["name"])
                row.setToolTip(category["name"])
                row.setData(Qt.ItemDataRole.UserRole, category["id"])
                self.categories.addItem(row)
            self.categories.setCurrentRow(0)
        self.categories.blockSignals(False)

    def render(self):
        if self.closed:
            return
        term = searchable(self.search.text().strip())
        tab = self.current_tab
        if tab == "home" and not term:
            self.pages.setCurrentWidget(self.home_scroll)
            self.subtitle.setText("Filmes adicionados e séries atualizadas recentemente na sua playlist.")
            return
        self.pages.setCurrentWidget(self.grid_page)
        if tab in self.catalog:
            items = list(self.catalog[tab]["items"])
            selected = self.categories.currentItem()
            category = selected.data(Qt.ItemDataRole.UserRole) if selected else None
            if category is not None:
                items = [item for item in items if category in item.categories]
        elif tab == "favorites":
            items = list(self.library.favorites.values())
        elif tab == "continue":
            items = self.library.continuing()
        else:
            items = [item for section in self.catalog.values() for item in section["items"]]
        if term:
            items = [item for item in items if term in self.names.get(item.uid, searchable(item.display_name))]
        if self.sort.currentIndex() == 1:
            items.sort(key=lambda item: searchable(item.name))
        elif tab != "continue":
            items.sort(key=lambda item: item.added, reverse=True)
        self.grid.set_items(items)
        self.result_count.setText(f"{len(items):,} conteúdos".replace(",", "."))
        descriptions = {
            "live": "Seus canais organizados nas categorias do provedor.",
            "movie": "Encontre seu próximo filme. Escolha uma categoria ou faça uma busca.",
            "series": "Explore suas séries e escolha a temporada e o episódio.",
            "favorites": "Seus conteúdos favoritos, salvos neste computador para esta conta.",
            "continue": "Retome filmes e episódios do ponto em que parou.",
            "home": "Resultados da busca em todo o catálogo.",
        }
        self.subtitle.setText(descriptions[tab])
        if items:
            self.result_pages.setCurrentWidget(self.grid)
        else:
            self.result_pages.setCurrentWidget(self.empty)
            self.empty_title.setText("Nenhum resultado encontrado" if term else "Seus favoritos ficam aqui" if tab == "favorites" else "Nenhum conteúdo em andamento" if tab == "continue" else "Nenhum conteúdo disponível")
            self.empty_description.setText("Tente outro nome ou categoria." if term else "Toque no coração de um conteúdo para salvá-lo." if tab == "favorites" else "Comece um filme ou episódio para retomar depois." if tab == "continue" else "Atualize o catálogo ou escolha outra categoria.")

    def toggle_favorite(self, item):
        try:
            self.library.toggle_favorite(item)
        except Exception:
            self.notify("Não foi possível salvar seus favoritos neste computador.", True)
            return
        for gallery in self.galleries:
            gallery.content_model.refresh()
        if self.current_tab == "favorites":
            self.render()

    def remove_progress(self, item):
        try:
            self.library.remove_progress(item)
            self.library_updated()
        except Exception:
            self.notify("Não foi possível atualizar seu progresso.", True)

    def open_content(self, item):
        if not item:
            return
        if item.kind == "episode":
            self.play(item)
            return
        if self.detail_dialog:
            self.detail_dialog.close()
        dialog = DetailDialog(item, self.client, self.library, self.tasks, self.artwork, self)
        self.detail_dialog = dialog
        dialog.favorite_requested.connect(self.toggle_favorite)
        dialog.play_requested.connect(self.play)
        dialog.finished.connect(lambda _result: self._detail_closed(dialog))
        dialog.open()

    def _detail_closed(self, dialog):
        if self.detail_dialog is dialog:
            self.detail_dialog = None
        dialog.deleteLater()

    def play(self, item, restart=False):
        if self.player_window:
            self.player_window.close()
            self.player_window.deleteLater()
        self.player_window = PlayerWindow(self.client, self.library, item, restart, self)
        self.player_window.library_changed.connect(self.library_updated)
        self.player_window.show()

    def library_updated(self):
        for gallery in self.galleries:
            gallery.content_model.refresh()
        if self.current_tab in ("continue", "favorites"):
            self.render()

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        if self.catalog_task:
            self.tasks.cancel(self.catalog_task)
        if self.detail_dialog:
            self.detail_dialog.close()
        if self.player_window:
            self.player_window.close()
        self.artwork.close()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
