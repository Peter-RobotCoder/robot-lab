"""Craft Lab lessons, missions and learning outcomes (CHANGE 200): Robot Lab's course, for a world of blocks and a
Craft Bot each learner programs.

Each lesson switches on the right garage tools and world settings and gives learners missions. Missions are checked
by the server from what learners actually do (a Fabricator built, a night survived, iron refined, a Bot that dug
ten blocks with a loop, a blueprint of their own built, a Glitch rift patched), and every tick is saved as evidence against the learning
outcomes below. Curriculum references live in OUTCOMES so a teacher can see which part of the curriculum a mission
covers. The teacher can re-word any mission (and add or hide them) in the HUD's Outcomes tab: engine.teaching keeps
those edits. (The club desk runs this file on its own to print the scheme of work: it imports only ast and re.)
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
    "ITER": ("Iteration", "Repeat steps with a loop and stop it with a condition",
             "England KS3: use programming constructs such as iteration | OCR J277 2.2.1 iteration (count and "
             "condition controlled loops) | AQA 8525 3.2.2 | Scotland TCH 3-14a | Wales PS3 loops"),
    "SEL": ("Selection and Boolean logic", "Use if / elif / else and conditions with and, or, not",
            "England KS3: simple Boolean logic (AND, OR, NOT) | OCR J277 2.2.1 selection, Boolean operators | "
            "AQA 8525 3.2.2, 3.2.5 | Wales PS3 conditional statements"),
    "FUNC": ("Functions", "Write and call your own functions",
             "England KS3: modular programs that use procedures or functions | OCR J277 2.2.3 sub programs | "
             "AQA 8525 3.2.10 | Scotland TCH 4-14a"),
    "ALG": ("Algorithms and decomposition", "Break a task into steps and put them in the right order",
            "England KS3: key algorithms, computational thinking | OCR J277 2.1.1 decomposition, 2.1.2 | "
            "AQA 8525 3.1.1 | Scotland TCH 4-13b | Wales PS4 decompose problems"),
    "ABS": ("Abstraction and modelling", "Explain how the game models a world with a grid of numbers",
            "England KS3: computational abstractions that model the state and behaviour of real-world problems | "
            "OCR J277 2.1.1 abstraction | AQA 8525 3.1.1 | Scotland TCH 3-13b"),
    "VALID": ("Robust programs", "Explain input validation and test with normal, boundary and invalid data",
              "OCR J277 2.3.1 input validation, 2.3.2 normal, boundary and invalid test data | AQA 8525 3.2.11 | "
              "Scotland N5 input validation; normal, extreme and exceptional test data"),
    "TEST": ("Testing and evaluation", "Predict, test, compare results and improve",
             "England KS3: create, reuse, revise and repurpose digital artefacts | OCR J277 2.3.2 testing and "
             "refining | AQA 8525 3.2.11 | Scotland TCH 3-15a | Wales PS4 test strategies"),
    "AISAFE": ("Safe use of AI", "Write an AI request with no personal information and clear limits",
               "England KS3: use technology safely, respectfully, responsibly and securely, protecting online identity "
               "and privacy | DfE: no personal data in generative AI tools | Wales: legal, social and ethical consequences"),
    "AIREVIEW": ("Checking AI code", "Check AI-written code does what was asked, test it, explain it and say where AI helped",
                 "DfE: AI content needs critical judgement to check accuracy | JCQ: verify and acknowledge AI use "
                 "(tool and date) | Curriculum and Assessment Review 2025: use AI effectively without becoming dependent"),
    "EVAL": ("Evaluate and reflect", "Evaluate a design against evidence and say what to change next",
             "England KS3: attention to trustworthiness, design and usability | OCR J277 2.3.2 refining | "
             "Scotland TCH 4-15a evaluate and refine | N5 evaluation"),
}

# ---------- lessons ----------
# the learner's garage: what is shown and changeable (the Bot's three points, its name and colour, the code view and
# the stats readout); "mobs" lets the creatures out (the rifts at dusk, the Rust Walkers), "energy" makes Energy
# drain as you work, "brains" lets learners upload a Bot brain
ALL_TOOLS = ["points_table", "dig", "build", "speed", "name_and_colour", "code_view", "stats_readout"]
NO_HAZARDS = {"mobs": False, "energy": False}


def tools(*on):
    return {k: k in on for k in ALL_TOOLS + ["brains"]}


def hazards(*on):
    return {k: k in on for k in NO_HAZARDS}


LESSONS = {
    1: dict(title="Variables: build your Craft Bot", mode="practice", hazards=hazards(),
            tools=tools("dig", "build", "speed", "name_and_colour", "code_view", "stats_readout")),
    2: dict(title="Lists and dictionaries: blueprints and the first night", mode="practice",
            hazards=hazards("mobs", "energy"), tools=tools(*ALL_TOOLS)),
    3: dict(title="Loops: program your Craft Bot", mode="practice", hazards=hazards(),
            tools=tools(*ALL_TOOLS, "brains")),
    4: dict(title="Selection and functions: a Bot that decides", mode="practice", hazards=hazards("mobs"),
            tools=tools(*ALL_TOOLS, "brains")),
    5: dict(title="Invent and evaluate: a build of your own, with AI", mode="practice", hazards=hazards("mobs", "energy"),
            tools=tools(*ALL_TOOLS, "brains")),
}

# ---------- missions ----------
# id: (lesson, title, what to do, outcome codes, how it is checked)
MISSIONS = {
    "1a": (1, "Change a STRING VARIABLE with the GUI",
           "Press B for the Bot tab and open the GARAGE. Under STRING VARIABLES type a new bot_name and press BUILD MY "
           "BOT. A string is text in quotes. Its type is str.", ["VAR", "DATA"], "auto"),
    "1b": (1, "Change INTEGER VARIABLES with the GUI",
           "In the Garage, change two of dig, build and speed and press BUILD MY BOT. An integer is a whole number (int).",
           ["VAR", "DATA"], "auto"),
    "1c": (1, "Change a LIST VARIABLE with the GUI",
           "In the Garage, click a colour block and press BUILD MY BOT. The colour is a list of three integers, "
           "[red, green, blue]. Its type is list.", ["DATA", "VAR"], "auto"),
    "1d": (1, "Hack the code",
           "Press B, then CODE: your Bot as Python, every variable with its type. Change a value there and press "
           "BUILD MY BOT in the code panel.", ["VAR", "DATA", "ALG"], "auto"),
    "1e": (1, "Your first tools",
           "Chop a log by hand to start. In your Backpack (I) open BLUEPRINTS: build Boards, then a FABRICATOR (6 "
           "Boards and 2 Rubble), put it down, and at the Fabricator build Rods and a Mk1 Drill.", ["ALG", "DATA"], "auto"),
    "1f": (1, "Safe use of AI",
           "Open the AI card (Tab) and ask for a change in the game. No personal information. When the teacher "
           "keeps the change, check what it did and answer the review questions.", ["AISAFE", "AIREVIEW"], "auto"),
    "2a": (2, "A blueprint is a dictionary",
           "Build five different things. Each blueprint is a dictionary: what it makes, how many, and its parts, "
           "another dictionary of names and amounts (look at craft_items.BLUEPRINTS).", ["DATA", "ALG"], "auto"),
    "2b": (2, "Refine it", "Build a REFINERY at the Fabricator (6 Rubble, 3 Clay balls), put Iron ore in its queue and "
                           "Coal in its power slot, and take an Iron ingot from the tray.", ["ALG", "ABS"], "auto"),
    "2c": (2, "Survive the night", "Build a shelter with a door, light it with Glowsticks, and still be here when the "
                                   "sun comes up.", ["ALG", "TEST"], "auto"),
    "2d": (2, "A blueprint of your own", "Write a blueprint in mods/blueprints.py (or ask the AI for one) and build it "
                                         "in the game.", ["DATA", "AIREVIEW"], "auto"),
    "2e": (2, "Boundary test data", "Build a Bot with one point at exactly 10 or exactly 60.", ["VALID", "TEST"], "auto"),
    "2f": (2, "Invalid test data", "Open the code (B, then CODE), make the points add up to more than 100, press BUILD "
                                   "MY BOT and read why it is refused.", ["VALID", "TEST"], "auto"),
    "3a": (3, "A Bot that runs", "Put down a BOT DOCK and right-click it. Edit brains/my_bot.py, press U to upload it "
                                 "and P to switch the autopilot on. It must run for 20 seconds without an error.",
           ["FUNC", "VAR"], "auto"),
    "3b": (3, "A loop", "Your brain counts with bot.dug (or bot.memory) and stops after a number of blocks: a loop "
                        "that the game repeats, with a condition that ends it.", ["ITER", "VAR"], "auto"),
    "3c": (3, "Dig a tunnel", "Your Bot digs 10 blocks by itself.", ["ITER", "TEST"], "auto"),
    "3d": (3, "Build a tower", "Give your Bot blocks (right-click its dock: its slots are in the Bot tab) and have it "
                               "place 10 by itself.", ["ITER", "ALG"], "auto"),
    "3e": (3, "Use a for loop", "Use for ... in range(...) in your brain (for example to count the blocks it carries).",
           ["ITER"], "auto"),
    "4a": (4, "Make a decision", "Your brain uses if, elif or else (for example: dig if the block in front isn't air, "
                                 "else move).", ["SEL"], "auto"),
    "4b": (4, "Write your own function", "Write a helper function and call it from brain().", ["FUNC", "ALG"], "auto"),
    "4c": (4, "Remember something", "Use bot.memory to keep a value between turns (a mode like 'dig' or 'build').",
           ["VAR", "SEL"], "auto"),
    "4d": (4, "Mine an ore", "Your Bot digs a coal, copper or iron ore by itself (world.find helps).", ["SEL", "TEST"], "auto"),
    "4e": (4, "Defend the base", "Defeat a Glitch or a Rust Walker (a Zapper helps).", ["TEST"], "auto"),
    "4f": (4, "Patch a Glitch rift", "Rifts open at dusk. Build a PATCH at the Fabricator (a Battery and 2 Copper "
                                     "ingots) and right-click a rift with it to seal it.", ["ALG", "TEST"], "auto"),
    "5a": (5, "A build of your own", "Put down 100 blocks of a build, with a door, a Recharge Pod and Glowsticks.",
           ["ALG", "EVAL"], "auto"),
    "5b": (5, "A block of your own", "Add a block to mods/blocks.py (or ask the AI for one) and place it in the world.",
           ["DATA", "AIREVIEW"], "auto"),
    "5c": (5, "Evaluate", "Write what worked, what you would change, and where AI did and didn't help.",
           ["EVAL", "AIREVIEW"], "auto"),
    "5d": (5, "Explain your code", "Explain one part of your Bot's brain to the group.", ["FUNC", "EVAL"], "teacher"),
}
REFLECTIONS = {"5c": 20}


def points_words(text, limits):
    total = limits["points_total"]
    lo, hi = min(v[0] for v in limits["points"].values()), max(v[1] for v in limits["points"].values())
    if (total, lo, hi) == (100, 10, 60):
        return text
    text = re.sub(r"(?<=more than )100\b", str(total), text)
    return re.sub(r"\bexactly 10 or exactly 60\b", f"exactly {lo} or exactly {hi}", text)


def missions_for(lesson):
    return {k: v for k, v in MISSIONS.items() if v[0] == lesson}


# ---------- the teacher's lesson guide ----------
LESSON_TASKS = {
    1: "Your Craft Bot is a set of variables. Change a string (its name), integers (dig, build and speed) and a list "
       "(its colour) with the GUI, then hack the code. In the world, chop a log by hand and build your first tools "
       "from blueprints.",
    2: "Blueprints are data: dictionaries of parts and amounts. Build five things, build a Refinery and refine iron, "
       "survive a night with a shelter, a door and Glowsticks, write a blueprint of your own, and test the Bot's "
       "limits with boundary and invalid data.",
    3: "Program your Craft Bot. Its brain is a function the game calls again and again: that repeat is a loop, and a "
       "condition stops it. Dig a tunnel, build a tower, and use a for loop.",
    4: "A Bot that decides: if / elif / else, a function of your own, memory between turns. Find and mine an ore "
       "with world.find, defend your base, and patch a Glitch rift.",
    5: "Bring it together: a build of your own, a block of your own added with AI, then evaluate with evidence and "
       "explain your code to the group.",
}

GUIDE = {
    1: {
        "VAR": dict(task="Change variables with the GUI, then in the code",
                    do=["Press B for the Bot tab, then GARAGE: the Bot's name, its three points and its colour are "
                        "variables.",
                        "Change bot_name, two of the points and the colour, press BUILD MY BOT.",
                        "Press B, then CODE: find the line  dig: int = 34  and change it there, then BUILD MY BOT."],
                    teach="A variable is a name that stores a value. Changing the value changes how the program "
                          "behaves without rewriting the program.",
                    success="They can point to the variable they changed and say what it did."),
        "DATA": dict(task="Strings, integers and lists",
                     do=["Hover over STRING, INTEGER and LIST in the Garage.",
                         "In the code, every variable has its type: str, int or list."],
                     teach="A string is text, an integer a whole number, a list keeps values in order in [ ].",
                     success="They name the data type of three values in their Bot's code."),
        "ALG": dict(task="Your first tools, in order",
                    do=["Chop a log by hand to start (hold the left button).",
                        "I: the Backpack. BLUEPRINTS: build Boards from the log, then a Fabricator (6 Boards, 2 Rubble).",
                        "Put the Fabricator down: next to it, build Rods, then a Mk1 Drill (3 Rubble, 2 Rods)."],
                    teach="An algorithm is steps in the right order: you can't build a Drill before a Fabricator.",
                    success="They explain the order and why it matters."),
        "AISAFE": dict(task="Your first AI request",
                       do=["Press Tab and open the AI card.", "Ask for a change: your Bot's colour, a new block...",
                           "No personal information. Say how you will test it."],
                       teach="Never give an AI tool personal information. A good request has a goal, a limit and a test.",
                       success="Their card passes the checks with a clear goal and a test."),
        "AIREVIEW": dict(task="Check the AI's work",
                         do=["When the teacher keeps the change, check it in the game.", "Answer the review questions."],
                         teach="AI can be wrong: check its work against your prediction.",
                         success="Their answers say what they tested."),
    },
    2: {
        "DATA": dict(task="A blueprint is a dictionary",
                     do=["Open craft_items.py and find BLUEPRINTS: each one is a dictionary.",
                         "Its parts are another dictionary: a part's name, and how many.",
                         "Build five different things."],
                     teach="Lists keep things in order; dictionaries look things up by a key.",
                     success="They read a blueprint aloud: what each key and value says."),
        "ALG": dict(task="Plan for the night",
                    do=["Before dusk: a shelter, a door, Glowsticks (a Rod and Coal).", "Refine iron for better tools.",
                        "A suit at the Fabricator (Fluff from brushing a Fluff, then upgrade it with ingots): "
                        "right-click a piece to wear it. It gives you a Shield."],
                    teach="Decomposition: surviving the night is small jobs in an order.",
                    success="Their plan lists the jobs in order."),
        "ABS": dict(task="The world is a grid of numbers",
                    do=["Press ` (backtick): the dev panel shows your x, y and z.",
                        "Every block is a number in a 3D list (craft_world.py)."],
                    teach="Abstraction: a whole island is one grid of numbers, each a block.",
                    success="They explain what one number in the grid stands for."),
        "VALID": dict(task="Break the rules on purpose",
                      do=["Open the code, set dig to 70: refused.", "Make the points add up to 110: refused, and why.",
                          "Set one to exactly 10, then 60: accepted (boundary data)."],
                      teach="Validation checks input before it is used: normal, boundary and invalid data.",
                      success="They give an example of each and what the program did."),
        "TEST": dict(task="Did the plan work?",
                     do=["After the night: what kept you safe, what didn't?"],
                     teach="Testing a plan means comparing what happened with what you expected.",
                     success="They name one change they'd make for the next night."),
        "AIREVIEW": dict(task="A blueprint with AI",
                         do=["Ask the AI for a blueprint of your own in mods/blueprints.py.", "Build it to test it."],
                         teach="Test an AI change in the game before you trust it.",
                         success="They built their blueprint and say whether it did what they asked."),
    },
    3: {
        "ITER": dict(task="The brain is called again and again",
                     do=["Open brains/my_bot.py. brain(bot, world) is asked what to do next, every time the Bot is ready.",
                         "That repeat is a loop: the condition  if bot.dug >= 10  stops it.",
                         "Change 10 to 20, upload (U), watch it dig further."],
                     teach="Iteration repeats steps. A condition-controlled loop stops when its condition says so.",
                     success="They say where the loop is and what stops it."),
        "VAR": dict(task="Counting",
                    do=["Use bot.memory['count'] to count the blocks placed."],
                    teach="A variable that counts goes up by one each time round the loop.",
                    success="Their count matches what the Bot did."),
        "FUNC": dict(task="A brain that runs",
                     do=["Upload with U, switch on with P: 20 seconds without an error."],
                     teach="brain() is a function the game calls: what goes in (bot, world) and what comes out (an action).",
                     success="Their Bot runs for 20 seconds."),
        "ALG": dict(task="A tower",
                    do=["Give the Bot blocks at its dock.", "Brain: place below, then up, ten times."],
                    teach="Two steps repeated build a tower: the order inside the loop matters.",
                    success="Their tower is ten high."),
        "TEST": dict(task="Predict, then watch",
                     do=["Predict how many blocks the tunnel will be before switching on.", "Count them after."],
                     teach="Predict, test, compare.", success="Their prediction was written down first."),
    },
    4: {
        "SEL": dict(task="Make a decision",
                    do=["if bot.front == 'air': return 'forward'  else: return 'dig'",
                        "Use and / or: if bot.below == 'air' and bot.has('rubble'): ..."],
                    teach="Selection chooses which code runs; conditions are True or False.",
                    success="They say which branch runs in a given place."),
        "FUNC": dict(task="Your own function",
                     do=["def ore_near(world): return world.find('coal_ore')", "Call it in brain()."],
                     teach="A function has a name, parameters and a return value.",
                     success="Their brain calls a function of their own."),
        "VAR": dict(task="Memory between turns",
                    do=["bot.memory['mode'] = 'dig' ... switch to 'home' when full."],
                    teach="Ordinary variables are forgotten each turn; bot.memory is kept.",
                    success="Their Bot changes mode and stays in it."),
        "ALG": dict(task="Plan an ore hunt, and a rift patrol",
                    do=["Write the steps: look, turn towards it, dig, carry on.",
                        "Before dusk: a Patch from the Fabricator, ready for the first rift."],
                    teach="Break the problem into steps and code one at a time.", success="Their plan matches their code."),
        "TEST": dict(task="Defend the base", do=["At night, beat a Glitch or a Rust Walker with a Zapper, and patch a rift."],
                     teach="Test the base's defences: a patched rift sends out no more Glitches.", success="They survived."),
    },
    5: {
        "ALG": dict(task="A build of your own",
                    do=["Plan it, then build: walls, a door, a Recharge Pod, Glowsticks (100 blocks)."],
                    teach="A big build is many small plans.", success="Their build matches their plan."),
        "DATA": dict(task="A block of your own", do=["Add a dictionary to BLOCKS in mods/blocks.py."],
                     teach="A new block is a dictionary of its properties.", success="Their block is in the world."),
        "EVAL": dict(task="Evaluate", do=["Write what worked, what you'd change, where AI helped."],
                     teach="An evaluation compares the result with the goal, using evidence.", success="Three points with evidence."),
        "FUNC": dict(task="Explain your code", do=["Explain one function of your Bot's brain to the group."],
                     teach="Explaining your code shows you understand it.", success="They explain its parameters and return value."),
        "AIREVIEW": dict(task="Credit AI", do=["Say where AI helped (the tool and the date)."],
                         teach="Crediting AI help is how AI is used honestly.", success="They say what they checked."),
    },
}


def outcome_lessons(code):
    return [n for n, pieces in GUIDE.items() if code in pieces]


def missions_for_outcome(lesson, code):
    return {k: v for k, v in MISSIONS.items() if v[0] == lesson and code in v[3]}


# ---------- checking a brain's code for missions ----------
def brain_features(source):
    """What a brain uses: selection, loops, its own functions, memory."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found = set()
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp)):
            found.add("if")
        if isinstance(node, ast.For):
            found.add("for")
        if isinstance(node, ast.While):
            found.add("while")
        if isinstance(node, ast.Attribute) and node.attr == "memory":
            found.add("memory")
        if isinstance(node, ast.Compare) and any(isinstance(n, ast.Attribute) and n.attr in ("dug", "placed", "moves")
                                                 for n in [node.left] + node.comparators):
            found.add("count")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in funcs - {"brain"}:
            found.add("own_function")
    return found


AI_CARD_MISSION = {1: "1f", 2: "2d", 5: "5b"}
AI_REVIEW_MISSION = {1: "1f", 2: "2d", 5: "5b"}
AI_TARGETS = {"bot": "My Craft Bot", "world": "The world", "rules": "The rules", "game": "The game (teacher only)"}

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
    if words("goal") < 1:
        problems.append("Type your idea in the My idea box.")
    if words("test") < 6:
        problems.append("Say how you will test it (at least 6 words).")
    if words("predict") < 3:
        tips.append("Add a prediction: what do you expect to happen?")
    if not re.search(r"\d|[a-z]+_[a-z]+", str(card.get("variables", ""))):
        tips.append("Name a variable or give a number, for example light = 15.")
    return problems, tips


def ai_prompt(card, learner):
    """The prompt the teacher pastes into an AI coding assistant, with the club's guardrails."""
    return f"""Learner request for Craft Lab (from {learner}, first name only).

GOAL: {card.get('goal', '').strip()}
VARIABLES / VALUES: {card.get('variables', '').strip()}
HOW THEY WILL TEST IT: {card.get('test', '').strip()}
THEIR PREDICTION: {card.get('predict', '').strip()}

Rules for the change:
- Change only the Craft Lab files (craft_*.py and the mods: mods/blocks.py, mods/blueprints.py, mods/world.py,
  mods/rules.py, mods/bots/<name>.py).
- A window predicts its own player with the same craft_sim step the server runs: anything that changes how a
  player moves must stay deterministic (no random numbers in a step) and live in craft_sim.
- Keep names simple and add a short comment explaining each change for 13-18 year olds.
- No internet access, no reading or writing files other than these, no personal data.
- If the request is unclear or unsafe, say so instead of guessing. Don't add anything that wasn't asked for.
- Explain the change step by step so the learner can follow it and explain it back.
- Run the game's test (craft_test.py quick) to show the feature working, and list what a learner should check.
"""
