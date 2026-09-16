"""Regression tests for score units, exported weights and position/label alignment."""
import json
import tempfile
import unittest
from pathlib import Path

import chess
import numpy as np
import torch

from generate_dataset import metadata_scores, read_games
from match_runner import statistics
from train_nnue import SparseNet, encode, quantize


class TrainingRegressions(unittest.TestCase):
    def test_material_and_export_units(self):
        model = SparseNet(32)
        network, clipped = quantize(model, "regression")
        self.assertFalse(any(clipped.values()))
        for removed, expected in ((None, 0), (chess.D8, 900), (chess.D1, -900),
                                  (chess.A7, 100), (chess.A2, -100)):
            board = chess.Board()
            if removed is not None:
                board.remove_piece_at(removed)
            x = torch.from_numpy(np.stack([encode(board.fen())]))
            self.assertAlmostEqual(float(model(x).detach()[0]), expected, delta=0.01)
            self.assertAlmostEqual(network.evaluate(board), expected, delta=2)
            board.turn = chess.BLACK
            self.assertAlmostEqual(network.evaluate(board), -expected, delta=2)
        # Output scale must also be folded into nonzero bias and trained weights.
        with torch.no_grad():
            model.output.weight.mul_(1.1)
            model.output.bias.fill_(0.12)
        network, clipped = quantize(model, "regression-trained")
        self.assertFalse(any(clipped.values()))
        board = chess.Board()
        board.remove_piece_at(chess.D8)
        prediction = float(model(torch.from_numpy(np.stack([encode(board.fen())]))).detach()[0])
        self.assertAlmostEqual(network.evaluate(board), prediction, delta=3)

    def test_search_labels_belong_to_root_before_move(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pgn = root / "games.pgn"
            pgn.write_text('[Result "1/2-1/2"]\n\n1. e4 e5 2. Nf3 Nc6 1/2-1/2\n', encoding="utf-8")
            metadata = root / "metadata.json"
            metadata.write_text(json.dumps({"artifacts": {"pgn": "games.pgn"}, "games": [
                {"round": 1, "moves": [{"ply": 1, "side": "white", "score_cp": 20},
                                       {"ply": 2, "side": "black", "score_cp": -70},
                                       {"ply": 3, "side": "white", "score_cp": 100}]}]}), encoding="utf-8")
            samples = read_games([pgn], metadata_scores([metadata]), 0, 1, 0)
            board = chess.Board()
            board.push_uci("e2e4")
            self.assertEqual(samples[0].fen, board.fen())
            self.assertEqual(samples[0].search_score_cp, -70)
            self.assertEqual(samples[0].search_score_perspective, "black")
            self.assertEqual(samples[1].search_score_cp, 100)
            self.assertIsNone(samples[-1].search_score_cp)

    def test_unanimous_games_retain_uncertainty(self):
        games = [{"result": "0-1", "engine_a_color": "white"} for _ in range(20)]
        result = statistics(games, None, False)
        self.assertGreater(result["score_confidence95"][1], result["score_confidence95"][0])
        self.assertTrue(result["elo_is_clipped"])


if __name__ == "__main__":
    unittest.main()
