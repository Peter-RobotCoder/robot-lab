# Club Coders

Club Coders is the club's games in one app. Log in with your username and the app opens the game your group is playing today:

- **Robot Lab**: design a fighting robot, tune it with numbers, write its brain in Python, and test it in a shared arena.
- **Fight Lab**: design a fighter, tune its moves, write its brain in Python, and fight your class in the ring.

## Download (Windows)

1. Go to the [latest release](https://github.com/Peter-RobotCoder/robot-lab/releases/latest) and download **ClubCoders-windows.zip**. You don't need a GitHub account.
2. Right-click the zip and choose **Extract All**.
3. Open the **Club Coders** folder and double-click **Club Coders.exe**.
   The first time, Windows may say it doesn't recognise the app. Choose **More info**, then **Run anyway**. This happens because the club's own program isn't signed by a big software company. The download comes only from this page.
4. Type your **username** and **password** and press **Log in**. The first time, use the starter password the teacher gave you: the app asks you to choose your own. Your group's game opens when the teacher has launched the session; until then the app waits and says so.

Nothing needs installing. The app tells you when a new version is out.

From the lesson where you write your robot's or fighter's brain, it's in the `brains` folder next to `Club Coders.exe`: `brains\robotlab\my_brain.py` for Robot Lab, `brains\fightlab\my_brain.py` for Fight Lab. Open it with Notepad, then press **U** in the game to upload it.

Mac and Chromebook aren't supported yet. Ask the club about a loan laptop.

## For parents

- Learners log in with a nickname or first name that the teacher sets up. There's no chat: learners can't message each other.
- The class server is in the UK. It keeps each learner's username, a scrambled (hashed) password, and their designs, missions and reflections. The club's privacy note says how long this is kept and who to ask to delete it.
- This page holds only the games' code. No learner information is ever stored here.

## Checking a download

Each release has a `ClubCoders-windows.zip.sha256` file. In PowerShell, `Get-FileHash ClubCoders-windows.zip` should print the same value.

## For the teacher

- `launcher/` is the app's window: learners' login, the Teacher screen (learners, groups, Launch and Stop, the session's notes) and the PDFs made after a session (`records.py`); `desk/` is the club desk on the class server that the app talks to.
- `games/robotlab/` and `games/fightlab/` are the games. Each has its own `smoke_test.py` and `security_test.py`: run them before every release.
- `release/build_windows.py` builds the zip. Pushing a tag such as `v1.1.0` (it must match `VERSION`) builds and publishes it; see `.github/workflows/release.yml`.
- `deploy/` sets up and updates the class server on the VPS, and adds classes playing either game; see `deploy/README.md`.
