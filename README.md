# Club Coders

Club Coders is the club's games in one app. Log in with your username and the app opens the game your group is playing today:

- **Robot Lab**: design a fighting robot, tune it with numbers, write its brain in Python, and test it in a shared arena.
- **Fight Lab**: design a fighter, tune its moves, write its brain in Python, and fight your class in the ring.
- **Kart Lab**: design a kart or a sports car, tune it with numbers, write a brain that drives it, and race your class.
- **City Lab**: walk and drive a small open city with your class: deliveries, taxi runs, street races and rogue robots to round up, with the cars, the fighters and the robots from the other games.
- **Craft Lab**: build, dig and survive on an island of blocks with your class, and write the Python that drives your own Craft Bot. On your own, it's on the first screen too: no login.

## Playing

Learners play Club Coders in the browser, on the club's web page: log in with your **username** and **password**. The first time, use the starter password the teacher gave you: you'll be asked to choose your own. Your group's game opens when the teacher has launched the session.

The Windows download (`Club Coders.exe`) was retired on 30 October 2026; its build is kept in `archive/`.

## For parents

- Learners log in with a nickname or first name that the teacher sets up. There's no chat: learners can't message each other.
- The class server is in the UK. It keeps each learner's username, a scrambled (hashed) password, and their designs, missions and reflections. The club's privacy note says how long this is kept and who to ask to delete it.
- This page holds only the games' code. No learner information is ever stored here.

## For the teacher

- `launcher/` is the app's window: learners' login, the Teacher screen (learners, groups, Launch and Stop, the session's notes) and the PDFs made after a session (`records.py`); `desk/` is the club desk on the class server that the app talks to.
- `games/robotlab/`, `games/fightlab/`, `games/kartlab/`, `games/citylab/` and `games/craftlab/` are the games. Each has its own `smoke_test.py` and `security_test.py`: run them before every release.
- `archive/` keeps the retired Windows build (`release/build_windows.py`) and its release workflow; nothing there runs.
- `deploy/` sets up and updates the class server on the VPS, and adds classes playing any of the games; see `deploy/README.md`.
