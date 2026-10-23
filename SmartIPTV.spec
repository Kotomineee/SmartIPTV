# Build with: python -m PyInstaller --noconfirm SmartIPTV.spec
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "THIRD_PARTY_NOTICES.md"), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="SmartIPTV", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    icon=str(root / "assets" / "app.ico"),
    version=str(root / "windows-version.txt"),
)
