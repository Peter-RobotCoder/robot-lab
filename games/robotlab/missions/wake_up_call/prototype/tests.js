/* The Wake-Up Call tests. Run by tests/run_node.js (node) and by index.html?selftest=1 (a browser).
   run({Pseudo, Game, dict}) returns [{name, pass, detail}]. */
(function (root) {
  "use strict";

  // The whole mission in one program, written the messy way a learner might (capitals, punctuation, synonyms).
  const SOLUTION = [
    "# 1 Battery",
    "Move forward 3.",
    "turn right",
    "go ahead one step",
    "Pick up the power cell!",
    "# 2 Tool",
    "turn left",
    "move forward 2",
    "turn right",
    "repeat 3 times",
    "  move forward 1",
    "end",
    "grab the front spinner",
    "# 3 Blockage",
    "turn right",
    "move forward 3",
    "turn left",
    "move forward 2",
    "use spinner",
    "# 4 Village",
    "move forward 6",
    "# 5 Repair",
    "turn right",
    "repair",
  ].join("\n");

  // The same route as five separate runs, one per objective.
  const STEPS = [
    ["Battery", "move forward 3\nturn right\nmove forward 1\npick up power cell"],
    ["Tool", "turn left\nmove forward 2\nturn right\nmove forward 3\npick up spinner"],
    ["Blockage", "turn right\nmove forward 3\nturn left\nmove forward 2\nuse spinner"],
    ["Village", "move forward 6"],
    ["Repair", "turn right\nrepair"],
  ];

  // phrase -> the Python it must become
  const PHRASES = [
    ["Move forward 3.", "robot.move_forward(3)"],
    ["please turn LEFT!", "robot.turn_left()"],
    ["Go ahead three steps", "robot.move_forward(3)"],
    ["Grab the battery", 'robot.pick_up("power cell")'],
    ["pick up the power cell", 'robot.pick_up("power cell")'],
    ["Use the front spinner.", 'robot.use("spinner")'],
    ["use the wedge", 'robot.use("flipper")'],
    ["Fix the generator", "robot.repair()"],
    ["repair the village power supply", "robot.repair()"],
    ["move back 1", "robot.move_back(1)"],
    ["rotate right", "robot.turn_right()"],
    ["Repeat twice", "for i in range(2):"],
    ["loop 4 times", "for i in range(4):"],
  ];

  // near misses: [phrase, the hint it must give (null: no hint), words the message must contain]
  const NEAR_MISSES = [
    ["mvoe forward 3", "move forward 3", "don't know"],
    ["move 3 forward", "move forward 3", "wrong order"],
    ["turn lfet", "turn left", "don't know"],
    ["use spiner", "use spinner", "don't know"],
    ["pick up the powr cell", "pick up power cell", "don't know"],
    ["repeat 3", "repeat 3 times", "missing"],
    ["forward 2", "move forward 2", "missing"],
    ["move forward 3 quickly", "move forward 3", "quickly"],
    ["move forward", null, "needs a number"],
    ["move forward 50", null, "from 1 to 20"],
    ["turn up", null, "left or right"],
    ["jump over the rocks", null, "don't recognise"],
    ["please", null, "only filler"],
  ];

  function run(api) {
    const { Pseudo, Game, dict } = api;
    const C = Pseudo.compile(dict);
    const out = [];
    const check = (name, pass, detail) => out.push({ name, pass: !!pass, detail: pass ? "" : detail });

    // ----- the interpreter, a line at a time -----
    for (const [text, py] of PHRASES) {
      const r = Pseudo.parseProgram(py.startsWith("for ") ? text + "\nturn left\nend" : text, C);  // a repeat needs a body and an end
      check(`phrase "${text}" -> ${py}`, r.program && r.rows[0].python === py, JSON.stringify(r.rows[0]));
    }
    for (const [text, hint, words] of NEAR_MISSES) {
      const r = Pseudo.parseProgram(text, C);
      const row = r.rows[0];
      check(`near miss "${text}" -> ${hint ? "did you mean " + hint : words}`,
        row.kind === "error" && r.program === null && row.hint === hint && row.message.toLowerCase().includes(words.toLowerCase()),
        JSON.stringify({ kind: row.kind, message: row.message, hint: row.hint }));
    }
    check("deterministic: the same line twice gives the same result",
      JSON.stringify(Pseudo.parseProgram("mvoe 3 forwrd", C).rows) === JSON.stringify(Pseudo.parseProgram("mvoe 3 forwrd", C).rows), "");
    check("ignores case and punctuation", Pseudo.parseProgram("MOVE, forward: 3!!!", C).rows[0].python === "robot.move_forward(3)", "");

    // ----- structure -----
    const st = (t) => Pseudo.parseProgram(t, C);
    check("an end with no repeat is an error", st("end").rows[0].message.includes("no repeat"), JSON.stringify(st("end").rows[0]));
    check("a repeat with no end is an error", st("repeat 2 times\nmove forward 1").rows[0].message.includes("needs an end"), "");
    check("an empty repeat is an error", st("repeat 2 times\nend").rows[1].message.includes("nothing inside"), "");
    check("one bad line stops the whole program running", st("move forward 1\nmvoe forward 2\nturn left").program === null, "");
    const nested = st("repeat 2 times\nrepeat 3 times\nmove forward 1\nend\nturn left\nend");
    check("nested repeats translate to nested Python",
      nested.python === "for i in range(2):\n    for j in range(3):\n        robot.move_forward(1)\n    # end of repeat\n    robot.turn_left()\n# end of repeat",
      "\n" + nested.python);
    check("comments and blank lines are kept but don't count as code", st("# hi\n\nturn left").codeLines === 1, "");

    // ----- the mission -----
    const runText = (m, text) => { const p = Pseudo.parseProgram(text, C); if (!p.program) throw new Error("did not parse: " + text + " " + JSON.stringify(p.errors)); return m.run(p.program, p.codeLines); };
    const m = Game.newMission("TITAN");
    check("the robot starts with a low battery", m.s.energy === Game.RULES.energyStart && m.s.energy < 10, String(m.s.energy));
    STEPS.forEach(([title, text], i) => {
      const res = runText(m, text);
      const obj = m.objectives();
      check(`step ${i + 1} (${title}) completes with its run`, obj.slice(0, i + 1).every((o) => o.done) && obj.slice(i + 1).every((o) => !o.done),
        JSON.stringify({ status: res.status, s: m.s, done: obj.map((o) => o.done) }));
    });
    check("five runs complete the mission", m.s.complete, JSON.stringify(m.s));
    check("the power cell recharged the battery", m.s.energy === Game.RULES.energyStart - 4 + Game.RULES.cellCharge - 5 - 5 - 2 - 6 - 3, String(m.s.energy));
    const stars = m.stars();
    check("an efficient short run earns three stars", stars.count === 3, JSON.stringify(stars));

    const one = Game.newMission("RAZORBACK");
    const p1 = Pseudo.parseProgram(SOLUTION, C);
    check("the one-program solution parses", p1.program !== null, JSON.stringify(p1.errors.map((r) => r.n + " " + r.message)));
    const r1 = one.run(p1.program, p1.codeLines);
    check("the one-program solution completes the mission (RAZORBACK)", r1.status === "complete" && one.s.complete, JSON.stringify(one.s));
    check("events are produced for the animation", r1.events.length > 20 && r1.events[r1.events.length - 1].type === "complete", String(r1.events.length));

    const flat = Game.newMission("TITAN");
    const rf = runText(flat, "move forward 5\nturn right\nmove forward 4");
    check("skipping the power cell flattens the battery", rf.status === "flat" && flat.s.failed && flat.s.energy === 0, JSON.stringify(flat.s));

    const tool = Game.newMission("TITAN");
    runText(tool, STEPS[0][1]); runText(tool, STEPS[1][1].replace("spinner", "flipper"));
    runText(tool, STEPS[2][1].replace("use spinner", "use flipper"));
    check("the wrong tool doesn't clear the rockfall", !tool.s.rockCleared && tool.s.toolPicked, JSON.stringify(tool.s));
    const bump = runText(tool, "move forward 1");
    check("the rockfall blocks the way until it is cleared", bump.status === "stopped" && tool.s.x === 7, JSON.stringify(tool.s));
    const nope = runText(tool, "use spinner");
    check("you can't use a tool you aren't holding", nope.status === "stopped" && !tool.s.rockCleared, JSON.stringify(nope.events.map((e) => e.msg)));

    const wall = Game.newMission("TITAN");
    const rw = runText(wall, "turn left\nmove forward 3\nturn right");
    check("a wall stops the run and the robot stays put", rw.status === "stopped" && wall.s.x === 1 && wall.s.y === 6 && wall.s.dir === 3, JSON.stringify(wall.s));

    const early = Game.newMission("TITAN");
    check("repair does nothing away from the power supply", runText(early, "repair").status === "stopped" && !early.s.complete, "");

    const lots = Game.newMission("TITAN");
    const big = runText(lots, "repeat 20 times\nrepeat 20 times\nrepeat 20 times\nturn left\nend\nend\nend");
    check("a run is capped at " + Game.RULES.maxActions + " steps", big.status === "stopped", big.status);
    return out;
  }

  root.CCTests = { run, SOLUTION, STEPS, PHRASES, NEAR_MISSES };
  if (typeof module !== "undefined") module.exports = root.CCTests;
})(typeof window !== "undefined" ? window : globalThis);
