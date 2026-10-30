"""Kart Lab lessons, missions and learning outcomes (Robot Lab's course, for karts).

Each lesson switches on the right garage tools and track features and gives learners missions.
Missions are checked by the server from what learners actually do (a design that was built,
a prediction then a timed lap, a brain that runs), and every tick is saved as evidence
against the learning outcomes below. Curriculum references live in OUTCOMES so a teacher
can see which part of the curriculum a mission covers. The teacher can re-word any mission
(and add or hide them) in the HUD's Outcomes tab: engine.teaching keeps those edits.
"""
import ast
import re

# ---------- learning outcomes ----------
# code: (short name, what the learner can do, curriculum references)
OUTCOMES = {
    "VAR": ("Variables", "Use variables and assignment to change how a program behaves",
            "England KS3: use 2 or more programming languages, at least one textual | OCR J277 2.2.1 variables, "
            "constants, operators, inputs, outputs and assignments | AQA 8525 3.2.2 | Wales PS4"),
    "DATA": ("Data types and structures", "Use text, whole numbers, lists and dictionaries",
             "England KS3: make appropriate use of data structures (lists, tables or arrays) | OCR J277 2.2 | "
             "AQA 8525 3.2.6 data structures | Scotland TCH 4-14a"),
    "ABS": ("Abstraction and modelling", "Explain how the game models a real kart's physics with a few numbers",
            "England KS3: computational abstractions that model the state and behaviour of real-world problems and "
            "physical systems | OCR J277 2.1.1 abstraction | AQA 8525 3.1.1 | Scotland TCH 3-13b"),
    "ALG": ("Algorithms and decomposition", "Break a problem into steps and choose values that meet a constraint",
            "England KS3: key algorithms, computational thinking | OCR J277 2.1.1 decomposition, 2.1.2 | "
            "AQA 8525 3.1.1 | Scotland TCH 4-13b | Wales PS4 decompose problems"),
    "SEL": ("Selection and Boolean logic", "Use if / elif / else and conditions with and, or, not",
            "England KS3: simple Boolean logic (AND, OR, NOT) | OCR J277 2.2.1 selection, Boolean operators | "
            "AQA 8525 3.2.2, 3.2.5 | Wales PS3 conditional statements"),
    "FUNC": ("Functions", "Write and call your own functions",
             "England KS3: modular programs that use procedures or functions | OCR J277 2.2.3 sub programs | "
             "AQA 8525 3.2.10 | Scotland TCH 4-14a"),
    "VALID": ("Robust programs", "Explain input validation and test with normal, boundary and invalid data",
              "OCR J277 2.3.1 input validation, 2.3.2 normal, boundary and invalid test data | AQA 8525 3.2.11 | "
              "Scotland N5 input validation; normal, extreme and exceptional test data"),
    "TEST": ("Testing and evaluation", "Predict, test, compare results and improve a design",
             "England KS3: create, reuse, revise and repurpose digital artefacts | OCR J277 2.3.2 testing and "
             "refining | AQA 8525 3.2.11 | Scotland TCH 3-15a | Wales PS4 test strategies"),
    "AISAFE": ("Safe use of AI", "Write an AI request with no personal information and clear limits",
               "England KS3: use technology safely, respectfully, responsibly and securely, protecting online identity "
               "and privacy | KS4: how changes in technology affect safety | DfE: no personal data in generative AI "
               "tools | Wales: legal, social and ethical consequences"),
    "AIREVIEW": ("Checking AI code", "Check AI-written code does what was asked, test it, explain it and say where AI helped",
                 "DfE: AI content needs critical judgement to check accuracy | JCQ: verify and acknowledge AI use "
                 "(tool and date) | Curriculum and Assessment Review 2025: use AI effectively without becoming dependent"),
    "EVAL": ("Evaluate and reflect", "Evaluate a design against evidence and say what to change next",
             "England KS3: attention to trustworthiness, design and usability | OCR J277 2.3.2 refining | "
             "Scotland TCH 4-15a evaluate and refine | N5 evaluation"),
}

# ---------- lessons ----------
# the learner's garage: what is shown and changeable (the kart's three points, its name and colour, the code view
# and the stats readout; "cpu_karts" puts computer karts in the race and "brains" lets learners upload a brain)
ALL_TOOLS = ["points_table", "speed", "acceleration", "grip", "name_and_colour", "code_view", "stats_readout"]
NO_HAZARDS = {"bumping": False, "cpu_karts": False}  # (the track's features: karts pushing each other, and
#                                                        computer karts on the grid; dash pads and oil are in the
#                                                        track itself, which every window must step identically)


def tools(*on):
    t = {k: k in on for k in ALL_TOOLS + ["cpu_karts", "brains"]}  # (computer karts in the race, and brains
    #                                                                 (U and P): the teacher turns them on)
    return t


def hazards(*on):
    return {k: k in on for k in NO_HAZARDS}


LESSONS = {
    1: dict(title="Variables: tune your kart", mode="practice", hazards=hazards(),
            tools=tools("speed", "acceleration", "grip", "name_and_colour", "code_view", "stats_readout")),
    2: dict(title="Trade-offs and robust programs: the 100-point budget", mode="practice",
            hazards=hazards("bumping", "cpu_karts"), tools=tools(*ALL_TOOLS, "cpu_karts")),
    3: dict(title="Selection and functions: write a kart brain", mode="practice",
            hazards=hazards("bumping", "cpu_karts"), tools=tools(*ALL_TOOLS, "cpu_karts", "brains")),
    4: dict(title="Using AI to code, safely", mode="race",
            hazards=hazards("bumping", "cpu_karts"), tools=tools(*ALL_TOOLS, "cpu_karts", "brains")),
    5: dict(title="Invent, compete and evaluate: the grand prix", mode="race",
            hazards=hazards("bumping", "cpu_karts"), tools=tools(*ALL_TOOLS, "cpu_karts", "brains")),
}

# ---------- missions ----------
# id: (lesson, title, what to do, outcome codes, how it is checked)
MISSIONS = {
    # Mission 1: what the learner sees is the title; the text drops down when the title is clicked, and is the
    # explanation and the guidance. The Garage (the GUI) shows the kart as variables.
    "1a": (1, "Change a STRING VARIABLE with the GUI",
           "In the Garage (press I for the HUD), under STRING VARIABLES, type a new name for your kart in the STRING VALUE box and "
           "press BUILD MY KART. A string is text: letters, digits and spaces, in quotes. Its type is str.",
           ["VAR", "DATA"], "auto"),
    "1b": (1, "Change an INTEGER VARIABLE with the GUI",
           "In the Garage, under INTEGER VARIABLES, move two of speed, acceleration and grip to new values and press "
           "BUILD MY KART. An integer is a whole number (type int). Race: what did each one change?",
           ["VAR", "DATA"], "auto"),
    "1c": (1, "Change a LIST VARIABLE with the GUI",
           "In the Garage, under VARIABLE LISTS, click a colour block and press BUILD MY KART. The colour is a "
           "list of three integers, [red, green, blue], each from 0 (none) to 255 (full). Its type is list.",
           ["DATA", "VAR"], "auto"),
    "1d": (1, "Hack the code",
           "Press C to open the code editor: your kart as Python, every variable with its type. Change a value "
           "there and press BUILD MY KART in the code panel. The extra power here: you can see ALL the "
           "variables, even the ones the Garage doesn't show.",
           ["VAR", "DATA", "ALG"], "auto"),
    "1e": (1, "Safe use of AI",
           "Press I and use an AI request card to ask for a change in the game: your kart, the track, the "
           "computer karts, the rules... almost anything you can imagine. No personal information. "
           "When the teacher keeps the change, look at what it did and answer the review questions.",
           ["AISAFE", "AIREVIEW"], "auto"),
    "2a": (2, "Spend exactly 100 points with the GUI", "In the Garage, share all 100 points between speed, "
                                                       "acceleration and grip: the Points table must say 0 left. "
                                                       "Press BUILD MY KART.", ["ALG", "VAR"], "auto"),
    "2b": (2, "Hack the code to spend more than 100 points", "Mission 1 d showed the code can change what the "
                                                          "garage can't. Press C, set the points so they add up to more "
                                                          "than 100, press APPLY CODE then BUILD MY KART, and read "
                                                          "the error message: invalid test data is refused.",
           ["VALID", "TEST"], "auto"),
    "2c": (2, "Boundary test data", "Build a kart with one category at exactly 10 or exactly 60.",
           ["VALID", "TEST"], "auto"),
    "2d": (2, "Predict, then time a lap", "Type your prediction of your kart's lap time in seconds in the Missions "
                                         "box, then drive a full lap. The server times it: how close were you?",
           ["TEST", "ABS"], "auto"),
    "2e": (2, "Design from evidence", "After rebuilding, finish a lap, then write why your design works (use your "
                                     "lap time).", ["EVAL", "TEST"], "auto"),
    "2f": (2, "AI rebalance", "Ask the AI to change your kart's points for a reason you can explain, then test "
                             "whether it worked.", ["AIREVIEW", "TEST"], "auto"),
    "3a": (3, "A brain that runs", "Edit brains/my_brain.py, press U to upload it and P to switch it on. "
                                  "It must run for 20 seconds without an error.", ["FUNC", "VAR"], "auto"),
    "3b": (3, "Make a decision", "Your brain uses if, elif or else (for example: brake for a bend).", ["SEL"], "auto"),
    "3c": (3, "Write your own function", "Write a helper function and call it from brain().", ["FUNC", "ALG"], "auto"),
    "3d": (3, "Remember something", "Use me.memory to keep a value between ticks (for example a state like "
                                   "'attack' or 'hold back').", ["VAR", "SEL"], "auto"),
    "3e": (3, "A brain that laps", "With autopilot on, your brain drives a whole lap by itself.",
           ["SEL", "TEST"], "auto"),
    "3f": (3, "Design the track with AI", "Ask the AI to change the track (its name, laps, which track is raced) "
                                          "and review what it did.", ["AISAFE", "ALG"], "auto"),
    "4a": (4, "Change the rules with AI", "Ask the AI to change a game rule (laps, the countdown, how karts bump...) "
                                         "and say why it makes the game better or fairer.", ["AISAFE", "ALG"], "auto"),
    "4b": (4, "Review the AI's code", "When the teacher marks your request ready, answer the review "
                                     "questions: does it work, did you test it, can you explain it?",
           ["AIREVIEW", "TEST"], "auto"),
    "4c": (4, "Spot the mistake", "Find what is wrong in a piece of AI-written code the teacher shows.",
           ["AIREVIEW"], "teacher"),
    "4d": (4, "Beat an Ace", "Finish a race ahead of an expert computer kart (the teacher sets the computer karts "
                            "to expert).", ["TEST", "EVAL"], "auto"),
    "5a": (5, "Grand prix ready", "Enter the grand prix with a kart you built and a brain you uploaded.",
           ["EVAL", "FUNC"], "auto"),
    "5b": (5, "Evaluate", "Write what worked, what you would change, and where AI did and didn't help.",
           ["EVAL", "AIREVIEW"], "auto"),
    "5d": (5, "A new feature with AI", "Ask the AI for a feature of your own design, then evaluate it with "
                                       "evidence from a race.", ["EVAL", "AIREVIEW"], "auto"),
    "5c": (5, "Explain your code", "Explain one part of your brain code to the group.", ["FUNC", "EVAL"], "teacher"),
}
REFLECTIONS = {"2e": 8, "5b": 20}  # missions answered in writing: the fewest words that count


# ---------- experiences ----------
# (CHANGE 210) A game-style first session played in the real game (engine/experience.py): CC-01 the coach, one
# objective at a time, XP and ranks over Kart Lab's own window, garage, code panel, brains and races. kart_teaching's
# Teaching measures each objective from the real kart on the real track. The teacher starts it for a class
# (Controls); on your own the app's EXPERIENCES button opens Kart Lab with --experience 1 (its server on your laptop).
# The lesson it is played in: the Club Circuit, open for practice, no computer karts until the race (they'd take the
# item boxes and bump a beginner off the road), every power-up on, everything in the garage and the brains on.
EXPERIENCES = {
    1: dict(
        title="Orientation", coach="CC-01",
        intro="CC-01 here, your coach. This is Kart Lab, the real thing: your kart, the Club Circuit, the code. Nine "
              "objectives, one at a time, and XP for each.",
        lesson=dict(mode="practice", track="club", laps=2, cpu_karts=3, cpu_level="easy", designs_locked=False,
                    tyres=False, hazards=hazards("bumping"),
                    items={n: True for n in ("boost", "oil", "shot", "homing", "shield")},  # (kart_items.ITEMS)
                    tools=tools(*ALL_TOOLS, "brains")),
        objectives=[
            dict(id="drive", title="Engines on", xp=10, goal=30, unit="m", hint="Drive 30 metres",
                 say="Systems online. Let's see you move: hold the up arrow (or W) to go, left and right to steer."),
            dict(id="speed", title="Flat out", xp=10, goal=60, unit="km/h", hint="Reach 60 km/h",
                 say="Open it up: find a straight, hold the throttle and watch your speed, bottom right."),
            dict(id="lap", title="Learn the track", xp=25, goal=8, unit="gates", hint="Drive all the way round",
                 say="The track has 8 gates round it. Drive a whole lap, through every one: the map, bottom left, "
                     "shows where you are. Off the road? R puts you back on the track."),
            dict(id="drift", title="Drift boost", xp=25, goal=2, hint="Earn 2 mini-turbos",
                 say="The racer's trick: hold Shift as you steer through a bend. The DRIFT bar fills, bottom right; "
                     "let go once it's past the first mark and you get a mini-turbo. Two of them."),
            dict(id="item", title="Power-up", xp=15, hint="Drive through an item box, then use the item",
                 say="See the boxes across the road? Drive through one for a power-up (it shows on the right), then "
                     "press Space to use it."),
            dict(id="garage", title="Variables", xp=45, goal=3, hint="Change a string, an integer and a list, then "
                                                                     "BUILD MY KART",
                 say="Your kart is made of VARIABLES. Press I and open the Garage: give it a new name (a STRING), "
                     "move speed, acceleration or grip (an INTEGER) and click a colour (a LIST), then press BUILD "
                     "MY KART.", outcomes=["VAR", "DATA"]),
            dict(id="code", title="Hack the code", xp=30, hint="Change a value in the code (C) and build from there",
                 say="Everything in the Garage is Python code. Press C: that's your kart, every variable with its "
                     "type. Change a value, press APPLY CODE, then BUILD MY KART in the code panel.",
                 outcomes=["VAR", "DATA"]),
            dict(id="brain", title="Brains", xp=30, goal=8, unit="s", hint="Autopilot on for 8 seconds",
                 say="A BRAIN is Python that drives for you. Press U to upload brains/my_brain.py, then P to switch "
                     "autopilot on, and watch it drive.", outcomes=["SEL", "FUNC"]),
            dict(id="race", title="First race", xp=60, hint="Finish a race (first place scores a bonus)",
                 say="Last one: a real race. Your teacher starts the races: when the countdown ends, it's real. "
                     "Get to the flag.",
                 solo="Ready for a real one? Three computer karts on the grid, two laps, the real countdown. "
                      "Autopilot's off: this one's you. Get to the flag, and first place scores a bonus."),
        ],
        bonus=dict(id="race", title="Race winner", xp=25),
        finish="Orientation complete. You drove it, coded it, gave it a brain and raced it. Welcome to Club Coders!"),
}


def points_words(text, limits):
    """A mission's words with the teacher's own numbers in them: the missions are written for 100 points to share
    and 10 to 60 for each (the standard limits), and the teacher can change both (the Limits tab)."""
    total = limits["points_total"]
    lo, hi = min(v[0] for v in limits["points"].values()), max(v[1] for v in limits["points"].values())
    if (total, lo, hi) == (100, 10, 60):
        return text
    text = re.sub(r"\b100(?=[ -]points?\b)", str(total), text)
    text = re.sub(r"(?<=more than )100\b", str(total), text)
    text = re.sub(r"\bexactly 10 or exactly 60\b", f"exactly {lo} or exactly {hi}", text)
    return re.sub(r"\b10 to 60\b", f"{lo} to {hi}", text)


def missions_for(lesson):
    return {k: v for k, v in MISSIONS.items() if v[0] == lesson}


# ---------- the teacher's lesson guide ----------
# The overall task for each lesson, and for each outcome it teaches a "lesson piece": the task learners do,
# the steps, what the teacher explains or shows, and what success looks like. The teacher's Outcomes tab shows
# these when an outcome is clicked, so a new teacher can see exactly what learners need to do.
LESSON_TASKS = {
    1: "Your kart is a set of variables. Change a string (its name), integers (speed, acceleration and grip) and "
       "a list (its colour) with the GUI, then hack the code to change them there, where every variable can be "
       "seen. Finish with a first safe AI request for a change in the game, then check what the AI did.",
    2: "Design a kart on a budget. Share exactly 100 points between speed, acceleration and grip in the code, "
       "prove the game rejects bad designs (invalid and boundary test data), then predict a lap time, race, and "
       "use the evidence to justify the design.",
    3: "Write a Python brain that drives the kart by itself. It must run without errors, make decisions with "
       "if / elif / else, use a function of your own and remember a state between ticks. Upload it (U), switch "
       "autopilot on (P) and watch it lap.",
    4: "Improve the game itself with AI. Write a safe, precise request to change a game rule, predict what it "
       "will do, then review the AI's code: does it work, was it tested, can you explain it? Then find a "
       "mistake hidden in AI-written code.",
    5: "Bring everything together for the class grand prix: a final design and an uploaded brain, one new "
       "feature of your own made with AI, then evaluate what worked using evidence from the races and "
       "explain your code to the group.",
}

GUIDE = {  # lesson: {outcome: lesson piece}
    1: {
        "VAR": dict(
            task="Change variables with the GUI, then in the code",
            do=["Open the Garage (I opens the HUD): the kart is shown as variables. Under STRING VARIABLES type a new "
                "kart_name; under INTEGER VARIABLES change speed, acceleration and grip. Press BUILD MY KART.",
                "Race: what did each change do?",
                "Press C. Find the line  grip: int = 33  - that is the variable you changed. Change a value "
                "here instead and press BUILD MY KART in the code panel."],
            teach="A variable is a name that stores a value. Changing the value changes how the program behaves "
                  "without rewriting the program. Writing grip = 33 is called assignment. The GUI and the "
                  "code change the same variables; the code shows all of them.",
            success="They can point to the variable they changed, say its old and new value, and what it did."),
        "DATA": dict(
            task="Strings, integers and lists",
            do=["In the Garage, hover over STRING, INTEGER and LIST to read what each type is.",
                "Change the name (a string), the points (integers) and the colour (a list) and press "
                "BUILD MY KART.",
                "Press C. Every variable has its type after its name: str, int or list. Change colour to "
                "[0, 200, 255] and press APPLY CODE: the custom block in the Garage takes that colour."],
            teach="Data types: a string (str) is text in quotes, made of chars; an integer (int) is a whole number; "
                  "a list keeps values in order in [ ]. The colour is a list of three integers: red, green, blue.",
            success="They can name the data type of three values in their kart's code."),
        "ALG": dict(
            task="Hack the code",
            do=["Press C. The code shows every variable, even the ones the Garage hides this mission.",
                "Change one of them and press BUILD MY KART in the code panel.",
                "The teacher's Warnings tab shows what was changed outside the Garage."],
            teach="The GUI is one way in; the code is a more powerful way in to the same program. Knowing the "
                  "variables means you can change things the buttons don't offer.",
            success="They changed a value in the code that the Garage doesn't show, and can say which."),
        "AISAFE": dict(
            task="Your first AI request",
            do=["Press I to open the AI card.",
                "Goal: a change in the game: your kart, the track, the computer karts... e.g. 'Make my kart "
                "bright green and call it Comet'.",
                "Say which values change, how you will test it, and your prediction.",
                "No personal information. Tick the three boxes and send it."],
            teach="Never give an AI tool personal information (full name, school, email, address). A good request "
                  "has a clear goal, a limit on what may change, and a way to test it.",
            success="Their card passes the checks with a clear goal and a test, and no personal information."),
        "AIREVIEW": dict(
            task="Check the AI's work",
            do=["When the teacher keeps the change, look at your kart. Did it do exactly what you asked?",
                "Answer the review questions in the AI card tab.",
                "Find one changed line and explain it in your own words."],
            teach="AI can be wrong or do more than you asked. You check its work against your prediction before "
                  "you trust it.",
            success="Their answers say what they tested and explain one changed line."),
    },
    2: {
        "VAR": dict(
            task="Spend exactly 100 points with the GUI (objective a)",
            do=["Open the Garage (I). Under INTEGER VARIABLES, the Points table shares 100 points.",
                "Use the -5, -, + and +5 buttons on speed, acceleration and grip so they add up to exactly 100 "
                "(e.g. 45, 25, 30): the table must say 0 left.",
                "Press BUILD MY KART and test it."],
            teach="The points are three integer variables. The program adds them up to check the total. "
                  "Raising one value means lowering another: every choice is a trade-off.",
            success="Their code shows a total of 100, and they can say which value they raised and which they lowered."),
        "ALG": dict(
            task="Plan the trade-off before you build",
            do=["Choose a plan: a straight-line rocket, a corner hugger, or an all-rounder.",
                "On paper, write the three numbers. Check they add up to 100 and each is from 10 to 60.",
                "Enter them, build, and try the plan on the track."],
            teach="Decomposition: a 'good kart' is broken into three parts (speed, acceleration, grip). "
                  "The rules are constraints: 100 in total, and 10 to 60 each.",
            success="They explain their numbers as a plan that meets both rules."),
        "VALID": dict(
            task="Break the rules on purpose, in the code (objectives b and c)",
            do=["Press C. Set speed to 70 (more than 60). APPLY CODE: it refuses (value too high).",
                "Make the three points add up to 110. APPLY CODE, then BUILD MY KART: the build is refused and "
                "says why (objective b: invalid data from the code).",
                "Put a word instead of a number, e.g. \"fast\". APPLY and read the error.",
                "Boundary: set grip to exactly 10, then exactly 60. Both should be accepted (objective c)."],
            teach="Validation checks input before it is used. Normal data (33), boundary data (10 and 60, the "
                  "edges that are still allowed) and invalid data (61, 110, text) should all be tested.",
            success="They can give an example of normal, boundary and invalid data and what the program did."),
        "TEST": dict(
            task="Predict a lap time, then measure it",
            do=["Type a lap time prediction in the Missions box before you drive.",
                "Drive one full lap: the server times it and the Missions tab shows your best lap.",
                "Make a table: prediction | actual | difference. Change one point and predict again."],
            teach="A test plan says what should happen before you try it. A prediction you can check is the start "
                  "of a fair test: change one variable at a time.",
            success="Their table has a prediction written before each timed lap."),
        "ABS": dict(
            task="What the numbers model",
            do=["Look at the stats readout: speed points become a top speed in km/h, acceleration points a rate, "
                "grip points how fast a slide dies.",
                "Say which real things about a kart the game leaves out (weight, tyres, fuel...)."],
            teach="Abstraction: the game models a kart with three numbers. That is enough to race with, and "
                  "simple enough to reason about.",
            success="They name one thing the model keeps and one it leaves out."),
        "EVAL": dict(
            task="Design from evidence",
            do=["Rebuild with your planned points and finish a lap.",
                "In the Missions box write why your design works (or doesn't), using numbers: lap time, top speed, "
                "where you lost time.",
                "Say one change you would make next."],
            teach="Evaluate against evidence, not feelings: 'my lap was 41 s and I slid wide at the hairpin' beats "
                  "'it was good'.",
            success="Their reflection uses a number from a lap and names one change."),
        "AIREVIEW": dict(
            task="AI rebalance",
            do=["Press I. Target: My kart. Ask the AI to change your points for a reason, "
                "e.g. 'more grip so I don't slide at the hairpin'.",
                "Predict what will be better and what will be worse.",
                "When it is kept, race, compare with your prediction, and answer the review questions."],
            teach="An AI change is only good if it meets your goal. Check it with a lap time, not just by reading it.",
            success="They say whether the AI change met their goal, with evidence from a lap."),
    },
    3: {
        "FUNC": dict(
            task="A brain that runs, with a function of your own",
            do=["Open brains/my_brain.py. brain(me, track, rivals) runs 20 times a second and returns throttle, "
                "steer and whether to drift.",
                "Write a helper function, e.g.  def bend_ahead(track): return abs(track.bend_ahead) > 25",
                "Call it inside brain(): if bend_ahead(track): throttle = 0.5",
                "Press U to upload and P for autopilot. It must run for 20 seconds without an error."],
            teach="A function has a name, parameters (what goes in) and a return value (what comes out). "
                  "brain() is a function the game calls; your helper is one you call.",
            success="Their brain calls their own function and runs for 20 seconds without an error."),
        "SEL": dict(
            task="Make a decision",
            do=["Add if / elif / else to your brain, e.g.",
                "if me.wrong_way: turn round.  elif track.bend_ahead > 25: brake.  else: full throttle.",
                "Use and / or / not in a condition: drift = abs(track.bend_ahead) > 30 and me.speed > 12"],
            teach="Selection chooses which code runs. Conditions are True or False; and, or and not combine them "
                  "(Boolean logic). Only the first true branch of an if / elif / else runs.",
            success="They can say which branch runs in a given situation, and why."),
        "VAR": dict(
            task="Remember something between ticks",
            do=["Use me.memory to keep a state, e.g. me.memory['mode'] = 'attack'.",
                "Switch to 'hold back' when a rival is right ahead, and back to 'attack' on a straight.",
                "Choose what to do with if me.memory.get('mode') == 'hold back':"],
            teach="Ordinary variables are forgotten every tick. me.memory is a dictionary the game keeps between "
                  "ticks, so the brain can remember its state.",
            success="Their brain changes mode and stays in it until something changes."),
        "ALG": dict(
            task="Plan the brain before you code it",
            do=["Write the brain as steps (pseudocode or a flowchart): look ahead, steer to the centre line, "
                "brake for bends, drift through the long ones, respawn if stuck.",
                "Code ONE step, upload, test, then add the next.",
                "Design the track with AI: ask for a change that tests your brain."],
            teach="Decomposition and algorithms: a big problem becomes small steps in order. Testing each step "
                  "as you add it makes bugs easy to find.",
            success="Their flowchart or pseudocode matches the order of their code."),
        "AISAFE": dict(
            task="Design the track with AI",
            do=["Press I. Target: The track.",
                "Ask for exactly what may change, e.g. 'race the oval for 5 laps and call it Speedbowl'.",
                "No personal information. Say how you will test it."],
            teach="Limiting what the AI may change keeps the result safe and checkable. Vague requests get "
                  "surprising results.",
            success="Their request says exactly what may change and how to test it."),
    },
    4: {
        "AISAFE": dict(
            task="Change a game rule with AI",
            do=["Press I. Target: The rules.",
                "Choose ONE rule (laps, countdown_seconds, bump_distance, bump_slowdown), "
                "a new value and a reason, e.g. 'bump_slowdown 0.1 so a nudge doesn't ruin a race'.",
                "No personal information. Say how you will test it."],
            teach="Be specific and limit the scope. The teacher approves every change before it goes in the game.",
            success="Their request names the variable, the value, the reason and a test."),
        "ALG": dict(
            task="Predict the knock-on effects",
            do=["Before sending, write what ELSE your change might affect "
                "(e.g. a bigger bump distance: karts touch sooner on the grid).",
                "Write the test steps you will follow."],
            teach="Changing one rule can change other things too. Thinking them through first is part of "
                  "designing an algorithm.",
            success="Their prediction names at least one knock-on effect."),
        "AIREVIEW": dict(
            task="Review the AI's code, and spot the mistake",
            do=["When your request is marked ready, the teacher shows the change (Changes tab).",
                "Answer the review questions: does it work, did you test it, can you explain it?",
                "Spot the mistake: the teacher shows AI-written code with a bug hidden in it "
                "(e.g. a points check that uses > 101). Find it and explain it."],
            teach="AI can write code that looks right but is wrong. Check it against what was asked, and think "
                  "of a test that would catch the mistake.",
            success="They find the bug and describe a test that would catch it."),
        "TEST": dict(
            task="Test the AI's change",
            do=["Race with the new rule.",
                "Compare what happened with your prediction.",
                "Record the evidence in your review answers."],
            teach="Only a test shows whether the change works in the game.",
            success="Evidence from a race supports their verdict."),
    },
    5: {
        "EVAL": dict(
            task="Evaluate your kart and your code",
            do=["After the grand prix, write: what worked, what you would change, and where AI did and didn't help.",
                "Back each point with evidence: places, lap times, where you lost time.",
                "Save it in the Missions tab."],
            teach="An evaluation compares the result with the goal, using evidence, and says what to do next.",
            success="Three points, each backed by evidence."),
        "FUNC": dict(
            task="Grand prix ready, and explain your code",
            do=["Enter the grand prix with a kart you built and a brain you uploaded.",
                "Your brain uses at least one function of your own.",
                "Explain one function to the group: what goes in, what comes out, and why you wrote it."],
            teach="Being able to explain your code shows you understand it (and that you wrote it).",
            success="They explain the parameters and the return value of one of their functions."),
        "AIREVIEW": dict(
            task="A new feature with AI",
            do=["Design a feature of your own, e.g. a slipstream boost behind another kart.",
                "Send an AI card, then review the code when it comes back.",
                "Test it in a race, and say where AI helped (the tool and the date)."],
            teach="Crediting AI help, and checking the work, is how AI is used honestly in coursework.",
            success="They say what they checked and where AI helped."),
    },
}


def outcome_lessons(code):
    """The lessons that teach an outcome."""
    return [n for n, pieces in GUIDE.items() if code in pieces]


def missions_for_outcome(lesson, code):
    """The missions in a lesson that give evidence for an outcome."""
    return {k: v for k, v in MISSIONS.items() if v[0] == lesson and code in v[3]}


# ---------- checking a brain's code for missions ----------
def brain_features(source):
    """What a brain uses: selection, its own functions, memory."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found = set()
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp)):
            found.add("if")
        if isinstance(node, ast.Attribute) and node.attr == "memory":
            found.add("memory")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in funcs - {"brain"}:
            found.add("own_function")
    return found


# AI request cards: which mission a card or a review completes in each lesson
AI_CARD_MISSION = {1: "1e", 3: "3f", 4: "4a"}
AI_REVIEW_MISSION = {1: "1e", 2: "2f", 4: "4b", 5: "5d"}
AI_TARGETS = {"kart": "My kart", "track": "The track", "rules": "The rules", "game": "The game (teacher only)"}

# ---------- AI request cards ----------
REVIEW_QUESTIONS = {
    "works": "Does the new code do what your card asked? What happened when you tried it?",
    "tested": "How did you test it? Did the result match your prediction?",
    "explain": "Explain one changed line or function in your own words.",
    "problems": "Is anything wrong, unsafe or unfair about the change?",
    "next_time": "How would you change your request next time?",
}

PERSONAL = [
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "an email address"),
    (r"(\+44\s?7\d{3}|\b07\d{3})\s?\d{3}\s?\d{3}\b", "a phone number"),
    (r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", "a postcode"),
    (r"\b(my|our) (address|house|street|school|password|surname|last name|birthday)\b", "personal details"),
    (r"\b(password|passcode|pin number)\b", "a password"),
]


def check_ai_card(card):
    """Return (problems, tips). Problems block sending; tips help write a better request."""
    text = " ".join(str(card.get(k, "")) for k in ("goal", "variables", "test", "predict"))
    problems, tips = [], []
    for pattern, what in PERSONAL:
        if re.search(pattern, text, re.IGNORECASE):
            problems.append(f"Remove {what}: never put personal information in an AI request.")
    for key, label in (("privacy", "no personal information"), ("review", "you will review and test the code"),
                       ("credit", "you will say where AI helped")):
        if not card.get(key):
            problems.append(f"Tick the box: {label}.")
    words = lambda k: len(str(card.get(k, "")).split())  # noqa: E731
    if words("goal") < 1:  # (a few words can be enough for an idea)
        problems.append("Type your idea in the My idea box.")
    if words("test") < 6:
        problems.append("Say how you will test it (at least 6 words).")
    if words("predict") < 3:
        tips.append("Add a prediction: what do you expect to happen?")
    if not re.search(r"\d|[a-z]+_[a-z]+", str(card.get("variables", ""))):
        tips.append("Name a variable or give a number, for example bump_slowdown = 0.1.")
    return problems, tips


def ai_prompt(card, learner):
    """The prompt the teacher pastes into an AI coding assistant, with the club's guardrails."""
    return f"""Learner request for Kart Lab (from {learner}, first name only).

GOAL: {card.get('goal', '').strip()}
VARIABLES / VALUES: {card.get('variables', '').strip()}
HOW THEY WILL TEST IT: {card.get('test', '').strip()}
THEIR PREDICTION: {card.get('predict', '').strip()}

Rules for the change:
- Change only the Kart Lab files (kart_sim.py, kart_track.py, kart_server.py, kart_client.py, kart_gfx.py,
  kart_missions.py, cpu_brains.py, the mods).
- A window predicts its own kart with the same kart_sim.step() the server runs: anything that changes how a kart
  moves must change on both ends the same way (it does, when it lives in kart_sim or kart_track), and must stay
  deterministic (no random numbers in step()).
- Keep names simple and add a short comment explaining each change for 13-18 year olds.
- No internet access, no reading or writing files other than these, no personal data.
- If the request is unclear or unsafe, say so instead of guessing. Don't add anything that wasn't asked for.
- Explain the change step by step so the learner can follow it and explain it back.
- Run the game's test (kart_test.py) to show the feature working, and list what a learner should check.
"""
