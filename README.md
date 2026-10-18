# nimber

**Exact game theory for subtraction games and Nim, from one plain-text file.**

nimber works out who wins a position with Sprague–Grundy theory. Describe a game in a small text file, and it gives you the Grundy value of every heap, the P/N verdict, every winning move, the period of the Grundy sequence, seeded play-outs against a random opponent, and a CI gate on the answer you expect. It is offline and uses only the Python standard library.

## Features

- **Plain-text game files** with `name`, `moves`, `heap` and `expect` lines, and line-numbered errors for anything malformed.
- **Subtraction-set games** where you take any amount in your move set from one heap, or `moves all` for classic Nim.
- **Multi-heap positions** combined as a sum of games, using XOR of Grundy values.
- **Exact Grundy values** for every heap up to the position's largest heap.
- **P/N verdict**: whether the player to move wins with best play.
- **Winning moves**: every legal move that leaves a P-position, with the heap, amount and resulting size.
- **Nim-sum cross-check** for classic Nim, showing that the XOR of heaps agrees with the Grundy total.
- **Grundy table** as aligned text or CSV, for any heap range.
- **Period detection** for the Grundy sequence, reporting the pre-period and period over a window you choose.
- **Seeded play-outs**: you always play a winning move when one exists, the opponent plays at random, and the seed makes every game reproducible.
- **JSON report** for scripts and dashboards.
- **Lint warnings** for things like moves that can never be played.
- **CI gate**: `check` exits 0 when the position matches its `expect` line, 2 when it does not, and 1 on errors.

## Quick start

Save this as `stone-drop.txt`:

```text
# Stone Drop: take 1, 2 or 4 stones from one pile per turn.
# The player who takes the last stone wins.
name Stone Drop
moves 1 2 4
heap 7
heap 10
heap 11
expect win
```

Then run:

```bash
python3 nimber.py report stone-drop.txt
```

Output:

```text
Game: Stone Drop
Moves: take 1, 2, 4 from one heap
Position: heaps 7 10 11

  Heap   Size  Grundy
     1      7       1
     2     10       1
     3     11       2

Total (XOR of Grundy values): 2
Verdict: N-position, the player to move wins with best play
Winning moves (1):
  take 2 from heap 3 (11 -> 9)
```

The total is 2, so the player to move wins. Taking 2 from the 11-stone heap leaves Grundy values 1, 1, 0, which XOR to zero.

## How to run

Requires Python 3.8 or newer. There is nothing to install.

```bash
python3 nimber.py report FILE [--json]
python3 nimber.py table FILE [--to N] [--format text|csv]
python3 nimber.py period FILE [--window 2000]
python3 nimber.py play FILE [--seed N] [--first me|them]
python3 nimber.py check FILE
```

`check` is meant for CI. It prints `PASS` or `FAIL` against the `expect` line, and returns:

| exit code | meaning |
|---|---|
| 0 | file is valid and the expectation holds (or there is no `expect` line) |
| 1 | file has errors, or the file could not be read |
| 2 | the position is not what `expect` says |

Game file keys:

| key | meaning |
|---|---|
| `name TEXT` | optional display name |
| `moves N N ...` | amounts you may take from one heap, or `moves all` |
| `heap N` | one heap; repeat the line for each heap |
| `expect win\|lose` | optional verdict for `check` to enforce |

Limits: heaps up to 10000 with a finite move set, and up to 2000 with `moves all`, because Nim's Grundy table is quadratic to build.

## How to test

```bash
python3 -m pytest -q tests/
```

Or, without pytest:

```bash
python3 -m unittest discover -s tests
```

The tests cover Grundy tables against hand-worked sequences, verdicts and winning moves, the property that every winning move reaches a P-position, period detection, parse errors with line numbers, the CI exit codes, CSV and JSON output, and seeded play.

## Layout

```text
nimber.py            the whole tool (one file, standard library only)
examples/            sample game files
tests/test_nimber.py unit and CLI tests
```

## Background

For a single heap, the Grundy value is the mex (smallest non-negative integer not present) of the Grundy values reachable in one move. A position is a P-position, meaning the player to move loses, exactly when the XOR of its heaps' Grundy values is zero. For classic Nim, the Grundy value of a heap is its size, so the rule reduces to the familiar nim-sum.
