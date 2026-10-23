from .login import STYLE

THEME = STYLE + """
QFrame#detailPanel { background: #121d1a; border: 1px solid #426653; border-radius: 16px; }
QFrame#accountSeparator { background: #2c4037; border: none; }
QFrame#settingsCard { background: #121d1a; border: 1px solid #2b4337; border-radius: 13px; }
QWidget#playerRoot { background: #070b0a; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 4px; }
QToolButton:hover, QToolButton:focus { background: #203b30; border-color: #559d79; }
QToolButton::menu-indicator { image: none; }
QLabel#playerTime { color: #c5d8d1; font-size: 12px; }
QMenu { background: #14221b; color: #e0eee4; border: 1px solid #426653; padding: 6px; }
QMenu::item { padding: 9px 26px; border-radius: 5px; }
QMenu::item:selected { background: #285640; }
QMenu::item:disabled { color: #7e9387; }
QMainWindow, QDialog, QWidget#libraryRoot { background: #0b1011; }
QFrame#sidebar { background: #101819; border-right: 1px solid #25312e; }
QPushButton#nav { color: #99aaa4; border: none; border-radius: 8px; background: transparent; text-align: left; padding: 13px 14px; font-size: 13px; }
QPushButton#nav:hover { background: #192824; color: #e9f7ef; }
QPushButton#nav:checked { background: #213d31; color: #83e8b8; font-weight: 600; }
QPushButton#nav:focus { border: 1px solid #65dfad; }
QPushButton#secondary { color: #d1e4d9; border: 1px solid #35473f; border-radius: 8px; background: #18251f; padding: 9px 16px; }
QPushButton#secondary:hover { border-color: #65dfad; background: #243e30; }
QLabel#pageTitle { font-size: 29px; font-weight: 650; letter-spacing: -0.8px; }
QLabel#sectionTitle { font-size: 19px; font-weight: 600; }
QLabel#detailTitle { font-size: 27px; font-weight: 650; }
QLabel#body { color: #b2c4bb; font-size: 14px; }
QLineEdit#search { border: 1px solid #304039; border-radius: 9px; background: #121c19; padding: 11px 14px; min-width: 180px; }
QLineEdit#search:focus { border-color: #65dfad; }
QComboBox { color: #c9ded1; background: #17221d; border: 1px solid #32463a; border-radius: 7px; padding: 7px 12px; min-height: 21px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #18241e; color: #e5f4e9; selection-background-color: #2b503c; }
QListWidget#categories { background: #101916; color: #a9beb1; border: 1px solid #263a2c; border-radius: 10px; outline: none; padding: 7px; font-size: 12px; }
QListWidget#categories::item { padding: 11px 7px; border-radius: 6px; }
QListWidget#categories::item:selected { background: #254233; color: #83e8b8; }
QListView#gallery { background: transparent; border: none; outline: none; }
QScrollArea { border: none; background: transparent; }
QWidget#homeBody { background: #0b1011; }
QFrame#heroBanner { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #203d30,stop:1 #13201b); border: 1px solid #35513e; border-radius: 14px; }
QLabel#bannerTitle { font-size: 28px; font-weight: 650; color: #e5f6e8; }
QLabel#bannerText { color: #a3c5ae; font-size: 13px; }
QScrollBar:vertical { background: #101916; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a5143; min-height: 32px; border-radius: 3px; }
QScrollBar:horizontal { background: #101916; height: 8px; margin: 2px; }
QScrollBar::handle:horizontal { background: #3a5143; min-width: 30px; border-radius: 3px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSlider::groove:horizontal { height: 5px; background: #2c4135; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #65dfad; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -4px 0; border-radius: 6px; background: #8cf0bf; }
QListWidget#episodes { background: #101916; color: #d0e2d5; border: 1px solid #2d4032; border-radius: 8px; outline: none; }
QListWidget#episodes::item { padding: 14px 10px; border-bottom: 1px solid #24362a; }
QListWidget#episodes::item:selected { background: #274735; color: #a1f0c7; }
QToolTip { color: #e8f4eb; background: #20382b; border: 1px solid #436149; padding: 6px; }
"""
