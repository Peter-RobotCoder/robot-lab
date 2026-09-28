#!/usr/bin/env bash
# Robot Lab: run a second class at the same time, with its own arena, accounts, data and class code.
#
#   sudo robotlab-add-class class2          wss://<domain>/class2 on internal port 8781
#   sudo robotlab-add-class class3 8782
#
# Each class has up to 4 learners and the teacher. The teacher code is shared; the class code isn't.
# One VPS S+ (1 CPU) is enough for one class; for several at once, move up to VPS M+ (2 CPUs, 4 GB).
set -euo pipefail

NAME="${1:-class2}"
PORT="${2:-}"
ETC=/etc/robotlab
DATA=/var/lib/robotlab

[ "$(id -u)" -eq 0 ] || { echo "Please run this as root: sudo robotlab-add-class $NAME" >&2; exit 1; }
[[ "$NAME" =~ ^class[0-9]{1,2}$ ]] || { echo "Class names are class2, class3 ... (not '$NAME')." >&2; exit 1; }
[ "$NAME" != "class1" ] || { echo "class1 is the first class, made by setup.sh." >&2; exit 1; }
[ -f "$ETC/domain" ] || { echo "Run setup.sh first." >&2; exit 1; }
DOMAIN=$(cat "$ETC/domain")
if [ -z "$PORT" ]; then
    PORT=$((8779 + ${NAME#class}))
fi
[[ "$PORT" =~ ^[0-9]+$ ]] && [ "$PORT" -ge 8781 ] && [ "$PORT" -le 8899 ] \
    || { echo "The port must be a number from 8781 to 8899." >&2; exit 1; }
for f in "$ETC"/class*.env; do
    [ -e "$f" ] || continue
    if [ "$f" != "$ETC/$NAME.env" ] && grep -qx "PORT=$PORT" "$f"; then
        echo "Port $PORT is already used by $(basename "$f" .env)." >&2
        exit 1
    fi
done

install -d -m 700 -o robotlab -g robotlab "$DATA/$NAME"
if [ -f "$ETC/$NAME.env" ]; then
    echo "$NAME already exists: keeping its class code (sudo cat $ETC/$NAME.env)."
    CODE=""
else
    CODE=$(python3 -c "import secrets; a='abcdefghjkmnpqrstuvwxyz23456789'; print('-'.join(''.join(secrets.choice(a) for _ in range(4)) for _ in range(2)))")
    umask 027
    cat > "$ETC/$NAME.env" <<EOF
# $NAME: wss://$DOMAIN/$NAME (robotlab-add-class). Its own class code; the teacher code is shared.
PORT=$PORT
JOIN_CODE=$CODE
EOF
    umask 022
fi
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
    rm -f "/etc/caddy/robotlab-classes/$NAME.caddy"
    echo "The Caddy settings didn't check out, so $NAME wasn't added." >&2
    exit 1
}
systemctl reload caddy
systemctl enable -q --now "robotlab@$NAME"
sleep 3
if systemctl is-active -q "robotlab@$NAME"; then
    echo "$NAME is running at wss://$DOMAIN/$NAME"
else
    journalctl -u "robotlab@$NAME" -n 15 --no-pager
    echo "$NAME didn't start: see the messages above." >&2
    exit 1
fi
if [ -n "$CODE" ]; then
    echo "Class code for $NAME: $CODE   (the teacher code is the same as class1's)"
fi
echo "Learners in $NAME need the game started with:  --host wss://$DOMAIN/$NAME"
