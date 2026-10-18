"""Tests for nimber: Grundy values, verdicts, winning moves, periods, play and CI gates."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nimber  # noqa: E402
from nimber import Game  # noqa: E402


def make(text):
    game, issues = nimber.parse_game(text)
    if game is None:
        raise AssertionError(f"unexpected parse errors: {[i.message for i in issues]}")
    return game


def run_cli(argv, text=None):
    """Run main() on a temporary game file and capture (exit code, stdout, stderr)."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "game.txt")
        if text is not None:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        out, err = io.StringIO(), io.StringIO()
        full_argv = [argv[0], path] + argv[1:]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = nimber.main(full_argv)
    return code, out.getvalue(), err.getvalue()


class GrundyTests(unittest.TestCase):
    def test_nim_grundy_equals_heap_size(self):
        self.assertEqual(list(range(11)), nimber.grundy_table(None, 10))

    def test_subtraction_one_or_two_has_period_three(self):
        self.assertEqual([0, 1, 2, 0, 1, 2, 0, 1], nimber.grundy_table((1, 2), 7))

    def test_two_three_sequence(self):
        self.assertEqual([0, 0, 1, 1, 2, 0, 0, 1, 1, 2], nimber.grundy_table((2, 3), 9))

    def test_period_detected_for_two_three(self):
        self.assertEqual((0, 5), nimber.find_period((2, 3), 200))

    def test_nim_never_repeats(self):
        self.assertIsNone(nimber.find_period(None, 200))

    def test_period_window_too_small_is_rejected_by_cli(self):
        code, _, err = run_cli(["period", "--window", "3"], "moves 1 2\nheap 3\n")
        self.assertEqual(1, code)
        self.assertIn("at least 6", err)

    def test_oversized_nim_table_is_refused(self):
        with self.assertRaises(ValueError):
            nimber.grundy_table(None, nimber.MAX_HEAP_ALL + 1)


class VerdictTests(unittest.TestCase):
    def test_single_heap_verdicts(self):
        self.assertEqual("P", nimber.analyse(make("moves 1 2\nheap 3\n"))["verdict"])
        self.assertEqual("N", nimber.analyse(make("moves 1 2\nheap 1\n"))["verdict"])

    def test_empty_position_is_p(self):
        res = nimber.analyse(make("moves 1 2\n"))
        self.assertEqual("P", res["verdict"])
        self.assertEqual(0, res["total"])

    def test_nim_sum_matches_grundy_total(self):
        res = nimber.analyse(make("moves all\nheap 3\nheap 4\nheap 5\n"))
        self.assertEqual(2, res["total"])
        self.assertEqual(2, res["nim_sum"])
        self.assertEqual("N", res["verdict"])

    def test_only_winning_move_in_nim_3_4_5(self):
        res = nimber.analyse(make("moves all\nheap 3\nheap 4\nheap 5\n"))
        self.assertEqual(
            [{"heap": 1, "size": 3, "take": 2, "leaves": 1}],
            res["winning_moves"],
        )

    def test_every_winning_move_reaches_a_p_position(self):
        game = make("name Stone Drop\nmoves 1 2 4\nheap 7\nheap 10\nheap 11\n")
        res = nimber.analyse(game)
        self.assertTrue(res["winning_moves"])
        for move in res["winning_moves"]:
            heaps = list(game.heaps)
            heaps[move["heap"] - 1] = move["leaves"]
            after = nimber.analyse(Game(game.name, game.moves, tuple(heaps), None))
            self.assertEqual("P", after["verdict"], move)

    def test_p_position_has_no_winning_moves(self):
        res = nimber.analyse(make("moves 1 2\nheap 3\nheap 6\n"))
        self.assertEqual("P", res["verdict"])
        self.assertEqual([], res["winning_moves"])

    def test_unplayable_move_is_linted(self):
        warnings = nimber.lint(Game("x", (1, 9), (3,), None))
        self.assertTrue(any("move 9 can never be played" in w.message for w in warnings))


class ParseTests(unittest.TestCase):
    def test_errors_carry_line_numbers(self):
        game, issues = nimber.parse_game("name x\nmoves 1 0 2\nheap seven\nbogus 3\n")
        self.assertIsNone(game)
        self.assertEqual([2, 3, 4], [issue.line for issue in issues])

    def test_missing_moves_is_reported(self):
        game, issues = nimber.parse_game("heap 3\n")
        self.assertIsNone(game)
        self.assertIn("missing required key 'moves'", issues[0].message)
        self.assertIsNone(issues[0].line)

    def test_moves_all_heap_limit(self):
        game, issues = nimber.parse_game("moves all\nheap 2001\n")
        self.assertIsNone(game)
        self.assertEqual(2, issues[0].line)
        self.assertIn("limit", issues[0].message)

    def test_duplicate_move_is_an_error(self):
        game, issues = nimber.parse_game("moves 2 3 2\nheap 4\n")
        self.assertIsNone(game)
        self.assertIn("duplicate move", issues[0].message)


class CommandTests(unittest.TestCase):
    def test_check_passes_when_expectation_holds(self):
        code, out, _ = run_cli(["check"], "moves 2 3\nheap 5\nheap 6\nexpect lose\n")
        self.assertEqual(0, code)
        self.assertIn("PASS", out)

    def test_check_fails_with_exit_two_when_expectation_breaks(self):
        code, out, _ = run_cli(["check"], "moves 2 3\nheap 9\nheap 13\nexpect lose\n")
        self.assertEqual(2, code)
        self.assertIn("FAIL", out)

    def test_check_returns_one_on_parse_error(self):
        code, _, err = run_cli(["check"], "moves 2 3\nheap x\n")
        self.assertEqual(1, code)
        self.assertIn(":2: error:", err)

    def test_table_csv_output(self):
        code, out, _ = run_cli(["table", "--to", "3", "--format", "csv"], "moves 1 2\nheap 3\n")
        self.assertEqual(0, code)
        self.assertEqual("heap,grundy\n0,0\n1,1\n2,2\n3,0\n", out)

    def test_json_report_fields(self):
        code, out, _ = run_cli(["report", "--json"], "moves 1 2\nheap 3\n")
        self.assertEqual(0, code)
        data = json.loads(out)
        self.assertEqual("P", data["verdict"])
        self.assertEqual([0], data["grundy"])

    def test_play_first_from_n_position_always_wins(self):
        text = "moves 1 2 4\nheap 7\nheap 10\nheap 11\n"
        game = make(text)
        for seed in range(20):
            _, winner = nimber.play(game, seed, me_first=True)
            self.assertEqual("me", winner, f"seed {seed}")

    def test_play_is_deterministic_for_a_seed(self):
        game = make("moves 1 2 4\nheap 7\nheap 10\nheap 11\n")
        self.assertEqual(nimber.play(game, 5), nimber.play(game, 5))

    def test_play_cli_prints_a_winner(self):
        code, out, _ = run_cli(["play", "--seed", "1"], "moves 1 2 4\nheap 7\nheap 10\nheap 11\n")
        self.assertEqual(0, code)
        self.assertIn("Winner: you", out)

    def test_report_text_states_verdict(self):
        code, out, _ = run_cli(["report"], "moves all\nheap 3\nheap 4\nheap 5\n")
        self.assertEqual(0, code)
        self.assertIn("Verdict: N-position", out)
        self.assertIn("take 2 from heap 1 (3 -> 1)", out)


if __name__ == "__main__":
    unittest.main()
