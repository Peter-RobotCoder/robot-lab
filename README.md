# Robot Lab

Robot Lab is the club's robot-building game. Learners design a fighting robot, tune it with numbers, write its brain in Python, and test it in a shared arena with their class and teacher.

## Download (Windows)

1. Go to the [latest release](https://github.com/Peter-RobotCoder/robot-lab/releases/latest) and download **RobotLab-windows.zip**. You don't need a GitHub account.
2. Right-click the zip and choose **Extract All**.
3. Open the **Robot Lab** folder and double-click **Robot Lab.exe**.
   The first time, Windows may say it doesn't recognise the app. Choose **More info**, then **Run anyway**. This happens because the club's own program isn't signed by a big software company. The download comes only from this page.
4. Log in with the **username, password and class code** from your welcome letter.

Nothing needs installing. The game tells you when a new version is out.

Mac and Chromebook aren't supported yet. Ask the club about a loan laptop.

## For parents

- Learners log in with a nickname or first name that the teacher sets up. There's no chat: learners can't message each other.
- The class server is in the UK. It keeps each learner's username, a scrambled (hashed) password, and their robot, missions and reflections. The club's privacy note says how long this is kept and who to ask to delete it.
- This page holds only the game's code. No learner information is ever stored here.

## Checking a download

Each release has a `RobotLab-windows.zip.sha256` file. In PowerShell, `Get-FileHash RobotLab-windows.zip` should print the same value.

## For the teacher

- `release/build_windows.py` builds the zip. Pushing a tag such as `v1.0.0` builds and publishes it automatically; see `.github/workflows/release.yml`.
- `deploy/` sets up and updates the class server on the VPS; see `deploy/README.md`.
- Run `python smoke_test.py` and `python security_test.py` before every release.
