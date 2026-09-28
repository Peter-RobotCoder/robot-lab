"""Copy the game (and only the game) into the public robot-lab repository folder, then check it.

    python release/make_public_repo.py [folder]      (default: robot-lab next to the ClubCodersAI folder)

What goes in: every Python file the learner window, the server, the showcase and the tests need (found by
following their imports), the starter mods and example robots, brains/my_brain.py, requirements, the release
build (release/), the VPS kit (deploy/), the GitHub release workflow and the learner README.

What never goes in, and is checked for after copying: profiles/, evidence/, ai_requests/, ai_changes/,
learners' robot files, saved lessons, logs, and any class or teacher code (from teacher_settings.json,
deploy settings or the JOIN_CODE / TEACHER_CODE environment variables). If the check finds any of them,
the script stops with an error and the folder must not be pushed.
"""
import ast
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PUBLIC = os.path.join(HERE, "release", "public")
DEFAULT_TARGET = os.path.abspath(os.path.join(HERE, "..", "..", "robot-lab"))

ENTRY_POINTS = ["lab_client.py", "lab_server.py", "robot_wars.py", "brain_worker.py", "smoke_test.py",
                "security_test.py"]
EXTRA_FILES = ["requirements.txt", "mods/arena.py", "mods/rules.py", "mods/robots/titan.py",
               "mods/robots/razorback.py", "brains/my_brain.py", "release/robotlab.spec", "release/build_windows.py",
               "release/make_public_repo.py"]
EXTRA_DIRS = ["deploy"]
FORBIDDEN_DIRS = {"profiles", "evidence", "ai_requests", "ai_changes", "assets", "dist", "build", "__pycache__"}
FORBIDDEN_FILES = re.compile(r"(lesson_saved\.json|teacher_settings\.json|release_config\.json|\.log|\.env)$")
DEMO_CODES = {"CLUB42", "TEACH99"}  # public on purpose: they only work on a laptop test server
SECRET_PATTERNS = [re.compile(p) for p in (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"sk-ant-[A-Za-z0-9_-]{10,}",
                                           r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}")]


def local_imports(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return {n + ".py" for n in names if os.path.exists(os.path.join(HERE, n + ".py"))}


def game_files():
    todo, found = list(ENTRY_POINTS), set()
    while todo:
        f = todo.pop()
        if f in found:
            continue
        found.add(f)
        todo += sorted(local_imports(os.path.join(HERE, f)) - found)
    return sorted(found)


def secrets_to_find():
    """The real codes, wherever this laptop keeps them, so the check can make sure none were copied."""
    found = set()
    for key in ("JOIN_CODE", "TEACHER_CODE", "ROBOTLAB_TEACHER_CODE"):
        if os.environ.get(key):
            found.add(os.environ[key])
    path = os.path.join(HERE, "teacher_settings.json")
    if os.path.exists(path):
        import json
        with open(path, encoding="utf-8") as f:
            found |= {str(v) for v in json.load(f).values() if isinstance(v, str) and len(v) >= 6}
    return {s for s in found if s and s not in DEMO_CODES}


def check(target):
    problems, secrets = [], secrets_to_find()
    for folder, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d != ".git"]
        rel_dir = os.path.relpath(folder, target).replace("\\", "/")
        for d in dirs:
            if d in FORBIDDEN_DIRS:
                problems.append(f"folder that must not be public: {rel_dir}/{d}")
        for name in files:
            rel = f"{rel_dir}/{name}".lstrip("./")
            if FORBIDDEN_FILES.search(name):
                problems.append(f"file that must not be public: {rel}")
            if rel.startswith("mods/robots/") and name not in ("titan.py", "razorback.py"):
                problems.append(f"a learner's robot file: {rel}")
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    text = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for s in secrets:
                if s in text:
                    problems.append(f"a real class or teacher code is written in {rel}")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    problems.append(f"something that looks like a key or token is in {rel}")
    return problems


def copy(target):
    os.makedirs(target, exist_ok=True)
    for name in os.listdir(target):  # start clean (keep the git history)
        if name != ".git":
            path = os.path.join(target, name)
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    for rel in game_files() + EXTRA_FILES:
        dest = os.path.join(target, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(os.path.join(HERE, rel), dest)
    for d in EXTRA_DIRS:
        if os.path.isdir(os.path.join(HERE, d)):
            shutil.copytree(os.path.join(HERE, d), os.path.join(target, d),
                            ignore=shutil.ignore_patterns("__pycache__", "*.env", "*.log"))
    shutil.copytree(PUBLIC, target, dirs_exist_ok=True)  # README, .gitignore and the release workflow
    os.replace(os.path.join(target, "gitignore.txt"), os.path.join(target, ".gitignore"))


def main():
    target = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET)
    copy(target)
    problems = check(target)
    if problems:
        print("STOP: don't push this folder. Found:\n  " + "\n  ".join(problems))
        sys.exit(1)
    if not os.path.isdir(os.path.join(target, ".git")):
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=target, check=True)
    files = sum(len(f) for _, _, f in os.walk(target) if ".git" not in _)
    print(f"Public repository ready in {target} ({files} files). Checked: no learner data, no codes, no keys.")


if __name__ == "__main__":
    main()
