#!/usr/bin/env python3
"""nimber: Sprague-Grundy calculator for subtraction games and Nim.

Reads a plain-text game file and works out exact Grundy values, P/N verdicts,
winning moves, the period of the Grundy sequence, seeded play-outs and CI
expectation checks. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import sys
from typing import NamedTuple

MAX_HEAP = 10000
MAX_HEAP_ALL = 2000
INT_RE = re.compile(r"^\d+$")
KEYS = {"name", "moves", "expect", "heap"}


class Issue(NamedTuple):
    line: int | None
    level: str
    message: str

    def describe(self, path):
        where = f"{path}:{self.line}" if self.line else path
        return f"{where}: {self.level}: {self.message}"


class Game(NamedTuple):
    name: str
    moves: tuple | None  # None means "all": classic Nim
    heaps: tuple
    expect: str | None  # "win", "lose" or None


def _parse_moves(value):
    """Return (moves, problem). moves is None for 'all'."""
    if value.lower() == "all":
        return None, None
    tokens = value.split()
    for token in tokens:
        if not INT_RE.match(token) or int(token) == 0:
            return None, f"moves must be positive whole numbers or 'all', got '{token}'"
    numbers = sorted(int(token) for token in tokens)
    if len(set(numbers)) != len(numbers):
        return None, "duplicate move in moves list"
    return tuple(numbers), None


def parse_game(text):
    """Parse game text. Returns (game, issues); game is None when any error was found."""
    issues = []
    seen = set()
    name = "unnamed game"
    moves = None
    moves_all = False
    expect = None
    heaps = []  # (line number, size)
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        key = parts[0].lower()
        value = parts[1].strip() if len(parts) > 1 else ""
        if key not in KEYS:
            issues.append(Issue(number, "error", f"unknown key '{parts[0]}'"))
            continue
        if key == "heap":
            if not INT_RE.match(value):
                issues.append(Issue(number, "error", "heap needs a whole number, e.g. 'heap 7'"))
            elif int(value) > MAX_HEAP:
                issues.append(Issue(number, "error", f"heap {value} is above the limit of {MAX_HEAP}"))
            else:
                heaps.append((number, int(value)))
            continue
        if key in seen:
            issues.append(Issue(number, "error", f"duplicate key '{key}'"))
            continue
        seen.add(key)
        if not value:
            issues.append(Issue(number, "error", f"'{key}' needs a value"))
            continue
        if key == "name":
            name = value
        elif key == "moves":
            moves, problem = _parse_moves(value)
            moves_all = problem is None and moves is None
            if problem:
                issues.append(Issue(number, "error", problem))
        elif value.lower() in ("win", "lose"):
            expect = value.lower()
        else:
            issues.append(Issue(number, "error", "expect must be 'win' or 'lose'"))
    if "moves" not in seen:
        issues.append(Issue(None, "error", "missing required key 'moves'"))
    if moves_all:
        for number, size in heaps:
            if size > MAX_HEAP_ALL:
                issues.append(Issue(number, "error", f"heap {size} is above the limit of {MAX_HEAP_ALL} for 'moves all'"))
    if issues:
        return None, issues
    return Game(name, moves, tuple(size for _, size in heaps), expect), issues


def load_game(path):
    with open(path, encoding="utf-8") as handle:
        return parse_game(handle.read())


def lint(game):
    """Warnings that do not stop a game from being analysed."""
    warnings = []
    if not game.heaps:
        warnings.append(Issue(None, "warning", "no heap lines: the position is empty and is a P-position"))
    elif game.moves is not None:
        biggest = max(game.heaps)
        for move in game.moves:
            if move > biggest:
                warnings.append(Issue(None, "warning", f"move {move} can never be played: no heap holds {move} or more"))
    return warnings


def mex(values):
    """Smallest non-negative integer not in values."""
    value = 0
    while value in values:
        value += 1
    return value


def _options(moves, heap):
    """Amounts that may be taken from a heap of this size."""
    if moves is None:
        return range(1, heap + 1)
    return [move for move in moves if move <= heap]


def grundy_table(moves, size):
    """Grundy values g[0..size] for a single heap."""
    limit = MAX_HEAP_ALL if moves is None else MAX_HEAP
    if size > limit:
        raise ValueError(f"heap {size} is above the limit of {limit}")
    table = [0] * (size + 1)
    for heap in range(1, size + 1):
        table[heap] = mex({table[heap - move] for move in _options(moves, heap)})
    return table


def xor_all(values):
    total = 0
    for value in values:
        total ^= value
    return total


def winning_moves(moves, heaps, table):
    """Every (heap index, amount) that leaves a total Grundy value of zero."""
    total = xor_all(table[heap] for heap in heaps)
    found = []
    for index, heap in enumerate(heaps):
        rest = total ^ table[heap]
        for move in _options(moves, heap):
            if rest ^ table[heap - move] == 0:
                found.append((index, move))
    return found


def legal_moves(moves, heaps):
    return [(index, move) for index, heap in enumerate(heaps) for move in _options(moves, heap)]


def analyse(game):
    size = max(game.heaps, default=0)
    table = grundy_table(game.moves, size)
    values = [table[heap] for heap in game.heaps]
    total = xor_all(values)
    found = winning_moves(game.moves, game.heaps, table)
    return {
        "name": game.name,
        "moves": "all" if game.moves is None else list(game.moves),
        "heaps": list(game.heaps),
        "grundy": values,
        "total": total,
        "verdict": "N" if total else "P",
        "winning_moves": [
            {"heap": index + 1, "size": game.heaps[index], "take": move, "leaves": game.heaps[index] - move}
            for index, move in found
        ],
        "nim_sum": xor_all(game.heaps) if game.moves is None else None,
    }


def find_period(moves, window):
    """Return (preperiod, period) of the Grundy sequence, or None.

    A period only counts when the window holds at least two full repeats, so
    the answer is an observation over the window, not a proof.
    """
    table = grundy_table(moves, window)
    n = len(table)
    for period in range(1, n // 3 + 1):
        start = n - period
        while start > 0 and table[start - 1] == table[start - 1 + period]:
            start -= 1
        if n - start >= 2 * period:
            return start, period
    return None


def play(game, seed, me_first=True):
    """One seeded game: you always play a winning move when one exists, the opponent moves at random.

    Returns (log, winner). Each log entry is (who, heap number, amount, before, after).
    """
    rng = random.Random(seed)
    heaps = list(game.heaps)
    table = grundy_table(game.moves, max(heaps, default=0))
    turn = "me" if me_first else "them"
    log = []
    while True:
        options = legal_moves(game.moves, heaps)
        if not options:
            winner = "them" if turn == "me" else "me"
            return log, winner
        if turn == "me":
            wins = winning_moves(game.moves, heaps, table)
            index, move = (wins or options)[0]
        else:
            index, move = rng.choice(options)
        before = heaps[index]
        heaps[index] -= move
        log.append((turn, index + 1, move, before, heaps[index]))
        turn = "them" if turn == "me" else "me"


def format_report(res):
    heaps = res["heaps"]
    lines = [f"Game: {res['name']}"]
    if res["moves"] == "all":
        lines.append("Moves: take any number from one heap (classic Nim)")
    else:
        lines.append("Moves: take " + ", ".join(str(move) for move in res["moves"]) + " from one heap")
    lines.append("Position: " + (f"heaps {' '.join(str(heap) for heap in heaps)}" if heaps else "no heaps"))
    lines += ["", f"{'Heap':>6}  {'Size':>5}  {'Grundy':>6}"]
    for number, (heap, value) in enumerate(zip(heaps, res["grundy"]), start=1):
        lines.append(f"{number:>6}  {heap:>5}  {value:>6}")
    lines += ["", f"Total (XOR of Grundy values): {res['total']}"]
    if res["verdict"] == "N":
        lines.append("Verdict: N-position, the player to move wins with best play")
    else:
        lines.append("Verdict: P-position, the player to move loses with best play")
    if res["nim_sum"] is not None:
        agree = "agrees" if res["nim_sum"] == res["total"] else "disagrees"
        lines.append(f"Nim-sum check: {res['nim_sum']} ({agree} with the Grundy total)")
    if res["winning_moves"]:
        lines.append(f"Winning moves ({len(res['winning_moves'])}):")
        for move in res["winning_moves"]:
            lines.append(f"  take {move['take']} from heap {move['heap']} ({move['size']} -> {move['leaves']})")
    elif not heaps:
        lines.append("Winning moves: none (no heaps, so no moves are possible)")
    else:
        lines.append("Winning moves: none (every move hands the opponent a winning position)")
    return "\n".join(lines)


def format_table(table, fmt):
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["heap", "grundy"])
        for heap, value in enumerate(table):
            writer.writerow([heap, value])
        return buffer.getvalue().rstrip("\n")
    lines = [f"{'Heap':>6}  {'Grundy':>6}"]
    lines += [f"{heap:>6}  {value:>6}" for heap, value in enumerate(table)]
    return "\n".join(lines)


def cmd_report(game, args):
    res = analyse(game)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(format_report(res))
    return 0


def cmd_table(game, args):
    size = args.to if args.to is not None else max(max(game.heaps, default=0), 20)
    print(format_table(grundy_table(game.moves, size), args.format))
    return 0


def cmd_period(game, args):
    if args.window < 6:
        print("nimber: --window must be at least 6", file=sys.stderr)
        return 1
    found = find_period(game.moves, args.window)
    if found is None:
        print(f"No period found in the first {args.window} heap sizes")
    else:
        preperiod, period = found
        print(f"Grundy sequence: period {period}, starts repeating from heap {preperiod} (observed over {args.window} heaps)")
    return 0


def cmd_play(game, args):
    res = analyse(game)
    who = "you move first" if args.first == "me" else "the opponent moves first"
    print(f"Start: {'N' if res['verdict'] == 'N' else 'P'}-position, {who}")
    log, winner = play(game, args.seed, me_first=args.first == "me")
    labels = {"me": "you", "them": "opponent"}
    for turn, heap, move, before, after in log:
        print(f"{labels[turn]} takes {move} from heap {heap} ({before} -> {after})")
    print(f"Winner: {labels[winner]}")
    return 0


def cmd_check(game, args):
    res = analyse(game)
    verdict = "win" if res["verdict"] == "N" else "lose"
    if game.expect is None:
        print(f"OK: position is an {res['verdict']}-position (no expect line)")
        return 0
    if verdict != game.expect:
        print(f"FAIL: expected {game.expect}, but the position is an {res['verdict']}-position")
        return 2
    print(f"PASS: position is an {res['verdict']}-position, as expected ({game.expect})")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="nimber", description="Sprague-Grundy calculator for subtraction games and Nim.")
    commands = parser.add_subparsers(dest="command", required=True)

    report = commands.add_parser("report", help="verdict, Grundy values and winning moves")
    report.add_argument("file")
    report.add_argument("--json", action="store_true", help="print JSON instead of text")

    table = commands.add_parser("table", help="Grundy values for heap sizes 0..N")
    table.add_argument("file")
    table.add_argument("--to", type=int, help="largest heap size to list")
    table.add_argument("--format", choices=["text", "csv"], default="text")

    period = commands.add_parser("period", help="find the period of the Grundy sequence")
    period.add_argument("file")
    period.add_argument("--window", type=int, default=2000, help="heap sizes to examine")

    play_cmd = commands.add_parser("play", help="seeded game against a random opponent")
    play_cmd.add_argument("file")
    play_cmd.add_argument("--seed", type=int, default=0)
    play_cmd.add_argument("--first", choices=["me", "them"], default="me")

    check = commands.add_parser("check", help="lint the file and gate on its expect line")
    check.add_argument("file")
    return parser


COMMANDS = {"report": cmd_report, "table": cmd_table, "period": cmd_period, "play": cmd_play, "check": cmd_check}


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        game, issues = load_game(args.file)
    except OSError as exc:
        print(f"nimber: {exc.strerror}: {args.file}", file=sys.stderr)
        return 1
    for issue in issues:
        print(issue.describe(args.file), file=sys.stderr)
    if game is None:
        return 1
    for warning in lint(game):
        print(warning.describe(args.file), file=sys.stderr)
    try:
        return COMMANDS[args.command](game, args)
    except ValueError as exc:
        print(f"nimber: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
