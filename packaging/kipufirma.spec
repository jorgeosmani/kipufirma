# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist/KipuFirma/ con KipuFirma.exe (ventana) y kipufirma-cli.exe (consola).
# Modo "onedir": arranca más rápido y genera menos falsos positivos de antivirus que "onefile".
# Uso:  pyinstaller packaging/kipufirma.spec --noconfirm --clean
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

datas = [
    (str(SRC / "kipufirma" / "resources"), "kipufirma/resources"),
]
datas += collect_data_files("pyhanko")
datas += collect_data_files("pyhanko_certvalidator")
binaries = collect_dynamic_libs("pypdfium2_raw")
hidden = ["pypdfium2_raw", "PySide6.QtNetwork", "kipufirma.gui.app", "kipufirma.cli"]
excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "matplotlib", "numpy"]

def analysis(script):
    return Analysis([str(ROOT / "packaging" / script)], pathex=[str(SRC)], binaries=binaries, datas=datas,
                    hiddenimports=hidden, excludes=excludes, noarchive=False)

a_gui = analysis("launcher_gui.py")
a_cli = analysis("launcher_cli.py")
pyz_gui = PYZ(a_gui.pure)
pyz_cli = PYZ(a_cli.pure)

version_file = str(ROOT / "packaging" / "version_info.txt")
icon = str(ROOT / "packaging" / "kipufirma.ico")

exe_gui = EXE(pyz_gui, a_gui.scripts, [], exclude_binaries=True, name="KipuFirma", console=False,
              icon=icon, version=version_file, upx=False)
exe_cli = EXE(pyz_cli, a_cli.scripts, [], exclude_binaries=True, name="kipufirma-cli", console=True,
              icon=icon, version=version_file, upx=False)
coll = COLLECT(exe_gui, a_gui.binaries, a_gui.datas, exe_cli, a_cli.binaries, a_cli.datas,
               strip=False, upx=False, name="KipuFirma")
