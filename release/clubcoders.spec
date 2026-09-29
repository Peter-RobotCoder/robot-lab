# PyInstaller recipe for the downloadable Club Coders app (Windows). Run by release/build_windows.py, not by hand.
# One runtime (Python, Panda3D and the other libraries) for every game: the app's own window is launcher/club_coders.py,
# and each game's files go in as they are (games/<game>/), run by the same exe with --game <game>. So the games
# never share or clash over module names, and the download is barely bigger than one game.
# One folder (not one file): it starts faster and antivirus programs are less suspicious of it.
import ast
import importlib.util
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 (SPECPATH is given by PyInstaller)
GAMES = os.path.join(ROOT, "games")
SKIP_DIRS = {"__pycache__", "brains", "profiles", "evidence", "ai_requests", "ai_changes", "build", "dist", ".venv"}
NOT_IN_APP = {"ursina", "pygame", "tkinter", "psutil", "IPython", "pytest"}  # (older demos and tests only)


def game_datas():
    """Every game's files (code, starter mods, models, the textures and sounds made before the build)."""
    out = []
    for folder, dirs, files in os.walk(GAMES):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(folder, ROOT)
        out += [(os.path.join(folder, f), rel) for f in files if not f.endswith((".pyc", ".log"))]
    return out


def game_imports():
    """The libraries (standard and installed) the games import: the exe only includes what it's told about."""
    names, local = set(), set()
    for folder, dirs, files in os.walk(GAMES):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        local |= {f[:-3] for f in files if f.endswith(".py")}
        for f in files:
            if f.endswith(".py"):
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    for node in ast.walk(ast.parse(fh.read())):
                        if isinstance(node, ast.Import):
                            names |= {a.name for a in node.names}
                        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                            names.add(node.module)  # (and its submodules: "from PIL import Image" needs PIL.Image)
                            names |= {f"{node.module}.{a.name}" for a in node.names}
    found = []
    for name in sorted(names):
        top = name.split(".")[0]
        if top in local or top in NOT_IN_APP:
            continue
        try:
            if importlib.util.find_spec(name) is not None:  # (a name that isn't a module, like a class, is skipped)
                found.append(name)
        except (ImportError, ValueError, AttributeError):
            pass
    return found


datas = game_datas() + [(os.path.join(ROOT, "build", "release_config.json"), ".")]
datas += collect_data_files("panda3d")                   # etc/Config.prc: which display and audio to load
datas += copy_metadata("panda3d-gltf")                   # (Panda3D finds the glTF model loader through this)
binaries = collect_dynamic_libs("panda3d")               # Panda3D loads its display and audio DLLs by name
hiddenimports = (collect_submodules("panda3d") + collect_submodules("direct") + collect_submodules("websockets")
                 + collect_submodules("gltf") + ["simplepbr", "live_format",
                                                  "cryptography.hazmat.primitives.asymmetric.ed25519"] + game_imports())

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "launcher", "club_coders.py")],
    pathex=[os.path.join(ROOT, "launcher"), os.path.join(ROOT, "live")],  # (live_format: checking live updates)
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=sorted(NOT_IN_APP),
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Club Coders",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Club Coders", upx=False)  # noqa: F821
