# PyInstaller build recipe for the Windows app. Build with:  build.bat
from PyInstaller.utils.hooks import collect_data_files

datas = [("assets/icon.ico", "assets"), ("assets/icon.png", "assets")]
datas += collect_data_files("sv_ttk")
datas += collect_data_files("soundcard")   # soundcard needs its .h files for cffi

a = Analysis(
    ["multi_headphones.py"],
    datas=datas,
    hiddenimports=["_cffi_backend"],
    excludes=["matplotlib", "PIL", "pytest", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MultiHeadphones",
    icon="assets/icon.ico",
    console=False,
    version="version_info.txt",
)
coll = COLLECT(exe, a.binaries, a.datas, name="MultiHeadphones")
