"""Regression tests for analysis evidence and the local model adapter (no model required)."""
import unittest
from unittest.mock import patch

from analyze_pgn import classify
from analysis_session import read_games
from explain_analysis import build_context, score_text
from local_explainer import explain, local_models


class ExplanationTests(unittest.TestCase):
    def test_forced_loss_is_not_a_new_blunder(self):
        label, loss, note = classify({"cp": None, "mate": -3}, {"cp": None, "mate": -3}, (50, 100, 200))
        self.assertEqual(label, "best")
        self.assertIsNone(loss)
        self.assertIn("inevitable", note)
        self.assertEqual(classify({"cp": 0, "mate": None}, {"cp": None, "mate": 0}, (50, 100, 200))[0], "blunder")

    def test_mate_units_and_sign(self):
        self.assertIn("en contra", score_text({"cp": None, "mate": -3}))
        self.assertIn("jaque mate", score_text({"cp": None, "mate": 0}))
        self.assertIn("movimientos", classify({"cp": None, "mate": 2}, {"cp": None, "mate": 4}, (50, 100, 200))[2])

    def test_input_validation_and_history(self):
        with self.assertRaises(ValueError):
            read_games({"kind": "fen", "text": "8/8/8/8/8/8/8/8 w - - 0 1"})
        with self.assertRaises(ValueError):
            read_games({"kind": "pgn", "text": ""})
        with self.assertRaises(ValueError):
            read_games({"kind": "game", "moves": ["e2e5"]})
        games, position = read_games({"kind": "game", "moves": ["e2e4", "e7e5"]})
        self.assertFalse(position)
        self.assertEqual(len(list(games[0].mainline_moves())), 2)

    def test_context_states_perspective_and_pv_limit(self):
        record = dict.fromkeys(["candidates", "classification", "centipawn_loss",
                               "mate_note", "static_before", "static_after"])
        candidate = {"san": "e4", "move": "e2e4", "score": {"cp": 0, "mate": None}}
        record.update(played=candidate, best=candidate, move_san="e4")
        record.update(fen_before="fen", color="black", mode="position")
        context = build_context(record, "¿Por qué?", None)
        self.assertEqual(context["score_perspective"], "player_before_move")
        self.assertEqual(context["mode"], "position")
        self.assertIn("does not prove forced", context["instruction"])

    @patch("local_explainer.request_json")
    def test_only_installed_local_models_and_grounded_prompt(self, request):
        request.side_effect = [{"models": [{"name": "remote:cloud"}, {"name": "remote", "remote_host": "host"},
                                           {"name": "qwen3.5:4b"}]},
                               {"message": {"content": "Explicación local"}}]
        answer, model = explain({"question": "¿Por qué?"})
        self.assertEqual((answer, model), ("Explicación local", "qwen3.5:4b"))
        payload = request.call_args.args[1]
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("No inventes", payload["messages"][0]["content"])

    @patch("local_explainer.request_json", return_value={"models": []})
    def test_missing_model(self, request):
        self.assertEqual(local_models(), [])
        with self.assertRaisesRegex(ValueError, "no tiene modelos"):
            explain({})

    @patch("local_explainer.request_json")
    def test_empty_response(self, request):
        request.side_effect = [{"models": [{"name": "local"}]}, {"message": {"content": ""}}]
        with self.assertRaisesRegex(ValueError, "vacía"):
            explain({})

    @patch("local_explainer.request_json")
    def test_non_reasoning_model_and_malformed_response(self, request):
        request.side_effect = [{"models": [{"name": "local"}]}, {"message": None}]
        with self.assertRaisesRegex(ValueError, "inválido"):
            explain({})
        self.assertNotIn("think", request.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
