#!/usr/bin/env bash
# Starts one class's game server (run by robotlab@<class>.service). The class's game is GAME in
# /etc/robotlab/<class>.env: robotlab (Robot Lab, the default) or fightlab (Fight Lab).
# The game's code is the release's (/opt/robotlab/app/games/<game>), or a live update the teacher sent
# (robotlab-live: /opt/robotlab/live/<game>/<id>, used from the class's next restart).
# Each game keeps the class's data in its own place: Robot Lab in /var/lib/robotlab/<class>, Fight Lab in
# /var/lib/robotlab/<class>/fightlab, so a class that changes game keeps both.
set -euo pipefail
CLASS="$1"
APP=/opt/robotlab/app
PY=/opt/robotlab/venv/bin/python
DATA="/var/lib/robotlab/$CLASS"
GAME="${GAME:-robotlab}"

case "$GAME" in
    robotlab|fightlab) ;;
    *)
        echo "Unknown GAME '$GAME' in /etc/robotlab/$CLASS.env: it can be robotlab or fightlab." >&2
        exit 1
        ;;
esac

# the club desk: who may join (the launched group), the tickets' key, and the desk's requests for this game
export CLUBCODERS_LIVE_FILE=/var/lib/robotlab/desk/live.json
export CLUBCODERS_TICKET_KEY=/var/lib/robotlab/desk/ticket_key
export CLUBCODERS_DESK_INBOX="/var/lib/robotlab/desk/inbox/$GAME"

CODE="$APP/games/$GAME"
export CLUBCODERS_LIVE_POINTER="/opt/robotlab/live/$GAME/current"  # (the server tells the teacher when it changes)
if [ -f "$CLUBCODERS_LIVE_POINTER" ]; then
    LIVE_ID=$(tr -d '[:space:]' < "$CLUBCODERS_LIVE_POINTER")
    if [[ "$LIVE_ID" =~ ^[0-9a-f]{24}$ ]] && [ -f "/opt/robotlab/live/$GAME/$LIVE_ID/LIVE_ID" ]; then
        CODE="/opt/robotlab/live/$GAME/$LIVE_ID"
        echo "$CLASS runs live update $LIVE_ID of $GAME"
    fi
fi
cd "$CODE"

case "$GAME" in
    robotlab)
        export ROBOTLAB_DATA="$DATA"
        exec "$PY" lab_server.py --class-server --port "$PORT"
        ;;
    fightlab)
        mkdir -p "$DATA/fightlab"
        export FIGHTLAB_DATA="$DATA/fightlab"
        exec "$PY" fight_server.py --class-server --port "$PORT"
        ;;
esac
