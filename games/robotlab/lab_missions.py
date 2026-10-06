"""Robot Lab lessons, missions and learning outcomes.

Each lesson switches on the right garage tools and hazards and gives learners missions.
Missions are checked by the server from what learners actually do (a design that was built,
a prediction then a test drive, a brain that runs), and every tick is saved as evidence
against the learning outcomes below. Curriculum references live in OUTCOMES so a teacher
can see which part of the curriculum a mission covers.
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
    "ABS": ("Abstraction and modelling", "Explain how the game models real robot physics with a few numbers",
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
ALL_TOOLS = ["points_table", "forward_speed", "reverse_speed", "turn_speed", "acceleration", "size",
             "choose_weapon", "name_and_colour", "code_view", "stats_readout", "weapon_toggle"]


def tools(*on, weapons=("wedge", "spinner", "drum", "hammer")):
    t = {k: k in on for k in ALL_TOOLS + ["house_robots"]}  # (Resident Robots in the garage: the teacher turns it on)
    t["weapons"] = list(weapons)
    return t


LESSONS = {
    1: dict(title="Variables: tune your robot", mode="practice",
            hazards={"pit": True, "floor_flipper": False, "saws": False, "spikes": False, "house_robots": False},
            tools=tools("forward_speed", "reverse_speed", "turn_speed", "acceleration", "size",
                        "name_and_colour", "code_view", "stats_readout", "weapon_toggle")),
    2: dict(title="Trade-offs and robust programs: the 100-point budget", mode="practice",
            hazards={"pit": True, "floor_flipper": True, "saws": False, "spikes": False, "house_robots": False},
            tools=tools(*ALL_TOOLS)),
    3: dict(title="Selection and functions: write a robot brain", mode="practice",
            hazards={"pit": True, "floor_flipper": True, "saws": True, "spikes": False, "house_robots": False},
            tools=tools(*ALL_TOOLS)),
    4: dict(title="Using AI to code, safely", mode="battle",
            hazards={"pit": True, "floor_flipper": True, "saws": True, "spikes": True, "house_robots": True},
            tools=tools(*ALL_TOOLS)),
    5: dict(title="Invent, compete and evaluate", mode="battle",
            hazards={"pit": True, "floor_flipper": True, "saws": True, "spikes": True, "house_robots": True},
            tools=tools(*ALL_TOOLS)),
}

# ---------- missions ----------
# id: (lesson, title, what to do, outcome codes, how it is checked)
MISSIONS = {
    # Mission 1 (CHANGE 50 to 53): what the learner sees is the title; the text drops down when the title is
    # clicked, and is the explanation and the guidance. The Garage (the GUI) shows the robot as variables.
    "1a": (1, "Change a STRING VARIABLE with the GUI",
           "In the Garage (G), under STRING VARIABLES, type a new name for your robot in the STRING VALUE box and "
           "press REBUILD MY ROBOT. A string is text: letters, digits and spaces, in quotes. Its type is str.",
           ["VAR", "DATA"], "auto"),
    "1b": (1, "Change an INTEGER VARIABLE with the GUI",
           "In the Garage, under INTEGER VARIABLES, slide turn_speed and size to new values and press REBUILD MY "
           "ROBOT. An integer is a whole number (type int). Drive: what did each one change?",
           ["VAR", "DATA"], "auto"),
    "1c": (1, "Change a LIST VARIABLE with the GUI",
           "In the Garage, under VARIABLE LISTS, click a colour block and press REBUILD MY ROBOT. The colour is a "
           "list of three integers, [red, green, blue], each from 0 (none) to 255 (full). Its type is list.",
           ["DATA", "VAR"], "auto"),
    "1d": (1, "Hack the code",
           "Press C to open the code editor: your robot as Python, every variable with its type. Change a value "
           "there and press REBUILD MY ROBOT in the code panel. The extra power here: you can see ALL the "
           "variables, even the ones the Garage doesn't show.",
           ["VAR", "DATA", "ALG"], "auto"),
    "1e": (1, "Safe use of AI",
           "Press I and use an AI request card to ask for a change in the game: your robot, your weapon, your "
           "defence, the arena, the Resident Robots... almost anything you can imagine. No personal information. "
           "When the teacher keeps the change, look at what it did and answer the review questions.",
           ["AISAFE", "AIREVIEW"], "auto"),
    "2a": (2, "Spend exactly 100 points", "Share all 100 points between speed, attack, armour and control.",
           ["ALG", "VAR"], "auto"),
    "2b": (2, "Invalid test data", "Try to build a robot that breaks the rules (for example more than 100 "
                                  "points) and read the error message.", ["VALID", "TEST"], "auto"),
    "2c": (2, "Boundary test data", "Build a robot with one category at exactly 5 or exactly 50.",
           ["VALID", "TEST"], "auto"),
    "2d": (2, "Design from evidence", "After rebuilding, land 3 hits, then write why your design works.",
           ["EVAL", "TEST"], "auto"),
    "2e": (2, "AI rebalance", "Ask the AI to change your robot's points or settings for a reason you can "
                             "explain, then test whether it worked.", ["AIREVIEW", "TEST"], "auto"),
    "3a": (3, "A brain that runs", "Edit brains/my_brain.py, press U to upload it and P to switch it on. "
                                  "It must run for 20 seconds without an error.", ["FUNC", "VAR"], "auto"),
    "3b": (3, "Make a decision", "Your brain uses if, elif or else.", ["SEL"], "auto"),
    "3c": (3, "Write your own function", "Write a helper function and call it from brain().", ["FUNC", "ALG"], "auto"),
    "3d": (3, "Remember something", "Use me.memory to keep a value between ticks (for example a state like "
                                   "'attack' or 'escape').", ["VAR", "SEL"], "auto"),
    "3e": (3, "Design the arena with AI", "Ask the AI to change the arena (hazards, colours, name) and "
                                          "review what it did.", ["AISAFE", "ALG"], "auto"),
    "4a": (4, "Change the rules with AI", "Ask the AI to change a game rule (damage, gravity, match time...) "
                                         "and say why it makes the game better or fairer.", ["AISAFE", "ALG"], "auto"),
    "4b": (4, "Review the AI's code", "When the teacher marks your request ready, answer the review "
                                     "questions: does it work, did you test it, can you explain it?",
           ["AIREVIEW", "TEST"], "auto"),
    "4c": (4, "Spot the mistake", "Find what is wrong in a piece of AI-written code the teacher shows.",
           ["AIREVIEW"], "teacher"),
    "5a": (5, "Tournament ready", "Enter the final battle with a design you built and a brain you uploaded.",
           ["EVAL", "FUNC"], "auto"),
    "5b": (5, "Evaluate", "Write what worked, what you would change, and where AI did and didn't help.",
           ["EVAL", "AIREVIEW"], "auto"),
    "5d": (5, "A new feature with AI", "Ask the AI for a feature of your own design, then evaluate it with "
                                       "evidence from a fight.", ["EVAL", "AIREVIEW"], "auto"),
    "5c": (5, "Explain your code", "Explain one part of your brain code to the group.", ["FUNC", "EVAL"], "teacher"),
}


def points_words(text, limits):
    """A mission's words with the teacher's own numbers in them: the missions are written for 100 points to share
    and 5 to 50 for each (the standard limits), and the teacher can change both (the Limits tab)."""
    total = limits["points_total"]
    lo, hi = min(v[0] for v in limits["points"].values()), max(v[1] for v in limits["points"].values())
    if (total, lo, hi) == (100, 5, 50):
        return text
    text = re.sub(r"\b100(?=[ -]points?\b)", str(total), text)
    text = re.sub(r"(?<=more than )100\b", str(total), text)
    return re.sub(r"\b5 to 50\b", f"{lo} to {hi}", text)


def missions_for(lesson):
    return {k: v for k, v in MISSIONS.items() if v[0] == lesson}


# ---------- the teacher's lesson guide ----------
# The overall task for each lesson, and for each outcome it teaches a "lesson piece": the task learners do,
# the steps, what the teacher explains or shows, and what success looks like. The teacher's Outcomes tab shows
# these when an outcome is clicked, so a new teacher can see exactly what learners need to do.
LESSON_TASKS = {
    1: "Your robot is a set of variables. Change a string (its name), integers (turn speed and size) and a list "
       "(its colour) with the GUI, then hack the code to change them there, where every variable can be seen. "
       "Finish with a first safe AI request for a change in the game, then check what the AI did.",
    2: "Design a robot on a budget. Share exactly 100 points between speed, attack, armour and control in the "
       "code, prove the game rejects bad designs (invalid and boundary test data), then fight and use the "
       "evidence to justify the design.",
    3: "Write a Python brain that drives the robot by itself. It must run without errors, make decisions with "
       "if / elif / else, use a function of your own and remember a state between ticks. Upload it (U), switch "
       "autopilot on (P) and watch it fight.",
    4: "Improve the game itself with AI. Write a safe, precise request to change a game rule, predict what it "
       "will do, then review the AI's code: does it work, was it tested, can you explain it? Then find a "
       "mistake hidden in AI-written code.",
    5: "Bring everything together for the class tournament: a final design and an uploaded brain, one new "
       "feature of your own made with AI, then evaluate what worked using evidence from the battles and "
       "explain your code to the group.",
}

GUIDE = {  # lesson: {outcome: lesson piece}
    1: {
        "VAR": dict(
            task="Change variables with the GUI, then in the code",
            do=["Open the Garage (G): the robot is shown as variables. Under STRING VARIABLES type a new "
                "robot_name; under INTEGER VARIABLES slide turn_speed and size. Press REBUILD MY ROBOT.",
                "Drive: what did each change do?",
                "Press C. Find the line  turn_speed: int = 100  - that is the variable you changed. Change a value "
                "here instead and press REBUILD MY ROBOT in the code panel."],
            teach="A variable is a name that stores a value. Changing the value changes how the program behaves "
                  "without rewriting the program. Writing turn_speed = 100 is called assignment. The GUI and the "
                  "code change the same variables; the code shows all of them.",
            success="They can point to the variable they changed, say its old and new value, and what it did."),
        "DATA": dict(
            task="Strings, integers and lists",
            do=["In the Garage, hover over STRING, INTEGER and LIST to read what each type is.",
                "Change the name (a string), turn speed and size (integers) and the colour (a list) and press "
                "REBUILD MY ROBOT.",
                "Press C. Every variable has its type after its name: str, int or list. Change colour to "
                "[0, 200, 255] and press APPLY CODE: the custom block in the Garage takes that colour."],
            teach="Data types: a string (str) is text in quotes, made of chars; an integer (int) is a whole number; "
                  "a list keeps values in order in [ ]. The colour is a list of three integers: red, green, blue.",
            success="They can name the data type of three values in their robot's code."),
        "ALG": dict(
            task="Hack the code",
            do=["Press C. The code shows every variable, even the ones the Garage hides this mission "
                "(the points, the weapon).",
                "Change one of them and press REBUILD MY ROBOT in the code panel.",
                "The teacher's Warnings tab shows what was changed outside the Garage."],
            teach="The GUI is one way in; the code is a more powerful way in to the same program. Knowing the "
                  "variables means you can change things the buttons don't offer.",
            success="They changed a value in the code that the Garage doesn't show, and can say which."),
        "AISAFE": dict(
            task="Your first AI request",
            do=["Press I to open the AI card.",
                "Goal: a change in the game: your robot, your weapon, your defence, the arena, the Resident "
                "Robots... e.g. 'Make my robot's lights green and its body blue'.",
                "Say which values change, how you will test it, and your prediction.",
                "No personal information. Tick the three boxes and send it."],
            teach="Never give an AI tool personal information (full name, school, email, address). A good request "
                  "has a clear goal, a limit on what may change, and a way to test it.",
            success="Their card passes the checks with a clear goal and a test, and no personal information."),
        "AIREVIEW": dict(
            task="Check the AI's work",
            do=["When the teacher keeps the change, look at your robot. Did it do exactly what you asked?",
                "Answer the review questions in the AI card tab.",
                "Find one changed line and explain it in your own words."],
            teach="AI can be wrong or do more than you asked. You check its work against your prediction before "
                  "you trust it.",
            success="Their answers say what they tested and explain one changed line."),
    },
    2: {
        "VAR": dict(
            task="Set the 100 points in the code",
            do=["Press C to see your robot as code.",
                "Change speed_points, attack_points, armour_points and control_points so they add up to exactly 100 "
                "(e.g. 30, 30, 25, 15).",
                "Press APPLY CODE. The line under them must say: points used: 100 of 100.",
                "Press REBUILD MY ROBOT and test it."],
            teach="The points are four integer variables. The program adds them up to check the total. "
                  "Raising one value means lowering another: every choice is a trade-off.",
            success="Their code shows a total of 100, and they can say which value they raised and which they lowered."),
        "ALG": dict(
            task="Plan the trade-off before you build",
            do=["Choose a plan: a fast rammer, a tank, or a heavy hitter.",
                "On paper, write the four numbers. Check they add up to 100 and each is from 5 to 50.",
                "Enter them, build, and try the plan in practice."],
            teach="Decomposition: a 'good robot' is broken into four parts (speed, attack, armour, control). "
                  "The rules are constraints: 100 in total, and 5 to 50 each.",
            success="They explain their numbers as a plan that meets both rules."),
        "VALID": dict(
            task="Break the rules on purpose",
            do=["In the code set speed_points to 60 (more than 50). APPLY and read the error.",
                "Make the total 110. APPLY and read the error.",
                "Put a word instead of a number, e.g. \"fast\". APPLY and read the error.",
                "Boundary: set armour_points to exactly 5, then exactly 50. Both should be accepted."],
            teach="Validation checks input before it is used. Normal data (25), boundary data (5 and 50, the "
                  "edges that are still allowed) and invalid data (51, 110, text) should all be tested.",
            success="They can give an example of normal, boundary and invalid data and what the program did."),
        "TEST": dict(
            task="Fill in a test table",
            do=["Make a table: test data | type (normal / boundary / invalid) | expected | actual | pass?",
                "Write the expected result BEFORE each test.",
                "Test: total 100 (normal), attack_points 50 (boundary), total 101 (invalid)."],
            teach="A test plan says what should happen before you try it. A test passes when what actually "
                  "happens matches what was expected.",
            success="Their table has one test of each type with expected results written first."),
        "EVAL": dict(
            task="Design from evidence",
            do=["Rebuild with your planned points and land 3 hits in practice.",
                "In the Missions box write why your design works (or doesn't), using numbers: hits, armour left, "
                "top speed.",
                "Say one change you would make next."],
            teach="Evaluate against evidence, not feelings: 'I landed 5 hits and kept 80% armour' beats "
                  "'it was good'.",
            success="Their reflection uses a number from the fight and names one change."),
        "AIREVIEW": dict(
            task="AI rebalance",
            do=["Press I. Target: My robot. Ask the AI to change your points or settings for a reason, "
                "e.g. 'more armour so I survive the floor saws'.",
                "Predict what will be better and what will be worse.",
                "When it is kept, fight, compare with your prediction, and answer the review questions."],
            teach="An AI change is only good if it meets your goal. Check it with a fight, not just by reading it.",
            success="They say whether the AI change met their goal, with evidence from a fight."),
    },
    3: {
        "FUNC": dict(
            task="A brain that runs, with a function of your own",
            do=["Open brains/my_brain.py. brain(me, enemies) runs 60 times a second and returns throttle, "
                "steer and attack.",
                "Write a helper function, e.g.  def nearest(me, enemies): return min(enemies, key=me.distance_to)",
                "Call it inside brain(): target = nearest(me, enemies)",
                "Press U to upload and P for autopilot. It must run for 20 seconds without an error."],
            teach="A function has a name, parameters (what goes in) and a return value (what comes out). "
                  "brain() is a function the game calls; your helper is one you call.",
            success="Their brain calls their own function and runs for 20 seconds without an error."),
        "SEL": dict(
            task="Make a decision",
            do=["Add if / elif / else to your brain, e.g.",
                "if me.upside_down: wait.  elif me.distance_to(me.pit) < 3: steer away.  else: attack.",
                "Use and / or / not in a condition: attack = me.distance_to(target) < 2.5 and me.weapon_ready"],
            teach="Selection chooses which code runs. Conditions are True or False; and, or and not combine them "
                  "(Boolean logic). Only the first true branch of an if / elif / else runs.",
            success="They can say which branch runs in a given situation, and why."),
        "VAR": dict(
            task="Remember something between ticks",
            do=["Use me.memory to keep a state, e.g. me.memory['mode'] = 'attack'.",
                "Switch to 'escape' when me.armour < 30, and back to 'attack' when it is safe.",
                "Choose what to do with if me.memory.get('mode') == 'escape':"],
            teach="Ordinary variables are forgotten every tick. me.memory is a dictionary the game keeps between "
                  "ticks, so the brain can remember its state.",
            success="Their brain changes mode and stays in it until something changes."),
        "ALG": dict(
            task="Plan the brain before you code it",
            do=["Write the brain as steps (pseudocode or a flowchart): find a target, face it, drive, attack "
                "when close, keep out of the pit.",
                "Code ONE step, upload, test, then add the next.",
                "Design the arena with AI: ask for a layout that tests your brain."],
            teach="Decomposition and algorithms: a big problem becomes small steps in order. Testing each step "
                  "as you add it makes bugs easy to find.",
            success="Their flowchart or pseudocode matches the order of their code."),
        "AISAFE": dict(
            task="Design the arena with AI",
            do=["Press I. Target: The arena.",
                "Ask for exactly what may change, e.g. 'only the floor saws on, and name the arena Scrapyard'.",
                "No personal information. Say how you will test it."],
            teach="Limiting what the AI may change keeps the result safe and checkable. Vague requests get "
                  "surprising results.",
            success="Their request says exactly what may change and how to test it."),
    },
    4: {
        "AISAFE": dict(
            task="Change a game rule with AI",
            do=["Press I. Target: The rules.",
                "Choose ONE rule (damage_multiplier, gravity, match_seconds, spinner_energy_share...), "
                "a new value and a reason, e.g. 'damage_multiplier 0.8 so battles last longer'.",
                "No personal information. Say how you will test it."],
            teach="Be specific and limit the scope. The teacher approves every change before it goes in the game.",
            success="Their request names the variable, the value, the reason and a test."),
        "ALG": dict(
            task="Predict the knock-on effects",
            do=["Before sending, write what ELSE your change might affect "
                "(e.g. lower gravity: flips go higher and robots fly out of the arena).",
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
            do=["Fight with the new rule.",
                "Compare what happened with your prediction.",
                "Record the evidence in your review answers."],
            teach="Only a test shows whether the change works in the game.",
            success="Evidence from a fight supports their verdict."),
    },
    5: {
        "EVAL": dict(
            task="Evaluate your robot and your code",
            do=["After the tournament, write: what worked, what you would change, and where AI did and didn't help.",
                "Back each point with evidence: damage dealt, hits, knockouts, time survived.",
                "Save it in the Missions tab."],
            teach="An evaluation compares the result with the goal, using evidence, and says what to do next.",
            success="Three points, each backed by evidence."),
        "FUNC": dict(
            task="Tournament ready, and explain your code",
            do=["Enter the final battle with a design you built and a brain you uploaded.",
                "Your brain uses at least one function of your own.",
                "Explain one function to the group: what goes in, what comes out, and why you wrote it."],
            teach="Being able to explain your code shows you understand it (and that you wrote it).",
            success="They explain the parameters and the return value of one of their functions."),
        "AIREVIEW": dict(
            task="A new feature with AI",
            do=["Design a feature of your own, e.g. a shield that recharges (shield_recharge = 10).",
                "Send an AI card, then review the code when it comes back.",
                "Test it in a fight, and say where AI helped (the tool and the date)."],
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
AI_CARD_MISSION = {1: "1d", 3: "3e", 4: "4a"}
AI_REVIEW_MISSION = {1: "1e", 2: "2e", 4: "4b", 5: "5d"}
AI_TARGETS = {"robot": "My robot", "arena": "The arena", "rules": "The rules", "game": "The game (teacher only)"}

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
    words = lambda k: len(str(card.get(k, "")).split())
    if words("goal") < 1:  # (a few words can be enough for an idea)
        problems.append("Type your idea in the My idea box.")
    if words("test") < 6:
        problems.append("Say how you will test it (at least 6 words).")
    if words("predict") < 3:
        tips.append("Add a prediction: what do you expect to happen?")
    if not re.search(r"\d|[a-z]+_[a-z]+", str(card.get("variables", ""))):
        tips.append("Name a variable or give a number, for example shield_recharge = 10.")
    return problems, tips


def ai_prompt(card, learner):
    """The prompt the teacher pastes into an AI coding assistant, with the club's guardrails."""
    return f"""Learner request for Robot Lab (from {learner}, first name only).

GOAL: {card.get('goal', '').strip()}
VARIABLES / VALUES: {card.get('variables', '').strip()}
HOW THEY WILL TEST IT: {card.get('test', '').strip()}
THEIR PREDICTION: {card.get('predict', '').strip()}

Rules for the change:
- Change only the Robot Lab files (lab_sim.py, lab_server.py, lab_client.py, lab_missions.py).
- Keep names simple and add a short comment explaining each change for 13-18 year olds.
- No internet access, no reading or writing files other than these, no personal data.
- If the request is unclear or unsafe, say so instead of guessing. Don't add anything that wasn't asked for.
- Explain the change step by step so the learner can follow it and explain it back.
- Run a headless test fight that shows the feature working, and list what a learner should check.
"""
