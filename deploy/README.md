# Club Coders class server: setting up the IONOS VPS

This folder turns a fresh IONOS VPS (Ubuntu 24.04) into the always-on class server at `wss://play.<club domain>`. Each of the club's games (Robot Lab, Fight Lab) has one game server. Learners use one app, **Club Coders**, and log in with a username and password: the server's club desk sends them to the game their launched group is playing. The teacher logs in to the same app to manage learners and groups, and to launch and stop a group.

## What the kit does

| File | What it does |
| --- | --- |
| `setup.sh` | One-time setup. It turns on SSH keys only, the firewall (ports 22, 80 and 443), fail2ban, automatic security updates and 30-day log retention. It then installs Caddy for the free certificate, downloads the latest release, makes the teacher code, and starts the first game server (Robot Lab) and the club desk. Run again on a server set up before the desk, it moves it to the new release and layout, keeping the code and the data. |
| `robotlab@.service` + `run-class.sh` | Runs each class's game server all the time as the unprivileged `robotlab` user, and restarts it if it stops. The class's game is `GAME=` in `/etc/robotlab/<class>.env`. |
| `club-desk.service` | The club desk (`desk/club_desk.py`): the learners (usernames, scrambled passwords), the groups, the live session and every login. Its data is in `/var/lib/robotlab/desk`. |
| `Caddyfile.template` | Sends `wss://` traffic to the games and the desk. A browser visit to the address shows "Club Coders server is running". No access log is kept. |
| `add-class.sh` | Adds a game server (`wss://play.<club domain>/class2`): one per game is all the desk needs. |
| `robotlab-update` | Installs a new release between lessons, after you've taken a snapshot. |
| `robotlab-backup`, plus the `.timer` | Nightly backup at 02:30 to `/var/backups/robotlab`, readable by root only and kept 14 days. |
| `requirements-server.txt` | The Python packages the servers need. |

The server keeps learners' data per class in `/var/lib/robotlab/<class>/` (Fight Lab's in `/var/lib/robotlab/<class>/fightlab/`): profiles, evidence and AI cards. Learners' robots and fighters are in each game's `mods/` folder under `/opt/robotlab/app/games/`. The teacher code is in `/etc/robotlab.env`, readable only by root, the desk and the game servers. The desk's records (usernames, scrambled passwords, groups, session records with notes) are in `/var/lib/robotlab/desk`, readable only by the desk.

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

At the end, the script prints the **teacher code**: it is the teacher password for the Club Coders app's Teacher screen. Never put it in GitHub, and never give it to a learner. Learners don't get a code: they log in with a username and password that you make on the Teacher screen.

To check it's working, open `https://play.<club domain>` in any browser. You should see a padlock and the words "Club Coders server is running".

## Moving an older server to the club desk

For a server set up before release 1.4.0: take a snapshot, `ssh robotlab`, then `sudo robotlab-update` followed by `sudo bash /opt/robotlab/app/deploy/setup.sh play.<club domain>`. The script sees the old layout, installs the club desk in place of the old front door and restarts every game server. The teacher code and learners' game data are kept. Then add the learners and groups on the Teacher screen: the old class codes and the learners' old game accounts are no longer used to log in (a learner keeps their designs and missions if their desk username is the one they used in the game).

## Learners, groups and sessions

Everything day to day is done in the Club Coders app's **Teacher** screen (your teacher password): add learners (username and a starter password), reset or remove them, make groups (a name, a game, the learners in it), and **Launch** a group on a lesson. Launch opens your teacher window in that game; only the launched group's learners can log in, and **Stop** ends the session. While it runs, the screen shows who is here and what they've completed, with a note field per learner. After Stop the app offers the session's PDFs (a card per learner, the session summary) into `Documents\Club Coders records` on your laptop; **Records** lists past sessions and prints the scheme of work. Nothing on the server needs touching for any of this.

## Game servers

Each game has one server; groups take turns on it (one group is live at a time). `setup.sh` starts Robot Lab's (`class1`). Fight Lab's is added once:

| Command (on the VPS) | What it does |
| --- | --- |
| `sudo robotlab-add-class class2 --game fightlab` | Fight Lab's game server (`wss://play.<club domain>/class2`); the desk finds it by its `GAME=` |

The desk uses the first server it finds for each game, so there's no need for more. (The per-class code these commands print is unused now.)

## Live code updates (no new download)

A kept AI change to a game's code can go live without a new release:

1. On your laptop, review the change (Changes tab), try it on the laptop windows, then double-click **`club-coders\Make my changes live.bat`** and choose the game. It lists every changed file and every new risky line, asks you to confirm you've reviewed them, signs the update with your key (its passphrase), tests it, and sends it over `ssh robotlab`.
2. Nothing changes for learners yet. Your teacher window says an update is ready. Warn the class, then press **Restart server** (Controls): everyone gets a 10-second warning, and their game reopens with the new code. Each learner's app checks your signature before running it.

| Command (on the VPS) | What it does |
| --- | --- |
| `sudo robotlab-live status` | Which code each class runs, and which update is waiting |
| `sudo robotlab-live back fightlab` | Go back to the previous update (or the release's code); then Restart server |

The signing key is made once with `live\make_live.py --new-key` and lives only on your laptop, locked with its passphrase. If it might have leaked, make a new key (`--new-key --replace-key`) and a new release: the server only lets in the newest app, so the old key stops working for everyone. A new release (`robotlab-update`) includes the live changes made before it, once they're committed, and deletes the old live updates from the server.

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
| `systemctl status club-desk` | Is the club desk running? |
| `grep -h GAME /etc/robotlab/*.env` | Which game each class plays |
| `sudo robotlab-backup` | Make a backup now |
| `sudo cat /etc/robotlab.env` | Show the teacher code |
| `journalctl -u club-desk -f` | The desk's messages, live (logins, launches, stops) |

To change the teacher code, edit `/etc/robotlab.env` with `sudo nano`, then `sudo systemctl restart club-desk 'robotlab@*'`. It must be at least 16 characters and not `TEACH99`. A forgotten learner password is reset on the Teacher screen, not here.
