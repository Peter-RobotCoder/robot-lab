# Club Coders class server: setting up the IONOS VPS

This folder turns a fresh IONOS VPS (Ubuntu 24.04) into the always-on class server at `wss://play.<club domain>`. Each class runs one of the club's games (Robot Lab or Fight Lab). Learners use one app, **Club Coders**: they type their class code, and the server's front door tells the app which game and class it is for.

## What the kit does

| File | What it does |
| --- | --- |
| `setup.sh` | One-time setup. It turns on SSH keys only, the firewall (ports 22, 80 and 443), fail2ban, automatic security updates and 30-day log retention. It then installs Caddy for the free certificate, downloads the latest release, makes the class codes, and starts the first class (Robot Lab) and the front door. Run again on a server set up before Club Coders, it moves it to the new release and layout, keeping codes and data. |
| `robotlab@.service` + `run-class.sh` | Runs each class's game server all the time as the unprivileged `robotlab` user, and restarts it if it stops. The class's game is `GAME=` in `/etc/robotlab/<class>.env`. |
| `club-door.service` | The front door (`door/club_door.py`): answers "which game and class is this class code for?". |
| `Caddyfile.template` | Sends `wss://` traffic to the classes and the front door. A browser visit to the address shows "Club Coders server is running". No access log is kept. |
| `add-class.sh` | Adds a class playing either game (`wss://play.<club domain>/class2`), or moves a class to another game. |
| `robotlab-update` | Installs a new release between lessons, after you've taken a snapshot. |
| `robotlab-backup`, plus the `.timer` | Nightly backup at 02:30 to `/var/backups/robotlab`, readable by root only and kept 14 days. |
| `requirements-server.txt` | The Python packages the servers need. |

The server keeps learners' data per class in `/var/lib/robotlab/<class>/` (Fight Lab's in `/var/lib/robotlab/<class>/fightlab/`): profiles, evidence and AI cards. Learners' robots and fighters are in each game's `mods/` folder under `/opt/robotlab/app/games/`. The class codes are in `/etc/robotlab.env` (the first class and the shared teacher code) and `/etc/robotlab/<class>.env`, readable only by root and the game servers.

## Before you start

1. In the IONOS panel, order a VPS M+ (or S+) with **Ubuntu 24.04** in a **UK data centre**, and add your laptop's SSH key.
2. In the IONOS firewall for the VPS, allow **22, 80 and 443** only.
3. In IONOS DNS for the club domain, add an **A record**: host `play`, pointing to the VPS's IPv4 address.

## Set it up (about 10 minutes)

From your laptop: `ssh robotlab` (or `ssh root@<VPS IP>`). Then, on the VPS:

```
curl -fsSLO https://raw.githubusercontent.com/Peter-RobotCoder/robot-lab/main/deploy/setup.sh
sudo bash setup.sh play.<club domain>
```

At the end, the script prints the first class's **class code** (for welcome letters) and the **teacher code**. Put the teacher line in `teacher_settings.json` next to `lab_client.py` on your laptop. Never put it in GitHub.

To check it's working, open `https://play.<club domain>` in any browser. You should see a padlock and the words "Club Coders server is running".

## Moving a Robot Lab-only server to Club Coders

After the first Club Coders release is on GitHub, run the two setup commands above again. The script sees the old layout, installs the newest release, adds the front door and restarts every class. Class codes, accounts and learners' data are kept. (Use `setup.sh` for this move, not `robotlab-update`: the old update tool doesn't know the new layout.)

## Classes and games

| Command (on the VPS) | What it does |
| --- | --- |
| `sudo robotlab-add-class class2 --game fightlab` | A new class playing Fight Lab, with its own class code (printed) |
| `sudo robotlab-add-class class3` | A new class playing Robot Lab |
| `sudo robotlab-add-class class1 --game fightlab` | Move a class to another game. Learners keep their class code; the app opens the new game next time |

Accounts belong to the class's game: after moving a class, make its learners' accounts in the new game's **Accounts** tab. The old game's data is kept, in case the class moves back.

Your teacher window for a class: in that game's folder on your laptop, `teacher_settings.json` with `{"server": "wss://play.<club domain>/class2", "teacher_code": "..."}` (class1 is `wss://play.<club domain>`). Then open the game's "teacher (class server)" launcher.

## Every week: copy the backup to your laptop

Backups are children's data. Keep them on the VPS and on your encrypted laptop only. From your laptop:

```
scp robotlab:/var/backups/robotlab/latest.tar.gz robotlab-backup.tar.gz
```

Delete old copies from the laptop when the course's deletion date comes.

## Installing a new release

After publishing a release on GitHub, do this between lessons:

1. IONOS panel → your VPS → **Snapshots** → take a snapshot.
2. `ssh robotlab`, then `sudo robotlab-update`. To go back to an older version, use `sudo robotlab-update v1.1.0`.

Learners whose download is older than the server are told to get the new version when they log in.

## Useful commands (on the VPS)

| Command | What it does |
| --- | --- |
| `systemctl status robotlab@class1` | Is the first class's game server running? |
| `journalctl -u robotlab@class1 -f` | Show its messages, live |
| `systemctl status club-door` | Is the front door running? |
| `grep -h GAME /etc/robotlab/*.env` | Which game each class plays |
| `sudo robotlab-backup` | Make a backup now |
| `sudo cat /etc/robotlab.env /etc/robotlab/*.env` | Show the class codes and the teacher code |

To change a code, edit the class's file with `sudo nano /etc/robotlab/class2.env` (the first class's code is in `/etc/robotlab.env`), then run `sudo systemctl restart robotlab@class2`. The class code must be at least 6 characters and the teacher code at least 16. Neither can be `CLUB42` or `TEACH99`.
