"""Copy the 2D prototype's interpreter, mission, tests and dictionary into prototype/ and dictionary.json here.

    python missions/wake_up_call/sync_prototype.py <prototype folder>           copy them
    python missions/wake_up_call/sync_prototype.py <prototype folder> --check   exit 1 if they differ

The prototype folder is prototypes/wake-up-call (branch prototype/wake-up-call). The Python port
(mission_pseudo.py, mission_wake_up.py) must give what these copies give: wake_up_call_test.py runs both.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def copies(folder):
    """{path here: text} from the prototype's folder: its page's two scripts, its tests and its dictionary."""
    with open(os.path.join(folder, "index.html"), encoding="utf-8") as f:
        page = f.read()
    out = {}
    for sid, name in (("cc-pseudo", "cc_pseudo.js"), ("cc-game", "cc_game.js")):
        m = re.search(r'<script id="%s">\n(.*?)</script>' % sid, page, re.S)
        if not m:
            sys.exit(f"index.html has no script {sid}")
        out[os.path.join(HERE, "prototype", name)] = m.group(1)
    for src, dst in (("tests/tests.js", "prototype/tests.js"), ("dictionary.json", "dictionary.json")):
        with open(os.path.join(folder, src), encoding="utf-8") as f:
            out[os.path.join(HERE, dst)] = f.read()
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    found = copies(sys.argv[1])
    if "--check" in sys.argv:
        stale = []
        for path, text in found.items():
            try:
                with open(path, encoding="utf-8") as f:
                    same = f.read() == text
            except OSError:
                same = False
            if not same:
                stale.append(os.path.relpath(path, HERE))
        print("the copies match the prototype" if not stale else "OUT OF DATE: " + ", ".join(stale))
        sys.exit(1 if stale else 0)
    os.makedirs(os.path.join(HERE, "prototype"), exist_ok=True)
    for path, text in found.items():
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("copied", os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
