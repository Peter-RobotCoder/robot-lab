#!/usr/bin/env bash
# Club Coders class server: one-time setup for a fresh IONOS VPS running Ubuntu 24.04.
#
#   sudo bash setup.sh play.yourclub.org.uk
#
# What it does: locks down the server (SSH keys only, firewall, fail2ban, automatic security updates),
# installs Caddy (the free, auto-renewing certificate for wss://), downloads the games from GitHub at their
# latest release, makes the class codes, and starts the first class's game server (Robot Lab) and the club desk
# (which tells the Club Coders app which game and class a class code is for), so they run all the time.
# Safe to run again: it keeps the existing codes, classes and learners' data. Run again on a server set up
# before Club Coders (Robot Lab only), it moves it to the newest release and the games/ layout.
set -euo pipefail

REPO="${ROBOTLAB_REPO:-https://github.com/Peter-RobotCoder/robot-lab.git}"
APP=/opt/robotlab/app
VENV=/opt/robotlab/venv
DATA=/var/lib/robotlab
ETC=/etc/robotlab
ENV_FILE=/etc/robotlab.env

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }

# ---------- checks before changing anything ----------
[ "$(id -u)" -eq 0 ] || fail "please run this as root: sudo bash setup.sh play.yourclub.org.uk"
if ! grep -q 'VERSION_ID="24.04"' /etc/os-release 2>/dev/null; then
    echo "Warning: this script was written for Ubuntu 24.04; this machine is: $(. /etc/os-release; echo "$PRETTY_NAME")"
fi

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ] && [ -f "$ETC/domain" ]; then
    DOMAIN=$(cat "$ETC/domain")
fi
if [ -z "$DOMAIN" ]; then
    read -rp "The server's web address (for example play.yourclub.org.uk): " DOMAIN
fi
DOMAIN=$(printf '%s' "$DOMAIN" | tr 'A-Z' 'a-z' | sed 's#^[a-z]*://##; s#/.*$##')
[[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]] \
    || fail "'$DOMAIN' doesn't look like a web address (for example play.yourclub.org.uk)"

# never lock anyone out: SSH will only accept keys, so a key must already be installed
key_found=""
for f in /root/.ssh/authorized_keys ${SUDO_USER:+"/home/$SUDO_USER/.ssh/authorized_keys"}; do
    if [ -s "$f" ] && grep -qE '^(ssh-|ecdsa-|sk-)' "$f"; then
        key_found="$f"
    fi
done
[ -n "$key_found" ] || fail "no SSH key found in /root/.ssh/authorized_keys. Add your laptop's SSH key in the
IONOS panel (or with ssh-copy-id) first, otherwise turning off password logins would lock you out."
echo "SSH key found in $key_found: password logins can safely be turned off."

# ---------- packages ----------
say "Installing updates and the tools the server needs (a few minutes)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -y -q
apt-get install -y -q python3 python3-venv python3-pip git curl gnupg ufw fail2ban python3-systemd \
    unattended-upgrades debian-keyring debian-archive-keyring apt-transport-https ca-certificates

if ! command -v caddy >/dev/null; then
    say "Installing Caddy (it gets and renews the free certificate for $DOMAIN)"
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q
    apt-get install -y -q caddy
fi

# ---------- locking the server down ----------
say "SSH: keys only (no passwords)"
cat > /etc/ssh/sshd_config.d/10-robotlab.conf <<'EOF'
# Robot Lab: log in with an SSH key only (setup.sh). Listed before 50-cloud-init.conf, so these win.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
MaxAuthTries 4
EOF
if ! sshd -t; then
    rm -f /etc/ssh/sshd_config.d/10-robotlab.conf
    fail "the SSH settings didn't check out, so they were removed and SSH wasn't restarted"
fi
systemctl reload ssh 2>/dev/null || systemctl restart ssh 2>/dev/null \
    || echo "Note: SSH couldn't be reloaded; the new settings apply from the next restart."

say "Firewall: only SSH (22) and the web ports (80, 443) are open"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
ufw status | sed 's/^/    /'

say "fail2ban: computers that keep failing to log in over SSH are blocked for an hour"
cat > /etc/fail2ban/jail.d/robotlab-sshd.conf <<'EOF'
[sshd]
enabled = true
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
systemctl enable --now fail2ban >/dev/null
systemctl restart fail2ban

say "Automatic security updates (restarting at 03:30 if an update needs it, never during a lesson)"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52robotlab-unattended <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:30";
EOF
systemctl enable --now unattended-upgrades >/dev/null

say "System logs kept for 30 days at most"
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/robotlab.conf <<'EOF'
[Journal]
MaxRetentionSec=30day
SystemMaxUse=500M
EOF
systemctl restart systemd-journald

# ---------- the game ----------
say "Robot Lab user and folders"
id robotlab >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin robotlab
install -d -m 755 -o root -g root /opt/robotlab
install -d -m 700 -o robotlab -g robotlab "$DATA" "$DATA/class1"
install -d -m 750 -o root -g robotlab "$ETC"
printf '%s\n' "$DOMAIN" > "$ETC/domain"

say "Downloading the games from $REPO"
if [ -d "$APP/.git" ] && [ ! -d "$APP/games" ]; then  # set up before Club Coders: move to the newest release
    echo "This server has the Robot Lab-only version ($(git -C "$APP" describe --tags --always)): moving it to Club Coders."
    git -C "$APP" remote set-url origin "$REPO"
    git -C "$APP" fetch -q --tags --force origin
    TAG=$(git -C "$APP" tag --list 'v*' --sort=-v:refname | head -n1)
    [ -n "$TAG" ] || fail "no release (v* tag) on GitHub yet: publish the Club Coders release first"
    git -C "$APP" -c advice.detachedHead=false checkout -q -f "$TAG"
    [ -d "$APP/games" ] || fail "the newest release ($TAG) is still the Robot Lab-only version: publish the Club Coders release first"
    echo "Using release $TAG"
elif [ -d "$APP/.git" ]; then  # run again: keep the version that's there (robotlab-update changes it)
    echo "The games are already downloaded ($(git -C "$APP" describe --tags --always)); to change version use robotlab-update."
else
    git clone -q "$REPO" "$APP"
    TAG=$(git -C "$APP" tag --list 'v*' --sort=-v:refname | head -n1)
    if [ -n "$TAG" ]; then
        git -C "$APP" -c advice.detachedHead=false checkout -q "$TAG"
        echo "Using release $TAG"
    else
        echo "Warning: the repository has no release yet (no v* tag), so the newest code is used."
    fi
fi
[ -f "$APP/games/robotlab/lab_server.py" ] || fail "games/robotlab/lab_server.py isn't in $REPO: is that the right repository?"
# approved AI changes to the arenas, stages and rules are saved in each game's mods/ folder
for m in "$APP"/games/*/mods; do chown -R robotlab:robotlab "$m"; done

say "Python packages for the server"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP/deploy/requirements-server.txt"

# ---------- class codes ----------
make_code() { python3 -c "import secrets; a='abcdefghjkmnpqrstuvwxyz23456789'; print('-'.join(''.join(secrets.choice(a) for _ in range(4)) for _ in range($1)))"; }
NEW_CODES=""
if [ -f "$ENV_FILE" ] && grep -q '^TEACHER_CODE=' "$ENV_FILE"; then
    say "Class codes already set (kept). To see them: sudo cat $ENV_FILE"
else
    say "Class codes"
    TEACHER_CODE=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
    JOIN_CODE=""
    if [ -t 0 ]; then
        echo "The class code is what learners type once, from their welcome letter."
        read -rp "Choose one (at least 6 letters, numbers or -), or press Enter for a random one: " JOIN_CODE
    fi
    [ -n "$JOIN_CODE" ] || JOIN_CODE=$(make_code 2)
    [[ "$JOIN_CODE" =~ ^[A-Za-z0-9-]{6,40}$ ]] || fail "the class code can only use letters, numbers and -, 6 to 40 of them"
    case "$JOIN_CODE" in CLUB42|TEACH99) fail "the demo codes can't be used on the class server";; esac
    umask 027
    cat > "$ENV_FILE" <<EOF
# Robot Lab class codes (setup.sh). Keep private: never put these in GitHub or an email to the whole class.
JOIN_CODE=$JOIN_CODE
TEACHER_CODE=$TEACHER_CODE
EOF
    umask 022
    NEW_CODES="yes"
fi
chown root:robotlab "$ENV_FILE"
chmod 640 "$ENV_FILE"
if [ ! -f "$ETC/class1.env" ]; then
    printf '# The first class: wss://%s (GAME: robotlab or fightlab; robotlab-add-class changes it)\nPORT=8780\nGAME=robotlab\n' "$DOMAIN" > "$ETC/class1.env"
fi
chown root:robotlab "$ETC/class1.env"
chmod 640 "$ETC/class1.env"

# ---------- services ----------
say "Starting the game server, the club desk, Caddy and the nightly backup"
install -m 644 "$APP/deploy/robotlab@.service" /etc/systemd/system/robotlab@.service
install -m 644 "$APP/deploy/club-desk.service" /etc/systemd/system/club-desk.service
install -d -m 700 -o robotlab -g robotlab /var/lib/robotlab/desk  # (the club desk's learners and groups)
if systemctl is-enabled -q club-door 2>/dev/null; then  # (the front door became the desk)
    systemctl disable -q --now club-door
    rm -f /etc/systemd/system/club-door.service
fi
install -m 644 "$APP/deploy/robotlab-backup.service" /etc/systemd/system/robotlab-backup.service
install -m 644 "$APP/deploy/robotlab-backup.timer" /etc/systemd/system/robotlab-backup.timer
install -m 755 "$APP/deploy/robotlab-backup" /usr/local/bin/robotlab-backup
install -m 755 "$APP/deploy/robotlab-update" /usr/local/bin/robotlab-update
install -m 755 "$APP/deploy/add-class.sh" /usr/local/bin/robotlab-add-class
install -m 755 "$APP/deploy/robotlab-live" /usr/local/bin/robotlab-live
install -d -m 755 -o root -g root /opt/robotlab/live /var/www /var/www/clubcoders-code  # (live code updates)

install -d -m 755 /etc/caddy/robotlab-classes
[ -f /etc/caddy/robotlab-classes/00-note.caddy ] \
    || echo "# extra classes added by robotlab-add-class go in this folder" > /etc/caddy/robotlab-classes/00-note.caddy
sed "s/{{DOMAIN}}/$DOMAIN/g" "$APP/deploy/Caddyfile.template" > /etc/caddy/Caddyfile.new
caddy validate --config /etc/caddy/Caddyfile.new --adapter caddyfile >/dev/null 2>&1 \
    || { caddy validate --config /etc/caddy/Caddyfile.new --adapter caddyfile; fail "the Caddy settings didn't check out"; }
mv /etc/caddy/Caddyfile.new /etc/caddy/Caddyfile

systemctl daemon-reload
systemctl enable -q caddy robotlab@class1 club-desk robotlab-backup.timer
systemctl restart caddy
for unit in $(systemctl list-units 'robotlab@*' --all --plain --no-legend | awk '$1 ~ /^robotlab@/ {print $1}'); do
    systemctl restart "$unit"  # (every class, so a moved server runs the new release everywhere)
done
systemctl restart robotlab@class1
systemctl restart club-desk
systemctl start robotlab-backup.timer

# ---------- check it works ----------
say "Checking"
ok=""
for _ in $(seq 1 20); do
    if systemctl is-active -q robotlab@class1 && timeout 2 bash -c '</dev/tcp/127.0.0.1/8780' 2>/dev/null; then
        ok="yes"
        break
    fi
    sleep 1
done
if [ -n "$ok" ]; then
    echo "The game server is running (port 8780, inside this VPS only)."
else
    echo "The game server isn't answering. Its last messages:"
    journalctl -u robotlab@class1 -n 20 --no-pager
    fail "see the messages above"
fi
systemctl is-active -q caddy && echo "Caddy is running." || fail "Caddy isn't running: journalctl -u caddy -n 30"
door=""
for _ in $(seq 1 10); do
    if timeout 2 bash -c '</dev/tcp/127.0.0.1/8779' 2>/dev/null; then door="yes"; break; fi
    sleep 1
done
[ -n "$door" ] && echo "The club desk is running (logins, learners, groups)." \
    || fail "the club desk isn't answering: journalctl -u club-desk -n 20"
if curl -fsS --max-time 20 "https://$DOMAIN" 2>/dev/null | grep -q "Club Coders server is running"; then
    echo "https://$DOMAIN answers with a padlock."
else
    echo "https://$DOMAIN doesn't answer yet. That's normal if the DNS record for $DOMAIN was only just added"
    echo "(it can take up to an hour). Caddy keeps trying and gets the certificate as soon as the name works."
    echo "Check again later with:  curl https://$DOMAIN"
fi

say "Done"
echo "Club Coders:   wss://$DOMAIN   (built into the downloaded app; class1 plays $(grep -h '^GAME=' "$ETC/class1.env" 2>/dev/null | cut -d= -f2 || echo robotlab))"
if [ -n "$NEW_CODES" ]; then
    echo
    echo "  Teacher code (your laptop only):   $TEACHER_CODE"
    echo
    echo "Write it down now: it is the password for the Teacher screen in the Club Coders app."
    echo "Learners don't get a code: add them (username and starter password) on the Teacher screen."
    echo "It is also in $ENV_FILE on this server (sudo cat $ENV_FILE)."
fi
echo
echo "Useful commands:"
echo "  systemctl status robotlab@class1       is the game server running?"
echo "  journalctl -u robotlab@class1 -f       its messages, live"
echo "  sudo robotlab-update                   install a new release (between lessons, after a snapshot)"
echo "  sudo robotlab-backup                   make a backup now"
echo "  sudo robotlab-add-class class2 --game fightlab   Fight Lab's game server (once)"
echo "  journalctl -u club-desk -f             the club desk's messages, live"
