"""Fight Lab lessons, missions and learning outcomes.

Each lesson switches on the right garage tools and hazards and gives learners missions.
Missions are checked by the server from what learners actually do (a design that was built,
a prediction then a test in the ring, a combo that lands, a brain that runs), and every tick is saved as
evidence against the learning outcomes below. Curriculum references live in OUTCOMES so a teacher
can see which part of the curriculum a mission covers. (The same outcomes as Robot Lab.)
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
    "ABS": ("Abstraction and modelling", "Explain how the game models a fight with a few numbers (timing, reach, "
                                         "damage, health)",
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
ALL_TOOLS = ["points_table", "walk_speed", "sidestep_speed", "jump_height", "attack_speed", "size",
             "choose_special", "combo_editor", "name_and_colour", "body_choice", "code_view", "stats_readout",
             "fighting_style"]
NO_HAZARDS = {"ring_out": False, "electric_ropes": False, "fire_jets": False, "slippery": False, "spikes": False}


def tools(*on, specials=("blast", "uppercut", "spin_kick", "slam")):
    t = {k: k in on for k in ALL_TOOLS + ["bosses"]}  # (playing as a boss: the teacher turns it on)
    t["specials"] = list(specials)
    return t


def hazards(*on):
    return {k: k in on for k in NO_HAZARDS}


LESSONS = {
    1: dict(title="Variables: tune your fighter", mode="practice", hazards=hazards("ring_out"),
            tools=tools("walk_speed", "sidestep_speed", "jump_height", "attack_speed", "size", "name_and_colour",
                        "body_choice", "code_view", "stats_readout", "fighting_style")),
    2: dict(title="Trade-offs, lists and robust programs: points and combos", mode="practice",
            hazards=hazards("ring_out", "fire_jets"), tools=tools(*ALL_TOOLS)),
    3: dict(title="Selection and functions: write a fighter brain", mode="practice",
            hazards=hazards("ring_out", "fire_jets", "slippery"), tools=tools(*ALL_TOOLS)),
    4: dict(title="Using AI to code, safely", mode="battle",
            hazards=hazards("electric_ropes", "fire_jets", "slippery"), tools=tools(*ALL_TOOLS)),
    5: dict(title="Invent, compete and evaluate", mode="battle",
            hazards=hazards("ring_out", "fire_jets", "slippery"), tools=tools(*ALL_TOOLS)),
}

# ---------- missions ----------
# id: (lesson, title, what to do, outcome codes, how it is checked)
MISSIONS = {
    # Mission 1 (as Robot Lab's: CHANGE 50 to 53): what the learner sees is the title; the text drops down when the
    # title is clicked, and is the explanation and the guidance. The Garage (the GUI) shows the fighter as variables.
    "1a": (1, "Change a STRING VARIABLE with the GUI",
           "In the Garage (G), under STRING VARIABLES, type a new name for your fighter in the STRING VALUE box and "
           "press BUILD MY FIGHTER. A string is text: letters, digits and spaces, in quotes. Its type is str.",
           ["VAR", "DATA"], "auto"),
    "1b": (1, "Change an INTEGER VARIABLE with the GUI",
           "In the Garage, under INTEGER VARIABLES, slide walk_speed and size to new values and press BUILD MY "
           "FIGHTER. An integer is a whole number (type int). Fight: what did each one change?",
           ["VAR", "DATA"], "auto"),
    "1c": (1, "Change a LIST VARIABLE with the GUI",
           "In the Garage, under VARIABLE LISTS, click a colour block and press BUILD MY FIGHTER. The colour is a "
           "list of three integers, [red, green, blue], each from 0 (none) to 255 (full). Its type is list.",
           ["DATA", "VAR"], "auto"),
    "1d": (1, "Hack the code",
           "Press C to open the code editor: your fighter as Python, every variable with its type. Change a value "
           "there and press BUILD MY FIGHTER in the code panel. The extra power here: you can see ALL the "
           "variables, even the ones the Garage doesn't show.",
           ["VAR", "DATA", "ALG"], "auto"),
    "1e": (1, "Safe use of AI",
           "Press I and use an AI request card to ask for a change in the game: your fighter, your special, your "
           "style, the stage, the bosses... almost anything you can imagine. No personal information. When the "
           "teacher keeps the change, look at what it did and answer the review questions.",
           ["AISAFE", "AIREVIEW"], "auto"),
    "2a": (2, "Spend exactly 100 points", "Share all 100 points between power, speed, defence and stamina.",
           ["ALG", "VAR"], "auto"),
    "2b": (2, "Invalid test data", "Try to build a fighter that breaks the rules (for example more than 100 "
                                  "points, or a combo of 6 moves) and read the error message.", ["VALID", "TEST"], "auto"),
    "2c": (2, "Boundary test data", "Build a fighter with one category at exactly 5 or exactly 50, or a combo of "
                                   "exactly 2 or exactly 5 moves.", ["VALID", "TEST"], "auto"),
    "2d": (2, "Your combo is a list", "Change your combo list (at least 3 moves), build it, then land the whole combo: "
                                     "press punch again each time a hit lands.", ["DATA", "ALG"], "auto"),
    "2e": (2, "Design from evidence", "After rebuilding, land 3 hits, then write why your design works.",
           ["EVAL", "TEST"], "auto"),
    "2f": (2, "AI rebalance", "Ask the AI to change your fighter's points, settings or combo for a reason you can "
                             "explain, then test whether it worked.", ["AIREVIEW", "TEST"], "auto"),
    "3a": (3, "A brain that runs", "Edit brains/my_brain.py, press U to upload it and P to switch autopilot on. "
                                  "It must run for 20 seconds without an error.", ["FUNC", "VAR"], "auto"),
    "3b": (3, "Make a decision", "Your brain uses if, elif or else (for example: block when they attack).", ["SEL"],
           "auto"),
    "3c": (3, "Write your own function", "Write a helper function and call it from brain().", ["FUNC", "ALG"], "auto"),
    "3d": (3, "Remember something", "Use me.memory to keep a value between ticks (for example a plan like "
                                   "'rush' or 'defend').", ["VAR", "SEL"], "auto"),
    "3e": (3, "A brain that lands hits", "With autopilot on, your brain lands 5 hits on your sparring partner.",
           ["SEL", "TEST"], "auto"),
    "3f": (3, "Design the stage with AI", "Ask the AI to change the stage (hazards, colours, name) and review what "
                                          "it did.", ["AISAFE", "ALG"], "auto"),
    "4a": (4, "Change the rules with AI", "Ask the AI to change a game rule (damage, gravity, round time, ring "
                                         "size...) and say why it makes the game better or fairer.", ["AISAFE", "ALG"],
           "auto"),
    "4b": (4, "Review the AI's code", "When the teacher marks your request ready, answer the review "
                                     "questions: does it work, did you test it, can you explain it?",
           ["AIREVIEW", "TEST"], "auto"),
    "4c": (4, "Spot the mistake", "Find what is wrong in a piece of AI-written code the teacher shows.",
           ["AIREVIEW"], "teacher"),
    "4d": (4, "Beat a boss", "Win a round against a boss fighter (the teacher chooses the computer's fighter).",
           ["TEST", "EVAL"], "auto"),
    "5a": (5, "Tournament ready", "Enter the final battle with a fighter you built and a brain you uploaded.",
           ["EVAL", "FUNC"], "auto"),
    "5b": (5, "Evaluate", "Write what worked, what you would change, and where AI did and didn't help.",
           ["EVAL", "AIREVIEW"], "auto"),
    "5d": (5, "A new feature with AI", "Ask the AI for a feature of your own design, then evaluate it with "
                                       "evidence from a fight.", ["EVAL", "AIREVIEW"], "auto"),
    "5c": (5, "Explain your code", "Explain one part of your brain code to the group.", ["FUNC", "EVAL"], "teacher"),
}
REFLECTIONS = {"2e": 8, "5b": 20}  # missions answered in writing: the fewest words that count


def missions_for(lesson):
    return {k: v for k, v in MISSIONS.items() if v[0] == lesson}


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
AI_TARGETS = {"fighter": "My fighter", "stage": "The stage", "rules": "The rules", "game": "The game (teacher only)"}

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
    if words("goal") < 6:
        problems.append("Describe the goal in a full sentence (at least 6 words).")
    if words("test") < 6:
        problems.append("Say how you will test it (at least 6 words).")
    if words("predict") < 3:
        tips.append("Add a prediction: what do you expect to happen?")
    if not re.search(r"\d|[a-z]+_[a-z]+", str(card.get("variables", ""))):
        tips.append("Name a variable or give a number, for example special_cost = 40.")
    return problems, tips


def ai_prompt(card, learner):
    """The request card as the teacher's record (saved in ai_requests/)."""
    return f"""Learner request for Fight Lab (from {learner}, first name only).

GOAL: {card.get('goal', '').strip()}
CHANGE: {AI_TARGETS.get(card.get('target'), card.get('target', ''))}
VARIABLES / VALUES: {card.get('variables', '').strip()}
HOW THEY WILL TEST IT: {card.get('test', '').strip()}
THEIR PREDICTION: {card.get('predict', '').strip()}

Rules for the change:
- Keep names simple and add a short comment explaining each change for 13-18 year olds.
- No internet access, no reading or writing files other than the game's, no personal data.
- If the request is unclear or unsafe, say so instead of guessing. Don't add anything that wasn't asked for.
- Explain the change step by step so the learner can follow it and explain it back.
- Run a headless test fight that shows the feature working, and list what a learner should check.
"""
