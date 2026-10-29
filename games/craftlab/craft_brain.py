"""Load a learner's Craft Bot brain safely and let it drive their Bot (CHANGE 200).

City Lab's arrangement: the file is checked (brain_rules.py: only functions and import math/random, no files, no
hidden __ names, a small set of built-ins), then runs in its own small process (brain_worker.py) with a memory limit
and a limit on how long each turn may take. A brain that crashes just stops; the error and its line number go back
to the learner. The world carries on for everyone else.

A Bot does one thing at a time (a move, a dig, a placement), so its brain is asked once each time the Bot is
ready for the next thing: the question is sent and the answer read when it comes (a later step), so a slow brain
never holds up the world. What the brain sees is plain numbers and words (bot_data, world_data); brain_worker
turns them back into bot.front, world.block(1, 0, 0) and so on.
"""
import ast
import json
import queue
import subprocess
import sys
import threading
import time

import brain_rules as rules

import os
HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "brain_worker.py")
LOAD_SECONDS = 5.0
TURN_SECONDS = 0.5     # a brain that hasn't answered in this long is stopped
TOO_LONG = "brain took too long (is there a loop that never ends?)"
SEE = 4                # world.block reaches this many blocks each way


class BrainError(Exception):
    pass


class SandboxedBrain:
    """One learner's brain, running in its own process."""

    def __init__(self, source, fname):
        self.source, self.fname = source, fname
        self.proc = None
        self._start()

    def _start(self):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen([sys.executable, "-I", WORKER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, cwd=HERE, creationflags=flags)
        self.replies = queue.Queue()
        threading.Thread(target=self._read, args=(self.proc, self.replies), daemon=True).start()
        self.pending = None
        reply = self._ask({"source": self.source, "fname": self.fname}, LOAD_SECONDS, "brain took too long to load")
        if "error" in reply:
            self.close()
            raise BrainError(reply["error"])

    @staticmethod
    def _read(proc, replies):
        for raw in proc.stdout:
            try:
                replies.put(json.loads(raw))
            except ValueError:
                pass
        replies.put({"error": "brain stopped (it may have used too much memory)", "dead": True})

    def _ask(self, msg, seconds, too_long=TOO_LONG):
        if not self.alive():
            return {"error": "brain stopped (it may have used too much memory)"}
        try:
            self.proc.stdin.write(json.dumps(msg, separators=(",", ":")).encode("utf-8") + b"\n")
            self.proc.stdin.flush()
            reply = self.replies.get(timeout=seconds)
        except queue.Empty:
            self.close()
            return {"error": too_long}
        except OSError:
            self.close()
            return {"error": "brain stopped (it may have used too much memory)"}
        if reply.get("dead"):
            self.close()
        return reply

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def ask(self, bot, world):
        """Send a turn's question (the answer is read by answer(), a step or two later)."""
        if not self.alive():
            raise BrainError("brain stopped (it may have used too much memory)")
        try:
            self.proc.stdin.write(json.dumps({"bot": bot, "world": world}, separators=(",", ":")).encode("utf-8") + b"\n")
            self.proc.stdin.flush()
        except OSError:
            self.close()
            raise BrainError("brain stopped (it may have used too much memory)")
        self.pending = time.perf_counter()

    def answer(self):
        """The answer to the question asked, [action, extra], or None if it hasn't come yet (raises BrainError for a
        brain that went wrong or took too long)."""
        if self.pending is None:
            return None
        try:
            reply = self.replies.get_nowait()
        except queue.Empty:
            if time.perf_counter() - self.pending > TURN_SECONDS:
                self.close()
                self.pending = None
                raise BrainError(TOO_LONG)
            return None
        self.pending = None
        if reply.get("dead"):
            self.close()
        if "error" in reply:
            raise BrainError(reply["error"])
        return reply["r"]

    def reset(self):
        """Forget bot.memory (and start again if the brain had stopped)."""
        if self.pending is not None:
            try:
                self.replies.get(timeout=TURN_SECONDS)
            except queue.Empty:
                pass
            self.pending = None
        if self.alive():
            self._ask({"reset": True}, LOAD_SECONDS)
        else:
            try:
                self._start()
            except BrainError:
                pass

    def close(self):
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=2)
            except Exception:
                pass
            self.proc = None

    def __del__(self):
        self.close()


def check_source(source, fname):
    """The quick checks, done here before starting a process (so mistakes come back straight away)."""
    if len(source) > rules.MAX_SOURCE:
        raise BrainError("the file is too long (max 20,000 characters)")
    try:
        tree = ast.parse(source, filename=fname)
    except SyntaxError as e:
        raise BrainError(f"line {e.lineno}: {e.msg}") from None
    try:
        rules.check_code(tree)
    except rules.RuleError as e:
        raise BrainError(str(e)) from None
    if not any(isinstance(n, ast.FunctionDef) and n.name == "brain" for n in tree.body):
        raise BrainError(f"the file needs a function called {rules.REQUIRED}")


def load_brain(source, learner):
    """Returns (the learner's brain, its file name), or raises BrainError with a message they can act on."""
    fname = f"{learner}_bot.py"
    check_source(source, fname)
    return SandboxedBrain(source, fname), fname


class Autopilot:
    """A learner's brain as the teaching layer keeps it (the engine's shape): its error, when it started, and the
    Bot's turns through it (craft_bot.Bot asks and reads)."""

    def __init__(self, fn, fname):
        self.fn, self.fname = fn, fname
        self._error, self.started, self.turns = None, None, 0

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, value):
        if value is None and self._error is not None:
            self.fn.reset()
        self._error = value

    @property
    def memory(self):
        return {}

    @memory.setter
    def memory(self, value):
        self.fn.reset()

    def ask(self, bot, world, now):
        if self._error:
            return
        if self.started is None:
            self.started = now
        try:
            self.fn.ask(bot, world)
        except BrainError as e:
            self._error = str(e)

    def answer(self):
        if self._error:
            return None
        try:
            r = self.fn.answer()
        except BrainError as e:
            self._error = str(e)
            return None
        if r is not None:
            self.turns += 1
        return r

    def waiting(self):
        return self.fn.pending is not None

    def close(self):
        self.fn.close()

    def seconds_running(self, now):
        return 0.0 if self.started is None or self._error else now - self.started
