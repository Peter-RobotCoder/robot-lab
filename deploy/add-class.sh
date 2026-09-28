#!/usr/bin/env bash
# Club Coders: add a class (it runs at the same time as the others, with its own game, arena or ring, accounts,
# data and class code), or move a class to another game.
#
#   sudo robotlab-add-class class2                      a new class playing Robot Lab: wss://<domain>/class2
#   sudo robotlab-add-class class2 --game fightlab      a new class playing Fight Lab
#   sudo robotlab-add-class class3 --game fightlab 8790 (a particular internal port)
#   sudo robotlab-add-class class1 --game fightlab      move a class to another game: learners keep their class
#                                                       code, and the Club Coders app opens the new game next time
#
# The teacher code is shared by every class; the class code isn't. The front door finds each class by its code
# (no restart needed). Accounts belong to the class's game: a class that moves game needs its accounts making in
# the new game too (the old game's data is kept, in case the class moves back).
set -euo pipefail

NAME=""
GAME=""
PORT=""
while [ $# -gt 0 ]; do
    case "$1" in
        --game) GAME="${2:-}"; shift 2 ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) if [ -z "$NAME" ]; then NAME="$1"; else PORT="$1"; fi; shift ;;
    esac
done
NAME="${NAME:-class2}"
ETC=/etc/robotlab
DATA=/var/lib/robotlab

[ "$(id -u)" -eq 0 ] || { echo "Please run this as root: sudo robotlab-add-class $NAME" >&2; exit 1; }
[[ "$NAME" =~ ^class[0-9]{1,2}$ ]] || { echo "Class names are class1, class2 ... (not '$NAME')." >&2; exit 1; }
[ -z "$GAME" ] || [[ "$GAME" =~ ^(robotlab|fightlab)$ ]] || { echo "The game can be robotlab or fightlab (not '$GAME')." >&2; exit 1; }
[ -f "$ETC/domain" ] || { echo "Run setup.sh first." >&2; exit 1; }
DOMAIN=$(cat "$ETC/domain")
ADDRESS="wss://$DOMAIN/$NAME"
[ "$NAME" != "class1" ] || ADDRESS="wss://$DOMAIN"
title() { [ "$1" = "fightlab" ] && echo "Fight Lab" || echo "Robot Lab"; }

# ---------- an existing class: change its game ----------
if [ -f "$ETC/$NAME.env" ]; then
    NOW=$(grep -h '^GAME=' "$ETC/$NAME.env" | cut -d= -f2)
    NOW="${NOW:-robotlab}"
    if [ -z "$GAME" ] || [ "$GAME" = "$NOW" ]; then
        echo "$NAME already exists and plays $(title "$NOW") (to move it: sudo robotlab-add-class $NAME --game fightlab)."
        exit 0
    fi
    if grep -q '^GAME=' "$ETC/$NAME.env"; then
        sed -i "s/^GAME=.*/GAME=$GAME/" "$ETC/$NAME.env"
    else
        echo "GAME=$GAME" >> "$ETC/$NAME.env"
    fi
    systemctl restart "robotlab@$NAME"
    sleep 3
    systemctl is-active -q "robotlab@$NAME" || { journalctl -u "robotlab@$NAME" -n 15 --no-pager; exit 1; }
    echo "$NAME now plays $(title "$GAME") at $ADDRESS. Learners keep their class code: the Club Coders app"
    echo "opens $(title "$GAME") from now on. Make their accounts in $(title "$GAME")'s Accounts tab."
    exit 0
fi
[ "$NAME" != "class1" ] || { echo "class1 is the first class, made by setup.sh." >&2; exit 1; }

# ---------- a new class ----------
GAME="${GAME:-robotlab}"
if [ -z "$PORT" ]; then
    PORT=$((8779 + ${NAME#class}))
fi
[[ "$PORT" =~ ^[0-9]+$ ]] && [ "$PORT" -ge 8781 ] && [ "$PORT" -le 8899 ] \
    || { echo "The port must be a number from 8781 to 8899." >&2; exit 1; }
for f in "$ETC"/class*.env; do
    [ -e "$f" ] || continue
    if grep -qx "PORT=$PORT" "$f"; then
        echo "Port $PORT is already used by $(basename "$f" .env)." >&2
        exit 1
    fi
done

install -d -m 700 -o robotlab -g robotlab "$DATA/$NAME"
CODE=$(python3 -c "import secrets; a='abcdefghjkmnpqrstuvwxyz23456789'; print('-'.join(''.join(secrets.choice(a) for _ in range(4)) for _ in range(2)))")
umask 027
cat > "$ETC/$NAME.env" <<EOF
# $NAME: $ADDRESS (robotlab-add-class). Its game (robotlab or fightlab) and its own class code;
# the teacher code is shared.
PORT=$PORT
GAME=$GAME
JOIN_CODE=$CODE
EOF
umask 022
chown root:robotlab "$ETC/$NAME.env"
chmod 640 "$ETC/$NAME.env"

cat > "/etc/caddy/robotlab-classes/$NAME.caddy" <<EOF
# $NAME (robotlab-add-class)
@$NAME {
	path /$NAME /$NAME/*
	header_regexp Upgrade (?i)^websocket$
}
handle @$NAME {
	reverse_proxy 127.0.0.1:$PORT
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || {
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile || true
    rm -f "/etc/caddy/robotlab-classes/$NAME.caddy" "$ETC/$NAME.env"
    echo "The Caddy settings didn't check out, so $NAME wasn't added." >&2
    exit 1
}
systemctl reload caddy
systemctl enable -q --now "robotlab@$NAME"
sleep 3
if systemctl is-active -q "robotlab@$NAME"; then
    echo "$NAME is running $(title "$GAME") at $ADDRESS"
else
    journalctl -u "robotlab@$NAME" -n 15 --no-pager
    echo "$NAME didn't start: see the messages above." >&2
    exit 1
fi
echo
echo "  Class code for $NAME (for its learners' welcome letters):   $CODE"
echo
echo "Learners type it in the Club Coders app, which opens $(title "$GAME") for them."
echo "Your teacher window for $NAME: in the $(title "$GAME") folder, teacher_settings.json with"
echo "  {\"server\": \"$ADDRESS\", \"teacher_code\": \"<the teacher code: sudo cat /etc/robotlab.env>\"}"
