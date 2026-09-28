# PyInstaller recipe for the downloadable Robot Lab (Windows). Run by release/build_windows.py, not by hand.
# One folder (not one file): it starts faster and antivirus programs are less suspicious of it.
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 (SPECPATH is given by PyInstaller)

datas = [
    # only the starter mods: learners' robot files (and their compiled copies) never go into the download
    (os.path.join(ROOT, "mods", "arena.py"), "mods"),
    (os.path.join(ROOT, "mods", "rules.py"), "mods"),
    (os.path.join(ROOT, "mods", "robots", "titan.py"), os.path.join("mods", "robots")),
    (os.path.join(ROOT, "mods", "robots", "razorback.py"), os.path.join("mods", "robots")),
    (os.path.join(ROOT, "assets"), "assets"),           # textures and sounds, made before the build
    (os.path.join(ROOT, "build", "release_config.json"), "."),   # the class server's address (from the build)
]
datas += collect_data_files("panda3d")                   # etc/Config.prc: which display and audio to load
binaries = collect_dynamic_libs("panda3d")               # Panda3D loads its display and audio DLLs by name
hiddenimports = collect_submodules("panda3d") + collect_submodules("direct") + ["simplepbr"]

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "lab_client.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["ursina", "pygame", "tkinter", "psutil", "lab_server", "tournament", "IPython"],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Robot Lab",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Robot Lab", upx=False)  # noqa: F821
