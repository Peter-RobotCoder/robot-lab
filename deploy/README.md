# Robot Lab class server: setting up the IONOS VPS

This folder turns a fresh IONOS VPS (Ubuntu 24.04) into the always-on Robot Lab arena at `wss://play.<club domain>`.

## What the kit does

| File | What it does |
| --- | --- |
| `setup.sh` | One-time setup. It turns on SSH keys only, the firewall (ports 22, 80 and 443), fail2ban, automatic security updates and 30-day log retention. It then installs Caddy for the free certificate, downloads the latest release, makes the class codes, and starts the server. |
| `robotlab@.service` | Runs the game server all the time as the unprivileged `robotlab` user, and restarts it if it stops. One copy runs per class. |
| `Caddyfile.template` | Sends `wss://` game traffic to the server. A browser visit to the address shows "Robot Lab server is running". No access log is kept. |
| `robotlab-update` | Installs a new release between lessons, after you've taken a snapshot. |
| `robotlab-backup`, plus the `.timer` | Nightly backup at 02:30 to `/var/backups/robotlab`, readable by root only and kept 14 days. |
| `add-class.sh` | Adds a second class at the same time (`wss://play.<club domain>/class2`). |
| `requirements-server.txt` | The Python packages the server needs. |

The server keeps learners' data in `/var/lib/robotlab/<class>/`: profiles, evidence and AI cards. Learners' robots are in `/opt/robotlab/app/mods/robots/`. The class codes are in `/etc/robotlab.env` and are readable only by root and the game server.

## Before you start

1. In the IONOS panel, order a VPS M+ (or S+) with **Ubuntu 24.04** in a **UK data centre**, and add your laptop's SSH key during ordering.
2. In the IONOS firewall for the VPS, allow **22, 80 and 443** only.
3. In IONOS DNS for the club domain, add an **A record**: host `play`, pointing to the VPS's IPv4 address.

## Set it up (about 10 minutes)

From your laptop, in PowerShell or Terminal (use the VPS's IP address from the IONOS panel):

```
ssh root@<VPS IP>
```

Then, on the VPS:

```
curl -fsSLO https://raw.githubusercontent.com/Peter-RobotCoder/robot-lab/main/deploy/setup.sh
sudo bash setup.sh play.<club domain>
```

At the end, the script prints the **class code** (for welcome letters) and the **teacher code**. Put the teacher code in `teacher_settings.json` next to `lab_client.py` on your laptop, like this: `{"teacher_code": "..."}`. Never put it in GitHub.

To check it's working, open `https://play.<club domain>` in any browser. You should see a padlock and the words "Robot Lab server is running". If you only just added the DNS record, it can take up to an hour.

## Every week: copy the backup to your laptop

Backups are children's data. Keep them on the VPS and on your encrypted laptop only. From your laptop:

```
scp root@<VPS IP>:/var/backups/robotlab/latest.tar.gz robotlab-backup.tar.gz
```

Delete old copies from the laptop when the course's deletion date comes.

## Installing a new release

After publishing a release on GitHub, do this between lessons:

1. IONOS panel → your VPS → **Snapshots** → take a snapshot.
2. `ssh root@<VPS IP>`, then `sudo robotlab-update`. To go back to an older version, use `sudo robotlab-update v1.0.0`.

Learners whose download is older than the server are told to get the new version when they log in.

## Useful commands (on the VPS)

| Command | What it does |
| --- | --- |
| `systemctl status robotlab@class1` | Is the game server running? |
| `journalctl -u robotlab@class1 -f` | Show its messages, live |
| `sudo robotlab-backup` | Make a backup now |
| `sudo robotlab-add-class class2` | Add a second class, with its own class code |
| `sudo cat /etc/robotlab.env` | Show the class and teacher codes |

To change a code, edit `/etc/robotlab.env` with `sudo nano /etc/robotlab.env`, then run `sudo systemctl restart robotlab@class1`. The class code must be at least 6 characters and the teacher code at least 16. Neither can be `CLUB42` or `TEACH99`.
