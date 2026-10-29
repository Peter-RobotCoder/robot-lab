"""Missions' lessons, missions and learning outcomes (CHANGE 195): what the club desk, the session records and the
Missions class server (missions_server.py) read for the story missions (lab_missions.STORY_MISSIONS: Mission 1
"Wake-Up Call", Mission 2 "Lights Out").

A lesson is one story mission. Its objectives here are checked by the class server from what each learner's
window reports (a run finished, the stars it earned), and saved as evidence against the outcomes below, as the
other games' lesson files are. Plain data, read by the desk's scheme() and launcher/records.py.
"""

# ---------- learning outcomes ----------
# code: (short name, what the learner can do, curriculum references)
OUTCOMES = {
    "SEQ": ("Sequence", "Write a sequence of instructions that reaches a goal",
            "England KS2/KS3: design, write and debug programs that accomplish specific goals | OCR J277 2.2.1 "
            "sequence | AQA 8525 3.2.2 | Scotland TCH 2-15a | Wales PS3 sequence"),
    "ALG": ("Algorithms and decomposition", "Break a task into steps and plan a route that fits a constraint",
            "England KS3: key algorithms, computational thinking | OCR J277 2.1.1 decomposition, 2.1.2 | "
            "AQA 8525 3.1.1 | Scotland TCH 4-13b | Wales PS4 decompose problems"),
    "VAR": ("Variables", "Use a variable to count and keep track of something as a program runs",
            "England KS3: use 2 or more programming languages, at least one textual | OCR J277 2.2.1 variables "
            "and assignment | AQA 8525 3.2.2 | Wales PS4"),
    "SEL": ("Selection", "Use if and else so the same program copes with different situations",
            "England KS3: simple Boolean logic | OCR J277 2.2.1 selection | AQA 8525 3.2.2, 3.2.5 | "
            "Wales PS3 conditional statements"),
    "TEST": ("Testing and debugging", "Run a program, read what went wrong and fix it",
             "England KS3: detect and correct errors in algorithms and programs | OCR J277 2.3.1 defensive design, "
             "2.3.2 testing | AQA 8525 3.2.11 | Scotland TCH 3-15a"),
    "EVAL": ("Efficiency and evaluation", "Make a program shorter or more efficient and say why it is better",
             "England KS3: evaluate the design of programs | OCR J277 2.1.1 | AQA 8525 3.1.2 efficiency | "
             "Wales PS4 evaluate"),
}

# ---------- lessons ----------
# each lesson is one story mission (lab_missions.STORY_MISSIONS); the number is the mission's number
LESSONS = {
    1: dict(title="Mission 1: Wake-Up Call (sequence)", mission="wake_up_call"),
    2: dict(title="Mission 2: Lights Out (if / else and variables)", mission="lights_out"),
}
LESSON_MISSIONS = {n: lesson["mission"] for n, lesson in LESSONS.items()}
MISSION_LESSONS = {mid: n for n, mid in LESSON_MISSIONS.items()}

LESSON_TASKS = {
    1: "Your robot has crash-landed above Brookfield with a nearly flat battery. In pseudo code (shown as Python "
       "beside it) recharge it, pick up a tool, clear the rockfall, reach the village and repair its power supply. "
       "Every move costs energy: plan the route first.",
    2: "Night on the hill road: rocks have come down and lamps are out, in different places each of three nights. "
       "One program has to work on all three, so it looks with if and else, counts the lamps it repairs in a "
       "variable and reports the count at the mast.",
}

# ---------- missions ----------
# id: (lesson, title, what to do, outcome codes, how it is checked)
MISSIONS = {
    "1a": (1, "Reach Brookfield", "Write a program that recharges the robot, picks up a tool, clears the rockfall and "
                                 "repairs the village's power supply (the mission's done card).", ["SEQ", "ALG"], "auto"),
    "1b": (1, "Energy to spare", "Finish with the energy star: plan a route that leaves 5 or more energy.",
           ["ALG", "EVAL"], "auto"),
    "1c": (1, "A short program", "Finish with the lines star: 15 lines or fewer (repeat helps).", ["EVAL", "SEQ"], "auto"),
    "1d": (1, "Fix a run that failed", "A run that stopped (a flat battery, a bump) and then a run that finished: "
                                      "read the log, change the program and try again.", ["TEST"], "auto"),
    "1e": (1, "Explain the route", "Explain to the group why your route is the one you chose.", ["ALG"], "teacher"),
    "2a": (2, "Three nights", "One program that clears the rocks, repairs the dark lamps and reports the count at the "
                             "mast on all three nights.", ["SEL", "VAR", "SEQ"], "auto"),
    "2b": (2, "Energy to spare", "Finish with the energy star: 5 or more energy left every night (an if that only "
                                "repairs a dark lamp saves it).", ["SEL", "EVAL"], "auto"),
    "2c": (2, "A short program", "Finish with the lines star: 15 lines or fewer.", ["EVAL"], "auto"),
    "2d": (2, "Fix a run that failed", "A run that failed on night 2 or 3, then one that finished all three.",
           ["TEST", "SEL"], "auto"),
    "2e": (2, "Explain the if", "Explain to the group what your if / else looks at and why.", ["SEL"], "teacher"),
}
REFLECTIONS = {}


def missions_for(lesson):
    return {k: v for k, v in MISSIONS.items() if v[0] == lesson}
