#!/usr/bin/env bash
# Starts one class's game server (run by robotlab@<class>.service). The class's game is GAME in
# /etc/robotlab/<class>.env: robotlab (Robot Lab, the default), fightlab (Fight Lab), kartlab (Kart Lab), citylab
# (City Lab) or missions (Missions: the story missions as a class game, whose server lives in Robot Lab's folder).
# The game's code is the release's (/opt/robotlab/app/games/<game>), or a live update the teacher sent
# (robotlab-live: /opt/robotlab/live/<game>/<id>, used from the class's next restart).
# Each game keeps the class's data in its own place: Robot Lab in /var/lib/robotlab/<class>, Fight Lab in
# /var/lib/robotlab/<class>/fightlab, Kart Lab in /var/lib/robotlab/<class>/kartlab, City Lab in
# /var/lib/robotlab/<class>/citylab, Missions in /var/lib/robotlab/<class>/missions, so a class that changes game
# keeps them all.
set -euo pipefail
CLASS="$1"
APP=/opt/robotlab/app
PY=/opt/robotlab/venv/bin/python
DATA="/var/lib/robotlab/$CLASS"
GAME="${GAME:-robotlab}"

case "$GAME" in
    robotlab|fightlab|kartlab|citylab|missions) ;;
    *)
        echo "Unknown GAME '$GAME' in /etc/robotlab/$CLASS.env: it can be robotlab, fightlab, kartlab, citylab or missions." >&2
        exit 1
        ;;
esac
FOLDER="$GAME"
[ "$GAME" != "missions" ] || FOLDER=robotlab  # (Missions' server and window are in Robot Lab's folder)

# the club desk: who may join (the launched group), the tickets' key, and the desk's requests for this game
export CLUBCODERS_LIVE_FILE=/var/lib/robotlab/desk/live.json
export CLUBCODERS_TICKET_KEY=/var/lib/robotlab/desk/ticket_key
export CLUBCODERS_DESK_INBOX="/var/lib/robotlab/desk/inbox/$GAME"

CODE="$APP/games/$FOLDER"
export CLUBCODERS_LIVE_POINTER="/opt/robotlab/live/$FOLDER/current"  # (the server tells the teacher when it changes)
if [ -f "$CLUBCODERS_LIVE_POINTER" ]; then
    LIVE_ID=$(tr -d '[:space:]' < "$CLUBCODERS_LIVE_POINTER")
    if [[ "$LIVE_ID" =~ ^[0-9a-f]{24}$ ]] && [ -f "/opt/robotlab/live/$FOLDER/$LIVE_ID/LIVE_ID" ]; then
        CODE="/opt/robotlab/live/$FOLDER/$LIVE_ID"
        echo "$CLASS runs live update $LIVE_ID of $FOLDER"
    fi
fi
# (CHANGE 168) a live update is tried first (engine/canary.py: its server on a port of this machine only, with data
# of its own, must let a teacher in and send 30 snapshots without an error); one that doesn't, the class runs the
# release's own code instead, and the teacher's live update waits to be fixed
case "$GAME" in
    robotlab) SCRIPT=lab_server.py ;;
    fightlab) SCRIPT=fight_server.py ;;
    kartlab) SCRIPT=kart_server.py ;;
    citylab) SCRIPT=city_server.py ;;
    missions) SCRIPT=missions_server.py ;;
esac
# (the canary logs a teacher in and waits for snapshots: Missions' server sends none, so its class runs a live
# update of Robot Lab's folder unchecked)
if [ "$CODE" != "$APP/games/$FOLDER" ] && [ -f "$APP/engine/canary.py" ] && [ "$GAME" != "missions" ]; then
    if ! (cd "$CODE" && "$PY" "$APP/engine/canary.py" "$SCRIPT" --seconds 20); then
        echo "$CLASS: live update $LIVE_ID of $FOLDER didn't pass its check, so the class runs the release's code" >&2
        export CLUBCODERS_LIVE_FAILED="$LIVE_ID"  # (the server tells the teacher, and doesn't offer it again)
        CODE="$APP/games/$FOLDER"
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
    kartlab)
        mkdir -p "$DATA/kartlab"
        export KARTLAB_DATA="$DATA/kartlab"
        exec "$PY" kart_server.py --class-server --port "$PORT"
        ;;
    citylab)
        mkdir -p "$DATA/citylab"
        export CITYLAB_DATA="$DATA/citylab"
        exec "$PY" city_server.py --class-server --port "$PORT"
        ;;
    missions)
        mkdir -p "$DATA/missions"
        export MISSIONS_DATA="$DATA/missions"
        exec "$PY" missions_server.py --class-server --port "$PORT"
        ;;
esac
