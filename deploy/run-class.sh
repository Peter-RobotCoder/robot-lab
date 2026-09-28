#!/usr/bin/env bash
# Starts one class's game server (run by robotlab@<class>.service). The class's game is GAME in
# /etc/robotlab/<class>.env: robotlab (Robot Lab, the default) or fightlab (Fight Lab).
# Each game keeps the class's data in its own place: Robot Lab in /var/lib/robotlab/<class>, Fight Lab in
# /var/lib/robotlab/<class>/fightlab, so a class that changes game keeps both.
set -euo pipefail
CLASS="$1"
APP=/opt/robotlab/app
PY=/opt/robotlab/venv/bin/python
DATA="/var/lib/robotlab/$CLASS"

case "${GAME:-robotlab}" in
    robotlab)
        cd "$APP/games/robotlab"
        export ROBOTLAB_DATA="$DATA"
        exec "$PY" lab_server.py --class-server --port "$PORT"
        ;;
    fightlab)
        mkdir -p "$DATA/fightlab"
        cd "$APP/games/fightlab"
        export FIGHTLAB_DATA="$DATA/fightlab"
        exec "$PY" fight_server.py --class-server --port "$PORT"
        ;;
    *)
        echo "Unknown GAME '$GAME' in /etc/robotlab/$CLASS.env: it can be robotlab or fightlab." >&2
        exit 1
        ;;
esac
