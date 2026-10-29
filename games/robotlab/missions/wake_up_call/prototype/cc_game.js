/* The mission. No drawing here: run() takes a parsed program and returns the events to animate. */
(function (root) {
  "use strict";
  // The robots and tools are Robot Lab's own (robot-lab: games/robotlab/mods/robots/*.py and lab_sim.WEAPONS).
  // In the arena the tools are weapons; on this mission they are tools.
  const ROBOTS = {
    TITAN: {
      name: "TITAN", colour: [235, 110, 20], weapon: "wedge",
      points: { speed: 25, attack: 25, armour: 30, control: 20 },
      settings: { forward_speed: 85, reverse_speed: 70, turn_speed: 75, acceleration: 75, size: 105 },
      style: { trim: [28, 28, 32], lights: [255, 170, 40], number: "TITAN" },
      blurb: "A heavy wedge. Its own tool is the flipper.",
    },
    RAZORBACK: {
      name: "RAZORBACK", colour: [200, 20, 28], weapon: "spinner",
      points: { speed: 25, attack: 35, armour: 20, control: 20 },
      settings: { forward_speed: 80, reverse_speed: 60, turn_speed: 70, acceleration: 70, size: 100 },
      style: { trim: [225, 225, 230], lights: [60, 170, 255], number: "RAZOR" },
      blurb: "A low, quick robot. Its own tool is the front spinner.",
    },
  };
  const TOOLS = {  // the mission's name for each: Robot Lab's weapon type
    spinner: { weapon: "spinner", name: "Front spinner", text: "a spinning bar at the front that stores energy: it grinds through rock" },
    flipper: { weapon: "wedge", name: "Flipper", text: "a wedge with a flipper: it scoops things up and lifts them" },
    hammer: { weapon: "hammer", name: "Hammer", text: "an arm that swings down over the top" },
    drum: { weapon: "drum", name: "Drum", text: "a vertical spinner: it throws things upwards" },
  };
  // # rock wall   . ground   S start   C power cell   T supply crate (the tools)   R rockfall
  // V village     H house    G the village power supply
  const MAP = [
    "################",
    "#....T..########",
    "#.......#VVVVVV#",
    "#.C.....#VHVVHV#",
    "#.......RVVVVVV#",
    "#.......#VVHVGV#",
    "#S......#VVVVVV#",
    "################",
  ];
  const W = MAP[0].length, H = MAP.length;
  const DX = [0, 1, 0, -1], DY = [-1, 0, 1, 0];  // north, east, south, west
  const DIR_NAMES = ["north", "east", "south", "west"];
  const RULES = {
    energyStart: 8, energyMax: 30, cellCharge: 25,
    cost: { move: 1, turn: 0, use: 2, repair: 3, pick: 0 },
    stars: { energy: 6, lines: 20 },  // a star for finishing, one for this much energy left, one for this few lines
    maxActions: 2000,
  };
  const OBJECTIVES = [
    { id: "battery", title: "Battery", text: "Find a power cell and pick it up to recharge." },
    { id: "tool", title: "Tool", text: "Pick up a tool from the supply crate." },
    { id: "blockage", title: "Blockage", text: "Face the rockfall and use the right tool to clear it." },
    { id: "village", title: "Village", text: "Drive into Brookfield village." },
    { id: "repair", title: "Repair", text: "Face the village power supply and repair it." },
  ];
  const UNLOCK = { id: "solar_panel", name: "Solar Panel", text: "A spare solar panel from Brookfield, fitted to your robot's back. In Mission 2 it recharges 1 energy for every 5 squares you drive." };
  let START = null;
  MAP.forEach((row, y) => { const x = row.indexOf("S"); if (x >= 0) START = { x, y, dir: 0 }; });

  function find(ch) { for (let y = 0; y < H; y++) { const x = MAP[y].indexOf(ch); if (x >= 0) return { x, y }; } return null; }

  function tileAt(s, x, y) {
    if (x < 0 || y < 0 || x >= W || y >= H) return "#";
    const t = MAP[y][x];
    if (t === "R" && s.rockCleared) return "r";
    if (t === "C" && s.cellTaken) return ".";
    if (t === "S") return ".";
    return t;
  }
  const BLOCKS = {
    "#": "Bump! A rock wall is in the way.",
    R: "Bump! The rockfall blocks the pass. Face it and use the right tool to clear it.",
    H: "Bump! That's a house.",
    G: "Bump! That's the village power supply. Face it and repair it.",
  };

  function Mission(robotName) {
    if (!ROBOTS[robotName]) throw new Error("No robot called " + robotName);
    this.robot = ROBOTS[robotName];
    this.s = {
      x: START.x, y: START.y, dir: START.dir, energy: RULES.energyStart, tool: null,
      cellTaken: false, toolPicked: false, rockCleared: false, inVillage: false, repaired: false,
      linesUsed: 0, runs: 0, failed: false, complete: false,
    };
  }
  Mission.prototype.snapshot = function () { return Object.assign({}, this.s); };
  Mission.prototype.objectives = function (s) {
    s = s || this.s;
    const done = [s.cellTaken, s.toolPicked, s.rockCleared, s.inVillage, s.repaired];
    const now = done.indexOf(false);
    return OBJECTIVES.map((o, i) => Object.assign({ done: done[i], now: i === now }, o));
  };
  Mission.prototype.stars = function (s) {
    s = s || this.s;
    const energy = s.energy >= RULES.stars.energy, lines = s.linesUsed <= RULES.stars.lines;
    return { complete: s.complete, energy, lines, count: s.complete ? 1 + (energy ? 1 : 0) + (lines ? 1 : 0) : 0 };
  };

  Mission.prototype.run = function (program, codeLines) {
    const s = this.s;
    if (s.complete || s.failed) return { events: [], status: s.complete ? "complete" : "flat" };
    s.linesUsed += codeLines || 0;
    s.runs += 1;
    const events = [];
    const STOP = {};
    const say = (type, line, msg, tone) => events.push({ type, line, msg, tone, state: this.snapshot() });
    let actions = 0;
    const pay = (cost, what, line) => {
      if (s.energy >= cost) { s.energy -= cost; return; }
      const onCell = tileAt(s, s.x, s.y) === "C";
      let msg = `Not enough energy: ${what} needs ${cost} and the battery has ${s.energy}.`;
      if (s.energy < RULES.cost.move && !onCell) {
        s.failed = true;
        msg += " The battery is flat. Restart the mission and plan a shorter route (or reach the power cell sooner).";
      }
      say("flat", line, msg, "bad");
      throw STOP;
    };
    const exec = (ops) => {
      for (const op of ops) {
        if (op.action === "repeat") { for (let k = 0; k < op.values.n; k++) exec(op.body); continue; }
        if (++actions > RULES.maxActions) { say("stop", op.line, "That's too many steps for one run.", "bad"); throw STOP; }
        this.act(op, say, pay, STOP);
      }
    };
    let status = "done";
    try { exec(program); } catch (e) {
      if (e !== STOP) throw e;
      status = s.complete ? "complete" : s.failed ? "flat" : "stopped";
    }
    return { events, status };
  };

  Mission.prototype.act = function (op, say, pay, STOP) {
    const s = this.s, v = op.values, line = op.line;
    const front = () => tileAt(s, s.x + DX[s.dir], s.y + DY[s.dir]);
    switch (op.action) {
      case "move_forward":
      case "move_back": {
        const step = op.action === "move_forward" ? 1 : -1;
        for (let k = 0; k < v.n; k++) {
          const nx = s.x + DX[s.dir] * step, ny = s.y + DY[s.dir] * step;
          const t = tileAt(s, nx, ny);
          if (BLOCKS[t]) { say("bump", line, BLOCKS[t], "bad"); throw STOP; }
          pay(RULES.cost.move, "a square", line);
          s.x = nx; s.y = ny;
          say("move", line);
          if (t === "V" && !s.inVillage) { s.inVillage = true; say("objective", line, "You've reached Brookfield village! Now find the power supply.", "ok"); }
        }
        return;
      }
      case "turn":
        s.dir = (s.dir + (v.dir === "left" ? 3 : 1)) % 4;
        say("turn", line, null);
        return;
      case "pick_up": {
        const here = tileAt(s, s.x, s.y);
        if (v.item === "power cell") {
          if (here !== "C") { say("info", line, "There's no power cell on this square.", "bad"); throw STOP; }
          s.cellTaken = true;
          const before = s.energy;
          s.energy = Math.min(RULES.energyMax, s.energy + RULES.cellCharge);
          say("objective", line, `Power cell fitted: energy ${before} → ${s.energy}.`, "ok");
          return;
        }
        if (here !== "T") { say("info", line, `There's no ${v.item} here. The tools are in the supply crate.`, "bad"); throw STOP; }
        if (s.tool === v.item) { say("info", line, `You're already holding the ${v.item}.`, "info"); return; }
        const old = s.tool;
        s.tool = v.item;
        const first = !s.toolPicked;
        s.toolPicked = true;
        say(first ? "objective" : "info", line, (old ? `You put the ${old} back and picked up the ${v.item}` : `You picked up the ${v.item}`) + ` (${TOOLS[v.item].text}).`, first ? "ok" : "info");
        return;
      }
      case "use": {
        if (s.tool !== v.tool) {
          say("info", line, s.tool ? `You're holding the ${s.tool}, not the ${v.tool}.` : `You aren't holding a ${v.tool}. Pick one up from the supply crate first.`, "bad");
          throw STOP;
        }
        pay(RULES.cost.use, `using the ${v.tool}`, line);
        const t = front();
        if (t === "R") {
          if (v.tool === "spinner") { s.rockCleared = true; say("use", line, "The front spinner grinds through the rockfall. The pass is clear!", "ok"); return; }
          const why = {
            flipper: "The flipper lifts one rock and drops it again. The pile's too big to lift: a tool that cuts would grind through it.",
            hammer: "The hammer chips at the rocks but the pile doesn't move. Something that spins and cuts sideways would grind through.",
            drum: "The drum throws grit upwards but can't reach into the pile. A flat spinning bar at the front would cut into it.",
          }[v.tool];
          say("use", line, why, "info");
          return;
        }
        say("use", line, `The ${v.tool} works, but there's nothing in front of you to use it on.`, "info");
        return;
      }
      case "repair": {
        if (front() !== "G") { say("info", line, "There's nothing in front of you to repair.", "bad"); throw STOP; }
        pay(RULES.cost.repair, "a repair", line);
        s.repaired = true; s.complete = true;
        say("complete", line, "The power supply hums back to life. The lights come on all over Brookfield!", "ok");
        throw STOP;
      }
      default:
        say("info", line, "The robot doesn't know how to do that yet.", "bad");
        throw STOP;
    }
  };

  root.CCGame = { ROBOTS, TOOLS, MAP, W, H, DX, DY, DIR_NAMES, RULES, OBJECTIVES, UNLOCK, START, tileAt, find, newMission: (name) => new Mission(name) };
})(typeof window !== "undefined" ? window : globalThis);
